"""
OANDA-ready signal bridge (paper/live wiring stub).

This module converts the locked dual strategy into broker-agnostic order intents.
It does not place orders; integrate with the OANDA REST/streaming client separately.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from historical_strategy_2020_2025.final_strategy.strategy_implementation import (
    StrategyConfig,
    prepare_pair_signals,
)


@dataclass
class OrderIntent:
    pair: str
    strategy: str
    side: str  # buy / sell
    units: float
    stop_loss: float
    take_profit: float
    risk_pct: float


PAIR_TO_OANDA = {
    "EURUSD": "EUR_USD",
    "GBPUSD": "GBP_USD",
    "USDJPY": "USD_JPY",
    "AUDUSD": "AUD_USD",
}


def load_config(path: Optional[str | Path] = None) -> StrategyConfig:
    path = Path(path or Path(__file__).with_name("config.json"))
    raw = json.loads(path.read_text())
    known = StrategyConfig().__dict__.keys()
    return StrategyConfig(**{k: v for k, v in raw.items() if k in known})


def latest_intents(
    pair_frames: Dict[str, pd.DataFrame],
    equity: float,
    cfg: Optional[StrategyConfig] = None,
) -> List[OrderIntent]:
    """
    Build order intents from the latest completed bar signals.

    `pair_frames` must already include the newest closed candle only through
    dates <= today; never pass unfinished bars.
    """
    cfg = cfg or load_config()
    intents: List[OrderIntent] = []
    for pair, df in pair_frames.items():
        sig = prepare_pair_signals(df, cfg)
        row = sig.iloc[-1]
        for strat, alloc, sig_col in [
            ("sniper", cfg.sniper_alloc, "sniper_signal"),
            ("background", cfg.background_alloc, "background_signal"),
        ]:
            signal = int(row[sig_col])
            if signal == 0:
                continue
            atr = float(row["atr"])
            entry = float(row["Close"])  # approximate; live should use next open / quote
            sl_mult = float(row[f"{strat}_sl_atr_mult"])
            tp_mult = float(row[f"{strat}_tp_atr_mult"])
            risk_pct = float(row[f"{strat}_risk_pct"])
            if signal > 0:
                side = "buy"
                sl = entry - sl_mult * atr
                tp = entry + tp_mult * atr
            else:
                side = "sell"
                sl = entry + sl_mult * atr
                tp = entry - tp_mult * atr
            stop_dist = abs(entry - sl)
            if stop_dist <= 0:
                continue
            risk_dollars = equity * alloc * (risk_pct / 100.0)
            if pair.endswith("JPY"):
                units = risk_dollars / (stop_dist / entry)
            else:
                units = risk_dollars / stop_dist
            max_units = equity * 50.0 * alloc / entry
            units = max(0.0, min(units, max_units))
            if signal < 0:
                units = -units
            intents.append(
                OrderIntent(
                    pair=PAIR_TO_OANDA.get(pair, pair),
                    strategy=strat,
                    side=side,
                    units=float(units),
                    stop_loss=float(sl),
                    take_profit=float(tp),
                    risk_pct=risk_pct,
                )
            )
    return intents


if __name__ == "__main__":
    print("OANDA bridge stub OK. Config:", load_config().name)
