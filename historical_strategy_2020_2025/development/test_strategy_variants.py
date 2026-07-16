#!/usr/bin/env python3
"""Backtest multiple dual-strategy configurations on 2020-2025 data only."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.backtest import Backtester
from core.data_handler import DataHandler
from historical_strategy_2020_2025.final_strategy.strategy_implementation import (
    StrategyConfig,
    allocation_map,
    build_signal_frames,
)

OUT_DIR = Path(__file__).resolve().parent / "backtest_results"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def composite_score(m: dict) -> float:
    ret = float(m.get("total_return_pct", 0.0))
    sharpe = float(m.get("sharpe", 0.0))
    dd = float(m.get("max_drawdown_pct", 100.0))
    wr = float(m.get("win_rate", 0.0))
    tpm = float(m.get("trades_per_month", 0.0))
    pf = float(m.get("profit_factor", 0.0))

    if 3 <= tpm <= 20:
        consistency = 100.0
    elif tpm < 3:
        consistency = max(0.0, tpm / 3.0 * 70.0)
    else:
        consistency = max(0.0, 100.0 - (tpm - 20) * 3.0)

    penalty = 0.0
    if dd > 20:
        penalty += (dd - 20) * 4.0
    if ret < 0:
        penalty += abs(ret) * 0.5
    if pf < 1.0:
        penalty += (1.0 - pf) * 30.0

    # High-R:R systems have low WR by design; weight PF/return/DD more than WR.
    score = (
        min(ret, 400) * 0.30
        + min(sharpe, 3) * 20 * 0.20
        + (100 - min(dd, 40)) * 0.25
        + min(pf, 3) * 20 * 0.15
        + consistency * 0.10
        - penalty
    )
    return round(score, 3)


def make_configs() -> list[StrategyConfig]:
    return [
        StrategyConfig(name="final_locked"),
        StrategyConfig(name="ref_3_9_9_21", sniper_fast=3, sniper_slow=9, bg_fast=9, bg_slow=21, sniper_adx=10, bg_adx=20, sniper_max_per_month=2, low_vol_mult=1.5),
        StrategyConfig(name="ema_5_13_ba15", bg_adx=15.0, sniper_max_per_month=3),
        StrategyConfig(name="ema_5_13_smax2", sniper_max_per_month=2),
        StrategyConfig(name="static_targets", use_dynamic_targets=False),
        StrategyConfig(name="strict_adx", sniper_adx=15.0, bg_adx=22.0),
        StrategyConfig(name="higher_rr_sniper", sniper_tp_atr=6.0, sniper_adx=14.0),
        StrategyConfig(name="conservative_risk", sniper_risk_pct=1.5, bg_risk_pct=0.75),
        StrategyConfig(name="alloc_70_30", sniper_alloc=0.70, background_alloc=0.30),
        StrategyConfig(name="alloc_50_50", sniper_alloc=0.50, background_alloc=0.50),
        StrategyConfig(name="no_rsi", use_rsi_filter=False),
        StrategyConfig(name="freq_boost", sniper_adx=10.0, bg_adx=15.0, sniper_max_per_month=4),
    ]


def run_bt(pair_data, cfg: StrategyConfig):
    signals = build_signal_frames(pair_data, cfg)
    bt = Backtester(
        initial_capital=10_000.0,
        leverage=50.0,
        max_drawdown_pct=20.0,
        use_breakeven=False,
        use_partial_tp=False,
        max_bars_held=10**9,
        allow_dual_positions=True,
    )
    return bt.run(signals, capital_alloc=allocation_map(cfg))


def run_all(start: str = "2020-01-01", end: str = "2025-12-31") -> pd.DataFrame:
    handler = DataHandler(cache_dir=ROOT / "data" / "cache")
    pair_data = handler.fetch_all_pairs(start=start, end=end, interval="1d")
    for pair, df in pair_data.items():
        handler.assert_no_2026(df, pair)
        print(f"{pair}: {len(df)} bars {df.index[0].date()} -> {df.index[-1].date()}")

    rows = []
    for cfg in make_configs():
        result = run_bt(pair_data, cfg)
        m = result.metrics
        score = composite_score(m)
        pos_years = int((result.yearly_returns > 0).sum())
        rows.append({"config": cfg.name, "score": score, "pos_years": pos_years, **m})
        result.trades_df().to_csv(OUT_DIR / f"{cfg.name}_trades.csv", index=False)
        result.equity_curve.to_csv(OUT_DIR / f"{cfg.name}_equity.csv", header=True)
        with open(OUT_DIR / f"{cfg.name}_config.json", "w") as f:
            json.dump(cfg.to_dict(), f, indent=2)
        print(
            f"{cfg.name:22s} ret={m['total_return_pct']:7.1f}% sh={m['sharpe']:5.2f} "
            f"dd={m['max_drawdown_pct']:5.1f}% wr={m['win_rate']:5.1f}% "
            f"tpm={m['trades_per_month']:4.1f} posY={pos_years} score={score:7.2f}"
        )

    summary = pd.DataFrame(rows).sort_values("score", ascending=False)
    summary.to_csv(OUT_DIR / "all_configs_summary.csv", index=False)
    print("\nTop configs:")
    print(summary.head(8).to_string(index=False))
    return summary


if __name__ == "__main__":
    run_all()
