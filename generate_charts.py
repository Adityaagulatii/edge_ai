"""
generate_charts.py
Generates PNG images for the GitHub README.
Run: python generate_charts.py
Output: images/pipeline.png, images/llm_calls.png,
        images/learning_curve.png, images/thermal.png
"""

import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

os.makedirs("images", exist_ok=True)

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.alpha": 0.3,
    "grid.linestyle": "--",
})

BG  = "#0f172a"
FG  = "#e2e8f0"
DIM = "#64748b"


# ── 1. Pipeline Architecture ──────────────────────────────────────────────────

def draw_pipeline():
    fig, ax = plt.subplots(figsize=(13, 2.8))
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)
    ax.set_xlim(0, 13)
    ax.set_ylim(0, 2.8)
    ax.axis("off")

    stages = [
        ("Sensors\n& Inputs",    "#475569", 1.1),
        ("Signal\nLookout",      "#22c55e", 3.0),
        ("Knowledge\nStore",     "#8b5cf6", 5.0),
        ("Prompt\nAssembly",     "#475569", 7.0),
        ("LLM\n(local)",         "#f59e0b", 9.0),
        ("AI\nOrchestrator",     "#06b6d4", 11.0),
    ]

    W, H = 1.55, 1.4
    for label, color, x in stages:
        rect = mpatches.FancyBboxPatch(
            (x - W / 2, 0.7), W, H,
            boxstyle="round,pad=0.08",
            facecolor=color, edgecolor="none", alpha=0.90, zorder=2,
        )
        ax.add_patch(rect)
        ax.text(x, 1.4, label, ha="center", va="center",
                color="white", fontsize=8.5, fontweight="bold", zorder=3)

    # Thin connector lines between boxes (no arrowheads)
    for i in range(len(stages) - 1):
        x1 = stages[i][2] + W / 2
        x2 = stages[i + 1][2] - W / 2
        ax.plot([x1, x2], [1.4, 1.4], color=DIM, lw=1.2, zorder=1)

    # Feedback arc: AI Orchestrator → Knowledge Store
    ax.annotate(
        "", xy=(5.0, 0.70), xytext=(11.0, 0.70),
        arrowprops=dict(
            arrowstyle="->", color="#8b5cf6", lw=1.1,
            connectionstyle="arc3,rad=0.0",
        ),
    )
    ax.text(8.0, 0.42, "outcome feedback", ha="center", va="center",
            color="#8b5cf6", fontsize=7, style="italic")

    ax.set_title("IAIF — Pipeline Component Flow", color=FG, fontsize=10, pad=8)
    fig.tight_layout(pad=0.4)
    fig.savefig("images/pipeline.png", dpi=150, bbox_inches="tight", facecolor=BG)
    plt.close()
    print("  images/pipeline.png")


# ── 2. LLM Calls — V1 vs V2 ──────────────────────────────────────────────────

def draw_llm_calls():
    fig, ax = plt.subplots(figsize=(5, 3.5))
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)

    labels = ["V1\n(no gate)", "V2\n(Signal Lookout)"]
    values = [96, 21]
    colors = ["#ef4444", "#22c55e"]

    bars = ax.bar(labels, values, color=colors, width=0.45, edgecolor="none")
    for bar, val in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1.5,
                str(val), ha="center", va="bottom", color=FG, fontsize=10, fontweight="bold")

    ax.set_ylabel("LLM calls / 24 h", color=DIM, fontsize=9)
    ax.set_title("LLM Invocations per Day", color=FG, fontsize=10, pad=8)
    ax.tick_params(colors=FG)
    ax.yaxis.label.set_color(DIM)
    for spine in ax.spines.values():
        spine.set_edgecolor(DIM)
    ax.set_ylim(0, 110)

    fig.tight_layout()
    fig.savefig("images/llm_calls.png", dpi=150, bbox_inches="tight", facecolor=BG)
    plt.close()
    print("  images/llm_calls.png")


# ── 3. Learning Curve ─────────────────────────────────────────────────────────

def draw_learning_curve():
    fig, ax = plt.subplots(figsize=(5.5, 3.5))
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)

    x      = [0, 1, 2, 3]
    labels = ["Week 1", "Week 2", "Month 1", "Month 3+"]
    y      = [58, 74, 87, 93]

    ax.plot(x, y, color="#8b5cf6", lw=2.2, marker="o",
            markersize=7, markerfacecolor="#8b5cf6", markeredgecolor=BG)
    ax.fill_between(x, y, alpha=0.12, color="#8b5cf6")

    for xi, yi in zip(x, y):
        ax.text(xi, yi + 1.5, f"{yi}%", ha="center", va="bottom",
                color=FG, fontsize=9, fontweight="bold")

    ax.set_xticks(x)
    ax.set_xticklabels(labels, color=FG, fontsize=9)
    ax.set_ylabel("Correction Success Rate (%)", color=DIM, fontsize=9)
    ax.set_ylim(50, 100)
    ax.set_title("Knowledge Store — Accuracy Over Time", color=FG, fontsize=10, pad=8)
    ax.tick_params(colors=FG)
    for spine in ax.spines.values():
        spine.set_edgecolor(DIM)

    fig.tight_layout()
    fig.savefig("images/learning_curve.png", dpi=150, bbox_inches="tight", facecolor=BG)
    plt.close()
    print("  images/learning_curve.png")


# ── 4. Thermal Comfort ────────────────────────────────────────────────────────

def draw_thermal():
    fig, axes = plt.subplots(1, 2, figsize=(8, 3.5))
    fig.patch.set_facecolor(BG)

    datasets = [
        ("Avg Deviation from Setpoint (°F)", ["Without IAIF", "With IAIF"], [4.2, 1.1], ["#ef4444", "#22c55e"]),
        ("Time in ±2 °F Comfort Band (%)",   ["Without IAIF", "With IAIF"], [51,  89],  ["#ef4444", "#22c55e"]),
    ]

    for ax, (title, labels, values, colors) in zip(axes, datasets):
        ax.set_facecolor(BG)
        bars = ax.bar(labels, values, color=colors, width=0.4, edgecolor="none")
        for bar, val in zip(bars, values):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.5,
                    str(val), ha="center", va="bottom",
                    color=FG, fontsize=10, fontweight="bold")
        ax.set_title(title, color=FG, fontsize=9, pad=6)
        ax.tick_params(colors=FG)
        for spine in ax.spines.values():
            spine.set_edgecolor(DIM)
        ax.set_ylim(0, max(values) * 1.25)

    fig.tight_layout(pad=1.2)
    fig.savefig("images/thermal.png", dpi=150, bbox_inches="tight", facecolor=BG)
    plt.close()
    print("  images/thermal.png")


if __name__ == "__main__":
    print("Generating charts...")
    draw_pipeline()
    draw_llm_calls()
    draw_learning_curve()
    draw_thermal()
    print("Done — 4 images saved to images/")
