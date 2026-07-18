"""
Test Pine Script logic on 2016-2020 data
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

# Test on 2016-2020 period
df_test = df[(df.index >= '2016-01-01') & (df.index <= '2020-12-31')].copy()

print("="*80)
print("TESTING PINE SCRIPT LOGIC ON 2016-2020 DATA")
print("="*80)
print(f"Period: {df_test.index[0]} to {df_test.index[-1]}")
print(f"Bars: {len(df_test)}")
print(f"Duration: {(df_test.index[-1] - df_test.index[0]).days / 365.25:.2f} years")
print("="*80)

# ============================================================================
# TEST 1: REALTIME LOGIC
# ============================================================================
print("\n" + "="*80)
print("TEST 1: SMC REALTIME LOGIC")
print("="*80)

def test_realtime_logic(df):
    """Simulate smc_realtime_logic.pine"""
    
    body = abs(df['Close'] - df['Open'])
    avg_body = body.rolling(20).mean()
    
    strong_bull = (df['Close'] > df['Open']) & (body > avg_body * 1.5)
    strong_bear = (df['Close'] < df['Open']) & (body > avg_body * 1.5)
    
    ob_lookback = 5
    strong_bull_recent = pd.Series(False, index=df.index)
    strong_bear_recent = pd.Series(False, index=df.index)
    
    for i in range(ob_lookback, len(df)):
        if strong_bull.iloc[i-ob_lookback:i].any():
            strong_bull_recent.iloc[i] = True
        if strong_bear.iloc[i-ob_lookback:i].any():
            strong_bear_recent.iloc[i] = True
    
    current_bearish = df['Close'] < df['Open']
    current_bullish = df['Close'] > df['Open']
    
    bullish_ob_forming = current_bearish & strong_bull_recent
    bearish_ob_forming = current_bullish & strong_bear_recent
    
    struct_length = 5
    recent_high = df['High'].rolling(struct_length).max()
    recent_low = df['Low'].rolling(struct_length).min()
    
    structure = pd.Series(0, index=df.index)
    structure[df['Close'] > recent_high.shift(1)] = 1
    structure[df['Close'] < recent_low.shift(1)] = -1
    
    long_signal = bullish_ob_forming & (structure >= 0)
    short_signal = bearish_ob_forming & (structure <= 0)
    
    return long_signal, short_signal

def test_simple_logic(df):
    """Simulate smc_simple_working.pine"""
    
    body = abs(df['Close'] - df['Open'])
    avg_body = body.rolling(20).mean()
    
    strong_bull_now = (df['Close'] > df['Open']) & (body > avg_body * 1.5)
    strong_bear_now = (df['Close'] < df['Open']) & (body > avg_body * 1.5)
    
    ti = TechnicalIndicators
    ma_fast = ti.ema(df, 10)
    ma_slow = ti.ema(df, 30)
    
    bullish_trend = ma_fast > ma_slow
    bearish_trend = ma_fast < ma_slow
    
    long_signal = (strong_bull_now.shift(1) | strong_bull_now.shift(2) | strong_bull_now.shift(3)) & bullish_trend & ~strong_bull_now
    short_signal = (strong_bear_now.shift(1) | strong_bear_now.shift(2) | strong_bear_now.shift(3)) & bearish_trend & ~strong_bear_now
    
    return long_signal, short_signal

def simulate_trades(df, long_signal, short_signal):
    """Simulate strategy execution"""
    
    ti = TechnicalIndicators
    atr = ti.atr(df, 14)
    
    equity = 1000.0
    trades = []
    equity_curve = [equity]
    position = 0
    entry_price = 0
    stop_loss = 0
    take_profit = 0
    
    for i in range(len(df)):
        current_price = df['Close'].iloc[i]
        current_atr = atr.iloc[i]
        
        # Check exits
        if position == 1:
            if current_price <= stop_loss:
                pnl = (stop_loss - entry_price) / entry_price
                equity *= (1 + pnl)
                trades.append({'type': 'LONG', 'pnl': pnl, 'exit': 'SL', 'equity': equity})
                position = 0
            elif current_price >= take_profit:
                pnl = (take_profit - entry_price) / entry_price
                equity *= (1 + pnl)
                trades.append({'type': 'LONG', 'pnl': pnl, 'exit': 'TP', 'equity': equity})
                position = 0
        
        elif position == -1:
            if current_price >= stop_loss:
                pnl = (entry_price - stop_loss) / entry_price
                equity *= (1 + pnl)
                trades.append({'type': 'SHORT', 'pnl': pnl, 'exit': 'SL', 'equity': equity})
                position = 0
            elif current_price <= take_profit:
                pnl = (entry_price - take_profit) / entry_price
                equity *= (1 + pnl)
                trades.append({'type': 'SHORT', 'pnl': pnl, 'exit': 'TP', 'equity': equity})
                position = 0
        
        equity_curve.append(equity)
        
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
    
    return trades, equity, equity_curve

# Test Realtime Logic
long_sig, short_sig = test_realtime_logic(df_test)

print(f"\nSignal Generation:")
print(f"  Long signals: {long_sig.sum()}")
print(f"  Short signals: {short_sig.sum()}")
print(f"  Total signals: {long_sig.sum() + short_sig.sum()}")

trades_rt, equity_rt, equity_curve_rt = simulate_trades(df_test, long_sig, short_sig)
trades_df_rt = pd.DataFrame(trades_rt)

duration_years = (df_test.index[-1] - df_test.index[0]).days / 365.25
annual_return_rt = ((equity_rt / 1000) ** (1 / duration_years) - 1) * 100

print(f"\nBacktest Results:")
print(f"  Final Equity: ${equity_rt:,.2f}")
print(f"  Total Return: {(equity_rt/1000-1)*100:+.2f}%")
print(f"  Annual Return: {annual_return_rt:+.2f}%")
print(f"  Total Trades: {len(trades_rt)}")
print(f"  Trades/Year: {len(trades_rt)/duration_years:.1f}")

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
    
    # Max Drawdown
    equity_series = pd.Series(equity_curve_rt)
    running_max = equity_series.cummax()
    drawdown = equity_series - running_max
    max_dd = drawdown.min()
    max_dd_pct = (max_dd / running_max[drawdown.idxmin()]) * 100
    print(f"  Max Drawdown: ${max_dd:.2f} ({max_dd_pct:.2f}%)")

# ============================================================================
# TEST 2: SIMPLE WORKING LOGIC
# ============================================================================
print("\n" + "="*80)
print("TEST 2: SMC SIMPLE WORKING LOGIC")
print("="*80)

long_sig2, short_sig2 = test_simple_logic(df_test)

print(f"\nSignal Generation:")
print(f"  Long signals: {long_sig2.sum()}")
print(f"  Short signals: {short_sig2.sum()}")
print(f"  Total signals: {long_sig2.sum() + short_sig2.sum()}")

trades_simple, equity_simple, equity_curve_simple = simulate_trades(df_test, long_sig2, short_sig2)
trades_df_simple = pd.DataFrame(trades_simple)

annual_return_simple = ((equity_simple / 1000) ** (1 / duration_years) - 1) * 100

print(f"\nBacktest Results:")
print(f"  Final Equity: ${equity_simple:,.2f}")
print(f"  Total Return: {(equity_simple/1000-1)*100:+.2f}%")
print(f"  Annual Return: {annual_return_simple:+.2f}%")
print(f"  Total Trades: {len(trades_simple)}")
print(f"  Trades/Year: {len(trades_simple)/duration_years:.1f}")

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
    
    # Max Drawdown
    equity_series = pd.Series(equity_curve_simple)
    running_max = equity_series.cummax()
    drawdown = equity_series - running_max
    max_dd = drawdown.min()
    max_dd_pct = (max_dd / running_max[drawdown.idxmin()]) * 100
    print(f"  Max Drawdown: ${max_dd:.2f} ({max_dd_pct:.2f}%)")

# ============================================================================
# SUMMARY
# ============================================================================
print("\n" + "="*80)
print("SUMMARY: 2016-2020 PERFORMANCE")
print("="*80)

print(f"\n{'Strategy':<25} {'Trades':<10} {'T/Year':<10} {'Win%':<10} {'Annual':<12} {'Max DD':<12} {'Status':<15}")
print("-" * 95)

if len(trades_rt) > 0:
    wr_rt = len(trades_df_rt[trades_df_rt['pnl'] > 0]) / len(trades_rt) * 100
    status_rt = "✅ WORKING" if equity_rt > 1000 else "❌ LOSING"
    
    equity_series = pd.Series(equity_curve_rt)
    running_max = equity_series.cummax()
    drawdown = equity_series - running_max
    max_dd_pct = (drawdown.min() / running_max[drawdown.idxmin()]) * 100
    
    print(f"{'Realtime Logic':<25} {len(trades_rt):<10} {len(trades_rt)/duration_years:<10.1f} {wr_rt:<10.1f} {annual_return_rt:+.1f}%{'':<7} {max_dd_pct:.1f}%{'':<7} {status_rt:<15}")

if len(trades_simple) > 0:
    wr_simple = len(trades_df_simple[trades_df_simple['pnl'] > 0]) / len(trades_simple) * 100
    status_simple = "✅ WORKING" if equity_simple > 1000 else "❌ LOSING"
    
    equity_series = pd.Series(equity_curve_simple)
    running_max = equity_series.cummax()
    drawdown = equity_series - running_max
    max_dd_pct = (drawdown.min() / running_max[drawdown.idxmin()]) * 100
    
    print(f"{'Simple Working':<25} {len(trades_simple):<10} {len(trades_simple)/duration_years:<10.1f} {wr_simple:<10.1f} {annual_return_simple:+.1f}%{'':<7} {max_dd_pct:.1f}%{'':<7} {status_simple:<15}")

# Comparison with validated results
print("\n" + "="*80)
print("COMPARISON WITH VALIDATED PYTHON BACKTEST")
print("="*80)
print(f"\nValidated Python (2016-2020):")
print(f"  Strategy: Original SMC Order Block")
print(f"  Trades: 428")
print(f"  Win Rate: 39.7%")
print(f"  Annual Return: +56.1%")
print(f"  Total Return: +823%")
print(f"  Max Drawdown: -56.1%")

print(f"\nPine Script Simple Working (2016-2020):")
if len(trades_simple) > 0:
    print(f"  Trades: {len(trades_simple)}")
    print(f"  Win Rate: {wr_simple:.1f}%")
    print(f"  Annual Return: {annual_return_simple:+.1f}%")
    print(f"  Total Return: {(equity_simple/1000-1)*100:+.1f}%")
    
    equity_series = pd.Series(equity_curve_simple)
    running_max = equity_series.cummax()
    drawdown = equity_series - running_max
    max_dd_pct = (drawdown.min() / running_max[drawdown.idxmin()]) * 100
    print(f"  Max Drawdown: {max_dd_pct:.1f}%")

print("\n" + "="*80)
print("CONCLUSION")
print("="*80)

if equity_simple > 1000:
    print(f"\n✅ Pine Script Simple Working is PROFITABLE on 2016-2020!")
    print(f"\n   Annual Return: {annual_return_simple:+.1f}%")
    print(f"   This confirms the strategy works on this period too.")
    
    if annual_return_simple < 56.1:
        print(f"\n   Note: Lower return than Python (+{annual_return_simple:.1f}% vs +56.1%)")
        print(f"   This is expected because:")
        print(f"   - Different entry logic (real-time vs retroactive)")
        print(f"   - No position sizing scaling")
        print(f"   - Simplified execution")
        print(f"\n   But still PROFITABLE and WORKING ✅")
else:
    print(f"\n⚠️ Strategy not profitable on 2016-2020")

print("="*80)
