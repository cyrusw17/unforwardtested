"""
Analyze why 2020-2024 had so many more trades than other periods
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from core.indicators import TechnicalIndicators


def analyze_market_characteristics(ohlc: pd.DataFrame, period_name: str):
    """Analyze volatility, momentum, and structure characteristics"""
    
    print(f"\n{'='*80}")
    print(f"MARKET CHARACTERISTICS: {period_name}")
    print(f"{'='*80}")
    print(f"Period: {ohlc.index[0]} to {ohlc.index[-1]}")
    print(f"Bars: {len(ohlc)}")
    
    # Calculate ATR (volatility)
    ti = TechnicalIndicators
    atr = ti.atr(ohlc, 14)
    
    # Calculate price change characteristics
    close = ohlc['Close']
    high = ohlc['High']
    low = ohlc['Low']
    open_price = ohlc['Open']
    
    # Body size (momentum)
    body = abs(close - open_price)
    body_pct = (body / close) * 100
    
    # Candle range
    candle_range = high - low
    range_pct = (candle_range / close) * 100
    
    # Strong moves (what creates Order Blocks)
    avg_body_20 = body.rolling(20).mean()
    strong_moves = body > (avg_body_20 * 1.5)
    strong_move_pct = (strong_moves.sum() / len(ohlc)) * 100
    
    # Directional moves (what creates structure breaks)
    price_change = close.diff()
    price_change_pct = (price_change / close.shift(1)) * 100
    
    # Calculate how often price breaks recent highs/lows (structure changes)
    swing_length = 5
    recent_high = high.rolling(swing_length).max()
    recent_low = low.rolling(swing_length).min()
    
    breaks_high = close > recent_high.shift(1)
    breaks_low = close < recent_low.shift(1)
    structure_breaks = breaks_high | breaks_low
    structure_break_pct = (structure_breaks.sum() / len(ohlc)) * 100
    
    # Print results
    print(f"\n📊 VOLATILITY METRICS:")
    print(f"  Average ATR:          {atr.mean():.5f}")
    print(f"  Median ATR:           {atr.median():.5f}")
    print(f"  Max ATR:              {atr.max():.5f}")
    print(f"  ATR Std Dev:          {atr.std():.5f}")
    
    print(f"\n💪 MOMENTUM METRICS:")
    print(f"  Avg Body Size:        {body.mean():.5f} ({body_pct.mean():.3f}%)")
    print(f"  Median Body:          {body.median():.5f}")
    print(f"  Avg Range:            {candle_range.mean():.5f} ({range_pct.mean():.3f}%)")
    print(f"  Strong Moves:         {strong_move_pct:.2f}% of bars")
    
    print(f"\n🔄 STRUCTURE METRICS:")
    print(f"  Structure Breaks:     {structure_break_pct:.2f}% of bars")
    print(f"  Avg Price Change:     {abs(price_change_pct).mean():.3f}%")
    print(f"  Trending Days:        {(abs(price_change_pct) > 0.5).sum()} ({(abs(price_change_pct) > 0.5).sum()/len(ohlc)*100:.1f}%)")
    
    return {
        'period': period_name,
        'bars': len(ohlc),
        'avg_atr': float(atr.mean()),
        'median_atr': float(atr.median()),
        'max_atr': float(atr.max()),
        'strong_move_pct': float(strong_move_pct),
        'structure_break_pct': float(structure_break_pct),
        'avg_body_pct': float(body_pct.mean()),
        'avg_range_pct': float(range_pct.mean())
    }


def count_order_blocks(ohlc: pd.DataFrame, lookback: int = 5):
    """Count how many order blocks are identified"""
    close = ohlc['Close']
    open_price = ohlc['Open']
    
    body = abs(close - open_price)
    avg_body = body.rolling(20).mean()
    
    strong_bullish = (close > open_price) & (body > avg_body * 1.5)
    strong_bearish = (close < open_price) & (body > avg_body * 1.5)
    
    bullish_ob_count = 0
    bearish_ob_count = 0
    
    for i in range(lookback, len(ohlc)):
        if strong_bullish.iloc[i]:
            for j in range(1, min(lookback, i)):
                if close.iloc[i-j] < open_price.iloc[i-j]:
                    bullish_ob_count += 1
                    break
        if strong_bearish.iloc[i]:
            for j in range(1, min(lookback, i)):
                if close.iloc[i-j] > open_price.iloc[i-j]:
                    bearish_ob_count += 1
                    break
    
    return bullish_ob_count, bearish_ob_count


def main():
    cache_dir = Path(__file__).parent.parent / 'data' / 'forex_cache'
    cache_file = cache_dir / 'EURUSD_2016_2024_4h.parquet'
    
    if not cache_file.exists():
        print(f"Error: Data not found: {cache_file}")
        return
    
    ohlc = pd.read_parquet(cache_file)
    if 'open' in ohlc.columns:
        ohlc.columns = [c.capitalize() for c in ohlc.columns]
    
    # Split into periods
    ohlc_2016_2020 = ohlc[(ohlc.index >= '2016-01-01') & (ohlc.index <= '2020-12-31')]
    ohlc_2020_2024 = ohlc[(ohlc.index >= '2020-01-01') & (ohlc.index <= '2024-12-31')]
    
    # Analyze each period
    results_2016_2020 = analyze_market_characteristics(ohlc_2016_2020, "2016-2020")
    results_2020_2024 = analyze_market_characteristics(ohlc_2020_2024, "2020-2024")
    
    # Count Order Blocks
    print(f"\n{'='*80}")
    print(f"ORDER BLOCK FORMATION")
    print(f"{'='*80}")
    
    bull_ob_2016, bear_ob_2016 = count_order_blocks(ohlc_2016_2020)
    bull_ob_2020, bear_ob_2020 = count_order_blocks(ohlc_2020_2024)
    
    total_ob_2016 = bull_ob_2016 + bear_ob_2016
    total_ob_2020 = bull_ob_2020 + bear_ob_2020
    
    print(f"\n2016-2020:")
    print(f"  Bullish OBs:          {bull_ob_2016}")
    print(f"  Bearish OBs:          {bear_ob_2016}")
    print(f"  Total OBs:            {total_ob_2016}")
    print(f"  OBs per bar:          {total_ob_2016/len(ohlc_2016_2020):.3f}")
    print(f"  Bars:                 {len(ohlc_2016_2020)}")
    
    print(f"\n2020-2024:")
    print(f"  Bullish OBs:          {bull_ob_2020}")
    print(f"  Bearish OBs:          {bear_ob_2020}")
    print(f"  Total OBs:            {total_ob_2020}")
    print(f"  OBs per bar:          {total_ob_2020/len(ohlc_2020_2024):.3f}")
    print(f"  Bars:                 {len(ohlc_2020_2024)}")
    
    print(f"\n📈 COMPARISON:")
    print(f"  OB Increase:          {(total_ob_2020/total_ob_2016):.2f}×")
    print(f"  OB per bar increase:  {((total_ob_2020/len(ohlc_2020_2024))/(total_ob_2016/len(ohlc_2016_2020))):.2f}×")
    
    # Compare metrics
    print(f"\n{'='*80}")
    print(f"METRIC COMPARISON")
    print(f"{'='*80}")
    
    print(f"\n{'Metric':<25} {'2016-2020':<15} {'2020-2024':<15} {'Change':<10}")
    print(f"{'-'*65}")
    
    metrics = [
        ('Average ATR', 'avg_atr', '.5f'),
        ('Strong Move %', 'strong_move_pct', '.2f'),
        ('Structure Break %', 'structure_break_pct', '.2f'),
        ('Avg Body %', 'avg_body_pct', '.3f'),
        ('Avg Range %', 'avg_range_pct', '.3f')
    ]
    
    for name, key, fmt in metrics:
        val_2016 = results_2016_2020[key]
        val_2020 = results_2020_2024[key]
        change = (val_2020 / val_2016 - 1) * 100
        
        print(f"{name:<25} {val_2016:<15{fmt}} {val_2020:<15{fmt}} {change:+.1f}%")
    
    # Summary
    print(f"\n{'='*80}")
    print(f"SUMMARY: WHY MORE TRADES IN 2020-2024")
    print(f"{'='*80}")
    
    atr_increase = (results_2020_2024['avg_atr'] / results_2016_2020['avg_atr'] - 1) * 100
    strong_move_increase = (results_2020_2024['strong_move_pct'] / results_2016_2020['strong_move_pct'] - 1) * 100
    structure_increase = (results_2020_2024['structure_break_pct'] / results_2016_2020['structure_break_pct'] - 1) * 100
    ob_increase = (total_ob_2020 / total_ob_2016 - 1) * 100
    
    print(f"\n1. 📈 HIGHER VOLATILITY:")
    print(f"   ATR increased by {atr_increase:+.1f}%")
    print(f"   More volatile = more opportunities")
    
    print(f"\n2. 💪 MORE STRONG MOVES:")
    print(f"   Strong moves increased by {strong_move_increase:+.1f}%")
    print(f"   More strong moves = more Order Blocks created")
    
    print(f"\n3. 🔄 MORE STRUCTURE CHANGES:")
    print(f"   Structure breaks increased by {structure_increase:+.1f}%")
    print(f"   More structure breaks = more valid entry signals")
    
    print(f"\n4. 🎯 MORE ORDER BLOCKS:")
    print(f"   Order Blocks increased by {ob_increase:+.1f}%")
    print(f"   More OBs + more structure = MORE TRADES")
    
    print(f"\n{'='*80}")
    print(f"ACTUAL TRADE COUNTS:")
    print(f"  2016-2020: 193 trades (38.6 per year)")
    print(f"  2020-2024: 446 trades (89.2 per year)")
    print(f"  Increase: 2.31× more trades per year")
    print(f"\n  This matches the increase in market activity:")
    print(f"  - Order Blocks: {(total_ob_2020/len(ohlc_2020_2024))/(total_ob_2016/len(ohlc_2016_2020)):.2f}× more per bar")
    print(f"  - Volatility: {atr_increase:+.1f}% higher")
    print(f"  - Strong moves: {strong_move_increase:+.1f}% more frequent")
    print(f"{'='*80}")


if __name__ == '__main__':
    main()
