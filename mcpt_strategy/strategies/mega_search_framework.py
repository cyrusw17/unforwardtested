"""
Mega Search Framework - Systematic Strategy Optimization
Goal: Find highest-return strategy that still passes MCPT (p < 0.05)

Tests across:
- Multiple pairs (AUD crosses, commodity currencies)
- Multiple parameter combinations (thresholds, lookbacks, weights)
- Multiple confluence additions (RSI, session filters, ATR regime)
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))

import pandas as pd
import numpy as np
from typing import Dict, Tuple, Optional
from tqdm import tqdm
import json
import itertools
import yfinance as yf
import time


DATA_CACHE_DIR = Path(__file__).parent.parent / 'data' / 'daily_cache'
DATA_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def fetch_daily_data(pair: str, start: str = '2018-01-01', end: str = '2026-12-31') -> Optional[pd.DataFrame]:
    """Fetch daily data with caching"""
    cache_file = DATA_CACHE_DIR / f"{pair.replace('=X', '').replace('^', '')}_{start}_{end}.parquet"
    
    if cache_file.exists():
        df = pd.read_parquet(cache_file)
        return df
    
    try:
        df = yf.download(pair, start=start, end=end, progress=False)
        if df is None or len(df) == 0:
            return None
        
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
        df = df[['Open', 'High', 'Low', 'Close', 'Volume']]
        df.to_parquet(cache_file)
        return df
    except Exception as e:
        print(f"  Error fetching {pair}: {e}")
        return None


class ICTIndicatorLib:
    """Library of ICT indicators for scoring strategies"""
    
    @staticmethod
    def order_blocks_with_strength(ohlc: pd.DataFrame, lookback: int = 5, body_mult: float = 1.2,
                                    causal: bool = True) -> Tuple[pd.Series, pd.Series]:
        """
        NOTE (lookahead fix): causal=False (the original behavior) backdates
        a displacement candle's strength onto the historical opposite candle
        that preceded it -- verified empirically to be lookahead bias (see
        mcpt_strategy/LOOKAHEAD_BIAS_FINDING.md). causal=True (new default)
        attributes the strength to the confirming bar itself instead.
        """
        bullish_ob = pd.Series(0.0, index=ohlc.index)
        bearish_ob = pd.Series(0.0, index=ohlc.index)
        
        close = ohlc['Close']
        open_price = ohlc['Open']
        body = abs(close - open_price)
        avg_body = body.rolling(20).mean()
        
        strength = (body / avg_body).fillna(0).clip(0, 3)
        
        strong_bullish = (close > open_price) & (body > avg_body * body_mult)
        strong_bearish = (close < open_price) & (body > avg_body * body_mult)
        
        for i in range(lookback, len(ohlc)):
            if strong_bullish.iloc[i]:
                for j in range(1, min(lookback, i)):
                    if close.iloc[i-j] < open_price.iloc[i-j]:
                        if causal:
                            bullish_ob.iloc[i] = strength.iloc[i]
                        else:
                            bullish_ob.iloc[i-j] = strength.iloc[i]
                        break
            if strong_bearish.iloc[i]:
                for j in range(1, min(lookback, i)):
                    if close.iloc[i-j] > open_price.iloc[i-j]:
                        if causal:
                            bearish_ob.iloc[i] = strength.iloc[i]
                        else:
                            bearish_ob.iloc[i-j] = strength.iloc[i]
                        break
        
        return bullish_ob, bearish_ob
    
    @staticmethod
    def fvg_with_size(ohlc: pd.DataFrame) -> Tuple[pd.Series, pd.Series]:
        high = ohlc['High']
        low = ohlc['Low']
        close = ohlc['Close']
        
        bullish_fvg_size = (low - high.shift(2)).clip(lower=0) / close * 100
        bearish_fvg_size = (low.shift(2) - high).clip(lower=0) / close * 100
        
        return bullish_fvg_size, bearish_fvg_size
    
    @staticmethod
    def liquidity_sweep_strength(ohlc: pd.DataFrame, lookback: int = 10) -> Tuple[pd.Series, pd.Series]:
        high = ohlc['High']
        low = ohlc['Low']
        close = ohlc['Close']
        
        bullish_sweep = pd.Series(0.0, index=ohlc.index)
        bearish_sweep = pd.Series(0.0, index=ohlc.index)
        
        for i in range(lookback, len(ohlc)):
            recent_low = low.iloc[i-lookback:i].min()
            if low.iloc[i] <= recent_low * 1.0001:
                wick_size = (close.iloc[i] - low.iloc[i]) / (high.iloc[i] - low.iloc[i] + 0.0001)
                if wick_size > 0.3:
                    bullish_sweep.iloc[i] = wick_size * 2
            recent_high = high.iloc[i-lookback:i].max()
            if high.iloc[i] >= recent_high * 0.9999:
                wick_size = (high.iloc[i] - close.iloc[i]) / (high.iloc[i] - low.iloc[i] + 0.0001)
                if wick_size > 0.3:
                    bearish_sweep.iloc[i] = wick_size * 2
        
        return bullish_sweep, bearish_sweep
    
    @staticmethod
    def market_structure_score(ohlc: pd.DataFrame, swing_length: int = 5) -> pd.Series:
        high = ohlc['High']
        low = ohlc['Low']
        close = ohlc['Close']
        
        recent_high = high.rolling(swing_length).max()
        recent_low = low.rolling(swing_length).min()
        
        above_high = ((close - recent_high.shift(1)) / recent_high.shift(1) * 100).clip(-5, 5)
        below_low = ((close - recent_low.shift(1)) / recent_low.shift(1) * 100).clip(-5, 5)
        
        structure = pd.Series(0.0, index=ohlc.index)
        structure[close > recent_high.shift(1)] = above_high[close > recent_high.shift(1)]
        structure[close < recent_low.shift(1)] = below_low[close < recent_low.shift(1)]
        
        return structure.ffill().fillna(0)
    
    @staticmethod
    def trend_strength(ohlc: pd.DataFrame, fast: int = 10, slow: int = 30) -> pd.Series:
        fast_ema = ohlc['Close'].ewm(span=fast).mean()
        slow_ema = ohlc['Close'].ewm(span=slow).mean()
        return ((fast_ema - slow_ema) / slow_ema * 100).clip(-5, 5)
    
    @staticmethod
    def rsi(ohlc: pd.DataFrame, period: int = 14) -> pd.Series:
        close = ohlc['Close']
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(period).mean()
        loss = (-delta.clip(upper=0)).rolling(period).mean()
        rs = gain / loss.replace(0, np.nan)
        return (100 - (100 / (1 + rs))).fillna(50)
    
    @staticmethod
    def atr_regime(ohlc: pd.DataFrame, period: int = 14, lookback: int = 100) -> pd.Series:
        """Returns volatility percentile (0-1)"""
        high = ohlc['High']
        low = ohlc['Low']
        close = ohlc['Close']
        tr = pd.DataFrame({
            'hl': high - low,
            'hc': abs(high - close.shift(1)),
            'lc': abs(low - close.shift(1))
        }).max(axis=1)
        atr = tr.rolling(period).mean()
        atr_pct = atr / close
        return atr_pct.rolling(lookback).apply(lambda x: pd.Series(x).rank(pct=True).iloc[-1] if len(x) > 0 else 0.5)


def enhanced_ict_scoring_v2(
    ohlc: pd.DataFrame,
    entry_threshold: float = 3.0,
    ob_lookback: int = 5,
    structure_length: int = 5,
    ob_weight: float = 2.0,
    fvg_weight: float = 1.5,
    sweep_weight: float = 1.5,
    structure_weight: float = 1.0,
    trend_weight: float = 1.0,
    trend_fast: int = 10,
    trend_slow: int = 30,
    use_rsi_filter: bool = False,
    rsi_period: int = 14,
    rsi_oversold: float = 35,
    rsi_overbought: float = 65,
    use_vol_filter: bool = False,
    vol_min: float = 0.2,
    vol_max: float = 0.8,
) -> pd.Series:
    """Enhanced ICT scoring with configurable weights and optional confluence filters"""
    ict = ICTIndicatorLib()
    
    bullish_ob, bearish_ob = ict.order_blocks_with_strength(ohlc, ob_lookback)
    bullish_fvg, bearish_fvg = ict.fvg_with_size(ohlc)
    bullish_sweep, bearish_sweep = ict.liquidity_sweep_strength(ohlc)
    structure = ict.market_structure_score(ohlc, structure_length)
    trend = ict.trend_strength(ohlc, trend_fast, trend_slow)
    
    bullish_score = (
        bullish_ob * ob_weight +
        bullish_fvg * fvg_weight +
        bullish_sweep * sweep_weight +
        structure.clip(lower=0) * structure_weight +
        trend.clip(lower=0) * trend_weight
    )
    
    bearish_score = (
        bearish_ob * ob_weight +
        bearish_fvg * fvg_weight +
        bearish_sweep * sweep_weight +
        abs(structure.clip(upper=0)) * structure_weight +
        abs(trend.clip(upper=0)) * trend_weight
    )
    
    signal = pd.Series(0, index=ohlc.index, dtype=float)
    signal[bullish_score >= entry_threshold] = 1
    signal[bearish_score >= entry_threshold] = -1
    
    both = (bullish_score >= entry_threshold) & (bearish_score >= entry_threshold)
    signal[both & (bullish_score > bearish_score)] = 1
    signal[both & (bearish_score > bullish_score)] = -1
    
    # Optional confluence filters
    if use_rsi_filter:
        rsi = ict.rsi(ohlc, rsi_period)
        # Only take longs when not overbought, shorts when not oversold
        signal[(signal == 1) & (rsi > rsi_overbought)] = 0
        signal[(signal == -1) & (rsi < rsi_oversold)] = 0
    
    if use_vol_filter:
        vol_regime = ict.atr_regime(ohlc)
        in_range = (vol_regime >= vol_min) & (vol_regime <= vol_max)
        signal[~in_range] = 0
    
    return signal.shift(1).fillna(0)


def calculate_metrics(ohlc: pd.DataFrame, signal: pd.Series, bars_per_year: float = 252) -> Optional[Dict]:
    """Calculate metrics"""
    returns = np.log(ohlc['Close']).diff().shift(-1)
    strategy_returns = signal * returns
    strategy_returns = strategy_returns.dropna()
    
    if len(strategy_returns) == 0 or len(strategy_returns[strategy_returns < 0]) == 0:
        return None
    if len(strategy_returns[strategy_returns != 0]) < 10:
        return None
    
    total_return = np.exp(strategy_returns.sum()) - 1
    years = len(ohlc) / bars_per_year
    annual_return = (1 + total_return) ** (1/years) - 1 if years > 0 else 0
    
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
        'calmar_ratio': float(annual_return / abs(max_dd)) if max_dd != 0 else 0
    }


def quick_mcpt_screen(ohlc: pd.DataFrame, strategy_func, params: Dict, n_permutations: int = 30) -> float:
    """Fast MCPT screen with fewer permutations for initial filtering"""
    from mcpt_strategy.utils import get_permutation
    
    signal = strategy_func(ohlc, **params)
    real_metrics = calculate_metrics(ohlc, signal)
    
    if real_metrics is None:
        return 1.0
    
    real_pf = real_metrics['profit_factor']
    perm_better = 1
    
    for i in range(1, n_permutations):
        try:
            ohlc_lower = ohlc.copy()
            ohlc_lower.columns = [c.lower() for c in ohlc_lower.columns]
            perm_data = get_permutation(ohlc_lower, seed=i * 100)
            perm_data.columns = [c.capitalize() for c in perm_data.columns]
            
            perm_signal = strategy_func(perm_data, **params)
            perm_metrics = calculate_metrics(perm_data, perm_signal)
            
            perm_pf = perm_metrics['profit_factor'] if perm_metrics else 1.0
            if perm_pf >= real_pf:
                perm_better += 1
        except:
            perm_better += 1
    
    return perm_better / n_permutations


def full_mcpt(ohlc: pd.DataFrame, strategy_func, params: Dict, n_permutations: int = 200) -> Dict:
    """Full MCPT with more permutations for final validation"""
    from mcpt_strategy.utils import get_permutation
    
    signal = strategy_func(ohlc, **params)
    real_metrics = calculate_metrics(ohlc, signal)
    
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
            perm_metrics = calculate_metrics(perm_data, perm_signal)
            
            perm_pf = perm_metrics['profit_factor'] if perm_metrics else 1.0
            if perm_pf >= real_pf:
                perm_better += 1
            perm_pfs.append(perm_pf)
        except:
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
        'passed': p_value < 0.05
    }


if __name__ == '__main__':
    print("Mega Search Framework loaded. Import functions for use in search scripts.")
