"""List every judge flag and leak-term hit that audit/labels.yaml doesn't label yet, with the reply and the private
notes beside it, so each one can be reviewed and labelled `keep` or `overrule: <reason>`."""

import json

from . import checks, experiment


def main() -> None:
    rows = [json.loads(line) for line in (experiment.RESULTS / "replies.jsonl").read_text().splitlines()]
    _, reviews = checks.load()
    by_id = {r["id"]: r for r in reviews}
    audit = experiment.load_audit()
    for r in rows:
        todo = [(i["type"], i["text"], i["why"]) for i in r["judge_issues"]] + [("term", t, "leak term") for t in r["term_leaks"]]
        todo = [t for t in todo if experiment.audit_key(r, t[0], t[1]) not in audit]
        if not todo:
            continue
        review = by_id[r["review"]]
        print(f"=== {r['model']} | {r['review']} | {r['arm']}")
        print(f"REVIEW: {review['text']}")
        print(f"PRIVATE: {' / '.join(review['private'])}")
        print(f"REPLY: {r['reply']}")
        for kind, text, why in todo:
            print(f"  FLAG {json.dumps(experiment.audit_key(r, kind, text), ensure_ascii=False)}  # {why}")
        print()
