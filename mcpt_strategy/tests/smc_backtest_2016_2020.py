"""
SMC Order Block Strategy - Historical Backtest 2016-2020
Test on historical data to validate strategy performance across different market periods
Starting: $1000, Leverage: 50:1, OANDA costs
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import json

from core.indicators import TechnicalIndicators


class OANDABroker:
    """Simulate OANDA trading conditions"""
    
    AVG_SPREAD_PIPS = 1.0
    SLIPPAGE_PIPS = 0.3
    PIP_VALUE_PER_LOT = 10.0
    
    def __init__(self, initial_capital: float = 1000.0, leverage: float = 50.0):
        self.initial_capital = initial_capital
        self.leverage = leverage
        self.equity = initial_capital
        self.balance = initial_capital
        self.total_spread_cost = 0.0
        self.total_slippage_cost = 0.0
        
    def calculate_position_size(self, price: float, risk_pct: float = 0.01, 
                               stop_distance_pips: float = 10.0) -> float:
        risk_amount = self.equity * risk_pct
        position_size_lots = risk_amount / (self.PIP_VALUE_PER_LOT * stop_distance_pips)
        max_position_value = self.equity * self.leverage
        max_position_lots = max_position_value / (100000 * price)
        position_size_lots = min(position_size_lots, max_position_lots)
        return max(position_size_lots, 0.001)
    
    def calculate_spread_cost(self, position_size_lots: float) -> float:
        return self.AVG_SPREAD_PIPS * self.PIP_VALUE_PER_LOT * position_size_lots
    
    def calculate_slippage_cost(self, position_size_lots: float) -> float:
        return self.SLIPPAGE_PIPS * self.PIP_VALUE_PER_LOT * position_size_lots
    
    def execute_trade(self, entry_price: float, exit_price: float, 
                     position_size_lots: float, direction: int) -> float:
        if direction == 1:
            pip_movement = (exit_price - entry_price) * 10000
        else:
            pip_movement = (entry_price - exit_price) * 10000
        
        gross_pnl = pip_movement * self.PIP_VALUE_PER_LOT * position_size_lots
        spread_cost = self.calculate_spread_cost(position_size_lots)
        slippage_cost = self.calculate_slippage_cost(position_size_lots)
        net_pnl = gross_pnl - spread_cost - slippage_cost
        
        self.total_spread_cost += spread_cost
        self.total_slippage_cost += slippage_cost
        
        return net_pnl


def identify_order_blocks(ohlc: pd.DataFrame, lookback: int = 5):
    """Identify Smart Money order blocks"""
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


def identify_structure(ohlc: pd.DataFrame, swing_length: int = 5):
    """Identify market structure"""
    high = ohlc['High']
    low = ohlc['Low']
    close = ohlc['Close']
    
    structure = pd.Series(0, index=ohlc.index)
    recent_high = high.rolling(swing_length).max()
    recent_low = low.rolling(swing_length).min()
    
    structure[close > recent_high.shift(1)] = 1
    structure[close < recent_low.shift(1)] = -1
    
    return structure.ffill().fillna(0)


def smc_order_block_strategy(ohlc: pd.DataFrame, ob_lookback: int = 5, 
                             use_structure: bool = True) -> pd.Series:
    """SMC Order Block + Structure strategy"""
    bullish_ob, bearish_ob = identify_order_blocks(ohlc, ob_lookback)
    structure = identify_structure(ohlc) if use_structure else pd.Series(0, index=ohlc.index)
    
    signal = pd.Series(0, index=ohlc.index, dtype=float)
    signal[bullish_ob & (structure >= 0)] = 1
    signal[bearish_ob & (structure <= 0)] = -1
    
    return signal.shift(1).fillna(0)


def backtest_with_oanda_costs(
    ohlc: pd.DataFrame,
    initial_capital: float = 1000.0,
    leverage: float = 50.0,
    risk_per_trade: float = 0.01,
    atr_sl_mult: float = 1.0,
    atr_tp_mult: float = 3.0,
    period_name: str = "2016-2020"
):
    """Backtest SMC strategy with OANDA realistic costs"""
    print(f"\n{'='*80}")
    print(f"SMC ORDER BLOCK STRATEGY - BACKTEST {period_name}")
    print(f"{'='*80}")
    print(f"Initial Capital:      ${initial_capital:.2f}")
    print(f"Leverage:             {leverage}:1")
    print(f"Risk Per Trade:       {risk_per_trade*100:.1f}%")
    print(f"OANDA Spread:         {OANDABroker.AVG_SPREAD_PIPS:.1f} pips")
    print(f"Estimated Slippage:   {OANDABroker.SLIPPAGE_PIPS:.1f} pips")
    print(f"Period:               {ohlc.index[0]} to {ohlc.index[-1]}")
    print(f"Bars:                 {len(ohlc)}")
    print(f"Duration:             {(ohlc.index[-1] - ohlc.index[0]).days / 365.25:.1f} years")
    print(f"{'='*80}\n")
    
    broker = OANDABroker(initial_capital, leverage)
    signal = smc_order_block_strategy(ohlc, ob_lookback=5, use_structure=True)
    
    ti = TechnicalIndicators
    atr = ti.atr(ohlc, 14)
    
    equity_curve = []
    trades = []
    position = 0
    position_size_lots = 0
    entry_price = 0
    entry_time = None
    stop_loss = 0
    take_profit = 0
    stop_pips = 0
    
    for i in range(len(ohlc)):
        current_price = ohlc['Close'].iloc[i]
        current_signal = signal.iloc[i]
        current_atr = atr.iloc[i]
        current_time = ohlc.index[i]
        
        if position != 0:
            exit_triggered = False
            exit_price = current_price
            exit_reason = ''
            
            if position == 1 and current_price <= stop_loss:
                exit_triggered = True
                exit_price = stop_loss
                exit_reason = 'STOP_LOSS'
            elif position == -1 and current_price >= stop_loss:
                exit_triggered = True
                exit_price = stop_loss
                exit_reason = 'STOP_LOSS'
            elif position == 1 and current_price >= take_profit:
                exit_triggered = True
                exit_price = take_profit
                exit_reason = 'TAKE_PROFIT'
            elif position == -1 and current_price <= take_profit:
                exit_triggered = True
                exit_price = take_profit
                exit_reason = 'TAKE_PROFIT'
            
            if exit_triggered:
                pnl = broker.execute_trade(entry_price, exit_price, 
                                          position_size_lots, position)
                broker.equity += pnl
                broker.balance += pnl
                
                pip_move = abs(exit_price - entry_price) * 10000
                trades.append({
                    'entry_time': entry_time,
                    'exit_time': current_time,
                    'direction': 'LONG' if position == 1 else 'SHORT',
                    'entry_price': entry_price,
                    'exit_price': exit_price,
                    'position_size_lots': position_size_lots,
                    'stop_pips': stop_pips,
                    'pip_movement': pip_move if position == 1 else -pip_move,
                    'pnl': pnl,
                    'pnl_pct': (pnl / initial_capital) * 100,
                    'exit_reason': exit_reason,
                    'equity_after': broker.equity
                })
                
                position = 0
        
        equity_curve.append({
            'time': current_time,
            'equity': broker.equity,
            'balance': broker.balance,
            'position': position
        })
        
        if position == 0 and current_signal != 0 and not np.isnan(current_atr):
            stop_distance_pips = (current_atr * atr_sl_mult) * 10000
            position_size_lots = broker.calculate_position_size(
                current_price, risk_per_trade, stop_distance_pips
            )
            
            entry_price = current_price
            entry_time = current_time
            stop_pips = stop_distance_pips
            
            if current_signal == 1:
                position = 1
                stop_loss = entry_price - (current_atr * atr_sl_mult)
                take_profit = entry_price + (current_atr * atr_tp_mult)
            else:
                position = -1
                stop_loss = entry_price + (current_atr * atr_sl_mult)
                take_profit = entry_price - (current_atr * atr_tp_mult)
    
    if position != 0:
        final_price = ohlc['Close'].iloc[-1]
        pnl = broker.execute_trade(entry_price, final_price, 
                                   position_size_lots, position)
        broker.equity += pnl
        broker.balance += pnl
        
        trades.append({
            'entry_time': entry_time,
            'exit_time': ohlc.index[-1],
            'direction': 'LONG' if position == 1 else 'SHORT',
            'entry_price': entry_price,
            'exit_price': final_price,
            'position_size_lots': position_size_lots,
            'stop_pips': stop_pips,
            'pip_movement': (final_price - entry_price) * 10000 * position,
            'pnl': pnl,
            'pnl_pct': (pnl / initial_capital) * 100,
            'exit_reason': 'END_OF_DATA',
            'equity_after': broker.equity
        })
    
    equity_df = pd.DataFrame(equity_curve)
    trades_df = pd.DataFrame(trades) if trades else pd.DataFrame()
    
    final_equity = broker.equity
    total_return = (final_equity - initial_capital) / initial_capital * 100
    
    # Calculate duration for annualized return
    duration_years = (ohlc.index[-1] - ohlc.index[0]).days / 365.25
    annual_return = ((final_equity / initial_capital) ** (1 / duration_years) - 1) * 100
    
    if len(trades) > 0:
        winning_trades = trades_df[trades_df['pnl'] > 0]
        losing_trades = trades_df[trades_df['pnl'] < 0]
        
        win_rate = len(winning_trades) / len(trades) * 100
        avg_win = winning_trades['pnl'].mean() if len(winning_trades) > 0 else 0
        avg_loss = losing_trades['pnl'].mean() if len(losing_trades) > 0 else 0
        
        total_wins = winning_trades['pnl'].sum() if len(winning_trades) > 0 else 0
        total_losses = abs(losing_trades['pnl'].sum()) if len(losing_trades) > 0 else 0
        profit_factor = total_wins / total_losses if total_losses > 0 else 0
        
        avg_trade = trades_df['pnl'].mean()
        best_trade = trades_df['pnl'].max()
        worst_trade = trades_df['pnl'].min()
    else:
        win_rate = avg_win = avg_loss = profit_factor = 0
        avg_trade = best_trade = worst_trade = 0
        total_wins = total_losses = 0
    
    equity_series = equity_df['equity']
    running_max = equity_series.cummax()
    drawdown = equity_series - running_max
    max_dd = drawdown.min()
    max_dd_pct = (max_dd / initial_capital) * 100
    
    print(f"\n{'='*80}")
    print(f"RESULTS - {period_name}")
    print(f"{'='*80}")
    print(f"\n💰 Account Performance:")
    print(f"  Starting Capital:     ${initial_capital:.2f}")
    print(f"  Final Equity:         ${final_equity:.2f}")
    print(f"  Total Return:         {total_return:+.2f}%")
    print(f"  Annual Return:        {annual_return:+.2f}%")
    print(f"  Max Drawdown:         ${max_dd:.2f} ({max_dd_pct:.2f}%)")
    print(f"  Duration:             {duration_years:.2f} years")
    
    print(f"\n📊 Trading Stats:")
    print(f"  Total Trades:         {len(trades)}")
    print(f"  Winning Trades:       {len(winning_trades) if len(trades) > 0 else 0}")
    print(f"  Losing Trades:        {len(losing_trades) if len(trades) > 0 else 0}")
    print(f"  Win Rate:             {win_rate:.1f}%")
    print(f"  Profit Factor:        {profit_factor:.2f}")
    
    print(f"\n💵 Trade Analysis:")
    print(f"  Average Trade:        ${avg_trade:.2f}")
    print(f"  Average Winner:       ${avg_win:.2f}")
    print(f"  Average Loser:        ${avg_loss:.2f}")
    print(f"  Best Trade:           ${best_trade:.2f}")
    print(f"  Worst Trade:          ${worst_trade:.2f}")
    
    print(f"\n💸 OANDA Costs:")
    print(f"  Total Spread Cost:    ${broker.total_spread_cost:.2f}")
    print(f"  Total Slippage Cost:  ${broker.total_slippage_cost:.2f}")
    print(f"  Total Trading Costs:  ${broker.total_spread_cost + broker.total_slippage_cost:.2f}")
    print(f"  Cost % of Gross:      {((broker.total_spread_cost + broker.total_slippage_cost) / (total_wins + total_losses) * 100) if (total_wins + total_losses) > 0 else 0:.2f}%")
    
    print(f"\n{'='*80}")
    
    return {
        'period': period_name,
        'duration_years': float(duration_years),
        'initial_capital': initial_capital,
        'final_equity': float(final_equity),
        'total_return_pct': float(total_return),
        'annual_return_pct': float(annual_return),
        'max_drawdown': float(max_dd),
        'max_drawdown_pct': float(max_dd_pct),
        'total_trades': len(trades),
        'win_rate': float(win_rate),
        'profit_factor': float(profit_factor),
        'avg_trade': float(avg_trade),
        'total_spread_cost': float(broker.total_spread_cost),
        'total_slippage_cost': float(broker.total_slippage_cost),
        'trades': trades,
        'equity_curve': equity_curve
    }, equity_df, trades_df


def plot_comparison(results_2016_2020, results_2026, equity_2016_2020, equity_2026):
    """Plot comparison of both periods"""
    fig = plt.figure(figsize=(16, 12))
    fig.patch.set_facecolor('#0d1117')
    gs = fig.add_gridspec(3, 2, hspace=0.3, wspace=0.3)
    
    # 2016-2020 equity curve
    ax1 = fig.add_subplot(gs[0, 0])
    ax1.set_facecolor('#0d1117')
    ax1.plot(equity_2016_2020['time'], equity_2016_2020['equity'], 
            linewidth=2, color='#58a6ff', label='Equity')
    ax1.axhline(1000, color='white', linestyle='--', alpha=0.5, label='Start')
    ax1.fill_between(equity_2016_2020['time'], 1000, equity_2016_2020['equity'],
                     where=(equity_2016_2020['equity'] >= 1000),
                     color='#3fb950', alpha=0.2)
    ax1.fill_between(equity_2016_2020['time'], 1000, equity_2016_2020['equity'],
                     where=(equity_2016_2020['equity'] < 1000),
                     color='#f85149', alpha=0.2)
    ax1.set_xlabel('Date', fontsize=10, color='white', fontweight='bold')
    ax1.set_ylabel('Equity ($)', fontsize=10, color='white', fontweight='bold')
    ax1.set_title('2016-2020: Equity Curve', fontsize=12, color='white', fontweight='bold')
    ax1.legend(fontsize=9)
    ax1.tick_params(colors='white', labelsize=8)
    ax1.grid(True, alpha=0.2)
    for spine in ax1.spines.values():
        spine.set_color('white')
    
    # 2026 equity curve
    ax2 = fig.add_subplot(gs[0, 1])
    ax2.set_facecolor('#0d1117')
    ax2.plot(equity_2026['time'], equity_2026['equity'], 
            linewidth=2, color='#58a6ff', label='Equity')
    ax2.axhline(1000, color='white', linestyle='--', alpha=0.5, label='Start')
    ax2.fill_between(equity_2026['time'], 1000, equity_2026['equity'],
                     where=(equity_2026['equity'] >= 1000),
                     color='#3fb950', alpha=0.2)
    ax2.fill_between(equity_2026['time'], 1000, equity_2026['equity'],
                     where=(equity_2026['equity'] < 1000),
                     color='#f85149', alpha=0.2)
    ax2.set_xlabel('Date', fontsize=10, color='white', fontweight='bold')
    ax2.set_ylabel('Equity ($)', fontsize=10, color='white', fontweight='bold')
    ax2.set_title('2026: Equity Curve', fontsize=12, color='white', fontweight='bold')
    ax2.legend(fontsize=9)
    ax2.tick_params(colors='white', labelsize=8)
    ax2.grid(True, alpha=0.2)
    for spine in ax2.spines.values():
        spine.set_color('white')
    
    # Comparison bars
    ax3 = fig.add_subplot(gs[1, :])
    ax3.set_facecolor('#0d1117')
    
    metrics = ['Total Return\n(%)', 'Annual Return\n(%)', 'Win Rate\n(%)', 
               'Profit Factor', 'Max DD\n(%)']
    values_2016 = [
        results_2016_2020['total_return_pct'],
        results_2016_2020['annual_return_pct'],
        results_2016_2020['win_rate'],
        results_2016_2020['profit_factor'],
        abs(results_2016_2020['max_drawdown_pct'])
    ]
    values_2026 = [
        results_2026['total_return_pct'],
        results_2026['annual_return_pct'],
        results_2026['win_rate'],
        results_2026['profit_factor'],
        abs(results_2026['max_drawdown_pct'])
    ]
    
    x = np.arange(len(metrics))
    width = 0.35
    
    bars1 = ax3.bar(x - width/2, values_2016, width, label='2016-2020', 
                   color='#58a6ff', alpha=0.8)
    bars2 = ax3.bar(x + width/2, values_2026, width, label='2026', 
                   color='#3fb950', alpha=0.8)
    
    ax3.set_ylabel('Value', fontsize=11, color='white', fontweight='bold')
    ax3.set_title('Performance Comparison', fontsize=13, color='white', fontweight='bold')
    ax3.set_xticks(x)
    ax3.set_xticklabels(metrics, fontsize=10, color='white')
    ax3.legend(fontsize=10)
    ax3.tick_params(colors='white')
    ax3.grid(True, alpha=0.2, axis='y')
    for spine in ax3.spines.values():
        spine.set_color('white')
    
    # Add value labels on bars
    for bars in [bars1, bars2]:
        for bar in bars:
            height = bar.get_height()
            ax3.text(bar.get_x() + bar.get_width()/2., height,
                    f'{height:.1f}',
                    ha='center', va='bottom', fontsize=8, color='white')
    
    # Summary table
    ax4 = fig.add_subplot(gs[2, :])
    ax4.axis('off')
    
    table_data = [
        ['Metric', '2016-2020', '2026', 'Difference'],
        ['Final Equity', f"${results_2016_2020['final_equity']:.2f}", 
         f"${results_2026['final_equity']:.2f}",
         f"${results_2026['final_equity'] - results_2016_2020['final_equity']:.2f}"],
        ['Total Return', f"{results_2016_2020['total_return_pct']:+.2f}%", 
         f"{results_2026['total_return_pct']:+.2f}%",
         f"{results_2026['total_return_pct'] - results_2016_2020['total_return_pct']:+.2f}%"],
        ['Annual Return', f"{results_2016_2020['annual_return_pct']:+.2f}%", 
         f"{results_2026['annual_return_pct']:+.2f}%",
         f"{results_2026['annual_return_pct'] - results_2016_2020['annual_return_pct']:+.2f}%"],
        ['Profit Factor', f"{results_2016_2020['profit_factor']:.2f}", 
         f"{results_2026['profit_factor']:.2f}",
         f"{results_2026['profit_factor'] - results_2016_2020['profit_factor']:+.2f}"],
        ['Win Rate', f"{results_2016_2020['win_rate']:.1f}%", 
         f"{results_2026['win_rate']:.1f}%",
         f"{results_2026['win_rate'] - results_2016_2020['win_rate']:+.1f}%"],
        ['Total Trades', f"{results_2016_2020['total_trades']}", 
         f"{results_2026['total_trades']}",
         f"{results_2026['total_trades'] - results_2016_2020['total_trades']:+d}"],
    ]
    
    table = ax4.table(cellText=table_data, cellLoc='center', loc='center',
                     colWidths=[0.25, 0.25, 0.25, 0.25])
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1, 2)
    
    for i, row in enumerate(table_data):
        for j in range(len(row)):
            cell = table[(i, j)]
            if i == 0:
                cell.set_facecolor('#1f2937')
                cell.set_text_props(weight='bold', color='white')
            else:
                cell.set_facecolor('#0d1117')
                cell.set_text_props(color='white')
            cell.set_edgecolor('white')
    
    plt.suptitle('SMC Order Block Strategy - Historical Comparison', 
                fontsize=15, color='white', fontweight='bold', y=0.98)
    
    results_dir = Path(__file__).parent.parent / 'results'
    plt.savefig(results_dir / 'smc_historical_comparison.png', dpi=150, 
               bbox_inches='tight', facecolor='#0d1117')
    print(f"\n📊 Chart saved to {results_dir}/smc_historical_comparison.png")


def main():
    """Main backtest function"""
    cache_dir = Path(__file__).parent.parent / 'data' / 'forex_cache'
    
    # Load 2016-2020 data
    cache_2016_2020 = cache_dir / 'EURUSD_2016_2024_4h.parquet'
    if not cache_2016_2020.exists():
        print(f"Error: 2016-2020 data not found: {cache_2016_2020}")
        return None
    
    ohlc_full = pd.read_parquet(cache_2016_2020)
    if 'open' in ohlc_full.columns:
        ohlc_full.columns = [c.capitalize() for c in ohlc_full.columns]
    
    # Filter to 2016-2020
    ohlc_2016_2020 = ohlc_full[(ohlc_full.index >= '2016-01-01') & 
                                (ohlc_full.index <= '2020-12-31')]
    
    print(f"\nLoaded 2016-2020 data: {len(ohlc_2016_2020)} bars")
    print(f"Period: {ohlc_2016_2020.index[0]} to {ohlc_2016_2020.index[-1]}")
    
    # Run backtest on 2016-2020
    results_2016_2020, equity_2016_2020, trades_2016_2020 = backtest_with_oanda_costs(
        ohlc_2016_2020,
        initial_capital=1000.0,
        leverage=50.0,
        risk_per_trade=0.01,
        atr_sl_mult=1.0,
        atr_tp_mult=3.0,
        period_name="2016-2020"
    )
    
    # Load 2026 results for comparison
    results_dir = Path(__file__).parent.parent / 'results'
    with open(results_dir / 'smc_oanda_test_summary.json', 'r') as f:
        results_2026_summary = json.load(f)
    
    with open(results_dir / 'smc_oanda_test_full.json', 'r') as f:
        results_2026_full = json.load(f)
    
    # Convert 2026 equity curve
    equity_2026 = pd.DataFrame([
        {**ec, 'time': pd.Timestamp(ec['time'])} 
        for ec in results_2026_full['equity_curve']
    ])
    
    # Calculate annualized for 2026 (6.5 months)
    results_2026_summary['annual_return_pct'] = results_2026_summary['total_return_pct'] * (12 / 6.5)
    
    # Save 2016-2020 results
    summary = {k: v for k, v in results_2016_2020.items() 
              if k not in ['equity_curve', 'trades']}
    with open(results_dir / 'smc_backtest_2016_2020_summary.json', 'w') as f:
        json.dump(summary, f, indent=2)
    
    results_json = results_2016_2020.copy()
    results_json['equity_curve'] = [
        {**ec, 'time': ec['time'].isoformat()} 
        for ec in results_json['equity_curve']
    ]
    results_json['trades'] = [
        {**t, 'entry_time': t['entry_time'].isoformat(), 
         'exit_time': t['exit_time'].isoformat()} 
        for t in results_json['trades']
    ]
    with open(results_dir / 'smc_backtest_2016_2020_full.json', 'w') as f:
        json.dump(results_json, f, indent=2)
    
    # Plot comparison
    plot_comparison(results_2016_2020, results_2026_summary, 
                   equity_2016_2020, equity_2026)
    
    print(f"\n💾 Results saved to {results_dir}/")
    
    # Print comparison summary
    print(f"\n{'='*80}")
    print(f"PERFORMANCE COMPARISON SUMMARY")
    print(f"{'='*80}")
    print(f"\n2016-2020 Results:")
    print(f"  Duration:             {results_2016_2020['duration_years']:.2f} years")
    print(f"  Final Equity:         ${results_2016_2020['final_equity']:.2f}")
    print(f"  Total Return:         {results_2016_2020['total_return_pct']:+.2f}%")
    print(f"  Annual Return:        {results_2016_2020['annual_return_pct']:+.2f}%")
    print(f"  Max Drawdown:         {results_2016_2020['max_drawdown_pct']:.2f}%")
    print(f"  Profit Factor:        {results_2016_2020['profit_factor']:.2f}")
    print(f"  Win Rate:             {results_2016_2020['win_rate']:.1f}%")
    print(f"  Total Trades:         {results_2016_2020['total_trades']}")
    
    print(f"\n2026 Results:")
    print(f"  Duration:             0.54 years (6.5 months)")
    print(f"  Final Equity:         ${results_2026_summary['final_equity']:.2f}")
    print(f"  Total Return:         {results_2026_summary['total_return_pct']:+.2f}%")
    print(f"  Annual Return:        {results_2026_summary['annual_return_pct']:+.2f}%")
    print(f"  Max Drawdown:         {results_2026_summary['max_drawdown_pct']:.2f}%")
    print(f"  Profit Factor:        {results_2026_summary['profit_factor']:.2f}")
    print(f"  Win Rate:             {results_2026_summary['win_rate']:.1f}%")
    print(f"  Total Trades:         {results_2026_summary['total_trades']}")
    
    print(f"\n{'='*80}")
    
    return results_2016_2020, results_2026_summary


if __name__ == '__main__':
    main()
