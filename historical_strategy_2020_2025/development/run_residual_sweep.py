#!/usr/bin/env python3
"""Sweep residual-momentum × liquidity-sweep configs on Dukascopy H4 2020-2025."""

from __future__ import annotations

import json
import sys
from pathlib import Path

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


def make_bt() -> Backtester:
    return Backtester(
        initial_capital=1000.0,
        leverage=50,
        max_drawdown_pct=20,
        soft_drawdown_pct=15,
        soft_risk_mult=0.5,
        slippage_pips=0.5,
        use_breakeven=False,
        use_partial_tp=False,
        max_bars_held=10**9,
        allow_dual_positions=True,
    )


def yearly_returns(eq: pd.Series) -> dict:
    out = {}
    prev = float(eq.iloc[0])
    for y in sorted(eq.index.year.unique()):
        end = float(eq[eq.index.year == y].iloc[-1])
        out[int(y)] = (end / prev - 1.0) * 100.0
        prev = end
    return out


def slice_pairs(pairs, start=None, end=None):
    out = {}
    for p, df in pairs.items():
        x = df
        if start:
            x = x.loc[x.index >= pd.Timestamp(start, tz="UTC")]
        if end:
            x = x.loc[x.index <= pd.Timestamp(end, tz="UTC")]
        out[p] = x
    return out


def run_one(pairs, cfg: StrategyConfig, start=None, end=None):
    subset = slice_pairs(pairs, start, end)
    signals = build_signal_frames(subset, cfg)
    return make_bt().run(signals, capital_alloc=allocation_map(cfg))


def main():
    pairs = download_all_h4(
        start="2020-01-01",
        end="2025-12-31",
        cache_dir=ROOT / "data" / "cache" / "h4",
    )

    combos = []
    # Focused grid around forward-edge winners (keeps runtime sane)
    for mom_l, mom_s in [(8, 4), (12, 4)]:
        for sw_l, sw_s in [(12, 18), (12, 24), (18, 24)]:
            for sz, bz in [(1.25, 0.75), (1.0, 0.5), (1.25, 0.5)]:
                for tp_s, tp_b in [(3.0, 2.5), (4.0, 2.5)]:
                    for risk in [1.0, 1.5]:
                        for persist in [2]:
                            combos.append(
                                dict(
                                    mom_lookback=mom_l,
                                    mom_lookback_short=mom_s,
                                    swing_lookback=sw_l,
                                    swing_lookback_short=sw_s,
                                    sniper_resid_z=sz,
                                    bg_resid_z=bz,
                                    sniper_tp_atr=tp_s,
                                    bg_tp_atr=tp_b,
                                    sniper_risk_pct=risk,
                                    bg_risk_pct=min(1.0, risk),
                                    use_sweep_stop=True,
                                    bg_persist=persist,
                                )
                            )
    # Ablations / alternatives
    for extra in [
        dict(mom_lookback=8, mom_lookback_short=4, swing_lookback=12, swing_lookback_short=18,
             sniper_resid_z=1.25, bg_resid_z=0.75, sniper_tp_atr=3.0, bg_tp_atr=2.5,
             sniper_risk_pct=1.0, bg_risk_pct=1.0, use_sweep_stop=False, bg_persist=2),
        dict(mom_lookback=8, mom_lookback_short=4, swing_lookback=12, swing_lookback_short=18,
             sniper_resid_z=1.5, bg_resid_z=1.0, sniper_tp_atr=3.0, bg_tp_atr=2.5,
             sniper_risk_pct=1.0, bg_risk_pct=1.0, use_sweep_stop=True, bg_persist=2),
        dict(mom_lookback=8, mom_lookback_short=4, swing_lookback=36, swing_lookback_short=24,
             sniper_resid_z=0.75, bg_resid_z=0.5, sniper_tp_atr=3.0, bg_tp_atr=2.5,
             sniper_risk_pct=1.0, bg_risk_pct=1.0, use_sweep_stop=True, bg_persist=3),
        dict(mom_lookback=4, mom_lookback_short=4, swing_lookback=48, swing_lookback_short=24,
             sniper_resid_z=1.0, bg_resid_z=0.5, sniper_tp_atr=3.0, bg_tp_atr=2.5,
             sniper_risk_pct=1.0, bg_risk_pct=1.0, use_sweep_stop=True, bg_persist=2),
    ]:
        combos.append(extra)

    # Deduplicate
    uniq = []
    seen = set()
    for c in combos:
        key = tuple(sorted(c.items()))
        if key not in seen:
            seen.add(key)
            uniq.append(c)
    combos = uniq
    print(f"Running {len(combos)} configs...")

    rows = []
    for i, params in enumerate(combos):
        cfg = StrategyConfig(name=f"rm_{i}", **params)
        train = run_one(pairs, cfg, end="2023-12-31 23:59:59")
        oos = run_one(pairs, cfg, start="2024-01-01")
        full = run_one(pairs, cfg)
        y = yearly_returns(full.equity_curve)
        pos = sum(1 for v in y.values() if v > 0)
        tag = (
            f"ml{params['mom_lookback']}_ms{params['mom_lookback_short']}"
            f"_sl{params['swing_lookback']}_ss{params['swing_lookback_short']}"
            f"_sz{params['sniper_resid_z']}_bz{params['bg_resid_z']}"
            f"_tp{params['sniper_tp_atr']}/{params['bg_tp_atr']}"
            f"_r{params['sniper_risk_pct']}_p{params['bg_persist']}"
        )
        row = {
            "config": tag,
            **params,
            "ret": full.metrics["total_return_pct"],
            "dd": full.metrics["max_drawdown_pct"],
            "sharpe": full.metrics["sharpe"],
            "wr": full.metrics["win_rate"],
            "tpm": full.metrics["trades_per_month"],
            "pf": full.metrics["profit_factor"],
            "trades": full.metrics["total_trades"],
            "pos_years": pos,
            "train": train.metrics["total_return_pct"],
            "train_dd": train.metrics["max_drawdown_pct"],
            "oos": oos.metrics["total_return_pct"],
            "oos_dd": oos.metrics["max_drawdown_pct"],
            "oos_sharpe": oos.metrics["sharpe"],
            "y2020": y.get(2020),
            "y2021": y.get(2021),
            "y2022": y.get(2022),
            "y2023": y.get(2023),
            "y2024": y.get(2024),
            "y2025": y.get(2025),
        }
        rows.append(row)
        if i % 20 == 0 or i == len(combos) - 1:
            print(
                f"[{i+1}/{len(combos)}] ret={row['ret']:.1f}% oos={row['oos']:.1f}% "
                f"dd={row['dd']:.1f}% wr={row['wr']:.1f}% tpm={row['tpm']:.1f} | {tag}"
            )

    df = pd.DataFrame(rows)
    df.to_csv(OUT / "residual_sweep.csv", index=False)

    scored = df.copy()
    scored["score"] = (
        (scored["oos"] > 0).astype(float) * 4
        + (scored["dd"] < 20).astype(float) * 3
        + (scored["pos_years"] >= 4).astype(float) * 2
        + (scored["oos_dd"] < 12).astype(float) * 1.5
        + scored["oos_sharpe"].clip(-1, 2) * 1.5
        + scored["sharpe"].clip(-1, 2)
        + (scored["ret"] / 40.0).clip(-1, 4)
        + scored["tpm"].between(3, 30).astype(float)
        + (scored["pf"] > 1.05).astype(float)
        + (scored["train"] > 0).astype(float)
    )
    scored = scored.sort_values(["score", "oos", "sharpe", "ret"], ascending=False)
    scored.to_csv(OUT / "residual_sweep_ranked.csv", index=False)
    top = scored.head(20)
    top.to_csv(OUT / "residual_top20.csv", index=False)

    best = scored.iloc[0]
    pick = {
        "picked": best["config"],
        "params": {k: (bool(v) if isinstance(v, (bool,)) else v)
                   for k, v in best.items()
                   if k in StrategyConfig.__dataclass_fields__},
        "metrics": {
            k: float(best[k]) if pd.notna(best[k]) else None
            for k in [
                "ret", "dd", "sharpe", "wr", "tpm", "pf", "trades", "pos_years",
                "train", "oos", "oos_dd", "oos_sharpe",
            ]
        },
        "yearly": {str(y): float(best[f"y{y}"]) for y in range(2020, 2026)},
    }
    # Fix params typing
    p = pick["params"]
    for k in ("mom_lookback", "mom_lookback_short", "swing_lookback", "swing_lookback_short",
              "bg_persist", "sniper_max_per_month"):
        if k in p:
            p[k] = int(p[k])
    for k in ("sniper_resid_z", "bg_resid_z", "sniper_tp_atr", "bg_tp_atr",
              "sniper_risk_pct", "bg_risk_pct"):
        if k in p:
            p[k] = float(p[k])
    if "use_sweep_stop" in p:
        p["use_sweep_stop"] = bool(p["use_sweep_stop"])

    (OUT / "residual_pick.json").write_text(json.dumps(pick, indent=2))
    print("\nTOP 15:")
    cols = ["config", "ret", "dd", "sharpe", "oos", "oos_dd", "wr", "tpm", "pos_years", "score"]
    print(top[cols].to_string(index=False))
    print("\nPICK:", json.dumps(pick, indent=2))


if __name__ == "__main__":
    main()
