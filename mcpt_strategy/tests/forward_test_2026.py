"""
Forward Test 2026 - Test Best Strategy with Real Leverage
Starting Capital: $1000
Leverage: 50:1
Failure Threshold: Drop below $400
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime
import json

from core.indicators import TechnicalIndicators


def fetch_2026_data():
    """Fetch EUR/USD data for 2026-current"""
    import requests
    import random
    import string
    import time
    
    def _jsonp_name():
        return "_callbacks____" + "".join(random.choices(string.ascii_letters + string.digits, k=9))
    
    print("📡 Fetching EUR/USD 2026-current data from Dukascopy...")
    
    # Start from 2026-01-01
    start_ts = pd.Timestamp("2026-01-01", tz="UTC")
    start_ms = int(start_ts.timestamp() * 1000)
    
    all_bars = []
    last_update = start_ms
    
    for iteration in range(20):  # Safety limit
        try:
            jsonp = _jsonp_name()
            params = {
                "path": "chart/json3",
                "splits": "true",
                "stocks": "true",
                "time_direction": "N",
                "jsonp": jsonp,
                "last_update": str(int(last_update)),
                "offer_side": "B",
                "instrument": "EUR/USD",
                "interval": "4HOUR",
                "limit": "5000",
            }
            headers = {
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
                "Referer": "https://freeserv.dukascopy.com/2.0/?path=chart/index",
                "Host": "freeserv.dukascopy.com",
            }
            
            r = requests.get(
                "https://freeserv.dukascopy.com/2.0/index.php",
                headers=headers,
                params=params,
                timeout=60,
            )
            r.raise_for_status()
            
            text = r.text
            if text.startswith(jsonp + "(") and text.endswith(");"):
                text = text[len(jsonp) + 1 : -2]
            
            data = json.loads(text)
            
            if not data or not isinstance(data, list):
                break
            
            all_bars.extend(data)
            
            last_bar_ts = data[-1][0]
            last_update = last_bar_ts
            
            bar_date = pd.Timestamp(last_bar_ts, unit='ms', tz='UTC')
            print(f"  Fetched {len(all_bars)} bars (latest: {bar_date.strftime('%Y-%m-%d %H:%M')})")
            
            # Check if we've reached current time
            if bar_date > pd.Timestamp.now(tz='UTC') - pd.Timedelta(hours=8):
                break
            
            time.sleep(0.3)
            
        except Exception as e:
            print(f"  Error: {e}")
            break
    
    if not all_bars:
        raise ValueError("No data fetched for 2026")
    
    # Convert to DataFrame
    df = pd.DataFrame(all_bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True)
    df = df.set_index('timestamp').sort_index()
    
    # Filter to 2026+
    df = df[df.index.year >= 2026]
    
    # Normalize columns
    df.columns = ['Open', 'High', 'Low', 'Close', 'Volume']
    
    print(f"✓ Fetched {len(df)} bars from {df.index[0]} to {df.index[-1]}")
    
    return df


def forex_strategy_signal(ohlc: pd.DataFrame) -> pd.Series:
    """
    Best strategy: EMA 3/9 + ADX + DI Filter
    """
    ti = TechnicalIndicators
    
    ema_fast = ti.ema(ohlc, 3)
    ema_slow = ti.ema(ohlc, 9)
    adx, plus_di, minus_di = ti.adx(ohlc, 14)
    
    cross_up = (ema_fast > ema_slow) & (ema_fast.shift(1) <= ema_slow.shift(1))
    cross_down = (ema_fast < ema_slow) & (ema_fast.shift(1) >= ema_slow.shift(1))
    
    long = cross_up & (adx > 15.0)
    short = cross_down & (adx > 15.0)
    
    # DI filter
    long = long & (plus_di > minus_di)
    short = short & (minus_di > plus_di)
    
    signal = pd.Series(0, index=ohlc.index, dtype=float)
    signal[long] = 1
    signal[short] = -1
    
    return signal.shift(1).fillna(0)


def backtest_with_leverage(
    ohlc: pd.DataFrame,
    initial_capital: float = 1000.0,
    leverage: float = 50.0,
    risk_per_trade: float = 0.01,  # 1% risk per trade
    failure_threshold: float = 400.0,
    atr_sl_mult: float = 1.0,
    atr_tp_mult: float = 3.0
):
    """
    Backtest with proper leverage and position sizing
    """
    ti = TechnicalIndicators
    
    print(f"\n{'='*80}")
    print(f"FORWARD TEST: 2026-CURRENT")
    print(f"{'='*80}")
    print(f"Initial Capital: ${initial_capital:.2f}")
    print(f"Leverage: {leverage}:1")
    print(f"Failure Threshold: ${failure_threshold:.2f}")
    print(f"Risk Per Trade: {risk_per_trade*100:.1f}%")
    print(f"{'='*80}\n")
    
    # Generate signals
    signal = forex_strategy_signal(ohlc)
    atr = ti.atr(ohlc, 14)
    
    # Initialize tracking
    equity = initial_capital
    equity_curve = []
    trades = []
    position = 0
    position_size = 0
    entry_price = 0
    stop_loss = 0
    take_profit = 0
    failed = False
    
    for i in range(len(ohlc)):
        current_price = ohlc['Close'].iloc[i]
        current_signal = signal.iloc[i]
        current_atr = atr.iloc[i]
        current_time = ohlc.index[i]
        
        # Check existing position
        if position != 0:
            # Check stop loss
            if position == 1 and current_price <= stop_loss:
                # Stopped out long
                pnl = (stop_loss - entry_price) * position_size
                equity += pnl
                
                trades.append({
                    'entry_time': entry_time,
                    'exit_time': current_time,
                    'direction': 'LONG',
                    'entry_price': entry_price,
                    'exit_price': stop_loss,
                    'position_size': position_size,
                    'pnl': pnl,
                    'pnl_pct': (pnl / initial_capital) * 100,
                    'exit_reason': 'STOP_LOSS'
                })
                
                position = 0
                
            elif position == -1 and current_price >= stop_loss:
                # Stopped out short
                pnl = (entry_price - stop_loss) * position_size
                equity += pnl
                
                trades.append({
                    'entry_time': entry_time,
                    'exit_time': current_time,
                    'direction': 'SHORT',
                    'entry_price': entry_price,
                    'exit_price': stop_loss,
                    'position_size': position_size,
                    'pnl': pnl,
                    'pnl_pct': (pnl / initial_capital) * 100,
                    'exit_reason': 'STOP_LOSS'
                })
                
                position = 0
            
            # Check take profit
            elif position == 1 and current_price >= take_profit:
                # Hit TP long
                pnl = (take_profit - entry_price) * position_size
                equity += pnl
                
                trades.append({
                    'entry_time': entry_time,
                    'exit_time': current_time,
                    'direction': 'LONG',
                    'entry_price': entry_price,
                    'exit_price': take_profit,
                    'position_size': position_size,
                    'pnl': pnl,
                    'pnl_pct': (pnl / initial_capital) * 100,
                    'exit_reason': 'TAKE_PROFIT'
                })
                
                position = 0
                
            elif position == -1 and current_price <= take_profit:
                # Hit TP short
                pnl = (entry_price - take_profit) * position_size
                equity += pnl
                
                trades.append({
                    'entry_time': entry_time,
                    'exit_time': current_time,
                    'direction': 'SHORT',
                    'entry_price': entry_price,
                    'exit_price': take_profit,
                    'position_size': position_size,
                    'pnl': pnl,
                    'pnl_pct': (pnl / initial_capital) * 100,
                    'exit_reason': 'TAKE_PROFIT'
                })
                
                position = 0
        
        # Record equity
        equity_curve.append({
            'time': current_time,
            'equity': equity,
            'position': position
        })
        
        # Check failure condition
        if equity < failure_threshold:
            failed = True
            print(f"\n🚨 FAILURE: Equity dropped below ${failure_threshold:.2f}")
            print(f"   Current Equity: ${equity:.2f}")
            print(f"   Time: {current_time}")
            break
        
        # Entry logic (only if no position)
        if position == 0 and current_signal != 0 and not np.isnan(current_atr):
            # Calculate position size based on risk
            risk_amount = equity * risk_per_trade
            sl_distance = current_atr * atr_sl_mult
            
            # Position size in currency units (with leverage)
            max_position_value = equity * leverage
            risk_based_position = risk_amount / sl_distance
            position_size = min(risk_based_position, max_position_value)
            
            entry_price = current_price
            entry_time = current_time
            
            if current_signal == 1:
                # Long entry
                position = 1
                stop_loss = entry_price - sl_distance
                take_profit = entry_price + (current_atr * atr_tp_mult)
                
            elif current_signal == -1:
                # Short entry
                position = -1
                stop_loss = entry_price + sl_distance
                take_profit = entry_price - (current_atr * atr_tp_mult)
    
    # Close any remaining position at end
    if position != 0:
        final_price = ohlc['Close'].iloc[-1]
        
        if position == 1:
            pnl = (final_price - entry_price) * position_size
        else:
            pnl = (entry_price - final_price) * position_size
        
        equity += pnl
        
        trades.append({
            'entry_time': entry_time,
            'exit_time': ohlc.index[-1],
            'direction': 'LONG' if position == 1 else 'SHORT',
            'entry_price': entry_price,
            'exit_price': final_price,
            'position_size': position_size,
            'pnl': pnl,
            'pnl_pct': (pnl / initial_capital) * 100,
            'exit_reason': 'END_OF_DATA'
        })
    
    equity_curve.append({
        'time': ohlc.index[-1],
        'equity': equity,
        'position': 0
    })
    
    # Calculate statistics
    equity_df = pd.DataFrame(equity_curve)
    trades_df = pd.DataFrame(trades) if trades else pd.DataFrame()
    
    total_return = (equity - initial_capital) / initial_capital * 100
    
    if len(trades) > 0:
        winning_trades = trades_df[trades_df['pnl'] > 0]
        losing_trades = trades_df[trades_df['pnl'] < 0]
        
        win_rate = len(winning_trades) / len(trades) * 100
        avg_win = winning_trades['pnl'].mean() if len(winning_trades) > 0 else 0
        avg_loss = losing_trades['pnl'].mean() if len(losing_trades) > 0 else 0
        
        total_wins = winning_trades['pnl'].sum() if len(winning_trades) > 0 else 0
        total_losses = abs(losing_trades['pnl'].sum()) if len(losing_trades) > 0 else 0
        profit_factor = total_wins / total_losses if total_losses > 0 else 0
    else:
        win_rate = 0
        avg_win = 0
        avg_loss = 0
        profit_factor = 0
    
    # Drawdown
    equity_series = equity_df['equity']
    running_max = equity_series.cummax()
    drawdown = equity_series - running_max
    max_dd = drawdown.min()
    max_dd_pct = (max_dd / initial_capital) * 100
    
    # Print results
    print(f"\n{'='*80}")
    print(f"RESULTS")
    print(f"{'='*80}")
    print(f"\n📊 Performance:")
    print(f"  Starting Capital:     ${initial_capital:.2f}")
    print(f"  Final Equity:         ${equity:.2f}")
    print(f"  Total Return:         {total_return:+.2f}%")
    print(f"  Max Drawdown:         ${max_dd:.2f} ({max_dd_pct:.2f}%)")
    
    print(f"\n📈 Trading Stats:")
    print(f"  Total Trades:         {len(trades)}")
    print(f"  Win Rate:             {win_rate:.1f}%")
    print(f"  Profit Factor:        {profit_factor:.2f}")
    print(f"  Avg Win:              ${avg_win:.2f}")
    print(f"  Avg Loss:             ${avg_loss:.2f}")
    
    print(f"\n💰 Status:")
    if failed:
        print(f"  ❌ FAILED - Dropped below ${failure_threshold:.2f}")
    elif equity >= initial_capital:
        print(f"  ✅ SUCCESS - Profitable")
    else:
        print(f"  ⚠️  MARGINAL - Lost money but didn't fail threshold")
    
    print(f"\n{'='*80}")
    
    # Save results
    results = {
        'initial_capital': initial_capital,
        'final_equity': float(equity),
        'total_return_pct': float(total_return),
        'max_drawdown': float(max_dd),
        'max_drawdown_pct': float(max_dd_pct),
        'total_trades': len(trades),
        'win_rate': float(win_rate),
        'profit_factor': float(profit_factor),
        'failed': failed,
        'failure_threshold': failure_threshold,
        'trades': trades,
        'equity_curve': equity_curve
    }
    
    return results, equity_df, trades_df


def plot_results(equity_df, initial_capital, failure_threshold):
    """Plot equity curve"""
    plt.style.use('dark_background')
    fig, ax = plt.subplots(figsize=(14, 8))
    
    # Equity curve
    ax.plot(equity_df['time'], equity_df['equity'], linewidth=2, color='#58a6ff', label='Equity')
    
    # Initial capital line
    ax.axhline(initial_capital, color='white', linestyle='--', alpha=0.5, label='Starting Capital')
    
    # Failure threshold
    ax.axhline(failure_threshold, color='#f85149', linestyle='--', linewidth=2, 
               label=f'Failure Threshold (${failure_threshold:.0f})')
    
    # Fill
    ax.fill_between(equity_df['time'], initial_capital, equity_df['equity'], 
                     where=(equity_df['equity'] >= initial_capital), 
                     color='#3fb950', alpha=0.2)
    ax.fill_between(equity_df['time'], initial_capital, equity_df['equity'], 
                     where=(equity_df['equity'] < initial_capital), 
                     color='#f85149', alpha=0.2)
    
    ax.set_xlabel('Date', fontsize=12, fontweight='bold')
    ax.set_ylabel('Equity ($)', fontsize=12, fontweight='bold')
    ax.set_title('Forward Test 2026: EUR/USD Strategy', fontsize=16, fontweight='bold')
    ax.legend(fontsize=11)
    ax.grid(True, alpha=0.2)
    
    plt.tight_layout()
    
    results_dir = Path(__file__).parent.parent / 'results'
    plt.savefig(results_dir / 'forward_test_2026_equity.png', dpi=150, bbox_inches='tight')
    print(f"📊 Chart saved to {results_dir}/forward_test_2026_equity.png")


def main():
    """Main forward test"""
    # Try to load cached data first
    cache_file = Path(__file__).parent.parent / 'data' / 'forex_cache' / 'EURUSD_2026_current_4h.parquet'
    
    if cache_file.exists():
        print(f"📂 Loading cached 2026 data...")
        ohlc = pd.read_parquet(cache_file)
        if 'open' in ohlc.columns:
            ohlc.columns = [c.capitalize() for c in ohlc.columns]
    else:
        # Fetch fresh data
        ohlc = fetch_2026_data()
        
        # Cache it
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        ohlc_save = ohlc.copy()
        ohlc_save.columns = [c.lower() for c in ohlc_save.columns]
        ohlc_save.to_parquet(cache_file)
        print(f"💾 Cached to {cache_file}")
    
    print(f"\nData: {len(ohlc)} bars from {ohlc.index[0]} to {ohlc.index[-1]}")
    
    # Run backtest
    results, equity_df, trades_df = backtest_with_leverage(
        ohlc,
        initial_capital=1000.0,
        leverage=50.0,
        risk_per_trade=0.01,
        failure_threshold=400.0
    )
    
    # Save results
    results_dir = Path(__file__).parent.parent / 'results'
    results_dir.mkdir(parents=True, exist_ok=True)
    
    # Save summary (without full equity curve for readability)
    summary = {k: v for k, v in results.items() if k not in ['equity_curve', 'trades']}
    summary['num_trades'] = len(results['trades'])
    
    with open(results_dir / 'forward_test_2026_summary.json', 'w') as f:
        json.dump(summary, f, indent=2)
    
    # Save full results
    with open(results_dir / 'forward_test_2026_full.json', 'w') as f:
        # Convert timestamps to strings for JSON
        results_json = results.copy()
        results_json['equity_curve'] = [
            {**ec, 'time': ec['time'].isoformat()} 
            for ec in results_json['equity_curve']
        ]
        results_json['trades'] = [
            {**t, 'entry_time': t['entry_time'].isoformat(), 'exit_time': t['exit_time'].isoformat()} 
            for t in results_json['trades']
        ]
        json.dump(results_json, f, indent=2)
    
    # Plot
    plot_results(equity_df, results['initial_capital'], results['failure_threshold'])
    
    print(f"\n💾 Results saved to {results_dir}/")
    
    return results


if __name__ == '__main__':
    results = main()
