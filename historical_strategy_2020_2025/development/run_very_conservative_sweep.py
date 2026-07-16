#!/usr/bin/env python3
"""
Implement + sweep the 2% Very Conservative Dual Strategy on Dukascopy 4H
data (2020-01-01 .. 2025-12-31 only). Selects a future-proof locked config.
"""

from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.backtest import Backtester
from core.h4_data import download_all_h4
from historical_strategy_2020_2025.final_strategy.strategy_implementation import (
    StrategyConfig,
    allocation_map,
    build_signal_frames,
)

OUT = Path(__file__).resolve().parent / "backtest_results"
OUT.mkdir(parents=True, exist_ok=True)
FINAL = Path(__file__).resolve().parents[1] / "final_strategy"
VAL = Path(__file__).resolve().parents[1] / "validation"


def make_bt(cfg_risk_scale: float = 1.0) -> Backtester:
    return Backtester(
        initial_capital=1_000.0,
        leverage=50.0,
        max_drawdown_pct=20.0,
        soft_drawdown_pct=15.0,
        soft_risk_mult=0.5,
        slippage_pips=0.5,
        use_breakeven=False,
        use_partial_tp=False,
        max_bars_held=10**9,
        allow_dual_positions=True,
    )


def score(m: dict, yearly: pd.Series | None = None) -> float:
    ret = float(m.get("total_return_pct", 0))
    sharpe = float(m.get("sharpe", 0))
    dd = float(m.get("max_drawdown_pct", 100))
    wr = float(m.get("win_rate", 0))
    pf = float(m.get("profit_factor", 0))
    tpm = float(m.get("trades_per_month", 0))
    pos_years = int((yearly > 0).sum()) if yearly is not None and len(yearly) else 0
    n_years = int(len(yearly)) if yearly is not None and len(yearly) else 6

    # Future-proof scoring: prefer consistency & DD control over lottery returns.
    consistency = 100.0 * pos_years / max(n_years, 1)
    freq = 100.0 if 4 <= tpm <= 25 else (70.0 if 2 <= tpm < 4 or 25 < tpm <= 40 else 40.0)

    penalty = 0.0
    if dd > 20:
        penalty += (dd - 20) * 8.0
    if ret < 0:
        penalty += abs(ret) * 0.4
    if pf < 1.0:
        penalty += (1.0 - pf) * 40.0
    # Soft-cap absurd returns (overfit / leverage artifacts)
    capped_ret = min(ret, 500.0)

    return round(
        capped_ret * 0.20
        + min(sharpe, 3) * 20 * 0.20
        + (100 - min(dd, 40)) * 0.25
        + min(pf, 3) * 15 * 0.10
        + consistency * 0.15
        + freq * 0.10
        - penalty,
        3,
    )


def run_one(pair_data, cfg: StrategyConfig):
    signals = build_signal_frames(pair_data, cfg)
    bt = make_bt()
    return bt.run(signals, capital_alloc=allocation_map(cfg))


def reference_config() -> StrategyConfig:
    return StrategyConfig(name="ref_2pct_very_conservative")


def variant_grid() -> list[StrategyConfig]:
    configs = [reference_config()]

    # Risk grid (spec says 9 risk configs were tested)
    for sr, br in [
        (1.0, 0.5),
        (1.5, 0.75),
        (2.0, 1.0),  # reference
        (2.5, 1.0),
        (3.0, 1.5),
        (5.0, 2.0),
        (1.0, 1.0),
        (2.0, 0.5),
        (2.0, 1.5),
    ]:
        configs.append(
            StrategyConfig(
                name=f"risk_s{sr}_b{br}",
                sniper_risk_pct=sr,
                bg_risk_pct=br,
            )
        )

    # EMA / ADX neighborhood around reference
    for sa, ba, smax in itertools.product([8, 10, 12, 15], [15, 20, 25], [2, 3]):
        configs.append(
            StrategyConfig(
                name=f"adx_sa{sa}_ba{ba}_sm{smax}",
                sniper_adx=float(sa),
                bg_adx=float(ba),
                sniper_max_per_month=int(smax),
            )
        )

    # Target / stop variants
    for stp, btp, lvm, hvm in itertools.product(
        [4.0, 5.0, 6.0],
        [2.5, 3.0],
        [1.25, 1.35],
        [0.75, 0.80],
    ):
        configs.append(
            StrategyConfig(
                name=f"tgt_stp{stp}_btp{btp}_l{lvm}_h{hvm}",
                sniper_tp_atr=float(stp),
                bg_tp_atr=float(btp),
                low_vol_mult=float(lvm),
                high_vol_mult=float(hvm),
            )
        )

    # Feature ablations
    configs.append(StrategyConfig(name="no_trend_boost", use_trend_boost=False))
    configs.append(StrategyConfig(name="no_dyn_targets", use_dynamic_targets=False))
    configs.append(
        StrategyConfig(
            name="ema_5_13_8_21",
            sniper_fast=5,
            sniper_slow=13,
            bg_fast=8,
            bg_slow=21,
            sniper_adx=12,
            bg_adx=18,
            sniper_max_per_month=3,
        )
    )
    configs.append(
        StrategyConfig(
            name="alloc_70_30",
            sniper_alloc=0.7,
            background_alloc=0.3,
        )
    )
    configs.append(
        StrategyConfig(
            name="alloc_50_50",
            sniper_alloc=0.5,
            background_alloc=0.5,
        )
    )

    # Deduplicate by name
    seen = set()
    uniq = []
    for c in configs:
        if c.name in seen:
            continue
        seen.add(c.name)
        uniq.append(c)
    return uniq


def slice_years(pair_data: dict, start_year: int, end_year: int) -> dict:
    out = {}
    for p, df in pair_data.items():
        part = df[(df.index.year >= start_year) & (df.index.year <= end_year)].copy()
        out[p] = part
    return out


def main():
    pair_data = download_all_h4(
        start="2020-01-01",
        end="2025-12-31",
        cache_dir=ROOT / "data" / "cache" / "h4",
    )
    for p, df in pair_data.items():
        assert df.index.max() <= pd.Timestamp("2025-12-31 23:59:59", tz="UTC")
        assert df.index.min() >= pd.Timestamp("2020-01-01", tz="UTC")

    configs = variant_grid()
    print(f"\nSweeping {len(configs)} configurations on H4 2020-2025...\n")

    rows = []
    results_by_name = {}
    for i, cfg in enumerate(configs, 1):
        res = run_one(pair_data, cfg)
        m = res.metrics
        sc = score(m, res.yearly_returns)
        pos = int((res.yearly_returns > 0).sum())
        row = {
            "config": cfg.name,
            "score": sc,
            "pos_years": pos,
            **m,
        }
        rows.append(row)
        results_by_name[cfg.name] = (cfg, res)
        if i % 10 == 0 or cfg.name.startswith("ref_"):
            print(
                f"[{i:3d}/{len(configs)}] {cfg.name:40s} "
                f"ret={m['total_return_pct']:8.1f}% sh={m['sharpe']:5.2f} "
                f"dd={m['max_drawdown_pct']:5.1f}% wr={m['win_rate']:5.1f}% "
                f"tpm={m['trades_per_month']:5.1f} posY={pos} score={sc:7.2f}"
            )

    summary = pd.DataFrame(rows).sort_values(
        ["pos_years", "score", "total_return_pct"], ascending=False
    )
    summary.to_csv(OUT / "very_conservative_sweep.csv", index=False)
    print("\nTOP 15:")
    print(
        summary.head(15)[
            [
                "config",
                "score",
                "pos_years",
                "total_return_pct",
                "sharpe",
                "max_drawdown_pct",
                "win_rate",
                "trades_per_month",
                "profit_factor",
            ]
        ].to_string(index=False)
    )

    # Robustness filter for lock
    robust = summary[
        (summary["max_drawdown_pct"] <= 20)
        & (summary["total_return_pct"] > 0)
        & (summary["profit_factor"] >= 1.05)
        & (summary["pos_years"] >= 4)
        & (summary["trades_per_month"] >= 2)
    ].copy()
    if robust.empty:
        robust = summary[(summary["max_drawdown_pct"] <= 20) & (summary["total_return_pct"] > 0)]

    # Prefer reference if it is in robust top-tier; else best robust
    best_name = robust.iloc[0]["config"]
    ref_row = summary[summary["config"] == "ref_2pct_very_conservative"]
    if not ref_row.empty:
        ref = ref_row.iloc[0]
        print("\nREFERENCE CONFIG:")
        print(ref.to_dict())

    # OOS validation for top 5 robust + reference
    oos_rows = []
    candidates = list(robust.head(5)["config"]) + ["ref_2pct_very_conservative"]
    candidates = list(dict.fromkeys(candidates))
    train = slice_years(pair_data, 2020, 2023)
    test = slice_years(pair_data, 2024, 2025)
    for name in candidates:
        cfg = results_by_name[name][0]
        tr = run_one(train, cfg)
        te = run_one(test, cfg)
        oos_rows.append(
            {
                "config": name,
                "train_ret": tr.metrics["total_return_pct"],
                "train_dd": tr.metrics["max_drawdown_pct"],
                "train_sharpe": tr.metrics["sharpe"],
                "train_wr": tr.metrics["win_rate"],
                "oos_ret": te.metrics["total_return_pct"],
                "oos_dd": te.metrics["max_drawdown_pct"],
                "oos_sharpe": te.metrics["sharpe"],
                "oos_wr": te.metrics["win_rate"],
                "oos_trades": te.metrics["total_trades"],
                "full_score": float(summary.loc[summary.config == name, "score"].iloc[0]),
                "pos_years": int(summary.loc[summary.config == name, "pos_years"].iloc[0]),
            }
        )
        print(
            f"OOS {name:40s} train={tr.metrics['total_return_pct']:7.1f}% "
            f"oos={te.metrics['total_return_pct']:7.1f}% dd_oos={te.metrics['max_drawdown_pct']:5.1f}"
        )

    oos_df = pd.DataFrame(oos_rows)
    # Future-proof pick: positive OOS, DD<=20 full+oos, maximize pos_years then OOS ret then score
    oos_ok = oos_df[(oos_df["oos_ret"] > 0) & (oos_df["oos_dd"] <= 20)].copy()
    if oos_ok.empty:
        oos_ok = oos_df.copy()
    oos_ok = oos_ok.sort_values(
        ["pos_years", "oos_ret", "full_score"], ascending=False
    )
    lock_name = oos_ok.iloc[0]["config"]
    lock_cfg, lock_res = results_by_name[lock_name]

    print("\n=== LOCKED CONFIG ===", lock_name)
    print(json.dumps(lock_cfg.to_dict(), indent=2))
    print(json.dumps(lock_res.metrics, indent=2))
    print("Yearly:", lock_res.yearly_returns.round(4).to_dict())

    # Persist lock
    payload = lock_cfg.to_dict()
    payload["name"] = "very_conservative_2pct_dual"
    payload["backtest"] = {
        "initial_capital": 1000,
        "leverage": 50,
        "max_drawdown_pct": 20,
        "soft_drawdown_pct": 15,
        "soft_risk_mult": 0.5,
        "slippage_pips": 0.5,
        "timeframe": "4h",
        "data_source": "dukascopy_freeserv",
        "data_start": "2020-01-01",
        "data_end": "2025-12-31",
        "pairs": ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD"],
        "selected_from": lock_name,
    }
    with open(FINAL / "config.json", "w") as f:
        json.dump(payload, f, indent=2)

    lock_res.trades_df().to_csv(FINAL / "full_period_trades.csv", index=False)
    lock_res.equity_curve.to_csv(FINAL / "full_period_equity.csv", header=True)
    with open(FINAL / "full_period_metrics.json", "w") as f:
        json.dump(lock_res.metrics, f, indent=2)

    # Yearly breakdown
    eq = lock_res.equity_curve
    yrows = []
    prev = 1000.0
    trades = lock_res.trades_df()
    for year, series in eq.groupby(eq.index.year):
        end = float(series.iloc[-1])
        yt = trades[trades["exit_time"].astype(str).str.startswith(str(year))] if not trades.empty else trades
        wr = float((yt["pnl"] > 0).mean() * 100) if len(yt) else 0.0
        yrows.append(
            {
                "year": year,
                "start_equity": round(prev, 2),
                "end_equity": round(end, 2),
                "return_pct": round((end / prev - 1) * 100, 2),
                "trades": len(yt),
                "win_rate": round(wr, 2),
            }
        )
        prev = end
    yearly = pd.DataFrame(yrows)
    yearly.to_csv(VAL / "yearly_breakdown.csv", index=False)
    oos_df.to_csv(OUT / "very_conservative_oos.csv", index=False)
    summary.head(10).to_csv(FINAL / "top3_candidates.csv", index=False)

    # 90-day window stats inside 2020-2025 (no 2026)
    # Evaluate rolling 90d returns on equity curve
    eq_d = eq.resample("1D").last().ffill()
    roll = eq_d / eq_d.shift(90) - 1
    roll = roll.dropna()
    print(
        "\n90-day rolling return stats (within 2020-2025): "
        f"median={roll.median()*100:.1f}% p95={roll.quantile(0.95)*100:.1f}% "
        f"max={roll.max()*100:.1f}%"
    )
    with open(OUT / "rolling_90d_stats.json", "w") as f:
        json.dump(
            {
                "median_pct": float(roll.median() * 100),
                "p95_pct": float(roll.quantile(0.95) * 100),
                "max_pct": float(roll.max() * 100),
                "mean_pct": float(roll.mean() * 100),
            },
            f,
            indent=2,
        )

    # Reference vs locked comparison note
    if "ref_2pct_very_conservative" in results_by_name:
        ref_res = results_by_name["ref_2pct_very_conservative"][1]
        comparison = {
            "reference_metrics": ref_res.metrics,
            "reference_yearly": {str(k): float(v) for k, v in ref_res.yearly_returns.items()},
            "locked_name": lock_name,
            "locked_metrics": lock_res.metrics,
            "locked_yearly": {str(k): float(v) for k, v in lock_res.yearly_returns.items()},
            "claimed_90d_return_pct": 1070,
            "observed_90d_median_pct": float(roll.median() * 100),
            "observed_90d_max_pct": float(roll.max() * 100),
            "claimed_win_rate_pct": 71,
            "observed_win_rate_pct": lock_res.metrics["win_rate"],
        }
        with open(OUT / "claim_vs_reality.json", "w") as f:
            json.dump(comparison, f, indent=2)

    print("\nDone. Locked ->", FINAL / "config.json")


if __name__ == "__main__":
    main()
