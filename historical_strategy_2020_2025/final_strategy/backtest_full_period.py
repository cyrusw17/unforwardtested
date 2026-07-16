#!/usr/bin/env python3
"""Full 2020-2025 H4 backtest for the locked future-proof dual strategy."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.backtest import Backtester
from core.h4_data import download_all_h4
from historical_strategy_2020_2025.final_strategy.strategy_implementation import (
    StrategyConfig,
    allocation_map,
    build_signal_frames,
)

HERE = Path(__file__).resolve().parent


def load_config() -> StrategyConfig:
    data = json.loads((HERE / "config.json").read_text())
    known = StrategyConfig().__dict__.keys()
    return StrategyConfig(**{k: v for k, v in data.items() if k in known})


def main():
    cfg = load_config()
    pairs = download_all_h4(start="2020-01-01", end="2025-12-31", cache_dir=ROOT / "data" / "cache" / "h4")
    for p, df in pairs.items():
        assert df.index[-1].year <= 2025

    signals = build_signal_frames(pairs, cfg)
    meta = json.loads((HERE / "config.json").read_text()).get("backtest", {})
    bt = Backtester(
        initial_capital=float(meta.get("initial_capital", 1000)),
        leverage=float(meta.get("leverage", 50)),
        max_drawdown_pct=float(meta.get("max_drawdown_pct", 20)),
        soft_drawdown_pct=float(meta.get("soft_drawdown_pct", 15)),
        soft_risk_mult=float(meta.get("soft_risk_mult", 0.5)),
        slippage_pips=float(meta.get("slippage_pips", 0.5)),
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
