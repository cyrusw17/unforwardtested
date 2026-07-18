"""
Live Paper Trading Engine
==========================
Runs the validated "Enhanced ICT v3" strategy (AUD/USD daily,
19.47% annual return, MCPT p=0.006, better drawdown/Sharpe/Calmar than
the earlier v2) as a live, fully-automated paper-trading simulation.
See mcpt_strategy/TRADE_ANALYSIS_2020_2024_ADJUSTMENT.md for how v3 was
derived from a trade-level winner/loser analysis of v2.

- $100,000 starting balance
- 1:100 leverage
- Conviction-weighted position sizing (risk % scales with signal strength)
- OANDA-realistic spread/slippage costs
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

from mcpt_strategy.strategies.enhanced_ict_v3_adjusted import enhanced_ict_v3_adjusted


PAIR_YF = 'AUDUSD=X'
PAIR_DISPLAY = 'AUD/USD'
STARTING_BALANCE = 100_000.0
LEVERAGE = 100.0
PIP_VALUE_PER_LOT = 10.0  # USD, since AUDUSD quote currency is USD
PIP_SIZE = 0.0001
AVG_SPREAD_PIPS = 1.2
SLIPPAGE_PIPS = 0.3
BASE_RISK_PCT = 0.01  # 1% of equity risked per 1.0x signal strength unit


def fetch_daily_history(lookback_days: int = 150) -> pd.DataFrame:
    """Fetch enough daily history to compute indicators reliably."""
    end = datetime.now(timezone.utc) + timedelta(days=1)
    start = end - timedelta(days=lookback_days)
    df = yf.download(PAIR_YF, start=start.strftime('%Y-%m-%d'), end=end.strftime('%Y-%m-%d'),
                      interval='1d', progress=False)
    if df is None or len(df) == 0:
        raise RuntimeError("Failed to fetch daily AUDUSD history")
    df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    df = df[['Open', 'High', 'Low', 'Close']].dropna()
    df.index = pd.to_datetime(df.index).tz_localize(None)
    return df


def fetch_recent_intraday(period: str = '7d', interval: str = '1h') -> pd.DataFrame:
    """Fetch recent intraday price data for the live price chart / mark-to-market."""
    df = yf.download(PAIR_YF, period=period, interval=interval, progress=False)
    if df is None or len(df) == 0:
        raise RuntimeError("Failed to fetch intraday AUDUSD data")
    df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    df = df[['Open', 'High', 'Low', 'Close']].dropna()
    df.index = pd.to_datetime(df.index)
    if df.index.tz is not None:
        df.index = df.index.tz_convert('UTC').tz_localize(None)
    return df


def compute_atr_pips(daily_df: pd.DataFrame, period: int = 14) -> float:
    """Average True Range of the most recent `period` daily bars, in pips."""
    high = daily_df['High']
    low = daily_df['Low']
    close = daily_df['Close']
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs()
    ], axis=1).max(axis=1)
    atr = tr.rolling(period).mean().iloc[-1]
    return float(atr / PIP_SIZE)


def calculate_position_size_lots(equity: float, signal_strength: float, stop_distance_pips: float, price: float) -> float:
    """
    Conviction-weighted, risk-based position sizing (mirrors the OANDA broker
    model used in backtesting). Larger |signal_strength| => more risk
    dollars => bigger position, capped by available 1:100 leverage.
    """
    risk_pct = BASE_RISK_PCT * abs(signal_strength)
    risk_amount = equity * risk_pct
    stop_distance_pips = max(stop_distance_pips, 5.0)  # floor to avoid absurd sizing
    position_size_lots = risk_amount / (PIP_VALUE_PER_LOT * stop_distance_pips)

    # Cap by available leverage (margin constraint)
    max_notional = equity * LEVERAGE
    notional = position_size_lots * 100_000 * price
    if notional > max_notional:
        position_size_lots = max_notional / (100_000 * price)

    return max(position_size_lots, 0.0)


def pnl_for_move(entry_price: float, current_price: float, size_lots: float, direction: int) -> float:
    """Gross P&L in USD for a given price move (direction: +1 long, -1 short)."""
    pip_movement = (current_price - entry_price) / PIP_SIZE if direction == 1 else (entry_price - current_price) / PIP_SIZE
    return pip_movement * PIP_VALUE_PER_LOT * size_lots


def spread_slippage_cost(size_lots: float) -> float:
    return (AVG_SPREAD_PIPS + SLIPPAGE_PIPS) * PIP_VALUE_PER_LOT * size_lots


def get_latest_signal(daily_df: pd.DataFrame) -> Tuple[float, pd.Timestamp]:
    """
    Return the position to hold TODAY, decided using data through the most
    recently CLOSED daily bar (yesterday's close) -- exactly matching the
    backtest's shift(1) semantics ("trade tomorrow based on today's score").

    `enhanced_ict_v3_adjusted` internally shifts its own output by one bar,
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

    signal = enhanced_ict_v3_adjusted(extended)
    return float(signal.iloc[-1]), last_closed_date
