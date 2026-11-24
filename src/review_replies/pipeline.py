"""Four ways to draft a public reply to one review:

- `plain`: the fact sheet, the review and the guest's full private booking notes (what a tool wired straight into
  the booking system sends), with a system prompt that sets only the format (prompts/plain.txt), one call;
- `oneshot`: the same context, with the safety rules in the system prompt (prompts/generate.txt), one call;

The other two use the same rules prompt and differ only in what the model is shown and what happens to the draft:

- `minimised`: the fact sheet, the review and one line from the booking system: whether a stay matching the reviewer
  was found. No private notes ever reach the model;
- `checked`: the `minimised` draft, then deterministic checks (checks.py) and up to 2 repair calls that list the exact
  problems. A reply that still fails after 2 repairs is flagged for a person to review instead of being posted.

`guarded` is the `checked` arm as a hotel would run it, one review at a time: a fact sheet missing what the checks
need, or a model call that fails, flags the review for a person instead of stopping the batch or posting unchecked.
A booking lookup that failed (`stay_found` missing or None) is told to the model as "not known", never as "not found".

The judge (judge.py) scores the final replies; it is never part of a pipeline.
"""

import subprocess
from pathlib import Path

import yaml

from . import checks, llm

PROMPTS = Path(__file__).resolve().parents[2] / "prompts"
ARMS = ["plain", "oneshot", "minimised", "checked"]
MAX_REPAIRS = 2
# What a failed CLI call raises (non-zero exit, timeout, bad JSON). A missing cassette (KeyError) still fails loudly.
MODEL_ERRORS = (subprocess.SubprocessError, OSError, ValueError)
NEEDED_TEXT = ("name", "town", "kind", "contact", "signoff")
NEEDED_LISTS = ("facts", "changes", "open_issues")  # may be empty, but must be there: a missing list is unknown


def prompt(name: str) -> str:
    return (PROMPTS / f"{name}.txt").read_text().strip()


def fact_sheet(hotel: dict) -> str:
    """The fact sheet as the model sees it. The checker's keywords stay out."""
    shown = {k: hotel[k] for k in ("name", "town", "kind", "facts", "contact")}
    shown["changes"] = [f"{c['what']} ({c['when']})" for c in hotel["changes"]]
    shown["open_issues"] = [o["what"] for o in hotel["open_issues"]]
    shown["signoff"] = hotel["signoff"]
    return yaml.safe_dump(shown, allow_unicode=True, sort_keys=False, width=200)


def review_block(review: dict) -> str:
    return f"REVIEW ({review['rating']} of 5 stars, by {review['author']})\n{review['text']}"


def booking_line(review: dict) -> str:
    found = review.get("stay_found")
    if found is None:
        line = "the lookup failed, so it is not known whether this reviewer stayed; don't say either way"
    else:
        line = "a stay matching this reviewer was found" if found else "no stay matching this reviewer was found"
    return f"BOOKING SYSTEM\n{line}"


def missing_inputs(hotel: dict) -> list[str]:
    gaps = [f"fact sheet has no {k}" for k in NEEDED_TEXT if not str(hotel.get(k) or "").strip()]
    return gaps + [f"fact sheet has no {k} list" for k in NEEDED_LISTS if not isinstance(hotel.get(k), list)]


def private_block(review: dict) -> str:
    notes = "\n".join(f"- {n}" for n in review["private"])
    return f"PRIVATE NOTES FROM THE BOOKING SYSTEM (internal, never to be made public)\n{notes}"


def context(hotel: dict, review: dict, full: bool) -> str:
    parts = [f"FACT SHEET\n{fact_sheet(hotel)}", review_block(review), private_block(review) if full else booking_line(review)]
    return "\n\n".join(parts)


def _call(alias: str, name: str, user: str, purpose: str, log: list) -> str:
    res = llm.call(alias, prompt(name), user, purpose=purpose)
    log.append({"purpose": purpose, "cost_usd": res["cost_usd"], "ms": res["ms"]})
    return res["text"].strip()


def run(alias: str, hotel: dict, review: dict) -> dict[str, dict]:
    """All four arms for one (model, review). Returns {arm: {reply, log, rounds, last_problems}}."""
    plain_log: list = []
    plain = _call(alias, "plain", context(hotel, review, full=True), "generate-plain", plain_log)
    one_log: list = []
    one = _call(alias, "generate", context(hotel, review, full=True), "generate-full", one_log)
    min_log: list = []
    first = _call(alias, "generate", context(hotel, review, full=False), "generate-minimised", min_log)
    out = {
        "plain": {"reply": plain, "log": plain_log, "rounds": 0, "last_problems": []},
        "oneshot": {"reply": one, "log": one_log, "rounds": 0, "last_problems": []},
        "minimised": {"reply": first, "log": min_log, "rounds": 0, "last_problems": []},
    }
    out["checked"] = check_and_repair(alias, hotel, review, first, list(min_log))
    return out


def check_and_repair(alias: str, hotel: dict, review: dict, reply: str, log: list) -> dict:
    rounds = 0
    while True:
        problems = checks.check_reply(reply, hotel, review)
        if not problems or rounds == MAX_REPAIRS:
            break
        listed = "\n".join(f"- [{p['rule']}] {p['detail']}" for p in problems)
        user = f"{context(hotel, review, full=False)}\n\nDRAFT REPLY\n{reply}\n\nPROBLEMS\n{listed}"
        try:
            reply = _call(alias, "repair", user, f"repair-{rounds}", log) or reply
        except MODEL_ERRORS as e:
            problems = [*problems, {"rule": "model-failed", "detail": f"repair call failed ({type(e).__name__})"}]
            break
        rounds += 1
    return {"reply": reply, "log": log, "rounds": rounds, "last_problems": problems}


def guarded(alias: str, hotel: dict, review: dict) -> dict:
    """The `checked` arm for one review that never raises on bad inputs or a failed call: those come back flagged
    (`last_problems` not empty) with the reason, and `reply` None when there is no draft at all."""
    gaps = missing_inputs(hotel)
    if gaps:
        return {"reply": None, "log": [], "rounds": 0, "last_problems": [{"rule": "missing-input", "detail": g} for g in gaps]}
    log: list = []
    try:
        first = _call(alias, "generate", context(hotel, review, full=False), "generate-minimised", log)
    except MODEL_ERRORS as e:
        failed = {"rule": "model-failed", "detail": f"draft call failed ({type(e).__name__})"}
        return {"reply": None, "log": log, "rounds": 0, "last_problems": [failed]}
    return check_and_repair(alias, hotel, review, first, log)
