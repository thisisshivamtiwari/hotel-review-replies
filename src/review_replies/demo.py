"""A terminal walk-through for the demo video: one review with its private notes, the one-shot reply that saw them,
the minimised reply, what the checks caught and the repaired reply, then the results table. Reads results/ only; no
model calls."""

import json
import textwrap
import time

from . import checks, experiment

REVIEW, MODEL = "hollowmere-1", "sonnet-5.5"


def _say(line: str = "", pause: float = 0.0) -> None:
    print(line, flush=True)
    if pause:
        time.sleep(pause)


def _reply(text: str, pause: float) -> None:
    for para in text.split("\n"):
        for line in textwrap.wrap(para, 96) or [""]:
            _say(f"    {line}", pause / 6)


def main(pause: float = 0.5, review_id: str = REVIEW, model: str = MODEL) -> None:
    rows = [json.loads(line) for line in (experiment.RESULTS / "replies.jsonl").read_text().splitlines()]
    pick = {r["arm"]: r for r in rows if (r["review"], r["model"]) == (review_id, model)}
    hotels, reviews = checks.load()
    review = next(r for r in reviews if r["id"] == review_id)
    audit = experiment.load_audit()
    _say(f"REVIEW  {hotels[review['hotel']]['name']} (made-up hotel), {review['rating']} stars, {review['author']}", pause)
    _reply(review["text"], pause)
    _say("PRIVATE NOTES (booking system)", pause)
    for note in review["private"]:
        _say(f"    - {note}", pause / 3)
    for arm, title in (("oneshot", "ONE-SHOT, model sees the notes"), ("minimised", "MINIMISED, model sees only 'stay found'")):
        r = pick[arm]
        _say()
        _say(f"{title} ({model})", pause)
        _reply(r["reply"], pause)
        for i in experiment.kept_issues(r, audit):
            _say(f"  problem  [{i['type']}] {i['text'][:80]}", pause / 2)
        for p in r["rule_issues"]:
            _say(f"  check    [{p['rule']}] {p['detail'][:80]}", pause / 2)
    c = pick["checked"]
    _say()
    _say(f"CHECKED: {c['rounds']} repair round(s), " + ("flagged for a person" if c["flagged_for_review"] else "passes"), pause)
    if c["rounds"]:
        _reply(c["reply"], pause)
    _say()
    _say("RESULTS  (32 made-up reviews, 1 reply each; judge flags reviewed one by one)", pause)
    summary = json.loads((experiment.RESULTS / "summary.json").read_text())
    _say(f"  {'model':<11}{'setup':<11}{'clean':>7}{'leaked':>8}{'invented':>10}{'posted bad':>12}{'$/reply':>9}")
    for r in summary["table"]:
        _say(
            f"  {r['model']:<11}{r['arm']:<11}{r['clean']:>4}/{r['replies']:<2}{r['leaked']:>8}{r['invented']:>10}"
            f"{r['shipped_dirty']:>12}{r['cost_per_reply_usd']:>9.4f}",
            pause / 2,
        )
