#!/usr/bin/env python3
"""Parameter search on 2020-2023 train window only (hold out 2024-2025)."""

from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.backtest import Backtester
from core.data_handler import DataHandler
from historical_strategy_2020_2025.development.test_strategy_variants import composite_score
from historical_strategy_2020_2025.final_strategy.strategy_implementation import (
    StrategyConfig,
    allocation_map,
    build_signal_frames,
)

OUT_DIR = Path(__file__).resolve().parent / "backtest_results"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def grid_configs() -> list[StrategyConfig]:
    configs = []
    i = 0
    for sa, ba, smax, stp, dyn in itertools.product(
        [10, 12, 15],
        [15, 18, 20],
        [2, 3],
        [4.0, 5.0],
        [True],
    ):
        i += 1
        configs.append(
            StrategyConfig(
                name=f"grid_{i:03d}_sa{sa}_ba{ba}_sm{smax}_stp{stp}",
                sniper_fast=5,
                sniper_slow=13,
                bg_fast=8,
                bg_slow=21,
                sniper_adx=float(sa),
                bg_adx=float(ba),
                sniper_max_per_month=int(smax),
                sniper_tp_atr=float(stp),
                use_dynamic_targets=dyn,
            )
        )
    return configs


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


def run_optimize(train_end: str = "2023-12-31") -> pd.DataFrame:
    handler = DataHandler(cache_dir=ROOT / "data" / "cache")
    train = handler.fetch_all_pairs(start="2020-01-01", end=train_end, interval="1d")
    rows = []
    configs = grid_configs()
    print(f"Testing {len(configs)} grid configs on 2020-{train_end[:4]}...")
    for cfg in configs:
        result = run_bt(train, cfg)
        m = result.metrics
        score = composite_score(m)
        rows.append(
            {
                "config": cfg.name,
                "score": score,
                **m,
                **{f"p_{k}": v for k, v in cfg.to_dict().items()},
            }
        )

    summary = pd.DataFrame(rows).sort_values("score", ascending=False)
    summary.to_csv(OUT_DIR / "grid_optimize_train_2020_2023.csv", index=False)
    top = summary.head(8)
    top.to_csv(OUT_DIR / "grid_optimize_top5.csv", index=False)
    cols = [
        "config",
        "score",
        "total_return_pct",
        "sharpe",
        "max_drawdown_pct",
        "win_rate",
        "total_trades",
        "trades_per_month",
        "profit_factor",
    ]
    print(top[cols].to_string(index=False))

    best_row = summary.iloc[0]
    best_params = {k[2:]: best_row[k] for k in summary.columns if k.startswith("p_")}
    for k, v in list(best_params.items()):
        if hasattr(v, "item"):
            best_params[k] = v.item()
    with open(OUT_DIR / "best_train_config.json", "w") as f:
        json.dump(best_params, f, indent=2)
    print("\nBest train config:", best_row["config"])
    return summary


if __name__ == "__main__":
    run_optimize()
