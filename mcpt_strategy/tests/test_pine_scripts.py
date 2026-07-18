"""
Test Pine Script logic in Python to verify it works before user tries in TradingView
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))

import pandas as pd
import numpy as np
from core.indicators import TechnicalIndicators

# Load data
cache_dir = Path(__file__).parent.parent / 'data' / 'forex_cache'
cache_file = cache_dir / 'EURUSD_2016_2024_4h.parquet'

df = pd.read_parquet(cache_file)
df.columns = [c.capitalize() for c in df.columns]

# Test on 2020-2024 period
df_test = df[(df.index >= '2020-01-01') & (df.index <= '2024-12-31')].copy()

print("="*80)
print("TESTING PINE SCRIPT LOGIC IN PYTHON")
print("="*80)
print(f"Period: {df_test.index[0]} to {df_test.index[-1]}")
print(f"Bars: {len(df_test)}")
print("="*80)

# ============================================================================
# TEST 1: REALTIME LOGIC (smc_realtime_logic.pine)
# ============================================================================
print("\n" + "="*80)
print("TEST 1: SMC REALTIME LOGIC")
print("="*80)

def test_realtime_logic(df):
    """Simulate smc_realtime_logic.pine"""
    
    # Order Block Detection
    body = abs(df['Close'] - df['Open'])
    avg_body = body.rolling(20).mean()
    
    strong_bull = (df['Close'] > df['Open']) & (body > avg_body * 1.5)
    strong_bear = (df['Close'] < df['Open']) & (body > avg_body * 1.5)
    
    # Check if strong move happened in last 5 bars
    ob_lookback = 5
    strong_bull_recent = pd.Series(False, index=df.index)
    strong_bear_recent = pd.Series(False, index=df.index)
    
    for i in range(ob_lookback, len(df)):
        # Check if strong move in previous bars
        if strong_bull.iloc[i-ob_lookback:i].any():
            strong_bull_recent.iloc[i] = True
        if strong_bear.iloc[i-ob_lookback:i].any():
            strong_bear_recent.iloc[i] = True
    
    # Current candle characteristics
    current_bearish = df['Close'] < df['Open']
    current_bullish = df['Close'] > df['Open']
    
    # OB forming
    bullish_ob_forming = current_bearish & strong_bull_recent
    bearish_ob_forming = current_bullish & strong_bear_recent
    
    # Market Structure
    struct_length = 5
    recent_high = df['High'].rolling(struct_length).max()
    recent_low = df['Low'].rolling(struct_length).min()
    
    structure = pd.Series(0, index=df.index)
    structure[df['Close'] > recent_high.shift(1)] = 1
    structure[df['Close'] < recent_low.shift(1)] = -1
    
    # Signals
    long_signal = bullish_ob_forming & (structure >= 0)
    short_signal = bearish_ob_forming & (structure <= 0)
    
    return long_signal, short_signal

long_sig, short_sig = test_realtime_logic(df_test)

print(f"\nSignal Generation:")
print(f"  Long signals: {long_sig.sum()}")
print(f"  Short signals: {short_sig.sum()}")
print(f"  Total signals: {long_sig.sum() + short_sig.sum()}")

# Simulate trades
def simulate_trades(df, long_signal, short_signal):
    """Simulate strategy execution"""
    
    ti = TechnicalIndicators
    atr = ti.atr(df, 14)
    
    equity = 1000.0
    trades = []
    position = 0
    entry_price = 0
    stop_loss = 0
    take_profit = 0
    
    for i in range(len(df)):
        current_price = df['Close'].iloc[i]
        current_atr = atr.iloc[i]
        
        # Check exits
        if position == 1:  # Long
            if current_price <= stop_loss:
                pnl = (stop_loss - entry_price) / entry_price
                equity *= (1 + pnl)
                trades.append({'type': 'LONG', 'pnl': pnl, 'exit': 'SL'})
                position = 0
            elif current_price >= take_profit:
                pnl = (take_profit - entry_price) / entry_price
                equity *= (1 + pnl)
                trades.append({'type': 'LONG', 'pnl': pnl, 'exit': 'TP'})
                position = 0
        
        elif position == -1:  # Short
            if current_price >= stop_loss:
                pnl = (entry_price - stop_loss) / entry_price
                equity *= (1 + pnl)
                trades.append({'type': 'SHORT', 'pnl': pnl, 'exit': 'SL'})
                position = 0
            elif current_price <= take_profit:
                pnl = (entry_price - take_profit) / entry_price
                equity *= (1 + pnl)
                trades.append({'type': 'SHORT', 'pnl': pnl, 'exit': 'TP'})
                position = 0
        
        # Check entries
        if position == 0 and not np.isnan(current_atr):
            if long_signal.iloc[i]:
                position = 1
                entry_price = current_price
                stop_loss = entry_price - (current_atr * 1.0)
                take_profit = entry_price + (current_atr * 3.0)
            
            elif short_signal.iloc[i]:
                position = -1
                entry_price = current_price
                stop_loss = entry_price + (current_atr * 1.0)
                take_profit = entry_price - (current_atr * 3.0)
    
    return trades, equity

trades_rt, equity_rt = simulate_trades(df_test, long_sig, short_sig)
trades_df_rt = pd.DataFrame(trades_rt)

print(f"\nBacktest Results:")
print(f"  Final Equity: ${equity_rt:,.2f}")
print(f"  Total Return: {(equity_rt/1000-1)*100:+.2f}%")
print(f"  Total Trades: {len(trades_rt)}")

if len(trades_rt) > 0:
    winners = trades_df_rt[trades_df_rt['pnl'] > 0]
    losers = trades_df_rt[trades_df_rt['pnl'] <= 0]
    
    print(f"  Winners: {len(winners)} ({len(winners)/len(trades_rt)*100:.1f}%)")
    print(f"  Losers: {len(losers)} ({len(losers)/len(trades_rt)*100:.1f}%)")
    
    tp_exits = trades_df_rt[trades_df_rt['exit'] == 'TP']
    sl_exits = trades_df_rt[trades_df_rt['exit'] == 'SL']
    
    print(f"  TP Exits: {len(tp_exits)} ({len(tp_exits)/len(trades_rt)*100:.1f}%)")
    print(f"  SL Exits: {len(sl_exits)} ({len(sl_exits)/len(trades_rt)*100:.1f}%)")
    
    if len(winners) > 0 and len(losers) > 0:
        total_wins = winners['pnl'].sum()
        total_losses = abs(losers['pnl'].sum())
        pf = total_wins / total_losses if total_losses > 0 else 0
        print(f"  Profit Factor: {pf:.2f}")

# ============================================================================
# TEST 2: SIMPLE WORKING LOGIC (smc_simple_working.pine)
# ============================================================================
print("\n" + "="*80)
print("TEST 2: SMC SIMPLE WORKING LOGIC")
print("="*80)

def test_simple_logic(df):
    """Simulate smc_simple_working.pine"""
    
    # Detect strong moves
    body = abs(df['Close'] - df['Open'])
    avg_body = body.rolling(20).mean()
    
    strong_bull_now = (df['Close'] > df['Open']) & (body > avg_body * 1.5)
    strong_bear_now = (df['Close'] < df['Open']) & (body > avg_body * 1.5)
    
    # Market structure (trend)
    ti = TechnicalIndicators
    ma_fast = ti.ema(df, 10)
    ma_slow = ti.ema(df, 30)
    
    bullish_trend = ma_fast > ma_slow
    bearish_trend = ma_fast < ma_slow
    
    # Entry logic: Strong move happened 1-3 bars ago + trend aligns
    long_signal = (strong_bull_now.shift(1) | strong_bull_now.shift(2) | strong_bull_now.shift(3)) & bullish_trend & ~strong_bull_now
    short_signal = (strong_bear_now.shift(1) | strong_bear_now.shift(2) | strong_bear_now.shift(3)) & bearish_trend & ~strong_bear_now
    
    return long_signal, short_signal

long_sig2, short_sig2 = test_simple_logic(df_test)

print(f"\nSignal Generation:")
print(f"  Long signals: {long_sig2.sum()}")
print(f"  Short signals: {short_sig2.sum()}")
print(f"  Total signals: {long_sig2.sum() + short_sig2.sum()}")

trades_simple, equity_simple = simulate_trades(df_test, long_sig2, short_sig2)
trades_df_simple = pd.DataFrame(trades_simple)

print(f"\nBacktest Results:")
print(f"  Final Equity: ${equity_simple:,.2f}")
print(f"  Total Return: {(equity_simple/1000-1)*100:+.2f}%")
print(f"  Total Trades: {len(trades_simple)}")

if len(trades_simple) > 0:
    winners = trades_df_simple[trades_df_simple['pnl'] > 0]
    losers = trades_df_simple[trades_df_simple['pnl'] <= 0]
    
    print(f"  Winners: {len(winners)} ({len(winners)/len(trades_simple)*100:.1f}%)")
    print(f"  Losers: {len(losers)} ({len(losers)/len(trades_simple)*100:.1f}%)")
    
    tp_exits = trades_df_simple[trades_df_simple['exit'] == 'TP']
    sl_exits = trades_df_simple[trades_df_simple['exit'] == 'SL']
    
    print(f"  TP Exits: {len(tp_exits)} ({len(tp_exits)/len(trades_simple)*100:.1f}%)")
    print(f"  SL Exits: {len(sl_exits)} ({len(sl_exits)/len(trades_simple)*100:.1f}%)")
    
    if len(winners) > 0 and len(losers) > 0:
        total_wins = winners['pnl'].sum()
        total_losses = abs(losers['pnl'].sum())
        pf = total_wins / total_losses if total_losses > 0 else 0
        print(f"  Profit Factor: {pf:.2f}")

# ============================================================================
# SUMMARY
# ============================================================================
print("\n" + "="*80)
print("SUMMARY COMPARISON")
print("="*80)

print(f"\n{'Strategy':<25} {'Trades':<10} {'Win%':<10} {'Return':<15} {'Status':<15}")
print("-" * 75)

if len(trades_rt) > 0:
    wr_rt = len(trades_df_rt[trades_df_rt['pnl'] > 0]) / len(trades_rt) * 100
    status_rt = "✅ WORKING" if equity_rt > 1000 else "❌ LOSING"
    print(f"{'Realtime Logic':<25} {len(trades_rt):<10} {wr_rt:<10.1f} {(equity_rt/1000-1)*100:+.1f}%{'':<8} {status_rt:<15}")

if len(trades_simple) > 0:
    wr_simple = len(trades_df_simple[trades_df_simple['pnl'] > 0]) / len(trades_simple) * 100
    status_simple = "✅ WORKING" if equity_simple > 1000 else "❌ LOSING"
    print(f"{'Simple Working':<25} {len(trades_simple):<10} {wr_simple:<10.1f} {(equity_simple/1000-1)*100:+.1f}%{'':<8} {status_simple:<15}")

print("\n" + "="*80)
print("CONCLUSION")
print("="*80)

if equity_rt > 1000 or equity_simple > 1000:
    print("\n✅ AT LEAST ONE STRATEGY IS WORKING!")
    print("\nThese Pine Scripts should work in TradingView:")
    if equity_rt > 1000:
        print(f"  ✅ smc_realtime_logic.pine - {(equity_rt/1000-1)*100:+.1f}% return")
    if equity_simple > 1000:
        print(f"  ✅ smc_simple_working.pine - {(equity_simple/1000-1)*100:+.1f}% return")
    
    print("\nExpected in TradingView:")
    print("  - Similar trade counts (±20%)")
    print("  - Similar win rates (±5%)")
    print("  - Positive returns (may differ due to execution)")
    print("  - NOT all losing trades!")
else:
    print("\n⚠️ WARNING: Both strategies showing losses")
    print("May need further adjustment")

print("="*80)
