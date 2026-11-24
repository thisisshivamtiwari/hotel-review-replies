"""python -m review_replies run|report|ci|demo|flags|faults

run     record any missing model calls (HRR_MODE=record) and write results/
report  rebuild results/summary.json, the README tables and the chart from results/replies.jsonl and the audit
ci      replay every call from cassettes, check results reproduce exactly, and apply the gate (evals/gate.yaml)
demo    terminal walk-through of one review and the results table (for the demo video)
flags   list the judge flags and leak-term hits not yet reviewed in audit/labels.yaml
faults  run the missing-input and failed-dependency fixtures (scripted model) -> results/faults.json, README table
"""

import argparse
import json
import sys

from . import experiment, readme


def main() -> int:
    ap = argparse.ArgumentParser(prog="review_replies")
    ap.add_argument("cmd", choices=["run", "report", "ci", "demo", "flags", "faults"])
    ap.add_argument("--models", nargs="*")
    ap.add_argument("--reviews", nargs="*")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--pause", type=float, default=0.0)
    a = ap.parse_args()
    if a.cmd == "run":
        rows = experiment.run_all(tuple(a.models) if a.models else tuple(experiment.llm.MODELS), a.reviews, a.workers)
        summary = experiment.write(rows)
        readme.update(summary)
        print(json.dumps(summary["table"], indent=1))
        return 0
    if a.cmd == "report":
        rows = [json.loads(line) for line in (experiment.RESULTS / "replies.jsonl").read_text().splitlines()]
        readme.update(experiment.write(rows))
        from . import chart

        chart.main()
        return 0
    if a.cmd == "ci":
        from . import gate

        return gate.main()
    if a.cmd == "faults":
        from . import faults

        res = faults.write()
        readme.update_faults(res)
        print(faults.table(res))
        return 0
    if a.cmd == "flags":
        from . import flags

        flags.main()
        return 0
    from . import demo

    demo.main(a.pause)
    return 0


if __name__ == "__main__":
    sys.exit(main())
