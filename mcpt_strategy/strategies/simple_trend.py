"""
Simple Trend Following Strategy
A more robust, simpler strategy that should pass MCPT tests
Based on moving average crossover with volatility filter
"""
import pandas as pd
import numpy as np


def simple_trend_signal(
    ohlc: pd.DataFrame,
    fast_period: int = 20,
    slow_period: int = 50,
    vol_period: int = 20,
    vol_filter: bool = True
) -> pd.Series:
    """
    Generate signals using simple trend following
    
    Logic:
    1. Long when fast MA > slow MA
    2. Short when fast MA < slow MA
    3. Optional: Only trade when volatility is above median
    
    Args:
        ohlc: DataFrame with OHLC data
        fast_period: Fast moving average period
        slow_period: Slow moving average period
        vol_period: Volatility lookback period
        vol_filter: Whether to apply volatility filter
        
    Returns:
        Series with signals: 1 (long), -1 (short)
    """
    close = ohlc['close']
    
    fast_ma = close.rolling(fast_period).mean()
    slow_ma = close.rolling(slow_period).mean()
    
    signal = pd.Series(0.0, index=ohlc.index)
    signal[fast_ma > slow_ma] = 1
    signal[fast_ma < slow_ma] = -1
    
    if vol_filter:
        returns = close.pct_change()
        volatility = returns.rolling(vol_period).std()
        vol_median = volatility.rolling(vol_period * 5).median()
        
        high_vol = volatility > vol_median
        signal[~high_vol] = 0
    
    signal = signal.ffill().fillna(0)
    
    return signal


def optimize_simple_trend(ohlc: pd.DataFrame) -> tuple:
    """
    Optimize simple trend strategy
    
    Tests reasonable parameter combinations
    
    Args:
        ohlc: DataFrame with OHLC data
        
    Returns:
        Tuple of (best_params dict, best_profit_factor)
    """
    r = np.log(ohlc['close']).diff().shift(-1)
    
    best_pf = 0
    best_params = {}
    
    fast_periods = [10, 15, 20, 25, 30]
    slow_periods = [40, 50, 60, 80, 100]
    vol_periods = [14, 20, 30]
    vol_filters = [True, False]
    
    for fast in fast_periods:
        for slow in slow_periods:
            if fast >= slow:
                continue
            for vol_period in vol_periods:
                for vol_filter in vol_filters:
                    try:
                        signal = simple_trend_signal(
                            ohlc,
                            fast_period=fast,
                            slow_period=slow,
                            vol_period=vol_period,
                            vol_filter=vol_filter
                        )
                        
                        sig_rets = signal * r
                        sig_rets = sig_rets.dropna()
                        
                        if len(sig_rets[sig_rets < 0]) == 0:
                            continue
                        
                        pf = sig_rets[sig_rets > 0].sum() / sig_rets[sig_rets < 0].abs().sum()
                        
                        if pf > best_pf:
                            best_pf = pf
                            best_params = {
                                'fast_period': fast,
                                'slow_period': slow,
                                'vol_period': vol_period,
                                'vol_filter': vol_filter
                            }
                    except:
                        continue
    
    if not best_params:
        best_params = {
            'fast_period': 20,
            'slow_period': 50,
            'vol_period': 20,
            'vol_filter': True
        }
        best_pf = 1.0
    
    return best_params, best_pf


def walkforward_simple_trend(
    ohlc: pd.DataFrame,
    train_lookback: int = 24 * 365 * 4,
    train_step: int = 24 * 30
) -> pd.Series:
    """
    Walk-forward optimization of simple trend strategy
    
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
    current_params = None
    tmp_signal = None
    
    for i in range(train_lookback, n):
        if i == next_train:
            print(f"Optimizing at bar {i}/{n} ({i/n*100:.1f}%)", end='\r')
            
            train_data = ohlc.iloc[i-train_lookback:i]
            best_params, _ = optimize_simple_trend(train_data)
            current_params = best_params
            
            tmp_signal = simple_trend_signal(ohlc, **current_params)
            
            next_train += train_step
        
        if tmp_signal is not None:
            wf_signal.iloc[i] = tmp_signal.iloc[i]
    
    print()
    return wf_signal
