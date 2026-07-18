"""
ATR Stop-Loss Backtest Engine
================================
Adds an ATR-based stop-loss on top of any signal series produced by the
existing strategy functions, WITHOUT changing the day-to-day return
attribution convention used by `mega_search_framework.calculate_metrics`
(signal.iloc[i] governs the log-return realized from close_i to
close_{i+1}). This lets us directly compare stop-loss vs. no-stop-loss
apples-to-apples, including running MCPT on the stop-loss-adjusted
returns.

Mechanism: each time a new directional trade begins (direction changes,
including from flat), a stop price is fixed at
`entry_close -/+ atr_mult * ATR(atr_period)` (computed at the entry bar).
For every subsequent day the trade persists, if the NEXT bar's high/low
breaches the stop, that day's return is capped at the stop distance
(instead of the full close-to-close move) and the position is forced
flat until the underlying signal naturally starts a new trade (a
direction change). If no stop is hit, behavior is IDENTICAL to the
plain vectorized signal*return model.
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))

import numpy as np
import pandas as pd
from typing import Dict, Optional


def compute_atr(ohlc: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = ohlc['High'], ohlc['Low'], ohlc['Close']
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def backtest_with_atr_stop(ohlc: pd.DataFrame, signal: pd.Series,
                            atr_mult: Optional[float] = 2.5,
                            atr_period: int = 14) -> pd.Series:
    """
    Returns a per-bar log-return-contribution series, directly comparable
    to `signal * log_return` in calculate_metrics, but with stop-loss
    capping applied. If atr_mult is None, this is exactly equivalent to
    the plain vectorized model (no stop).
    """
    close = ohlc['Close']
    high = ohlc['High']
    low = ohlc['Low']
    log_close = np.log(close)
    atr = compute_atr(ohlc, atr_period) if atr_mult is not None else None

    n = len(ohlc)
    strat_returns = pd.Series(0.0, index=ohlc.index)

    if atr_mult is None:
        returns = log_close.diff().shift(-1)
        return (signal * returns).fillna(0.0)

    current_dir = 0
    entry_price = None
    stop_price = None
    stopped = False

    sig_vals = signal.values
    close_vals = close.values
    high_vals = high.values
    low_vals = low.values
    log_close_vals = log_close.values
    atr_vals = atr.values

    out = np.zeros(n)

    for i in range(n - 1):
        sig = sig_vals[i]
        d = np.sign(sig)
        sz = abs(sig)

        if d == 0:
            current_dir = 0
            stopped = False
            continue

        if current_dir == 0 or d != current_dir:
            current_dir = d
            entry_price = close_vals[i]
            stopped = False
            atr_val = atr_vals[i]
            if not np.isnan(atr_val) and atr_val > 0:
                stop_price = entry_price - current_dir * atr_mult * atr_val
            else:
                stop_price = None

        if stopped or sz == 0:
            continue

        next_low = low_vals[i + 1]
        next_high = high_vals[i + 1]

        hit = stop_price is not None and (
            (current_dir == 1 and next_low <= stop_price) or
            (current_dir == -1 and next_high >= stop_price)
        )

        if hit:
            out[i] = current_dir * sz * (np.log(stop_price) - log_close_vals[i])
            stopped = True
        else:
            out[i] = current_dir * sz * (log_close_vals[i + 1] - log_close_vals[i])

    strat_returns[:] = out
    return strat_returns


def calculate_metrics_from_returns(strategy_returns: pd.Series, n_bars: int,
                                    signal: pd.Series, bars_per_year: float = 252) -> Optional[Dict]:
    strategy_returns = strategy_returns.dropna()

    if len(strategy_returns) == 0 or len(strategy_returns[strategy_returns < 0]) == 0:
        return None
    if len(strategy_returns[strategy_returns != 0]) < 10:
        return None

    total_return = np.exp(strategy_returns.sum()) - 1
    years = n_bars / bars_per_year
    annual_return = (1 + total_return) ** (1 / years) - 1 if years > 0 else 0

    winning = strategy_returns[strategy_returns > 0].sum()
    losing = strategy_returns[strategy_returns < 0].abs().sum()
    profit_factor = winning / losing if losing > 0 else 0

    sharpe = strategy_returns.mean() / strategy_returns.std() * np.sqrt(bars_per_year) if strategy_returns.std() > 0 else 0

    cum_returns = strategy_returns.cumsum()
    running_max = cum_returns.cummax()
    drawdown = cum_returns - running_max
    max_dd = drawdown.min()

    trades = (signal.diff() != 0).sum()
    win_rate = len(strategy_returns[strategy_returns > 0]) / len(strategy_returns) * 100

    return {
        'total_return': float(total_return),
        'annual_return': float(annual_return),
        'annual_return_pct': float(annual_return * 100),
        'profit_factor': float(profit_factor),
        'sharpe_ratio': float(sharpe),
        'max_drawdown': float(max_dd),
        'max_drawdown_pct': float(max_dd * 100),
        'win_rate': float(win_rate),
        'trades': int(trades),
        'trades_per_year': float(trades / years) if years > 0 else 0,
        'years': float(years),
        'calmar_ratio': float(annual_return / abs(max_dd)) if max_dd != 0 else 0,
    }


def calculate_metrics_with_stop(ohlc: pd.DataFrame, signal: pd.Series,
                                 atr_mult: Optional[float] = 2.5,
                                 atr_period: int = 14, bars_per_year: float = 252) -> Optional[Dict]:
    returns = backtest_with_atr_stop(ohlc, signal, atr_mult, atr_period)
    return calculate_metrics_from_returns(returns, len(ohlc), signal, bars_per_year)


def full_mcpt_with_stop(ohlc: pd.DataFrame, strategy_func, params: Dict,
                         atr_mult: Optional[float] = 2.5, atr_period: int = 14,
                         n_permutations: int = 200) -> Dict:
    """Full MCPT, but scoring real vs. permuted data using the ATR-stop-adjusted returns."""
    from mcpt_strategy.utils import get_permutation

    signal = strategy_func(ohlc, **params)
    real_metrics = calculate_metrics_with_stop(ohlc, signal, atr_mult, atr_period)

    if real_metrics is None:
        return {'passed': False, 'error': 'No valid metrics'}

    real_pf = real_metrics['profit_factor']
    perm_better = 1
    perm_pfs = []

    for i in range(1, n_permutations):
        try:
            ohlc_lower = ohlc.copy()
            ohlc_lower.columns = [c.lower() for c in ohlc_lower.columns]
            perm_data = get_permutation(ohlc_lower, seed=i * 100)
            perm_data.columns = [c.capitalize() for c in perm_data.columns]

            perm_signal = strategy_func(perm_data, **params)
            perm_metrics = calculate_metrics_with_stop(perm_data, perm_signal, atr_mult, atr_period)

            perm_pf = perm_metrics['profit_factor'] if perm_metrics else 1.0
            if perm_pf >= real_pf:
                perm_better += 1
            perm_pfs.append(perm_pf)
        except Exception:
            perm_pfs.append(1.0)

    p_value = perm_better / n_permutations

    return {
        'real_metrics': real_metrics,
        'real_pf': float(real_pf),
        'p_value': float(p_value),
        'permuted_mean': float(np.mean(perm_pfs)),
        'permuted_std': float(np.std(perm_pfs)),
        'permuted_better_count': int(perm_better - 1),
        'n_permutations': n_permutations,
        'passed': p_value < 0.05,
    }
