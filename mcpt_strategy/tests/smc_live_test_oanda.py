"""
SMC Order Block Strategy - Live Test with OANDA Conditions
Test on 2025+ data with realistic spreads and commissions
Starting: $1000, Leverage: 50:1
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
    
    # OANDA EUR/USD spreads (pips) - varies by market conditions
    SPREAD_PIPS = {
        'normal': 0.8,      # Normal market hours
        'volatile': 1.5,    # News events, high volatility
        'overnight': 2.0    # Low liquidity periods
    }
    
    # OANDA commission structure (they don't charge commission, but spread is their fee)
    # We'll use average spread
    AVG_SPREAD_PIPS = 1.0
    
    # Pip value for EUR/USD (standard lot = 100,000 units)
    PIP_VALUE_PER_LOT = 10.0  # $10 per pip for 1 standard lot
    
    # Slippage estimate (pips) - realistic slippage on market orders
    SLIPPAGE_PIPS = 0.3
    
    def __init__(self, initial_capital: float = 1000.0, leverage: float = 50.0):
        self.initial_capital = initial_capital
        self.leverage = leverage
        self.equity = initial_capital
        self.balance = initial_capital
        self.total_spread_cost = 0.0
        self.total_slippage_cost = 0.0
        
    def calculate_position_size(self, price: float, risk_pct: float = 0.01, 
                               stop_distance_pips: float = 10.0) -> float:
        """
        Calculate position size in lots based on risk
        OANDA allows fractional lots (micro lots = 0.001)
        """
        risk_amount = self.equity * risk_pct
        
        # Position size based on risk
        # risk_amount = position_size * pip_value * stop_distance_pips
        # position_size = risk_amount / (pip_value * stop_distance_pips)
        
        # For micro lots (1000 units), pip value = $0.10
        # For mini lots (10000 units), pip value = $1.00
        # For standard lots (100000 units), pip value = $10.00
        
        position_size_lots = risk_amount / (self.PIP_VALUE_PER_LOT * stop_distance_pips)
        
        # Apply leverage limit
        max_position_value = self.equity * self.leverage
        max_position_lots = max_position_value / (100000 * price)  # 100k units per lot
        
        position_size_lots = min(position_size_lots, max_position_lots)
        
        # OANDA minimum is 1 micro lot (0.001 standard lots)
        return max(position_size_lots, 0.001)
    
    def calculate_spread_cost(self, position_size_lots: float) -> float:
        """Calculate spread cost in dollars"""
        spread_cost = self.AVG_SPREAD_PIPS * self.PIP_VALUE_PER_LOT * position_size_lots
        return spread_cost
    
    def calculate_slippage_cost(self, position_size_lots: float) -> float:
        """Calculate slippage cost in dollars"""
        slippage_cost = self.SLIPPAGE_PIPS * self.PIP_VALUE_PER_LOT * position_size_lots
        return slippage_cost
    
    def execute_trade(self, entry_price: float, exit_price: float, 
                     position_size_lots: float, direction: int) -> float:
        """
        Execute trade and return P&L including all costs
        direction: 1 for long, -1 for short
        """
        # Calculate pip movement
        if direction == 1:  # Long
            pip_movement = (exit_price - entry_price) * 10000  # EUR/USD: 4 decimal places
        else:  # Short
            pip_movement = (entry_price - exit_price) * 10000
        
        # Gross P&L
        gross_pnl = pip_movement * self.PIP_VALUE_PER_LOT * position_size_lots
        
        # Costs
        spread_cost = self.calculate_spread_cost(position_size_lots)
        slippage_cost = self.calculate_slippage_cost(position_size_lots)
        
        # Net P&L
        net_pnl = gross_pnl - spread_cost - slippage_cost
        
        # Track costs
        self.total_spread_cost += spread_cost
        self.total_slippage_cost += slippage_cost
        
        return net_pnl


def identify_order_blocks(ohlc: pd.DataFrame, lookback: int = 5):
    """Identify Smart Money order blocks"""
    bullish_ob = pd.Series(False, index=ohlc.index)
    bearish_ob = pd.Series(False, index=ohlc.index)
    
    close = ohlc['Close']
    open_price = ohlc['Open']
    
    # Identify strong moves
    body = abs(close - open_price)
    avg_body = body.rolling(20).mean()
    strong_bullish = (close > open_price) & (body > avg_body * 1.5)
    strong_bearish = (close < open_price) & (body > avg_body * 1.5)
    
    # Find order blocks
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
    atr_tp_mult: float = 3.0
):
    """
    Backtest SMC strategy with OANDA realistic costs
    """
    print(f"\n{'='*80}")
    print(f"SMC ORDER BLOCK STRATEGY - OANDA LIVE TEST")
    print(f"{'='*80}")
    print(f"Initial Capital:      ${initial_capital:.2f}")
    print(f"Leverage:             {leverage}:1")
    print(f"Risk Per Trade:       {risk_per_trade*100:.1f}%")
    print(f"OANDA Spread:         {OANDABroker.AVG_SPREAD_PIPS:.1f} pips")
    print(f"Estimated Slippage:   {OANDABroker.SLIPPAGE_PIPS:.1f} pips")
    print(f"Period:               {ohlc.index[0]} to {ohlc.index[-1]}")
    print(f"Bars:                 {len(ohlc)}")
    print(f"{'='*80}\n")
    
    # Initialize broker
    broker = OANDABroker(initial_capital, leverage)
    
    # Generate signals
    signal = smc_order_block_strategy(ohlc, ob_lookback=5, use_structure=True)
    
    # Calculate ATR for stops/targets
    ti = TechnicalIndicators
    atr = ti.atr(ohlc, 14)
    
    # Initialize tracking
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
        
        # Check existing position
        if position != 0:
            exit_triggered = False
            exit_price = current_price
            exit_reason = ''
            
            # Check stop loss
            if position == 1 and current_price <= stop_loss:
                exit_triggered = True
                exit_price = stop_loss
                exit_reason = 'STOP_LOSS'
            elif position == -1 and current_price >= stop_loss:
                exit_triggered = True
                exit_price = stop_loss
                exit_reason = 'STOP_LOSS'
            
            # Check take profit
            elif position == 1 and current_price >= take_profit:
                exit_triggered = True
                exit_price = take_profit
                exit_reason = 'TAKE_PROFIT'
            elif position == -1 and current_price <= take_profit:
                exit_triggered = True
                exit_price = take_profit
                exit_reason = 'TAKE_PROFIT'
            
            if exit_triggered:
                # Execute trade with OANDA costs
                pnl = broker.execute_trade(entry_price, exit_price, 
                                          position_size_lots, position)
                
                broker.equity += pnl
                broker.balance += pnl
                
                # Record trade
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
        
        # Record equity
        equity_curve.append({
            'time': current_time,
            'equity': broker.equity,
            'balance': broker.balance,
            'position': position
        })
        
        # Entry logic
        if position == 0 and current_signal != 0 and not np.isnan(current_atr):
            # Calculate position size
            stop_distance_pips = (current_atr * atr_sl_mult) * 10000
            position_size_lots = broker.calculate_position_size(
                current_price, risk_per_trade, stop_distance_pips
            )
            
            entry_price = current_price
            entry_time = current_time
            stop_pips = stop_distance_pips
            
            if current_signal == 1:
                # Long entry
                position = 1
                stop_loss = entry_price - (current_atr * atr_sl_mult)
                take_profit = entry_price + (current_atr * atr_tp_mult)
            else:
                # Short entry
                position = -1
                stop_loss = entry_price + (current_atr * atr_sl_mult)
                take_profit = entry_price - (current_atr * atr_tp_mult)
    
    # Close any remaining position
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
    
    # Calculate statistics
    equity_df = pd.DataFrame(equity_curve)
    trades_df = pd.DataFrame(trades) if trades else pd.DataFrame()
    
    final_equity = broker.equity
    total_return = (final_equity - initial_capital) / initial_capital * 100
    
    if len(trades) > 0:
        winning_trades = trades_df[trades_df['pnl'] > 0]
        losing_trades = trades_df[trades_df['pnl'] < 0]
        
        win_rate = len(winning_trades) / len(trades) * 100
        avg_win = winning_trades['pnl'].mean() if len(winning_trades) > 0 else 0
        avg_loss = losing_trades['pnl'].mean() if len(losing_trades) > 0 else 0
        
        total_wins = winning_trades['pnl'].sum() if len(winning_trades) > 0 else 0
        total_losses = abs(losing_trades['pnl'].sum()) if len(losing_trades) > 0 else 0
        profit_factor = total_wins / total_losses if total_losses > 0 else 0
        
        # Average trade
        avg_trade = trades_df['pnl'].mean()
        
        # Best/worst trades
        best_trade = trades_df['pnl'].max()
        worst_trade = trades_df['pnl'].min()
    else:
        win_rate = avg_win = avg_loss = profit_factor = 0
        avg_trade = best_trade = worst_trade = 0
        total_wins = total_losses = 0
    
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
    print(f"\n💰 Account Performance:")
    print(f"  Starting Capital:     ${initial_capital:.2f}")
    print(f"  Final Equity:         ${final_equity:.2f}")
    print(f"  Total Return:         {total_return:+.2f}%")
    print(f"  Max Drawdown:         ${max_dd:.2f} ({max_dd_pct:.2f}%)")
    
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
        'initial_capital': initial_capital,
        'final_equity': float(final_equity),
        'total_return_pct': float(total_return),
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


def plot_results(equity_df, trades_df, initial_capital):
    """Plot equity curve and trade analysis"""
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10))
    fig.patch.set_facecolor('#0d1117')
    
    # Equity curve
    ax1.set_facecolor('#0d1117')
    ax1.plot(equity_df['time'], equity_df['equity'], linewidth=2, 
            color='#58a6ff', label='Equity')
    ax1.axhline(initial_capital, color='white', linestyle='--', 
               alpha=0.5, label='Starting Capital')
    ax1.fill_between(equity_df['time'], initial_capital, equity_df['equity'],
                     where=(equity_df['equity'] >= initial_capital),
                     color='#3fb950', alpha=0.2)
    ax1.fill_between(equity_df['time'], initial_capital, equity_df['equity'],
                     where=(equity_df['equity'] < initial_capital),
                     color='#f85149', alpha=0.2)
    ax1.set_xlabel('Date', fontsize=11, color='white', fontweight='bold')
    ax1.set_ylabel('Equity ($)', fontsize=11, color='white', fontweight='bold')
    ax1.set_title('SMC Order Block Strategy - OANDA Live Test', 
                 fontsize=14, color='white', fontweight='bold')
    ax1.legend(fontsize=10)
    ax1.tick_params(colors='white')
    ax1.grid(True, alpha=0.2)
    for spine in ax1.spines.values():
        spine.set_color('white')
    
    # Trade P&L
    if len(trades_df) > 0:
        ax2.set_facecolor('#0d1117')
        colors = ['#3fb950' if pnl > 0 else '#f85149' for pnl in trades_df['pnl']]
        ax2.bar(range(len(trades_df)), trades_df['pnl'], color=colors, alpha=0.7)
        ax2.axhline(0, color='white', linestyle='-', linewidth=1)
        ax2.set_xlabel('Trade Number', fontsize=11, color='white', fontweight='bold')
        ax2.set_ylabel('P&L ($)', fontsize=11, color='white', fontweight='bold')
        ax2.set_title('Individual Trade P&L', fontsize=12, color='white', fontweight='bold')
        ax2.tick_params(colors='white')
        ax2.grid(True, alpha=0.2)
        for spine in ax2.spines.values():
            spine.set_color('white')
    
    plt.tight_layout()
    
    results_dir = Path(__file__).parent.parent / 'results'
    plt.savefig(results_dir / 'smc_oanda_live_test.png', dpi=150, 
               bbox_inches='tight', facecolor='#0d1117')
    print(f"\n📊 Chart saved to {results_dir}/smc_oanda_live_test.png")


def main():
    """Main test function"""
    # Load 2025+ data
    cache_dir = Path(__file__).parent.parent / 'data' / 'forex_cache'
    
    # Load 2026 data (this is our 2025+ test set)
    cache_2026 = cache_dir / 'EURUSD_2026_current_4h.parquet'
    
    if not cache_2026.exists():
        print(f"Error: 2025+ data not found: {cache_2026}")
        return None
    
    ohlc = pd.read_parquet(cache_2026)
    if 'open' in ohlc.columns:
        ohlc.columns = [c.capitalize() for c in ohlc.columns]
    
    print(f"\nLoaded {len(ohlc)} bars from {ohlc.index[0]} to {ohlc.index[-1]}")
    
    # Run backtest
    results, equity_df, trades_df = backtest_with_oanda_costs(
        ohlc,
        initial_capital=1000.0,
        leverage=50.0,
        risk_per_trade=0.01,
        atr_sl_mult=1.0,
        atr_tp_mult=3.0
    )
    
    # Save results
    results_dir = Path(__file__).parent.parent / 'results'
    results_dir.mkdir(parents=True, exist_ok=True)
    
    # Summary
    summary = {k: v for k, v in results.items() if k not in ['equity_curve', 'trades']}
    with open(results_dir / 'smc_oanda_test_summary.json', 'w') as f:
        json.dump(summary, f, indent=2)
    
    # Full results
    results_json = results.copy()
    results_json['equity_curve'] = [
        {**ec, 'time': ec['time'].isoformat()} 
        for ec in results_json['equity_curve']
    ]
    results_json['trades'] = [
        {**t, 'entry_time': t['entry_time'].isoformat(), 
         'exit_time': t['exit_time'].isoformat()} 
        for t in results_json['trades']
    ]
    with open(results_dir / 'smc_oanda_test_full.json', 'w') as f:
        json.dump(results_json, f, indent=2)
    
    # Plot
    plot_results(equity_df, trades_df, results['initial_capital'])
    
    print(f"\n💾 Results saved to {results_dir}/")
    
    return results


if __name__ == '__main__':
    results = main()
