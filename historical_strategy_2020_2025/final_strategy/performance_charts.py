#!/usr/bin/env python3
"""Generate equity / drawdown / monthly performance charts (no 2026 data)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

HERE = Path(__file__).resolve().parent
ART = Path("/opt/cursor/artifacts")
ART.mkdir(parents=True, exist_ok=True)


def main():
    eq_path = HERE / "full_period_equity.csv"
    if not eq_path.exists():
        eq_path = ROOT / "historical_strategy_2020_2025" / "validation" / "full_period_equity.csv"
    eq = pd.read_csv(eq_path, index_col=0, parse_dates=True).iloc[:, 0]
    if eq.index.tz is None:
        eq.index = eq.index.tz_localize("UTC")
    assert eq.index.max().year <= 2025

    metrics = {}
    mpath = HERE / "full_period_metrics.json"
    if mpath.exists():
        metrics = json.loads(mpath.read_text())

    # Equity curve
    fig, ax = plt.subplots(figsize=(11, 5))
    ax.plot(eq.index, eq.values, color="#0B3D4A", lw=1.8)
    ax.fill_between(eq.index, eq.values, eq.iloc[0], color="#0B3D4A", alpha=0.12)
    ax.set_title("Dual Strategy Equity Curve (2020-2025)")
    ax.set_ylabel("Equity ($)")
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    fig.savefig(HERE / "equity_curve.png", dpi=140)
    fig.savefig(ART / "equity_curve_2020_2025.png", dpi=140)
    plt.close(fig)

    # Drawdown
    roll = eq.cummax()
    dd = (eq - roll) / roll * 100
    fig, ax = plt.subplots(figsize=(11, 4))
    ax.fill_between(dd.index, dd.values, 0, color="#8B1E3F", alpha=0.75)
    ax.set_title("Drawdown (%)")
    ax.set_ylabel("Drawdown %")
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    fig.savefig(HERE / "drawdown.png", dpi=140)
    fig.savefig(ART / "drawdown_2020_2025.png", dpi=140)
    plt.close(fig)

    # Monthly returns heatmap-like bar
    monthly = eq.resample("ME").last().pct_change().dropna() * 100
    fig, ax = plt.subplots(figsize=(11, 4))
    colors = ["#1F7A4D" if v >= 0 else "#8B1E3F" for v in monthly.values]
    ax.bar(monthly.index, monthly.values, width=20, color=colors)
    ax.set_title("Monthly Returns (%)")
    ax.grid(True, axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(HERE / "monthly_returns.png", dpi=140)
    fig.savefig(ART / "monthly_returns_2020_2025.png", dpi=140)
    plt.close(fig)

    # Yearly bars — start from first equity point (initial capital)
    years = sorted(eq.index.year.unique())
    yrets = []
    prev = float(eq.iloc[0])
    for y in years:
        end = float(eq[eq.index.year == y].iloc[-1])
        yrets.append((y, (end / prev - 1) * 100))
        prev = end
    fig, ax = plt.subplots(figsize=(8, 4))
    xs = [y for y, _ in yrets]
    ys = [r for _, r in yrets]
    colors = ["#1F7A4D" if v >= 0 else "#8B1E3F" for v in ys]
    ax.bar([str(x) for x in xs], ys, color=colors)
    ax.set_title("Yearly Strategy Returns (%)")
    ax.axhline(0, color="black", lw=0.8)
    ax.grid(True, axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(HERE / "yearly_returns.png", dpi=140)
    fig.savefig(ART / "yearly_returns_2020_2025.png", dpi=140)
    plt.close(fig)

    print("Charts written.")
    if metrics:
        print(metrics)


if __name__ == "__main__":
    main()
