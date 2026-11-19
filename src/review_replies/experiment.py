"""Run every (model, review), judge each review's six final replies together, apply the flag review, and summarise.

results/replies.jsonl one row per (model, review, arm): the reply, rule problems, judge flags, leak-term hits, cost, time
results/summary.json  the tables in the README (generated from replies.jsonl by `summarise`)
"""

import json
import math
import re
import statistics
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml

from . import checks, judge, llm, pipeline

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "results"
AUDIT = ROOT / "audit" / "labels.yaml"


def term_leaks(reply: str, review: dict) -> list[str]:
    """Scoring terms from the private notes that appear in the reply but not in the review."""
    hits = []
    for term in review["leak_terms"]:
        pat = rf"(?<![\w£]){re.escape(str(term).lower())}(?!\w)"
        if re.search(pat, reply.lower()) and not re.search(pat, review["text"].lower()):
            hits.append(str(term))
    return hits


def _pipelines(alias: str, hotel: dict, review: dict) -> list[dict]:
    rows = []
    for arm, r in pipeline.run(alias, hotel, review).items():
        rows.append(
            {
                "model": alias,
                "review": review["id"],
                "kind": review["kind"],
                "arm": arm,
                "reply": r["reply"],
                "rounds": r["rounds"],
                "calls": len(r["log"]),
                "cost_usd": round(sum(c["cost_usd"] for c in r["log"]), 6),
                "seconds": round(sum(c["ms"] for c in r["log"]) / 1000, 2),
                "flagged_for_review": bool(r["last_problems"]) and arm == "checked",
                "rule_issues": checks.check_reply(r["reply"], hotel, review),
                "term_leaks": term_leaks(r["reply"], review),
            }
        )
    return rows


def _judge(hotel: dict, review: dict, rows: list[dict]) -> None:
    replies = {f"{r['model']}|{r['arm']}": r["reply"] for r in rows}
    j = judge.judge(hotel, review, replies)
    for r in rows:
        r["judge_issues"] = j["issues"][f"{r['model']}|{r['arm']}"]
        r["judge_unparsed"] = j["unparsed"]
    rows[0]["judge_cost_usd"] = j["cost_usd"]


def run_all(models=tuple(llm.MODELS), only=None, workers: int = 4) -> list[dict]:
    hotels, reviews = checks.load()
    reviews = [r for r in reviews if not only or r["id"] in only]
    jobs = [(m, r) for r in reviews for m in models]
    with ThreadPoolExecutor(workers) as ex:
        rows = [row for rs in ex.map(lambda j: _pipelines(j[0], hotels[j[1]["hotel"]], j[1]), jobs) for row in rs]
    by_review: dict[str, list] = {}
    for row in rows:
        by_review.setdefault(row["review"], []).append(row)
    by_id = {r["id"]: r for r in reviews}
    with ThreadPoolExecutor(workers) as ex:
        list(ex.map(lambda rid: _judge(hotels[by_id[rid]["hotel"]], by_id[rid], by_review[rid]), sorted(by_review)))
    order = {r["id"]: i for i, r in enumerate(reviews)}
    return sorted(rows, key=lambda r: (r["model"], order[r["review"]], pipeline.ARMS.index(r["arm"])))


def audit_key(row: dict, kind: str, text: str) -> str:
    return f"{row['model']}|{row['review']}|{row['arm']}|{kind}|{text}"


def load_audit() -> dict[str, str]:
    return (yaml.safe_load(AUDIT.read_text()) or {}).get("labels", {}) if AUDIT.exists() else {}


def kept_issues(row: dict, audit: dict[str, str]) -> list[dict]:
    """Judge flags and leak-term hits that survived the flag review (an unreviewed flag counts as kept)."""
    out = []
    for i in row["judge_issues"]:
        if not str(audit.get(audit_key(row, i["type"], i["text"]), "keep")).startswith("overrule"):
            out.append({"type": i["type"], "text": i["text"]})
    for t in row["term_leaks"]:
        if not str(audit.get(audit_key(row, "term", t), "keep")).startswith("overrule"):
            out.append({"type": "leak", "text": t})
    return out


def wilson(k: int, n: int, z: float = 1.96) -> list[float]:
    if n == 0:
        return [0.0, 0.0]
    p = k / n
    mid = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return [round(max(0.0, mid - half), 3), round(min(1.0, mid + half), 3)]


def opening(reply: str) -> str:
    return " ".join(re.findall(r"[a-z']+", reply.lower())[:3])


def _count(kept: list[list[dict]], kind: str) -> int:
    return sum(any(i["type"] == kind for i in k) for k in kept)


def summarise(rows: list[dict]) -> dict:
    audit = load_audit()
    table = []
    for model in sorted({r["model"] for r in rows}):
        for arm in pipeline.ARMS:
            rs = [r for r in rows if r["model"] == model and r["arm"] == arm]
            kept = [kept_issues(r, audit) for r in rs]
            dirty = [any(i["type"] in judge.SEVERE for i in k) for k in kept]
            clean = sum(not d for d in dirty)
            openings = Counter(opening(r["reply"]) for r in rs)
            needs_contact = [r for r in rs if r["kind"] != "praise"]
            table.append(
                {
                    "model": model,
                    "arm": arm,
                    "replies": len(rs),
                    "leaked": _count(kept, "leak"),
                    "invented": _count(kept, "invented"),
                    "compensation": _count(kept, "compensation"),
                    "accusation": _count(kept, "accusation"),
                    "generic_action": _count(kept, "generic-action"),
                    "clean": clean,
                    "clean_ci95": wilson(clean, len(rs)),
                    "flagged_for_review": sum(r["flagged_for_review"] for r in rs),
                    "shipped_dirty": sum(d and not r["flagged_for_review"] for d, r in zip(dirty, rs, strict=True)),
                    "not_paste_ready": sum(any(p["rule"] == "not-paste-ready" for p in r["rule_issues"]) for r in rs),
                    "no_contact": sum(any(p["rule"] == "contact" for p in r["rule_issues"]) for r in needs_contact),
                    "needs_contact": len(needs_contact),
                    "same_opening": sum(c for c in openings.values() if c > 1),
                    "median_words": int(statistics.median(len(r["reply"].split()) for r in rs)),
                    "cost_per_reply_usd": round(sum(r["cost_usd"] for r in rs) / len(rs), 4),
                    "seconds_per_reply": round(sum(r["seconds"] for r in rs) / len(rs), 1),
                    "repairs": sum(r["rounds"] for r in rs),
                }
            )
    flags = [(r, i["type"], i["text"]) for r in rows for i in r["judge_issues"]] + [
        (r, "term", t) for r in rows for t in r["term_leaks"]
    ]
    reviewed = [audit_key(r, k, t) in audit for r, k, t in flags]
    overruled = [str(audit.get(audit_key(r, k, t), "")).startswith("overrule") for r, k, t in flags]
    return {
        "table": table,
        "judge": {
            "model": judge.JUDGE,
            "calls": sum(1 for r in rows if "judge_cost_usd" in r),
            "unparsed": sum(r["judge_unparsed"] for r in rows),
            "cost_usd": round(sum(r.get("judge_cost_usd", 0.0) for r in rows), 4),
        },
        "flags": {"total": len(flags), "reviewed": sum(reviewed), "overruled": sum(overruled)},
        "pipeline_cost_usd": round(sum(r["cost_usd"] for r in rows if r["arm"] != "minimised"), 4),
    }


def write(rows: list[dict]) -> dict:
    RESULTS.mkdir(exist_ok=True)
    with (RESULTS / "replies.jsonl").open("w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    summary = summarise(rows)
    (RESULTS / "summary.json").write_text(json.dumps(summary, indent=1) + "\n")
    return summary
