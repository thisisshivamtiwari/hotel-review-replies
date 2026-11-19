"""Three ways to draft a public reply to one review. All three get the same rules in the same system prompt; they
differ only in what the model is shown and what happens to the draft:

- `oneshot`: the fact sheet, the review and the guest's full private booking notes (what a tool wired straight into
  the booking system sends), one call;
- `minimised`: the fact sheet, the review and one line from the booking system: whether a stay matching the reviewer
  was found. No private notes ever reach the model;
- `checked`: the `minimised` draft, then deterministic checks (checks.py) and up to 2 repair calls that list the exact
  problems. A reply that still fails after 2 repairs is flagged for a person to review instead of being posted.

The judge (judge.py) scores the final replies; it is never part of a pipeline.
"""

from pathlib import Path

import yaml

from . import checks, llm

PROMPTS = Path(__file__).resolve().parents[2] / "prompts"
ARMS = ["oneshot", "minimised", "checked"]
MAX_REPAIRS = 2


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
    found = "a stay matching this reviewer was found" if review["stay_found"] else "no stay matching this reviewer was found"
    return f"BOOKING SYSTEM\n{found}"


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
    """All three arms for one (model, review). Returns {arm: {reply, log, rounds, last_problems}}."""
    one_log: list = []
    one = _call(alias, "generate", context(hotel, review, full=True), "generate-full", one_log)
    min_log: list = []
    first = _call(alias, "generate", context(hotel, review, full=False), "generate-minimised", min_log)
    out = {
        "oneshot": {"reply": one, "log": one_log, "rounds": 0, "last_problems": []},
        "minimised": {"reply": first, "log": min_log, "rounds": 0, "last_problems": []},
    }
    log, reply, rounds = list(min_log), first, 0
    while True:
        problems = checks.check_reply(reply, hotel, review)
        if not problems or rounds == MAX_REPAIRS:
            break
        listed = "\n".join(f"- [{p['rule']}] {p['detail']}" for p in problems)
        user = f"{context(hotel, review, full=False)}\n\nDRAFT REPLY\n{reply}\n\nPROBLEMS\n{listed}"
        reply = _call(alias, "repair", user, f"repair-{rounds}", log) or reply
        rounds += 1
    out["checked"] = {"reply": reply, "log": log, "rounds": rounds, "last_problems": problems}
    return out
