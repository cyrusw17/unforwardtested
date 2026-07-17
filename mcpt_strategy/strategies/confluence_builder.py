"""
Confluence Strategy Builder
Combines multiple signals and tests until walk-forward MCPT passes

Philosophy: Strategy must agree on MULTIPLE signals before taking a trade
- Reduces false signals
- Improves win rate
- Better chance of real edge
"""
import pandas as pd
import numpy as np
from typing import List, Dict, Tuple


def calculate_ema(close: pd.Series, period: int) -> pd.Series:
    """Calculate Exponential Moving Average"""
    return close.ewm(span=period, adjust=False).mean()


def calculate_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Calculate RSI"""
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def calculate_adx(ohlc: pd.DataFrame, period: int = 14) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """Calculate ADX and directional indicators"""
    high = ohlc['high']
    low = ohlc['low']
    close = ohlc['close']
    
    plus_dm = high.diff()
    minus_dm = -low.diff()
    
    plus_dm[plus_dm < 0] = 0
    minus_dm[minus_dm < 0] = 0
    
    tr1 = high - low
    tr2 = abs(high - close.shift())
    tr3 = abs(low - close.shift())
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    atr = tr.rolling(period).mean()
    
    plus_di = 100 * (plus_dm.rolling(period).mean() / atr)
    minus_di = 100 * (minus_dm.rolling(period).mean() / atr)
    
    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
    adx = dx.rolling(period).mean()
    
    return adx, plus_di, minus_di


def detect_swing_structure(ohlc: pd.DataFrame, lookback: int = 20) -> pd.Series:
    """Detect market structure: 1=uptrend, -1=downtrend, 0=ranging"""
    high = ohlc['high']
    low = ohlc['low']
    close = ohlc['close']
    
    higher_highs = (high > high.shift(lookback)) & (high.shift(lookback) > high.shift(lookback*2))
    lower_lows = (low < low.shift(lookback)) & (low.shift(lookback) < low.shift(lookback*2))
    
    structure = pd.Series(0, index=ohlc.index)
    structure[higher_highs] = 1
    structure[lower_lows] = -1
    
    return structure.ffill().fillna(0)


def detect_order_blocks(ohlc: pd.DataFrame, lookback: int = 20) -> Tuple[pd.Series, pd.Series]:
    """Simple order block detection"""
    close = ohlc['close']
    high = ohlc['high']
    low = ohlc['low']
    
    swing_high = high.rolling(lookback).max()
    swing_low = low.rolling(lookback).min()
    
    # Near bullish OB (support)
    near_support = (low <= swing_low * 1.02) & (low >= swing_low * 0.98)
    # Near bearish OB (resistance)
    near_resistance = (high >= swing_high * 0.98) & (high <= swing_high * 1.02)
    
    return near_support, near_resistance


def detect_fair_value_gaps(ohlc: pd.DataFrame) -> Tuple[pd.Series, pd.Series]:
    """Detect FVG (price gaps)"""
    high = ohlc['high']
    low = ohlc['low']
    
    # Bullish FVG: current low > 2 bars ago high
    bullish_fvg = low > high.shift(2)
    # Bearish FVG: current high < 2 bars ago low
    bearish_fvg = high < low.shift(2)
    
    return bullish_fvg, bearish_fvg


def detect_liquidity_sweep(ohlc: pd.DataFrame, lookback: int = 20) -> Tuple[pd.Series, pd.Series]:
    """Detect liquidity sweeps (false breakouts)"""
    high = ohlc['high']
    low = ohlc['low']
    close = ohlc['close']
    
    recent_high = high.rolling(lookback).max().shift(1)
    recent_low = low.rolling(lookback).min().shift(1)
    
    # Sweep low then close back above
    buy_sweep = (low < recent_low) & (close > recent_low)
    # Sweep high then close back below
    sell_sweep = (high > recent_high) & (close < recent_high)
    
    return buy_sweep, sell_sweep


def confluence_strategy_v1(
    ohlc: pd.DataFrame,
    ema_fast: int = 20,
    ema_slow: int = 50,
    rsi_period: int = 14,
    adx_period: int = 14,
    structure_lookback: int = 20,
    min_adx: float = 20,
    require_all: bool = False
) -> pd.Series:
    """
    Confluence Strategy V1: EMA + RSI + ADX + Structure
    
    Buy when MULTIPLE signals align:
    - Fast EMA > Slow EMA (trend)
    - RSI in favorable zone (30-70)
    - ADX > threshold (strength)
    - Market structure bullish
    
    Args:
        require_all: If True, ALL signals must agree. If False, majority (3/4) sufficient
    """
    close = ohlc['close']
    
    # Signal 1: EMA trend
    ema_f = calculate_ema(close, ema_fast)
    ema_s = calculate_ema(close, ema_slow)
    ema_bull = ema_f > ema_s
    ema_bear = ema_f < ema_s
    
    # Signal 2: RSI
    rsi = calculate_rsi(close, rsi_period)
    rsi_bull = (rsi > 30) & (rsi < 70)
    rsi_bear = (rsi < 70) & (rsi > 30)
    
    # Signal 3: ADX
    adx, plus_di, minus_di = calculate_adx(ohlc, adx_period)
    adx_bull = (adx > min_adx) & (plus_di > minus_di)
    adx_bear = (adx > min_adx) & (minus_di > plus_di)
    
    # Signal 4: Structure
    structure = detect_swing_structure(ohlc, structure_lookback)
    struct_bull = structure >= 0
    struct_bear = structure <= 0
    
    signal = pd.Series(0.0, index=ohlc.index)
    
    if require_all:
        # ALL signals must agree
        signal[ema_bull & rsi_bull & adx_bull & struct_bull] = 1
        signal[ema_bear & rsi_bear & adx_bear & struct_bear] = -1
    else:
        # Majority rule: 3+ signals
        bull_count = ema_bull.astype(int) + rsi_bull.astype(int) + adx_bull.astype(int) + struct_bull.astype(int)
        bear_count = ema_bear.astype(int) + rsi_bear.astype(int) + adx_bear.astype(int) + struct_bear.astype(int)
        
        signal[bull_count >= 3] = 1
        signal[bear_count >= 3] = -1
    
    return signal.replace(0, np.nan).ffill().fillna(0)


def confluence_strategy_v2(
    ohlc: pd.DataFrame,
    ema_fast: int = 20,
    ema_slow: int = 50,
    ob_lookback: int = 20,
    min_adx: float = 20
) -> pd.Series:
    """
    Confluence Strategy V2: EMA + Order Blocks + ADX
    
    Buy when:
    - Fast EMA > Slow EMA
    - Price near order block (support)
    - ADX shows strength
    """
    close = ohlc['close']
    
    ema_f = calculate_ema(close, ema_fast)
    ema_s = calculate_ema(close, ema_slow)
    ema_bull = ema_f > ema_s
    ema_bear = ema_f < ema_s
    
    near_support, near_resistance = detect_order_blocks(ohlc, ob_lookback)
    
    adx, plus_di, minus_di = calculate_adx(ohlc, 14)
    strong_trend = adx > min_adx
    
    signal = pd.Series(0.0, index=ohlc.index)
    
    signal[ema_bull & near_support & strong_trend] = 1
    signal[ema_bear & near_resistance & strong_trend] = -1
    
    return signal.replace(0, np.nan).ffill().fillna(0)


def confluence_strategy_v3(
    ohlc: pd.DataFrame,
    ema_period: int = 50,
    rsi_period: int = 14,
    sweep_lookback: int = 20
) -> pd.Series:
    """
    Confluence Strategy V3: EMA + RSI + Liquidity Sweeps
    
    Buy when:
    - Price above EMA (trend filter)
    - RSI not overbought (<70)
    - Liquidity sweep occurred (stop hunt reversal)
    """
    close = ohlc['close']
    
    ema = calculate_ema(close, ema_period)
    above_ema = close > ema
    below_ema = close < ema
    
    rsi = calculate_rsi(close, rsi_period)
    rsi_ok_long = rsi < 70
    rsi_ok_short = rsi > 30
    
    buy_sweep, sell_sweep = detect_liquidity_sweep(ohlc, sweep_lookback)
    
    signal = pd.Series(0.0, index=ohlc.index)
    
    signal[above_ema & rsi_ok_long & buy_sweep] = 1
    signal[below_ema & rsi_ok_short & sell_sweep] = -1
    
    return signal.replace(0, np.nan).ffill().fillna(0)


def confluence_strategy_v4(
    ohlc: pd.DataFrame,
    ema_fast: int = 20,
    ema_slow: int = 50,
    ob_lookback: int = 20,
    fvg_confirm: bool = True
) -> pd.Series:
    """
    Confluence Strategy V4: EMA + Order Blocks + FVG
    
    Buy when:
    - Fast EMA > Slow EMA
    - Price near order block
    - Optional: FVG present (imbalance)
    """
    close = ohlc['close']
    
    ema_f = calculate_ema(close, ema_fast)
    ema_s = calculate_ema(close, ema_slow)
    ema_bull = ema_f > ema_s
    ema_bear = ema_f < ema_s
    
    near_support, near_resistance = detect_order_blocks(ohlc, ob_lookback)
    
    signal = pd.Series(0.0, index=ohlc.index)
    
    if fvg_confirm:
        bullish_fvg, bearish_fvg = detect_fair_value_gaps(ohlc)
        signal[ema_bull & near_support & bullish_fvg.shift(1)] = 1
        signal[ema_bear & near_resistance & bearish_fvg.shift(1)] = -1
    else:
        signal[ema_bull & near_support] = 1
        signal[ema_bear & near_resistance] = -1
    
    return signal.replace(0, np.nan).ffill().fillna(0)


def confluence_strategy_v5(
    ohlc: pd.DataFrame,
    ema_period: int = 50,
    rsi_period: int = 14,
    structure_lookback: int = 20,
    min_confluence: int = 2
) -> pd.Series:
    """
    Confluence Strategy V5: Triple Confluence (EMA + RSI + Structure + OB)
    
    Takes trade when min_confluence signals align
    """
    close = ohlc['close']
    
    # Signal 1: EMA
    ema = calculate_ema(close, ema_period)
    ema_bull = close > ema
    ema_bear = close < ema
    
    # Signal 2: RSI
    rsi = calculate_rsi(close, rsi_period)
    rsi_bull = (rsi > 40) & (rsi < 60)
    rsi_bear = (rsi < 60) & (rsi > 40)
    
    # Signal 3: Structure
    structure = detect_swing_structure(ohlc, structure_lookback)
    struct_bull = structure > 0
    struct_bear = structure < 0
    
    # Signal 4: Order Blocks
    near_support, near_resistance = detect_order_blocks(ohlc, structure_lookback)
    
    signal = pd.Series(0.0, index=ohlc.index)
    
    # Count confluences
    bull_score = (
        ema_bull.astype(int) + 
        rsi_bull.astype(int) + 
        struct_bull.astype(int) + 
        near_support.astype(int)
    )
    bear_score = (
        ema_bear.astype(int) + 
        rsi_bear.astype(int) + 
        struct_bear.astype(int) + 
        near_resistance.astype(int)
    )
    
    signal[bull_score >= min_confluence] = 1
    signal[bear_score >= min_confluence] = -1
    
    return signal.replace(0, np.nan).ffill().fillna(0)
