"""CI gate. Replays every model call from cassettes/, rebuilds the results, and fails if

1. the replay doesn't reproduce the committed results/summary.json exactly (a prompt, data file or check changed
   without a new recorded run), or
2. a pipeline arm breaks a rule in evals/gate.yaml (for example, it leaks more often than the one-shot baseline,
   or ships more unflagged problem replies than allowed).
"""

import json
from pathlib import Path

import yaml

from . import experiment

GATE = Path(__file__).resolve().parents[2] / "evals" / "gate.yaml"


def evaluate(summary: dict, rules: list[dict]) -> list[str]:
    rows = {(r["model"], r["arm"]): r for r in summary["table"]}
    models = sorted({m for m, _ in rows})
    failures = []
    for rule in rules:
        for model in models if rule.get("model", "*") == "*" else [rule["model"]]:
            r = rows[(model, rule["arm"])]
            value = r[rule["metric"]]
            if "max" in rule and value > rule["max"]:
                failures.append(f"{model} {rule['arm']}: {rule['metric']} = {value} > {rule['max']}")
            if "max_vs" in rule:
                base = rows[(model, rule["max_vs"])][rule["metric"]]
                if value > base:
                    failures.append(f"{model} {rule['arm']}: {rule['metric']} = {value} > {rule['max_vs']} ({base})")
            if "min_vs" in rule:
                base = rows[(model, rule["min_vs"])][rule["metric"]]
                if value < base:
                    failures.append(f"{model} {rule['arm']}: {rule['metric']} = {value} < {rule['min_vs']} ({base})")
    return failures


def main() -> int:
    rows = experiment.run_all(workers=1)
    summary = experiment.summarise(rows)
    committed = json.loads((experiment.RESULTS / "summary.json").read_text())
    if summary != committed:
        print("FAIL: replay does not reproduce results/summary.json")
        for a, b in zip(summary["table"], committed["table"], strict=False):
            if a != b:
                print(" replay   ", a, "\n committed", b)
        return 1
    print(f"replay reproduces results/summary.json ({len(rows)} replies)")
    failures = evaluate(summary, yaml.safe_load(GATE.read_text())["rules"])
    for f in failures:
        print("FAIL:", f)
    if not failures:
        print("gate passed")
    return 1 if failures else 0
