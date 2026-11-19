"""results/summary.json -> media/results.png: replies that leaked a private detail, and clean replies with 95%
intervals, by setup and model."""

import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from . import experiment  # noqa: E402

COLOURS = {"haiku-4.5": "#2a78d6", "sonnet-5.5": "#eb6834"}  # fixed categorical order (blue, orange)
ARMS = {"oneshot": "one-shot,\nfull notes", "minimised": "minimised\ncontext", "checked": "minimised +\nchecks + repair"}
INK, MUTED, SURFACE = "#0b0b0b", "#52514e", "#fcfcfb"


def main() -> None:
    s = json.loads((experiment.RESULTS / "summary.json").read_text())
    rows = {(r["model"], r["arm"]): r for r in s["table"]}
    n = s["table"][0]["replies"]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2), facecolor=SURFACE)
    panels = [("leaked", f"Replies that leaked a private booking detail (of {n})"), ("clean", f"Clean replies (of {n}), 95% CI")]
    for ax, (metric, title) in zip(axes, panels, strict=True):
        ax.set_facecolor(SURFACE)
        width = 0.38
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
        ax.set_title(title, fontsize=10, color=INK, loc="left")
        ax.tick_params(colors=MUTED, length=0)
        for side in ("top", "right", "left"):
            ax.spines[side].set_visible(False)
        ax.spines["bottom"].set_color("#d9d8d4")
        ax.grid(axis="y", color="#ecebe8", linewidth=0.8)
        ax.set_axisbelow(True)
    fig.legend(*axes[0].get_legend_handles_labels(), frameon=False, labelcolor=MUTED, loc="upper right", ncol=2)
    note = "Clean = no reviewed leak, invented fix or fact, public compensation or accusation. 32 made-up reviews, 1 reply each."
    fig.suptitle(note, fontsize=9, color=MUTED, x=0.01, ha="left")
    fig.tight_layout()
    fig.savefig(experiment.ROOT / "media" / "results.png", dpi=150)
