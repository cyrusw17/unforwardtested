"""Residual momentum and liquidity-sweep primitives (causal, no look-ahead)."""

from __future__ import annotations

from typing import Dict, Tuple

import numpy as np
import pandas as pd


def aligned_log_returns(pair_data: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    closes = pd.DataFrame({p: df["Close"] for p, df in pair_data.items()})
    return np.log(closes / closes.shift(1))


def basket_factor(returns: pd.DataFrame) -> pd.Series:
    """Equal-weight cross-pair factor (USD-proxy basket of traded majors)."""
    return returns.mean(axis=1)


def rolling_residual(
    returns: pd.Series,
    factor: pd.Series,
    beta_lookback: int = 60,
) -> Tuple[pd.Series, pd.Series]:
    """Rolling OLS residual: r - beta * factor. Beta uses only past windows."""
    cov = returns.rolling(beta_lookback, min_periods=max(20, beta_lookback // 3)).cov(factor)
    var = factor.rolling(beta_lookback, min_periods=max(20, beta_lookback // 3)).var()
    beta = cov / var.replace(0.0, np.nan)
    resid = returns - beta * factor
    return resid, beta


def residual_momentum(
    resid: pd.Series,
    mom_lookback: int = 12,
    z_lookback: int = 60,
) -> Tuple[pd.Series, pd.Series]:
    """Sum of recent residuals + z-score of that sum (for thresholds)."""
    mom = resid.rolling(mom_lookback, min_periods=max(3, mom_lookback // 2)).sum()
    mu = mom.rolling(z_lookback, min_periods=max(20, z_lookback // 3)).mean()
    sd = mom.rolling(z_lookback, min_periods=max(20, z_lookback // 3)).std()
    z = (mom - mu) / sd.replace(0.0, np.nan)
    return mom, z


def compute_cross_pair_residuals(
    pair_data: Dict[str, pd.DataFrame],
    beta_lookback: int = 60,
    mom_lookback: int = 12,
    z_lookback: int = 60,
) -> Dict[str, pd.DataFrame]:
    """
    For each pair, attach residual, residual momentum, and residual-z.
    Factor = equal-weight mean of available pair log-returns at each timestamp.
    """
    rets = aligned_log_returns(pair_data)
    factor = basket_factor(rets)
    out: Dict[str, pd.DataFrame] = {}
    for pair, df in pair_data.items():
        if pair not in rets.columns:
            continue
        resid, beta = rolling_residual(rets[pair], factor, beta_lookback)
        mom, z = residual_momentum(resid, mom_lookback, z_lookback)
        frame = df.copy()
        frame["log_ret"] = rets[pair].reindex(frame.index)
        frame["factor_ret"] = factor.reindex(frame.index)
        frame["resid_beta"] = beta.reindex(frame.index)
        frame["resid"] = resid.reindex(frame.index)
        frame["resid_mom"] = mom.reindex(frame.index)
        frame["resid_z"] = z.reindex(frame.index)
        out[pair] = frame
    return out


def liquidity_sweep_flags(
    df: pd.DataFrame,
    swing_lookback: int = 24,
    min_wick_atr: float = 0.15,
) -> pd.DataFrame:
    """
    Liquidity sweep = take out prior swing extreme, then reclaim (close back inside).

    Bullish: Low pierces prior swing low, Close reclaims above that low.
    Bearish: High pierces prior swing high, Close reclaims below that high.
    """
    out = df.copy()
    atr = out["atr"] if "atr" in out.columns else (out["High"] - out["Low"]).rolling(14).mean()

    prior_low = out["Low"].rolling(swing_lookback, min_periods=swing_lookback).min().shift(1)
    prior_high = out["High"].rolling(swing_lookback, min_periods=swing_lookback).max().shift(1)

    bull_pierce = out["Low"] < prior_low
    bear_pierce = out["High"] > prior_high
    bull_reclaim = out["Close"] > prior_low
    bear_reclaim = out["Close"] < prior_high

    # Rejection wick quality vs ATR
    lower_wick = (out[["Open", "Close"]].min(axis=1) - out["Low"]).clip(lower=0.0)
    upper_wick = (out["High"] - out[["Open", "Close"]].max(axis=1)).clip(lower=0.0)
    bull_wick_ok = lower_wick >= (min_wick_atr * atr)
    bear_wick_ok = upper_wick >= (min_wick_atr * atr)

    out["swing_low"] = prior_low
    out["swing_high"] = prior_high
    out["bull_sweep"] = bull_pierce & bull_reclaim & bull_wick_ok
    out["bear_sweep"] = bear_pierce & bear_reclaim & bear_wick_ok
    out["sweep_extreme"] = np.where(out["bull_sweep"], out["Low"], np.where(out["bear_sweep"], out["High"], np.nan))
    return out


def recent_event(flag: pd.Series, persistence: int) -> pd.Series:
    """True if flag fired on this bar or any of the prior (persistence-1) bars."""
    if persistence <= 1:
        return flag.fillna(False)
    return flag.fillna(False).rolling(persistence, min_periods=1).max().astype(bool)


def displacement_ok(df: pd.DataFrame, min_body_atr: float = 0.35) -> pd.Series:
    body = (df["Close"] - df["Open"]).abs()
    atr = df["atr"] if "atr" in df.columns else (df["High"] - df["Low"]).rolling(14).mean()
    return body >= (min_body_atr * atr)
