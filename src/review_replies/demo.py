"""A terminal walk-through for the demo video: one review with its private notes, the replies that saw them (without
and with rules), the minimised reply, the checked result, then the results table. Reads results/ only; no model
calls."""

import json
import textwrap
import time

from . import checks, experiment

REVIEW, MODEL = "saltmarsh-6", "haiku-4.5"


def _say(line: str = "", pause: float = 0.0) -> None:
    print(line, flush=True)
    if pause:
        time.sleep(pause)


def _reply(text: str, pause: float) -> None:
    for para in text.split("\n"):
        for line in textwrap.wrap(para, 70) or [""]:
            _say(f"    {line}", pause / 6)


def main(pause: float = 0.5, review_id: str = REVIEW, model: str = MODEL) -> None:
    rows = [json.loads(line) for line in (experiment.RESULTS / "replies.jsonl").read_text().splitlines()]
    pick = {r["arm"]: r for r in rows if (r["review"], r["model"]) == (review_id, model)}
    hotels, reviews = checks.load()
    review = next(r for r in reviews if r["id"] == review_id)
    audit = experiment.load_audit()
    _say(f"REVIEW  {hotels[review['hotel']]['name']} (made-up), {review['rating']}/5, {review['author']}", pause)
    _reply(review["text"], pause)
    _say("PRIVATE NOTES (booking system)", pause)
    for note in review["private"]:
        _say(textwrap.fill(note, 72, initial_indent="    - ", subsequent_indent="      "), pause / 3)
    arms = (
        ("plain", "FULL NOTES, NO RULES"),
        ("oneshot", "FULL NOTES + RULES"),
        ("minimised", "MINIMISED + RULES: model sees only 'stay found'"),
    )
    for arm, title in arms:
        r = pick[arm]
        _say()
        _say(f"{title} ({model})", pause)
        _reply(r["reply"], pause)
        kept = experiment.kept_issues(r, audit)
        terms = [i["text"] for i in kept if i["text"] in r["term_leaks"]]
        for i in kept:
            if i["text"] not in terms:
                _say(f"  problem  [{i['type']}] {i['text'][:52]}", pause / 2)
        if terms:
            _say(f"  problem  [leak] private terms: {', '.join(terms)}", pause / 2)
        if not experiment.kept_issues(r, audit):
            _say("  no problem found", pause / 2)
    c = pick["checked"]
    _say()
    _say(f"CHECKED: {c['rounds']} repair round(s), " + ("flagged for a person" if c["flagged_for_review"] else "passes"), pause)
    if c["rounds"]:
        _reply(c["reply"], pause)
    _say()
    _say("RESULTS  (32 made-up reviews, 1 reply each, flags reviewed)", pause)
    summary = json.loads((experiment.RESULTS / "summary.json").read_text())
    _say(f"  {'model':<11}{'setup':<11}{'unsafe':>7}{'leaked':>8}{'clean':>8}{'posted bad':>12}{'$/reply':>9}")
    for r in summary["table"]:
        _say(
            f"  {r['model']:<11}{r['arm']:<11}{r['replies'] - r['safe']:>7}{r['leaked']:>8}{r['clean']:>5}/{r['replies']:<2}"
            f"{r['shipped_dirty']:>12}{r['cost_per_reply_usd']:>9.4f}",
            pause / 2,
        )
