"""
Donchian Channel Breakout Strategy
Based on the strategy from neurotrader888's video
"""
import pandas as pd
import numpy as np


def donchian_breakout(ohlc: pd.DataFrame, lookback: int) -> pd.Series:
    """
    Generate Donchian breakout signals
    
    Args:
        ohlc: DataFrame with OHLC data
        lookback: Lookback period for channel
        
    Returns:
        Series with signals: 1 (long), -1 (short)
    """
    close = ohlc['close']
    
    upper = close.rolling(lookback - 1).max().shift(1)
    lower = close.rolling(lookback - 1).min().shift(1)
    
    signal = pd.Series(np.nan, index=ohlc.index, dtype=float)
    signal.loc[close > upper] = 1
    signal.loc[close < lower] = -1
    signal = signal.ffill().fillna(0)
    
    return signal


def optimize_donchian(ohlc: pd.DataFrame) -> tuple:
    """
    Optimize Donchian breakout lookback parameter
    
    Args:
        ohlc: DataFrame with OHLC data
        
    Returns:
        Tuple of (best_lookback, best_profit_factor)
    """
    r = np.log(ohlc['close']).diff().shift(-1)
    
    best_pf = 0
    best_lookback = -1
    
    for lookback in range(12, 169):
        try:
            signal = donchian_breakout(ohlc, lookback)
            sig_rets = signal * r
            sig_rets = sig_rets.dropna()
            
            if len(sig_rets[sig_rets < 0]) == 0:
                continue
            
            pf = sig_rets[sig_rets > 0].sum() / sig_rets[sig_rets < 0].abs().sum()
            
            if pf > best_pf:
                best_pf = pf
                best_lookback = lookback
        except:
            continue
    
    if best_lookback == -1:
        best_lookback = 50
        best_pf = 1.0
    
    return {'lookback': best_lookback}, best_pf


def walkforward_donchian(
    ohlc: pd.DataFrame,
    train_lookback: int = 24 * 365 * 4,
    train_step: int = 24 * 30
) -> pd.Series:
    """
    Walk-forward optimization of Donchian strategy
    
    Args:
        ohlc: DataFrame with OHLC data
        train_lookback: Number of bars for training
        train_step: Number of bars between reoptimizations
        
    Returns:
        Series with walk-forward signals
    """
    n = len(ohlc)
    wf_signal = pd.Series(np.nan, index=ohlc.index)
    
    next_train = train_lookback
    current_lookback = None
    tmp_signal = None
    
    for i in range(train_lookback, n):
        if i == next_train:
            print(f"Optimizing at bar {i}/{n} ({i/n*100:.1f}%)", end='\r')
            
            train_data = ohlc.iloc[i-train_lookback:i]
            best_params, _ = optimize_donchian(train_data)
            current_lookback = best_params['lookback']
            
            tmp_signal = donchian_breakout(ohlc, current_lookback)
            
            next_train += train_step
        
        if tmp_signal is not None:
            wf_signal.iloc[i] = tmp_signal.iloc[i]
    
    print()
    return wf_signal
