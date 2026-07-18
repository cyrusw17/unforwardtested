"""
Hybrid Momentum Strategy
Combines trend-following, volatility filtering, and mean-reversion elements
"""
import pandas as pd
import numpy as np


def calculate_atr(ohlc: pd.DataFrame, period: int = 14) -> pd.Series:
    """Calculate Average True Range"""
    high = ohlc['high']
    low = ohlc['low']
    close = ohlc['close']
    
    tr1 = high - low
    tr2 = abs(high - close.shift())
    tr3 = abs(low - close.shift())
    
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(period).mean()
    
    return atr


def calculate_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Calculate Relative Strength Index"""
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    
    return rsi


def hybrid_momentum_signal(
    ohlc: pd.DataFrame,
    trend_lookback: int = 50,
    volatility_period: int = 20,
    rsi_period: int = 14,
    vol_multiplier: float = 1.5
) -> pd.Series:
    """
    Generate trading signals using hybrid momentum approach
    
    Strategy logic:
    1. Trend direction: Price vs. moving average
    2. Volatility filter: Only trade when volatility is elevated
    3. RSI filter: Avoid extreme overbought/oversold
    4. Breakout confirmation: Price breaks recent high/low
    
    Args:
        ohlc: DataFrame with OHLC data
        trend_lookback: Lookback for trend determination
        volatility_period: Period for volatility calculation
        rsi_period: Period for RSI calculation
        vol_multiplier: Multiplier for volatility threshold
        
    Returns:
        Series with signals: 1 (long), -1 (short), 0 (neutral)
    """
    close = ohlc['close']
    high = ohlc['high']
    low = ohlc['low']
    
    ma = close.rolling(trend_lookback).mean()
    
    upper_band = close.rolling(trend_lookback - 1).max().shift(1)
    lower_band = close.rolling(trend_lookback - 1).min().shift(1)
    
    atr = calculate_atr(ohlc, volatility_period)
    vol_threshold = atr.rolling(volatility_period * 2).mean() * vol_multiplier
    high_vol = atr > vol_threshold
    
    rsi = calculate_rsi(close, rsi_period)
    rsi_long_ok = (rsi > 30) & (rsi < 70)
    rsi_short_ok = (rsi < 70) & (rsi > 30)
    
    signal = pd.Series(0, index=ohlc.index, dtype=float)
    
    long_condition = (
        (close > upper_band) &
        (close > ma) &
        high_vol &
        rsi_long_ok
    )
    
    short_condition = (
        (close < lower_band) &
        (close < ma) &
        high_vol &
        rsi_short_ok
    )
    
    signal.loc[long_condition] = 1
    signal.loc[short_condition] = -1
    
    signal = signal.ffill().fillna(0)
    
    return signal


def optimize_hybrid_momentum(ohlc: pd.DataFrame) -> tuple:
    """
    Optimize hybrid momentum strategy parameters
    
    Tests various combinations of parameters and returns the best
    configuration based on profit factor.
    
    Args:
        ohlc: DataFrame with OHLC data
        
    Returns:
        Tuple of (best_params dict, best_profit_factor)
    """
    r = np.log(ohlc['close']).diff().shift(-1)
    
    best_pf = 0
    best_params = {}
    
    trend_lookbacks = [30, 40, 50, 60, 70, 80, 100]
    volatility_periods = [14, 20, 28]
    rsi_periods = [10, 14, 21]
    vol_multipliers = [1.0, 1.2, 1.5, 1.8, 2.0]
    
    for trend_lb in trend_lookbacks:
        for vol_period in volatility_periods:
            for rsi_period in rsi_periods:
                for vol_mult in vol_multipliers:
                    try:
                        signal = hybrid_momentum_signal(
                            ohlc,
                            trend_lookback=trend_lb,
                            volatility_period=vol_period,
                            rsi_period=rsi_period,
                            vol_multiplier=vol_mult
                        )
                        
                        sig_rets = signal * r
                        
                        if sig_rets[sig_rets < 0].sum() == 0:
                            continue
                        
                        pf = sig_rets[sig_rets > 0].sum() / sig_rets[sig_rets < 0].abs().sum()
                        
                        if pf > best_pf:
                            best_pf = pf
                            best_params = {
                                'trend_lookback': trend_lb,
                                'volatility_period': vol_period,
                                'rsi_period': rsi_period,
                                'vol_multiplier': vol_mult
                            }
                    except:
                        continue
    
    return best_params, best_pf


def walkforward_hybrid_momentum(
    ohlc: pd.DataFrame,
    train_lookback: int = 24 * 365 * 4,
    train_step: int = 24 * 30
) -> pd.Series:
    """
    Walk-forward optimization of hybrid momentum strategy
    
    Args:
        ohlc: DataFrame with OHLC data
        train_lookback: Number of bars to use for training
        train_step: Number of bars between reoptimizations
        
    Returns:
        Series with walk-forward signals
    """
    n = len(ohlc)
    wf_signal = pd.Series(np.nan, index=ohlc.index)
    
    next_train = train_lookback
    current_params = None
    tmp_signal = None
    
    for i in range(next_train, n):
        if i == next_train:
            print(f"Optimizing at bar {i}/{n} ({i/n*100:.1f}%)", end='\r')
            
            train_data = ohlc.iloc[i-train_lookback:i]
            best_params, _ = optimize_hybrid_momentum(train_data)
            current_params = best_params
            
            tmp_signal = hybrid_momentum_signal(ohlc, **current_params)
            
            next_train += train_step
        
        wf_signal.iloc[i] = tmp_signal.iloc[i]
    
    print()
    return wf_signal


if __name__ == '__main__':
    df = pd.read_parquet('../data/BTCUSDT_1h.parquet')
    train = df[(df.index.year >= 2020) & (df.index.year < 2022)]
    
    print("Optimizing strategy...")
    params, pf = optimize_hybrid_momentum(train)
    print(f"Best parameters: {params}")
    print(f"Best profit factor: {pf:.4f}")
    
    signal = hybrid_momentum_signal(train, **params)
    print(f"Signal stats - Long: {(signal == 1).sum()}, Short: {(signal == -1).sum()}, Neutral: {(signal == 0).sum()}")
