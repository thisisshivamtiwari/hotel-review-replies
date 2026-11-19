"""results/summary.json -> media/results.png: unsafe replies (leak, invented claim, public compensation or accusation),
and clean replies with 95% intervals, by setup and model."""

import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from . import experiment  # noqa: E402

COLOURS = {"haiku-4.5": "#2a78d6", "sonnet-5.5": "#eb6834"}  # fixed categorical order (blue, orange)
ARMS = {
    "plain": "full notes,\nno rules",
    "oneshot": "full notes\n+ rules",
    "minimised": "minimised\n+ rules",
    "checked": "minimised + rules\n+ checks + repair",
}
INK, MUTED, SURFACE = "#0b0b0b", "#52514e", "#fcfcfb"


def main() -> None:
    s = json.loads((experiment.RESULTS / "summary.json").read_text())
    rows = {(r["model"], r["arm"]): r for r in s["table"]}
    n = s["table"][0]["replies"]
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.4), facecolor=SURFACE)
    for r in s["table"]:
        r["unsafe"] = r["replies"] - r["safe"]
    panels = [
        ("unsafe", f"Unsafe replies (of {n}): leak, invented claim, compensation or accusation"),
        ("clean", f"Clean, ready-to-post replies (of {n}), 95% CI"),
    ]
    for ax, (metric, title) in zip(axes, panels, strict=True):
        ax.set_facecolor(SURFACE)
        width = 0.36
        for k, m in enumerate(COLOURS):
            xs = [i + (k - 0.5) * (width + 0.02) for i in range(len(ARMS))]
            vals = [rows[(m, a)][metric] for a in ARMS]
            err = None
            if metric == "clean":
                cis = [rows[(m, a)]["clean_ci95"] for a in ARMS]
                err = [
                    [v - lo * n for v, (lo, _) in zip(vals, cis, strict=True)],
                    [hi * n - v for v, (_, hi) in zip(vals, cis, strict=True)],
                ]
            bars = ax.bar(xs, vals, width, color=COLOURS[m], label=m, edgecolor=SURFACE, linewidth=2)
            if err:
                ax.errorbar(xs, vals, yerr=err, fmt="none", ecolor=MUTED, elinewidth=1, capsize=3)
            for b, v in zip(bars, vals, strict=True):
                ax.text(
                    b.get_x() + b.get_width() / 2,
                    v + 0.3,
                    f"{v}",
                    ha="left" if err else "center",
                    va="bottom",
                    fontsize=9,
                    color=INK,
                )
        ax.set_xticks(range(len(ARMS)), list(ARMS.values()), color=MUTED, fontsize=9)
        ax.set_ylim(0, n + 2 if metric == "clean" else max(4, max(rows[k][metric] for k in rows) + 2))
        ax.yaxis.get_major_locator().set_params(integer=True)
        ax.set_title(title, fontsize=10, color=INK, loc="left")
        ax.tick_params(colors=MUTED, length=0)
        for side in ("top", "right", "left"):
            ax.spines[side].set_visible(False)
        ax.spines["bottom"].set_color("#d9d8d4")
        ax.grid(axis="y", color="#ecebe8", linewidth=0.8)
        ax.set_axisbelow(True)
    fig.legend(*axes[0].get_legend_handles_labels(), frameon=False, labelcolor=MUTED, loc="upper right", ncol=2, fontsize=9)
    note = (
        "Clean = no reviewed leak, invented fix or fact, public compensation or accusation, and no note to the hotel left in. "
        "32 made-up reviews, 1 reply each."
    )
    fig.text(0.01, 0.01, note, fontsize=8.5, color=MUTED, ha="left")
    fig.tight_layout(rect=(0, 0.04, 1, 0.94))
    fig.savefig(experiment.ROOT / "media" / "results.png", dpi=150)
