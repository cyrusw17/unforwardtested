#!/usr/bin/env python3
"""Full 2020-2025 backtest for the locked final strategy configuration."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.backtest import Backtester
from core.data_handler import DataHandler
from historical_strategy_2020_2025.final_strategy.strategy_implementation import (
    StrategyConfig,
    allocation_map,
    build_signal_frames,
)

HERE = Path(__file__).resolve().parent


def load_config() -> StrategyConfig:
    path = HERE / "config.json"
    data = json.loads(path.read_text())
    known = StrategyConfig().__dict__.keys()
    return StrategyConfig(**{k: v for k, v in data.items() if k in known})


def main():
    cfg = load_config()
    handler = DataHandler(cache_dir=ROOT / "data" / "cache")
    pairs = handler.fetch_all_pairs(start="2020-01-01", end="2025-12-31", interval="1d")
    for p, df in pairs.items():
        handler.assert_no_2026(df, p)
        assert df.index[-1].year <= 2025

    signals = build_signal_frames(pairs, cfg)
    bt = Backtester(
        initial_capital=10_000.0,
        leverage=50.0,
        max_drawdown_pct=20.0,
        use_breakeven=False,
        use_partial_tp=False,
        max_bars_held=10**9,
        allow_dual_positions=True,
    )
    result = bt.run(signals, capital_alloc=allocation_map(cfg))

    result.trades_df().to_csv(HERE / "full_period_trades.csv", index=False)
    result.equity_curve.to_csv(HERE / "full_period_equity.csv", header=True)
    with open(HERE / "full_period_metrics.json", "w") as f:
        json.dump(result.metrics, f, indent=2)

    print(json.dumps(result.metrics, indent=2))
    return result


if __name__ == "__main__":
    main()
