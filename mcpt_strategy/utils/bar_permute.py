"""
Bar Permutation Module
Generates permutations of OHLC price data while preserving statistical properties
"""
import numpy as np
import pandas as pd
from typing import List, Union


def get_permutation(
    ohlc: Union[pd.DataFrame, List[pd.DataFrame]], 
    start_index: int = 0, 
    seed=None
) -> Union[pd.DataFrame, List[pd.DataFrame]]:
    """
    Generate a permutation of OHLC data by shuffling log returns.
    
    This creates synthetic price paths that have the same statistical properties
    (mean, std, skew, kurtosis) as the original data but with no temporal structure.
    
    Args:
        ohlc: DataFrame or list of DataFrames with columns ['open', 'high', 'low', 'close']
        start_index: Index from which to start permutation (earlier data is preserved)
        seed: Random seed for reproducibility
        
    Returns:
        Permuted OHLC data in the same format as input
    """
    assert start_index >= 0
    
    if seed is not None:
        np.random.seed(seed)
    
    if isinstance(ohlc, list):
        time_index = ohlc[0].index
        for mkt in ohlc:
            assert np.all(time_index == mkt.index), "Indexes do not match"
        n_markets = len(ohlc)
    else:
        n_markets = 1
        time_index = ohlc.index
        ohlc = [ohlc]
    
    n_bars = len(ohlc[0])
    perm_index = start_index + 1
    perm_n = n_bars - perm_index
    
    start_bar = np.empty((n_markets, 4))
    relative_open = np.empty((n_markets, perm_n))
    relative_high = np.empty((n_markets, perm_n))
    relative_low = np.empty((n_markets, perm_n))
    relative_close = np.empty((n_markets, perm_n))
    
    for mkt_i, reg_bars in enumerate(ohlc):
        log_bars = np.log(reg_bars[['open', 'high', 'low', 'close']])
        
        start_bar[mkt_i] = log_bars.iloc[start_index].to_numpy()
        
        r_o = (log_bars['open'] - log_bars['close'].shift()).to_numpy()
        r_h = (log_bars['high'] - log_bars['open']).to_numpy()
        r_l = (log_bars['low'] - log_bars['open']).to_numpy()
        r_c = (log_bars['close'] - log_bars['open']).to_numpy()
        
        relative_open[mkt_i] = r_o[perm_index:]
        relative_high[mkt_i] = r_h[perm_index:]
        relative_low[mkt_i] = r_l[perm_index:]
        relative_close[mkt_i] = r_c[perm_index:]
    
    idx = np.arange(perm_n)
    
    perm1 = np.random.permutation(idx)
    relative_high = relative_high[:, perm1]
    relative_low = relative_low[:, perm1]
    relative_close = relative_close[:, perm1]
    
    perm2 = np.random.permutation(idx)
    relative_open = relative_open[:, perm2]
    
    perm_ohlc = []
    for mkt_i, reg_bars in enumerate(ohlc):
        perm_bars = np.zeros((n_bars, 4))
        
        log_bars = np.log(reg_bars[['open', 'high', 'low', 'close']]).to_numpy().copy()
        perm_bars[:start_index] = log_bars[:start_index]
        
        perm_bars[start_index] = start_bar[mkt_i]
        
        for i in range(perm_index, n_bars):
            k = i - perm_index
            perm_bars[i, 0] = perm_bars[i - 1, 3] + relative_open[mkt_i][k]
            perm_bars[i, 1] = perm_bars[i, 0] + relative_high[mkt_i][k]
            perm_bars[i, 2] = perm_bars[i, 0] + relative_low[mkt_i][k]
            perm_bars[i, 3] = perm_bars[i, 0] + relative_close[mkt_i][k]
        
        perm_bars = np.exp(perm_bars)
        perm_bars = pd.DataFrame(
            perm_bars, 
            index=time_index, 
            columns=['open', 'high', 'low', 'close']
        )
        
        perm_ohlc.append(perm_bars)
    
    if n_markets > 1:
        return perm_ohlc
    else:
        return perm_ohlc[0]
