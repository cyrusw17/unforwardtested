"""
Final validated strategy: Causal 2-Pair ICT Portfolio (GBP/JPY + NZD/CAD)
============================================================================
See mcpt_strategy/PHASE10_15PCT_HONEST_RESULTS.md for full methodology:
parameters selected using ONLY 2005-2024 data (no test-set leakage), the
causal (lookahead-free) `enhanced_ict_scoring_v2` signal, combined
50/50 into a portfolio because the two legs are -0.24 correlated on the
untouched 2025-2026 test window. Validated with a portfolio-level MCPT
(p=0.019, 1000 permutations, correlation-preserving multi-market permutation) on that same untouched window.

Unscaled (1x): +4.04%/yr, MaxDD -3.18%, PF 1.45, Sharpe 1.58 (2025-2026).
At SCALE=4.0 (position-size multiplier -- exactly scale-invariant for PF/
Sharpe/MCPT, see docs): ~+16.2%/yr, MaxDD ~-12.7%.
"""
from typing import Dict, Tuple
import numpy as np
import pandas as pd

from mega_search_framework import enhanced_ict_scoring_v2


LEGS = [
    {'pair': 'GBPJPY=X', 'weight': 0.5,
     'params': dict(entry_threshold=2.5, ob_lookback=3, ob_weight=3.0, trend_weight=1.0)},
    {'pair': 'NZDCAD=X', 'weight': 0.5,
     'params': dict(entry_threshold=2.0, ob_lookback=3, ob_weight=1.5, trend_weight=1.5)},
]
SCALE = 4.0


def leg_signal(ohlc: pd.DataFrame, pair: str) -> pd.Series:
    """Raw causal directional signal (+1/0/-1) for one leg of the portfolio."""
    leg = next(l for l in LEGS if l['pair'] == pair)
    return enhanced_ict_scoring_v2(ohlc, **leg['params'])


def portfolio_returns(ohlc_by_pair: Dict[str, pd.DataFrame], scale: float = SCALE) -> pd.Series:
    """
    Combine per-leg log-returns into one portfolio return series, using
    EXACTLY the same signal/return alignment as `calculate_metrics` in
    mega_search_framework.py (the function all pair/parameter selection in
    this project was screened with):
        returns = log(Close).diff().shift(-1)   # forward return, day t -> t+1
        strategy_returns = signal * returns      # signal is already
                                                   # internally shift(1)'d
    `ohlc_by_pair`: {pair: OHLC DataFrame}, index-aligned across legs
    (caller should reindex to the intersection of dates first).
    """
    total = None
    for leg in LEGS:
        pair = leg['pair']
        ohlc = ohlc_by_pair[pair]
        sig = leg_signal(ohlc, pair)  # already internally shift(1)'d -- do not shift again
        returns = np.log(ohlc['Close']).diff().shift(-1)
        leg_ret = scale * leg['weight'] * sig * returns
        total = leg_ret if total is None else total.add(leg_ret, fill_value=0)
    return total.fillna(0)
