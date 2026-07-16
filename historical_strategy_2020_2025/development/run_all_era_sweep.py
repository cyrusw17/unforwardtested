#!/usr/bin/env python3
"""
Select a strategy that works across regimes — not just the train window.

Hard gates (all must pass):
  2018-2019 return >= floor_prior
  2020 return >= floor_covid
  2021-2023 return >= 0
  2024-2025 return >= 0
  full 2018-2025 return > 0
  full max DD < 20%
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.all_era_signals import AllEraConfig, allocation_map, build_signal_frames
from core.backtest import Backtester

OUT = Path(__file__).resolve().parent / "backtest_results"
OUT.mkdir(parents=True, exist_ok=True)
CACHE = ROOT / "data" / "cache" / "h4_2018_2025"

FLOOR_PRIOR = -2.0  # 2018-2019
FLOOR_COVID = -5.0  # 2020
FLOOR_TRAIN = 0.0  # 2021-2023
FLOOR_OOS = 0.0  # 2024-2025


def load_pairs() -> dict:
    out = {}
    for p in ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD"]:
        df = pd.read_parquet(CACHE / f"{p}_h4_2018_2025.parquet")
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC")
        else:
            df.index = df.index.tz_convert("UTC")
        assert df.index.max().year <= 2025
        out[p] = df
    return out


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


def era_pnl_pct(trades: pd.DataFrame, y0: int, y1: int, capital: float = 1000.0) -> float:
    if trades is None or len(trades) == 0:
        return 0.0
    t = trades.copy()
    t["entry_time"] = pd.to_datetime(t["entry_time"], utc=True)
    m = (t.entry_time.dt.year >= y0) & (t.entry_time.dt.year <= y1)
    return float(t.loc[m, "pnl"].sum() / capital * 100.0)


def eval_cfg(pairs: dict, cfg: AllEraConfig) -> dict:
    sig = build_signal_frames(pairs, cfg)
    res = make_bt().run(sig, capital_alloc=allocation_map(cfg))
    tdf = res.trades_df()
    m = res.metrics
    e1819 = era_pnl_pct(tdf, 2018, 2019)
    e2020 = era_pnl_pct(tdf, 2020, 2020)
    e2123 = era_pnl_pct(tdf, 2021, 2023)
    e2425 = era_pnl_pct(tdf, 2024, 2025)
    # equity yearly path
    eq = res.equity_curve
    yearly = {}
    prev = float(eq.iloc[0])
    for y in sorted(eq.index.year.unique()):
        end = float(eq[eq.index.year == y].iloc[-1])
        yearly[int(y)] = (end / prev - 1) * 100.0
        prev = end
    pos_years = sum(1 for v in yearly.values() if v > 0)
    passes = (
        e1819 >= FLOOR_PRIOR
        and e2020 >= FLOOR_COVID
        and e2123 >= FLOOR_TRAIN
        and e2425 >= FLOOR_OOS
        and m["total_return_pct"] > 0
        and m["max_drawdown_pct"] < 20
        and m["total_trades"] >= 25
    )
    min_era = min(e1819, e2020, e2123, e2425)
    score = (
        float(passes) * 20
        + min_era
        + m["sharpe"] * 2
        + min(m["total_return_pct"], 40) / 10
        + (4 if m["max_drawdown_pct"] < 12 else 0)
        + (2 if pos_years >= 6 else 0)
        + (1 if m["profit_factor"] and m["profit_factor"] > 1.1 else 0)
    )
    return {
        "family": cfg.family,
        "name": cfg.name,
        "ret": m["total_return_pct"],
        "dd": m["max_drawdown_pct"],
        "sharpe": m["sharpe"],
        "wr": m["win_rate"],
        "pf": m["profit_factor"],
        "trades": m["total_trades"],
        "tpm": m["trades_per_month"],
        "e1819": round(e1819, 2),
        "e2020": round(e2020, 2),
        "e2123": round(e2123, 2),
        "e2425": round(e2425, 2),
        "min_era": round(min_era, 2),
        "pos_years": pos_years,
        "passes": passes,
        "score": round(score, 3),
        "yearly": {str(k): round(v, 2) for k, v in yearly.items()},
        "params": cfg.to_dict(),
    }


def build_grid() -> list[AllEraConfig]:
    cfgs: list[AllEraConfig] = []
    i = 0

    # --- residual × sweep sniper-only (focused) ---
    for mom_l, mom_s in [(8, 4), (12, 4), (18, 8)]:
        for sw_l, sw_s in [(12, 18), (18, 24), (36, 48)]:
            for z in [1.0, 1.25, 1.5]:
                for adx in [12, 18]:
                    for tp in [3.0, 4.0]:
                        for max_az in [2.5, 10.0]:
                            cfgs.append(
                                AllEraConfig(
                                    name=f"rs_{i}",
                                    family="residual_sweep",
                                    mom_lookback=mom_l,
                                    mom_lookback_short=mom_s,
                                    swing_lookback=sw_l,
                                    swing_lookback_short=sw_s,
                                    sniper_resid_z=z,
                                    bg_resid_z=max(0.5, z - 0.5),
                                    min_adx=float(adx),
                                    sniper_tp_atr=tp,
                                    sniper_risk_pct=1.0,
                                    max_atr_z=max_az,
                                    sniper_only=True,
                                    use_sweep=True,
                                )
                            )
                            i += 1

    # residual TS (no sweep)
    for mom in [8, 12, 18, 24]:
        for z in [1.0, 1.25, 1.5, 2.0]:
            for adx in [12, 18, 22]:
                for tp in [2.5, 3.5]:
                    cfgs.append(
                        AllEraConfig(
                            name=f"rts_{i}",
                            family="residual_ts",
                            mom_lookback=mom,
                            mom_lookback_short=mom,
                            sniper_resid_z=z,
                            min_adx=float(adx),
                            sniper_tp_atr=tp,
                            sniper_sl_atr=1.5,
                            sniper_risk_pct=1.0,
                            sniper_only=True,
                            use_sweep_stop=False,
                            max_atr_z=2.5,
                        )
                    )
                    i += 1

    # Donchian
    for n in [20, 30, 40, 55]:
        for adx in [15, 20, 25]:
            for tp in [2.0, 3.0, 4.0]:
                for sl in [1.5, 2.0]:
                    cfgs.append(
                        AllEraConfig(
                            name=f"dc_{i}",
                            family="donchian",
                            donchian_n=n,
                            min_adx=float(adx),
                            sniper_tp_atr=tp,
                            sniper_sl_atr=sl,
                            sniper_risk_pct=1.0,
                            sniper_only=True,
                            use_sweep_stop=False,
                            max_atr_z=2.5,
                            sniper_max_per_month=4,
                        )
                    )
                    i += 1

    # Cross-sectional residual
    for mom in [8, 12, 20]:
        for edge in [0.75, 1.0, 1.25]:
            for adx in [12, 18]:
                for tp in [2.5, 3.5]:
                    cfgs.append(
                        AllEraConfig(
                            name=f"xs_{i}",
                            family="xs_residual",
                            mom_lookback=mom,
                            mom_lookback_short=mom,
                            xs_z_edge=edge,
                            min_adx=float(adx),
                            sniper_tp_atr=tp,
                            sniper_sl_atr=1.75,
                            sniper_risk_pct=1.0,
                            sniper_only=True,
                            use_sweep_stop=False,
                            max_atr_z=2.5,
                            sniper_max_per_month=6,
                        )
                    )
                    i += 1

    # prior dual lock as baseline reference
    cfgs.append(
        AllEraConfig(
            name="dual_lock_ref",
            family="residual_sweep",
            mom_lookback=8,
            mom_lookback_short=4,
            swing_lookback=18,
            swing_lookback_short=24,
            sniper_resid_z=1.25,
            bg_resid_z=0.75,
            sniper_tp_atr=4.0,
            bg_tp_atr=2.5,
            sniper_risk_pct=1.5,
            bg_risk_pct=1.0,
            sniper_only=False,
            sniper_alloc=0.6,
            background_alloc=0.4,
            min_adx=10,
            max_atr_z=10.0,
        )
    )

    # dedupe by params signature
    uniq, seen = [], set()
    for c in cfgs:
        key = json.dumps(c.to_dict(), sort_keys=True)
        if key not in seen:
            seen.add(key)
            uniq.append(c)
    return uniq


def main():
    pairs = load_pairs()
    grid = build_grid()
    print(f"Evaluating {len(grid)} configs on 2018-2025 ...")
    rows = []
    for i, cfg in enumerate(grid):
        try:
            row = eval_cfg(pairs, cfg)
        except Exception as e:
            row = {"family": cfg.family, "name": cfg.name, "passes": False, "score": -999, "error": str(e)}
        rows.append(row)
        if i % 25 == 0 or i == len(grid) - 1:
            flag = "PASS" if row.get("passes") else "fail"
            print(
                f"[{i+1}/{len(grid)}] {flag} {row.get('family')} ret={row.get('ret')} "
                f"min_era={row.get('min_era')} e1819={row.get('e1819')} e2425={row.get('e2425')} dd={row.get('dd')}"
            )

    df = pd.DataFrame(rows)
    # Flatten params not needed in csv — drop
    if "params" in df.columns:
        df_save = df.drop(columns=["params", "yearly"], errors="ignore")
    else:
        df_save = df
    df_save.to_csv(OUT / "all_era_sweep.csv", index=False)

    passed = df[df["passes"] == True].sort_values(["min_era", "score", "sharpe"], ascending=False)
    ranked = df.sort_values(["passes", "min_era", "score"], ascending=False)
    ranked.drop(columns=["params", "yearly"], errors="ignore").to_csv(OUT / "all_era_ranked.csv", index=False)
    passed.drop(columns=["params", "yearly"], errors="ignore").to_csv(OUT / "all_era_passed.csv", index=False)

    print(f"\nPassed hard gates: {len(passed)} / {len(df)}")
    if len(passed) == 0:
        # relax report: top by min_era among dd<20 and ret>0
        soft = df[(df["ret"] > 0) & (df["dd"] < 20)].sort_values(["min_era", "e1819", "e2425"], ascending=False)
        print("No hard passes. Top soft candidates by min_era:")
        cols = ["family", "name", "ret", "dd", "sharpe", "e1819", "e2020", "e2123", "e2425", "min_era", "trades", "pf"]
        print(soft[cols].head(20).to_string(index=False))
        best = soft.iloc[0] if len(soft) else ranked.iloc[0]
        pick_mode = "soft_min_era"
    else:
        cols = ["family", "name", "ret", "dd", "sharpe", "e1819", "e2020", "e2123", "e2425", "min_era", "trades", "pf", "score"]
        print(passed[cols].head(20).to_string(index=False))
        best = passed.iloc[0]
        pick_mode = "hard_gates"

    # recover full params from rows
    best_full = [r for r in rows if r.get("name") == best["name"]][0]
    pick = {
        "mode": pick_mode,
        "floors": {
            "2018_2019": FLOOR_PRIOR,
            "2020": FLOOR_COVID,
            "2021_2023": FLOOR_TRAIN,
            "2024_2025": FLOOR_OOS,
        },
        "picked": best_full["name"],
        "family": best_full["family"],
        "metrics": {
            k: best_full.get(k)
            for k in [
                "ret", "dd", "sharpe", "wr", "pf", "trades", "tpm",
                "e1819", "e2020", "e2123", "e2425", "min_era", "pos_years", "passes",
            ]
        },
        "yearly": best_full.get("yearly"),
        "params": best_full.get("params"),
        "n_tested": len(df),
        "n_passed": int(len(passed)),
    }
    (OUT / "all_era_pick.json").write_text(json.dumps(pick, indent=2))
    print("\nPICK:", json.dumps(pick, indent=2)[:2000])


if __name__ == "__main__":
    main()
