"""Missing-input and failed-dependency fixtures for the `checked` arm, with a scripted model (no API calls).

The recorded experiment always has a complete fact sheet, a booking lookup that answered, and model calls that
worked. These fixtures cover what goes wrong in a real batch without anyone noticing:

failed-dependency  the booking lookup failed (told to the model as "not known"), the model call times out or the
                   CLI exits with an error, the model returns nothing or a refusal, a repair call fails
missing-input      the fact sheet has no contact address, no sign-off or no open-issues list; the review has no
                   booking-lookup field at all
contradiction      the booking system found the stay, but the draft says it can't
control            a found stay and a not-found stay with a reply that should go out

Every fixture uses one made-up hotel (lantern) and the recorded Sonnet 5.5 `checked` replies to one complaint
(lantern-3, `found`) and to the review with no matching stay (lantern-8, `not_found`): real drafts that pass every
check for the review they were written for. The scripted model sends the same draft again when asked to repair it
(the worst case: a model that ignores the repair request).

Expected: nothing that depends on a failed or missing input is posted; it is flagged for a person with the reason,
and the batch carries on. A reply that says "we can't find your stay" goes out only when the booking system said so.

Every fixture also runs against the `checked` arm as it was on 19 Nov (`legacy`): no input check, no stay-claim rule,
a failed lookup shown to the model as "no stay found", and model errors raised. That is the "before" column in the
README. `crashed` means the exception would stop the batch, so no review after it gets a reply.
"""

import copy
import json
import subprocess
from contextlib import contextmanager
from pathlib import Path

from . import checks, pipeline

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "results" / "faults.json"
HOTEL, FOUND, NOT_FOUND = "lantern", "lantern-3", "lantern-8"
REFUSAL = "I'm sorry, but I can't write a reply to this review without more information about the guest's stay."


def recorded(review_id: str) -> str:
    rows = map(json.loads, (ROOT / "results" / "replies.jsonl").read_text().splitlines())
    return next(r["reply"] for r in rows if (r["model"], r["review"], r["arm"]) == ("sonnet-5.5", review_id, "checked"))


def _raise(exc: Exception):
    def fail():
        raise exc

    return fail


def fixtures() -> list[dict]:
    """id, kind, what, the review (found / not_found), changes to the hotel or review, the model's behaviour at each
    step (a draft, or a function that raises) and the expected outcome."""
    good, says_missing = recorded(FOUND), recorded(NOT_FOUND)
    offer = good.replace("If you would like", "We'd like to offer you a partial refund. If you would like", 1)
    timeout = subprocess.TimeoutExpired(["claude", "-p"], 600)
    cli_error = subprocess.CalledProcessError(1, ["claude", "-p"], stderr="API Error: 529 Overloaded")
    return [
        {"id": "lookup-failed", "kind": "failed-dependency", "what": "booking lookup failed; draft says stay not found",
         "review": FOUND, "review_set": {"stay_found": None}, "draft": says_missing, "expect": "flagged"},
        {"id": "lookup-failed-neutral", "kind": "failed-dependency", "what": "booking lookup failed; draft doesn't say",
         "review": FOUND, "review_set": {"stay_found": None}, "draft": good, "expect": "posted"},
        {"id": "model-timeout", "kind": "failed-dependency", "what": "the draft call times out",
         "review": FOUND, "draft": _raise(timeout), "expect": "flagged"},
        {"id": "model-error", "kind": "failed-dependency", "what": "the CLI exits with an API error",
         "review": FOUND, "draft": _raise(cli_error), "expect": "flagged"},
        {"id": "model-empty", "kind": "failed-dependency", "what": "the model returns no text",
         "review": FOUND, "draft": "", "expect": "flagged"},
        {"id": "model-refusal", "kind": "failed-dependency", "what": "the model refuses",
         "review": FOUND, "draft": REFUSAL, "expect": "flagged"},
        {"id": "repair-fails", "kind": "failed-dependency", "what": "draft offers a refund; the repair call times out",
         "review": FOUND, "draft": offer, "repair": _raise(timeout), "expect": "flagged"},
        {"id": "no-contact", "kind": "missing-input", "what": "fact sheet has no contact address",
         "review": FOUND, "hotel_drop": "contact", "draft": good, "expect": "flagged"},
        {"id": "no-signoff", "kind": "missing-input", "what": "fact sheet has no sign-off",
         "review": FOUND, "hotel_drop": "signoff", "draft": good, "expect": "flagged"},
        {"id": "no-open-issues", "kind": "missing-input", "what": "fact sheet has no open-issues list (unknown, not empty)",
         "review": FOUND, "hotel_drop": "open_issues", "draft": good, "expect": "flagged"},
        {"id": "no-lookup-field", "kind": "missing-input", "what": "no booking-lookup field; draft says not found",
         "review": FOUND, "review_drop": "stay_found", "draft": says_missing, "expect": "flagged"},
        {"id": "no-lookup-field-neutral", "kind": "missing-input", "what": "no booking-lookup field; draft doesn't say",
         "review": FOUND, "review_drop": "stay_found", "draft": good, "expect": "posted"},
        {"id": "found-says-missing", "kind": "contradiction", "what": "stay found; draft says it can't be found",
         "review": FOUND, "draft": says_missing, "expect": "flagged"},
        {"id": "found", "kind": "control", "what": "stay found; the recorded reply", "review": FOUND, "draft": good,
         "expect": "posted"},
        {"id": "not-found", "kind": "control", "what": "no stay found; the recorded reply", "review": NOT_FOUND,
         "draft": says_missing, "expect": "posted"},
    ]  # fmt: skip


def inputs(fx: dict) -> tuple[dict, dict]:
    hotels, reviews = checks.load()
    hotel = copy.deepcopy(hotels[HOTEL])
    review = copy.deepcopy(next(r for r in reviews if r["id"] == fx["review"]))
    hotel.pop(fx.get("hotel_drop", ""), None)
    review.pop(fx.get("review_drop", ""), None)
    review.update(fx.get("review_set", {}))
    return hotel, review


def scripted(fx: dict):
    """A model that writes fx["draft"] and returns it again on every repair, or raises where the fixture says so."""

    def call(alias, system, prompt, sample=0, purpose="", effort="pipeline"):
        step = fx.get("repair", fx["draft"]) if purpose.startswith("repair") else fx["draft"]
        text = step() if callable(step) else step
        return {"text": text, "cost_usd": 0.0, "ms": 0, "cached": True}

    return call


@contextmanager
def model(fx: dict):
    real = pipeline.llm.call
    pipeline.llm.call = scripted(fx)
    try:
        yield
    finally:
        pipeline.llm.call = real


def legacy_booking_line(review: dict) -> str:
    found = "a stay matching this reviewer was found" if review["stay_found"] else "no stay matching this reviewer was found"
    return f"BOOKING SYSTEM\n{found}"


def legacy(hotel: dict, review: dict) -> dict:
    """The `checked` arm as committed on 19 Nov (pipeline.run before the guard), for the "before" column."""
    user = f"FACT SHEET\n{pipeline.fact_sheet(hotel)}\n\n{pipeline.review_block(review)}\n\n{legacy_booking_line(review)}"
    log: list = []
    reply, rounds = pipeline._call("sonnet-5.5", "generate", user, "generate-minimised", log), 0
    while True:
        problems = [p for p in checks.check_reply(reply, hotel, review) if p["rule"] != "stay-claim"]
        if not problems or rounds == pipeline.MAX_REPAIRS:
            break
        reply = pipeline._call("sonnet-5.5", "repair", user, f"repair-{rounds}", log) or reply
        rounds += 1
    return {"reply": reply, "rounds": rounds, "last_problems": problems}


def outcome(fn, hotel: dict, review: dict) -> dict:
    try:
        r = fn(hotel, review)
    except Exception as e:  # noqa: BLE001 - a crash is the result being measured
        return {"outcome": "crashed", "error": type(e).__name__, "problems": []}
    rules = sorted({p["rule"] for p in r["last_problems"]})
    return {"outcome": "flagged" if r["last_problems"] else "posted", "problems": rules, "repairs": r["rounds"]}


def run() -> dict:
    rows = []
    for fx in fixtures():
        hotel, review = inputs(fx)
        with model(fx):
            new = outcome(lambda h, r: pipeline.guarded("sonnet-5.5", h, r), hotel, review)
            old = outcome(legacy, hotel, review)
        shown = pipeline.booking_line(review).split("\n", 1)[1]
        try:
            shown_before = legacy_booking_line(review).split("\n", 1)[1]
        except KeyError:
            shown_before = None
        rows.append({
            "id": fx["id"], "kind": fx["kind"], "what": fx["what"], "expect": fx["expect"], "model_told": shown,
            "model_told_before": shown_before,
            "guarded": {**new, "pass": new["outcome"] == fx["expect"]},
            "legacy": {**old, "pass": old["outcome"] == fx["expect"]},
        })  # fmt: skip
    return {
        "fixtures": rows,
        "cases": len(rows),
        "passed": sum(r["guarded"]["pass"] for r in rows),
        "legacy_passed": sum(r["legacy"]["pass"] for r in rows),
        "legacy_crashed": sum(r["legacy"]["outcome"] == "crashed" for r in rows),
    }


def table(res: dict) -> str:
    lines = [
        "| Fixture | Kind | Expected | Guarded (now) | Before (19 Nov) |",
        "|---|---|---|---|---|",
    ]
    for r in res["fixtures"]:
        cells = []
        for side in ("guarded", "legacy"):
            o = r[side]
            why = o.get("error") or ", ".join(o["problems"])
            cells.append(f"{'✅' if o['pass'] else '❌'} {o['outcome']}" + (f" ({why})" if why else ""))
        lines.append(f"| {r['what']} | {r['kind']} | {r['expect']} | {cells[0]} | {cells[1]} |")
    lines.append("")
    lines.append(
        f"Guarded: {res['passed']}/{res['cases']} as expected. Before: {res['legacy_passed']}/{res['cases']}, "
        f"and {res['legacy_crashed']} of the {res['cases']} would have stopped the batch."
    )
    return "\n".join(lines)


def write() -> dict:
    res = run()
    OUT.write_text(json.dumps(res, indent=1, ensure_ascii=False) + "\n")
    return res
