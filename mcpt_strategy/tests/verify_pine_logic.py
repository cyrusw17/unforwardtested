"""
Verify Pine Script logic matches Python implementation exactly
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))

import pandas as pd
import numpy as np

# Load a small sample of data
cache_dir = Path(__file__).parent.parent / 'data' / 'forex_cache'
cache_file = cache_dir / 'EURUSD_2016_2024_4h.parquet'

df = pd.read_parquet(cache_file)
df.columns = [c.capitalize() for c in df.columns]

# Take just 1000 bars for testing
df_test = df.head(1000).copy()

print("="*80)
print("TESTING ORDER BLOCK LOGIC")
print("="*80)

# Python implementation (from smc_strategy_builder.py)
def identify_order_blocks_python(ohlc, lookback=5):
    bullish_ob = pd.Series(False, index=ohlc.index)
    bearish_ob = pd.Series(False, index=ohlc.index)
    
    close = ohlc['Close']
    open_price = ohlc['Open']
    
    body = abs(close - open_price)
    avg_body = body.rolling(20).mean()
    strong_bullish = (close > open_price) & (body > avg_body * 1.5)
    strong_bearish = (close < open_price) & (body > avg_body * 1.5)
    
    for i in range(lookback, len(ohlc)):
        if strong_bullish.iloc[i]:
            for j in range(1, min(lookback, i)):
                if close.iloc[i-j] < open_price.iloc[i-j]:
                    bullish_ob.iloc[i-j] = True
                    break
        
        if strong_bearish.iloc[i]:
            for j in range(1, min(lookback, i)):
                if close.iloc[i-j] > open_price.iloc[i-j]:
                    bearish_ob.iloc[i-j] = True
                    break
    
    return bullish_ob, bearish_ob

def identify_structure_python(ohlc, swing_length=5):
    high = ohlc['High']
    low = ohlc['Low']
    close = ohlc['Close']
    
    structure = pd.Series(0, index=ohlc.index)
    recent_high = high.rolling(swing_length).max()
    recent_low = low.rolling(swing_length).min()
    
    structure[close > recent_high.shift(1)] = 1
    structure[close < recent_low.shift(1)] = -1
    
    return structure.ffill().fillna(0)

# Run Python logic
print("\n1. Testing Python Order Block Detection...")
bull_ob, bear_ob = identify_order_blocks_python(df_test)
structure = identify_structure_python(df_test)

print(f"   Bullish OBs detected: {bull_ob.sum()}")
print(f"   Bearish OBs detected: {bear_ob.sum()}")
print(f"   Structure bullish bars: {(structure == 1).sum()}")
print(f"   Structure bearish bars: {(structure == -1).sum()}")

# Generate signals
signal = pd.Series(0, index=df_test.index, dtype=float)
signal[bull_ob & (structure >= 0)] = 1
signal[bear_ob & (structure <= 0)] = -1
signal = signal.shift(1).fillna(0)

long_signals = (signal == 1).sum()
short_signals = (signal == -1).sum()

print(f"\n2. Signal Generation:")
print(f"   Long signals: {long_signals}")
print(f"   Short signals: {short_signals}")
print(f"   Total signals: {long_signals + short_signals}")

# Show first few signals
signal_bars = df_test[signal != 0].head(10)
print(f"\n3. First 10 Signal Examples:")
for idx, row in signal_bars.iterrows():
    sig = signal.loc[idx]
    struct = structure.loc[idx]
    is_bull_ob = bull_ob.loc[idx]
    is_bear_ob = bear_ob.loc[idx]
    
    print(f"   {idx}: Signal={sig:+.0f}, Structure={struct:+.0f}, "
          f"BullOB={is_bull_ob}, BearOB={is_bear_ob}, "
          f"Close={row['Close']:.5f}")

# Check the CRITICAL issue: Are OBs persistent or one-time?
print(f"\n4. Understanding OB Persistence:")
first_bull_ob_idx = bull_ob[bull_ob].index[0] if bull_ob.any() else None
if first_bull_ob_idx:
    # Check if OB stays True after being marked
    idx_pos = df_test.index.get_loc(first_bull_ob_idx)
    print(f"   First bullish OB at index {idx_pos}: {first_bull_ob_idx}")
    print(f"   OB value at that bar: {bull_ob.iloc[idx_pos]}")
    if idx_pos + 5 < len(df_test):
        print(f"   OB value 5 bars later: {bull_ob.iloc[idx_pos + 5]}")
    
print(f"\n5. KEY INSIGHT:")
print(f"   In Python: OB is marked ONCE on a specific historical bar")
print(f"   Signal enters on THAT specific bar (with shift)")
print(f"   This means: Entry happens at the OB candle, not when price returns to it")

print(f"\n6. Pine Script Issue:")
print(f"   Pine needs to mark OBs the SAME way:")
print(f"   - When strong move detected, mark THAT PAST candle as OB")
print(f"   - Generate signal on bars where bullish_ob[bar] == true")
print(f"   - NOT 'wait for price to return to OB zone'")

print("\n" + "="*80)
print("CONCLUSION: Pine Script needs to be REWRITTEN")
print("="*80)
print("""
Current Pine Script is WRONG because it:
1. Tries to create OB 'zones' that persist
2. Waits for price to return to those zones
3. Enters when price touches the zone

Correct logic should:
1. Mark specific PAST candles as OBs when strong move happens
2. Enter signal on THOSE SPECIFIC CANDLES (with shift)
3. NOT create zones or wait for returns

This is fundamentally different!
""")
