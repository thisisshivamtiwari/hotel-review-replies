"""Rewrite the generated tables in README.md (between the RESULTS markers) from results/summary.json."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
START, END = "<!-- RESULTS:START -->", "<!-- RESULTS:END -->"
ARM_NAMES = {
    "oneshot": "one-shot, full booking notes",
    "minimised": "minimised context",
    "checked": "minimised + checks + repair",
}
MODEL_NAMES = {"haiku-4.5": "Haiku 4.5", "sonnet-5.5": "Sonnet 5.5"}


def table(summary: dict) -> str:
    head = (
        "| Model | Setup | Clean replies (95% CI) | Leaked a private detail | Invented a fix, fact or promise | "
        "Offered compensation | Flagged for a person | Posted with a problem | No contact route | Median words | "
        "Cost per reply | Seconds per reply |\n|---|---|---|---|---|---|---|---|---|---|---|---|"
    )
    lines = [head]
    for r in summary["table"]:
        n = r["replies"]
        lo, hi = (round(100 * x) for x in r["clean_ci95"])
        flagged = str(r["flagged_for_review"]) if r["arm"] == "checked" else "-"
        lines.append(
            f"| {MODEL_NAMES[r['model']]} | {ARM_NAMES[r['arm']]} | {r['clean']}/{n} ({lo}-{hi}%) | {r['leaked']} | "
            f"{r['invented']} | {r['compensation']} | {flagged} | {r['shipped_dirty']} | "
            f"{r['no_contact']}/{r['needs_contact']} | {r['median_words']} | ${r['cost_per_reply_usd']:.4f} | "
            f"{r['seconds_per_reply']} |"
        )
    j, f = summary["judge"], summary["flags"]
    lines.append("")
    lines.append(
        f"Judge: {j['calls']} calls to Claude {MODEL_NAMES[j['model']]} (${j['cost_usd']:.2f}), {j['unparsed']} unparsed. "
        f"Flags (judge + leak-term hits): {f['total']}, reviewed {f['reviewed']}, overruled {f['overruled']}. "
        f"Pipeline spend for all replies: ${summary['pipeline_cost_usd']:.2f}."
    )
    return "\n".join(lines)


def update(summary: dict) -> None:
    path = ROOT / "README.md"
    text = path.read_text()
    if START not in text:
        return
    head, rest = text.split(START, 1)
    _, tail = rest.split(END, 1)
    path.write_text(f"{head}{START}\n{table(summary)}\n{END}{tail}")
