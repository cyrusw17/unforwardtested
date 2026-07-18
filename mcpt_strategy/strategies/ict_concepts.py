"""
ICT (Inner Circle Trader) Concepts Implementation
Institutional order flow and smart money concepts
"""
import pandas as pd
import numpy as np
from typing import Tuple, List


def identify_order_blocks(ohlc: pd.DataFrame, lookback: int = 20) -> Tuple[pd.Series, pd.Series]:
    """
    Identify bullish and bearish order blocks
    
    Order Block: Last bearish candle before bullish move (bullish OB)
                 Last bullish candle before bearish move (bearish OB)
    
    Args:
        ohlc: DataFrame with OHLC data
        lookback: Lookback period for structure breaks
        
    Returns:
        Tuple of (bullish_ob, bearish_ob) series with price levels
    """
    close = ohlc['close']
    high = ohlc['high']
    low = ohlc['low']
    open_price = ohlc['open']
    
    # Identify swing highs and lows
    swing_high = high.rolling(lookback, center=True).max() == high
    swing_low = low.rolling(lookback, center=True).min() == low
    
    bullish_ob = pd.Series(np.nan, index=ohlc.index)
    bearish_ob = pd.Series(np.nan, index=ohlc.index)
    
    # Find bearish candles before swing lows (bullish OB)
    is_bearish = close < open_price
    for i in range(lookback, len(ohlc) - lookback):
        if swing_low.iloc[i]:
            # Look back for last bearish candle
            for j in range(i-1, max(0, i-lookback), -1):
                if is_bearish.iloc[j]:
                    bullish_ob.iloc[i] = low.iloc[j]
                    break
    
    # Find bullish candles before swing highs (bearish OB)
    is_bullish = close > open_price
    for i in range(lookback, len(ohlc) - lookback):
        if swing_high.iloc[i]:
            # Look back for last bullish candle
            for j in range(i-1, max(0, i-lookback), -1):
                if is_bullish.iloc[j]:
                    bearish_ob.iloc[i] = high.iloc[j]
                    break
    
    return bullish_ob.ffill(), bearish_ob.ffill()


def identify_fair_value_gaps(ohlc: pd.DataFrame, min_gap_atr_mult: float = 0.5) -> Tuple[pd.Series, pd.Series]:
    """
    Identify Fair Value Gaps (FVG) / Imbalances
    
    FVG: Gap in price where no trading occurred
    Bullish FVG: Current low > Previous candle's high
    Bearish FVG: Current high < Previous candle's low
    
    Args:
        ohlc: DataFrame with OHLC data
        min_gap_atr_mult: Minimum gap size as ATR multiplier
        
    Returns:
        Tuple of (bullish_fvg, bearish_fvg) boolean series
    """
    high = ohlc['high']
    low = ohlc['low']
    
    # Calculate ATR for gap filtering
    tr1 = high - low
    tr2 = abs(high - ohlc['close'].shift())
    tr3 = abs(low - ohlc['close'].shift())
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(14).mean()
    
    # Bullish FVG: current low > 2 bars ago high
    bullish_fvg = (low > high.shift(2)) & ((low - high.shift(2)) > min_gap_atr_mult * atr)
    
    # Bearish FVG: current high < 2 bars ago low
    bearish_fvg = (high < low.shift(2)) & ((low.shift(2) - high) > min_gap_atr_mult * atr)
    
    return bullish_fvg, bearish_fvg


def identify_liquidity_sweeps(ohlc: pd.DataFrame, lookback: int = 20, sweep_threshold: float = 0.0005) -> Tuple[pd.Series, pd.Series]:
    """
    Identify liquidity sweeps (stop hunts)
    
    Sweep: Price breaks recent high/low then reverses quickly
    This captures stops above/below obvious levels
    
    Args:
        ohlc: DataFrame with OHLC data
        lookback: Lookback for recent highs/lows
        sweep_threshold: Minimum sweep distance (as fraction)
        
    Returns:
        Tuple of (buy_sweep, sell_sweep) boolean series
    """
    high = ohlc['high']
    low = ohlc['low']
    close = ohlc['close']
    
    # Recent highs and lows
    recent_high = high.rolling(lookback).max().shift(1)
    recent_low = low.rolling(lookback).min().shift(1)
    
    # Sweep occurs when price breaks level then closes back inside range
    buy_sweep = (
        (low < recent_low * (1 - sweep_threshold)) &  # Sweep below recent low
        (close > recent_low)  # But close back above
    )
    
    sell_sweep = (
        (high > recent_high * (1 + sweep_threshold)) &  # Sweep above recent high
        (close < recent_high)  # But close back below
    )
    
    return buy_sweep, sell_sweep


def identify_market_structure_shift(ohlc: pd.DataFrame, lookback: int = 10) -> pd.Series:
    """
    Identify market structure shifts (change of character)
    
    Structure shift: Break of recent swing high (bullish) or low (bearish)
    
    Args:
        ohlc: DataFrame with OHLC data
        lookback: Lookback for swing identification
        
    Returns:
        Series with 1 (bullish shift), -1 (bearish shift), 0 (no shift)
    """
    high = ohlc['high']
    low = ohlc['low']
    close = ohlc['close']
    
    # Swing highs and lows
    swing_high = high.rolling(lookback, center=True).max()
    swing_low = low.rolling(lookback, center=True).min()
    
    # Structure shift when price breaks swing level
    bullish_shift = close > swing_high.shift(1)
    bearish_shift = close < swing_low.shift(1)
    
    structure = pd.Series(0, index=ohlc.index)
    structure[bullish_shift] = 1
    structure[bearish_shift] = -1
    
    return structure


def calculate_premium_discount(ohlc: pd.DataFrame, lookback: int = 50) -> pd.Series:
    """
    Calculate if price is in premium (above 50% of range) or discount (below 50%)
    
    ICT concept: Buy in discount, sell in premium
    
    Args:
        ohlc: DataFrame with OHLC data
        lookback: Lookback for range calculation
        
    Returns:
        Series with 1 (premium), -1 (discount), 0 (equilibrium)
    """
    close = ohlc['close']
    high = ohlc['high']
    low = ohlc['low']
    
    range_high = high.rolling(lookback).max()
    range_low = low.rolling(lookback).min()
    range_mid = (range_high + range_low) / 2
    
    premium_discount = pd.Series(0, index=ohlc.index)
    premium_discount[close > range_mid * 1.02] = 1  # Premium
    premium_discount[close < range_mid * 0.98] = -1  # Discount
    
    return premium_discount


def ict_order_block_strategy(
    ohlc: pd.DataFrame,
    ob_lookback: int = 20,
    structure_lookback: int = 10,
    use_fvg: bool = True,
    use_sweep: bool = True
) -> pd.Series:
    """
    ICT Order Block Strategy
    
    Entry Logic:
    1. Identify order blocks
    2. Wait for price to return to order block
    3. Confirm with structure shift
    4. Optional: Confirm with FVG or liquidity sweep
    
    Args:
        ohlc: DataFrame with OHLC data
        ob_lookback: Lookback for order block identification
        structure_lookback: Lookback for structure shifts
        use_fvg: Whether to use FVG confirmation
        use_sweep: Whether to use liquidity sweep confirmation
        
    Returns:
        Series with signals: 1 (long), -1 (short), 0 (neutral)
    """
    close = ohlc['close']
    low = ohlc['low']
    high = ohlc['high']
    
    # Get ICT components
    bullish_ob, bearish_ob = identify_order_blocks(ohlc, ob_lookback)
    structure = identify_market_structure_shift(ohlc, structure_lookback)
    
    signal = pd.Series(0, index=ohlc.index, dtype=float)
    
    # Long setup: Price at bullish OB + bullish structure shift
    at_bullish_ob = (low <= bullish_ob * 1.01) & (low >= bullish_ob * 0.99)
    long_condition = at_bullish_ob & (structure == 1)
    
    # Short setup: Price at bearish OB + bearish structure shift
    at_bearish_ob = (high >= bearish_ob * 0.99) & (high <= bearish_ob * 1.01)
    short_condition = at_bearish_ob & (structure == -1)
    
    # Optional confirmations
    if use_fvg:
        bullish_fvg, bearish_fvg = identify_fair_value_gaps(ohlc)
        long_condition = long_condition & bullish_fvg.shift(1)
        short_condition = short_condition & bearish_fvg.shift(1)
    
    if use_sweep:
        buy_sweep, sell_sweep = identify_liquidity_sweeps(ohlc, ob_lookback)
        long_condition = long_condition & buy_sweep
        short_condition = short_condition & sell_sweep
    
    signal[long_condition] = 1
    signal[short_condition] = -1
    
    # Forward fill to maintain positions
    signal = signal.replace(0, np.nan).ffill().fillna(0)
    
    return signal


def ict_fvg_strategy(
    ohlc: pd.DataFrame,
    min_gap_mult: float = 0.5,
    structure_lookback: int = 10,
    use_premium_discount: bool = True
) -> pd.Series:
    """
    ICT Fair Value Gap Strategy
    
    Entry Logic:
    1. Identify FVG
    2. Wait for price to fill FVG partially
    3. Enter in direction of FVG
    4. Optional: Only trade from premium/discount zones
    
    Args:
        ohlc: DataFrame with OHLC data
        min_gap_mult: Minimum gap size as ATR multiplier
        structure_lookback: Lookback for structure
        use_premium_discount: Whether to use premium/discount filter
        
    Returns:
        Series with signals: 1 (long), -1 (short), 0 (neutral)
    """
    bullish_fvg, bearish_fvg = identify_fair_value_gaps(ohlc, min_gap_mult)
    structure = identify_market_structure_shift(ohlc, structure_lookback)
    
    signal = pd.Series(0, index=ohlc.index, dtype=float)
    
    # Long: Bullish FVG + bullish structure
    long_condition = bullish_fvg & (structure.shift(1) >= 0)
    
    # Short: Bearish FVG + bearish structure
    short_condition = bearish_fvg & (structure.shift(1) <= 0)
    
    if use_premium_discount:
        pd_zone = calculate_premium_discount(ohlc)
        long_condition = long_condition & (pd_zone == -1)  # Buy in discount
        short_condition = short_condition & (pd_zone == 1)  # Sell in premium
    
    signal[long_condition] = 1
    signal[short_condition] = -1
    
    signal = signal.replace(0, np.nan).ffill().fillna(0)
    
    return signal


def ict_liquidity_sweep_strategy(
    ohlc: pd.DataFrame,
    lookback: int = 20,
    sweep_threshold: float = 0.0005,
    confirm_structure: bool = True
) -> pd.Series:
    """
    ICT Liquidity Sweep Strategy
    
    Entry Logic:
    1. Identify liquidity sweep (stop hunt)
    2. Enter in reversal direction
    3. Optional: Confirm with structure shift
    
    Args:
        ohlc: DataFrame with OHLC data
        lookback: Lookback for sweep identification
        sweep_threshold: Minimum sweep distance
        confirm_structure: Whether to confirm with structure shift
        
    Returns:
        Series with signals: 1 (long), -1 (short), 0 (neutral)
    """
    buy_sweep, sell_sweep = identify_liquidity_sweeps(ohlc, lookback, sweep_threshold)
    
    signal = pd.Series(0, index=ohlc.index, dtype=float)
    
    if confirm_structure:
        structure = identify_market_structure_shift(ohlc, lookback // 2)
        # Buy after downside sweep + bullish structure
        signal[buy_sweep & (structure == 1)] = 1
        # Sell after upside sweep + bearish structure
        signal[sell_sweep & (structure == -1)] = -1
    else:
        signal[buy_sweep] = 1
        signal[sell_sweep] = -1
    
    signal = signal.replace(0, np.nan).ffill().fillna(0)
    
    return signal
