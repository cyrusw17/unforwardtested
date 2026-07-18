"""
Live Paper Trading Engine
==========================
Runs the "Causal 2-Pair ICT Portfolio" strategy: GBP/JPY + NZD/CAD, equal
weighted, using the lookahead-free `enhanced_ict_scoring_v2` signal with
parameters selected using ONLY 2005-2024 data (train+validation) and
validated with a portfolio-level Monte Carlo Permutation Test on the
untouched 2025-2026 window (p=0.019, 1000 permutations, correlation-preserving multi-market permutation). See
mcpt_strategy/PHASE10_15PCT_HONEST_RESULTS.md for the full methodology,
including why position-size scaling (SCALE below) does not affect the
MCPT p-value (Profit Factor and Sharpe are exactly scale-invariant to a
uniform position-size multiplier -- only $ return and $ drawdown scale
with it).

Unscaled (1x) portfolio, 2025-2026 out-of-sample: +4.04%/yr, MaxDD -3.18%,
PF 1.45, Sharpe 1.58. At SCALE=4.0 (still within normal retail forex
leverage): ~+16%/yr, MaxDD ~-12.7%.

- $100,000 starting balance
- 1:100 leverage available (headroom only -- SCALE=4.0 uses far less)
- Two independent legs, each risk-sized as a fixed fraction of equity
  notional (not lots/pips -- pip economics differ by quote currency, so
  P&L is modeled directly as notional_usd * log-return, exactly mirroring
  the validated backtest's math)
- Realistic spread/slippage cost charged on every round-trip
- State persisted to JSON files consumed by the GitHub Pages dashboard

This module contains no side effects (no file I/O) - see run_cycle.py and
init_state.py for the CLI entry points that call into this engine.
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List, Tuple

from mcpt_strategy.strategies.mega_search_framework import enhanced_ict_scoring_v2


STARTING_BALANCE = 100_000.0
LEVERAGE = 100.0
SCALE = 4.0  # position-size multiplier chosen (via train/val, see docs) to hit the 15%+ target

LEGS = [
    {
        'pair': 'GBPJPY=X', 'display': 'GBP/JPY', 'weight': 0.5,
        'params': dict(entry_threshold=2.5, ob_lookback=3, ob_weight=3.0, trend_weight=1.0),
        'spread_bps': 3.0,
    },
    {
        'pair': 'NZDCAD=X', 'display': 'NZD/CAD', 'weight': 0.5,
        'params': dict(entry_threshold=2.0, ob_lookback=3, ob_weight=1.5, trend_weight=1.5),
        'spread_bps': 6.0,
    },
]
PAIRS = [leg['pair'] for leg in LEGS]
LEG_BY_PAIR = {leg['pair']: leg for leg in LEGS}


def fetch_daily_history(pair: str, lookback_days: int = 400) -> pd.DataFrame:
    """Fetch enough daily history to compute indicators reliably."""
    end = datetime.now(timezone.utc) + timedelta(days=1)
    start = end - timedelta(days=lookback_days)
    df = yf.download(pair, start=start.strftime('%Y-%m-%d'), end=end.strftime('%Y-%m-%d'),
                      interval='1d', progress=False)
    if df is None or len(df) == 0:
        raise RuntimeError(f"Failed to fetch daily history for {pair}")
    df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    df = df[['Open', 'High', 'Low', 'Close']].dropna()
    df.index = pd.to_datetime(df.index).tz_localize(None)
    return df


def fetch_recent_intraday(pair: str, period: str = '7d', interval: str = '1h') -> pd.DataFrame:
    """Fetch recent intraday price data for the live price chart / mark-to-market."""
    df = yf.download(pair, period=period, interval=interval, progress=False)
    if df is None or len(df) == 0:
        raise RuntimeError(f"Failed to fetch intraday data for {pair}")
    df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    df = df[['Open', 'High', 'Low', 'Close']].dropna()
    df.index = pd.to_datetime(df.index)
    if df.index.tz is not None:
        df.index = df.index.tz_convert('UTC').tz_localize(None)
    return df


def get_latest_signal(pair: str, daily_df: pd.DataFrame) -> float:
    """
    Return the raw directional signal (+1/0/-1) to hold TODAY for `pair`,
    decided using data through the most recently CLOSED daily bar
    (yesterday's close) -- exactly matching the backtest's shift(1)
    semantics ("trade tomorrow based on today's score").

    `enhanced_ict_scoring_v2` internally shifts its own output by one bar,
    so signal.iloc[-1] on `daily_df` as-is would give the position that
    applied to the LAST closed bar (already in the past), not today's.
    To get today's position we append a one-day placeholder row (whose own
    OHLC values are irrelevant -- rolling/ewm indicators never look ahead)
    so the shift lands the last closed bar's score on "today".
    """
    last_closed_date = daily_df.index[-1]
    placeholder_date = last_closed_date + pd.Timedelta(days=1)
    placeholder_row = daily_df.iloc[[-1]].copy()
    placeholder_row.index = [placeholder_date]
    extended = pd.concat([daily_df, placeholder_row])

    params = LEG_BY_PAIR[pair]['params']
    signal = enhanced_ict_scoring_v2(extended, **params)
    return float(signal.iloc[-1])


def leg_notional_usd(equity: float, pair: str, raw_signal: float) -> float:
    """|notional| in USD-equivalent terms for a leg, sized as a fixed
    fraction of current equity (weight * SCALE), independent of |raw_signal|
    since raw_signal is always in {-1, 0, 1} here (binary directional)."""
    leg = LEG_BY_PAIR[pair]
    return equity * leg['weight'] * SCALE * abs(raw_signal)


def pnl_for_move(entry_price: float, current_price: float, notional_usd: float, direction: int) -> float:
    """
    P&L in USD for a given price move, computed via log-return exactly as
    in the validated backtest (strategy_return = signal * log_return):
        pnl_usd = notional_usd * direction * log(current_price / entry_price)
    This is deliberately NOT pip/lot based -- pip economics differ by quote
    currency (JPY vs CAD), so modeling P&L directly as a notional-weighted
    log-return keeps live results consistent with the backtested math.
    """
    log_ret = np.log(current_price / entry_price)
    return notional_usd * direction * log_ret


def spread_slippage_cost(pair: str, notional_usd: float) -> float:
    bps = LEG_BY_PAIR[pair]['spread_bps']
    return notional_usd * (bps / 10_000.0)
