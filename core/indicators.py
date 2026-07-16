"""Technical indicators used by the dual forex strategy."""

from __future__ import annotations

import numpy as np
import pandas as pd


class TechnicalIndicators:
    """Vectorized indicator helpers (no look-ahead within a bar)."""

    @staticmethod
    def ema(df: pd.DataFrame, period: int, column: str = "Close") -> pd.Series:
        return df[column].ewm(span=period, adjust=False).mean()

    @staticmethod
    def sma(df: pd.DataFrame, period: int, column: str = "Close") -> pd.Series:
        return df[column].rolling(window=period).mean()

    @staticmethod
    def rsi(df: pd.DataFrame, period: int = 14, column: str = "Close") -> pd.Series:
        delta = df[column].diff()
        gain = delta.clip(lower=0.0)
        loss = -delta.clip(upper=0.0)
        avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        return 100 - (100 / (1 + rs))

    @staticmethod
    def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
        prev_close = df["Close"].shift(1)
        tr = pd.concat(
            [
                df["High"] - df["Low"],
                (df["High"] - prev_close).abs(),
                (df["Low"] - prev_close).abs(),
            ],
            axis=1,
        ).max(axis=1)
        return tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    @staticmethod
    def adx(df: pd.DataFrame, period: int = 14):
        high = df["High"]
        low = df["Low"]
        close = df["Close"]

        up = high.diff()
        down = -low.diff()
        plus_dm = np.where((up > down) & (up > 0), up, 0.0)
        minus_dm = np.where((down > up) & (down > 0), down, 0.0)

        prev_close = close.shift(1)
        tr = pd.concat(
            [
                high - low,
                (high - prev_close).abs(),
                (low - prev_close).abs(),
            ],
            axis=1,
        ).max(axis=1)

        atr = pd.Series(tr, index=df.index).ewm(
            alpha=1 / period, min_periods=period, adjust=False
        ).mean()
        plus_di = 100 * pd.Series(plus_dm, index=df.index).ewm(
            alpha=1 / period, min_periods=period, adjust=False
        ).mean() / atr.replace(0, np.nan)
        minus_di = 100 * pd.Series(minus_dm, index=df.index).ewm(
            alpha=1 / period, min_periods=period, adjust=False
        ).mean() / atr.replace(0, np.nan)

        dx = (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan) * 100
        adx = dx.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
        return adx, plus_di, minus_di

    @staticmethod
    def macd(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9):
        ema_fast = TechnicalIndicators.ema(df, fast)
        ema_slow = TechnicalIndicators.ema(df, slow)
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        hist = macd_line - signal_line
        return macd_line, signal_line, hist

    @staticmethod
    def bollinger(df: pd.DataFrame, period: int = 20, num_std: float = 2.0):
        mid = TechnicalIndicators.sma(df, period)
        std = df["Close"].rolling(period).std()
        upper = mid + num_std * std
        lower = mid - num_std * std
        return upper, mid, lower

    @staticmethod
    def stochastic(df: pd.DataFrame, k_period: int = 14, d_period: int = 3):
        lowest = df["Low"].rolling(k_period).min()
        highest = df["High"].rolling(k_period).max()
        k = 100 * (df["Close"] - lowest) / (highest - lowest).replace(0, np.nan)
        d = k.rolling(d_period).mean()
        return k, d

    @staticmethod
    def cci(df: pd.DataFrame, period: int = 20) -> pd.Series:
        tp = (df["High"] + df["Low"] + df["Close"]) / 3.0
        sma = tp.rolling(period).mean()
        mad = tp.rolling(period).apply(lambda x: np.mean(np.abs(x - x.mean())), raw=True)
        return (tp - sma) / (0.015 * mad.replace(0, np.nan))

    @staticmethod
    def atr_zscore(atr: pd.Series, lookback: int = 50) -> pd.Series:
        mean = atr.rolling(lookback).mean()
        std = atr.rolling(lookback).std()
        return (atr - mean) / std.replace(0, np.nan)

    @staticmethod
    def volatility_regime(atr_z: pd.Series, high_thr: float = 1.0, low_thr: float = -1.0) -> pd.Series:
        regime = pd.Series("normal", index=atr_z.index, dtype=object)
        regime = regime.mask(atr_z >= high_thr, "high")
        regime = regime.mask(atr_z <= low_thr, "low")
        return regime
