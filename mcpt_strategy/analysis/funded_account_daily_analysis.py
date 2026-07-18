"""
Daily Analysis of Funded Account Performance
Shows day-by-day compliance with rules
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime

from core.indicators import TechnicalIndicators


class OANDABroker:
    """Realistic OANDA broker model"""
    
    def __init__(self, initial_capital: float = 1000, leverage: int = 50, 
                 risk_per_trade: float = 0.01):
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.leverage = leverage
        self.risk_per_trade = risk_per_trade
        self.spread_pips = 0.8
        self.slippage_pips = 0.2
        
    def calculate_position_size(self, stop_loss_pips: float, price: float) -> float:
        risk_amount = self.capital * self.risk_per_trade
        pip_value = 10
        max_position_lots = (risk_amount / stop_loss_pips) / pip_value
        max_position_value = max_position_lots * 100000
        
        max_with_leverage = self.capital * self.leverage
        if max_position_value > max_with_leverage:
            max_position_value = max_with_leverage
        
        return max_position_value / price
    
    def apply_costs(self, entry_price: float, direction: int) -> float:
        total_cost_pips = self.spread_pips + self.slippage_pips
        pip_size = 0.0001
        cost = total_cost_pips * pip_size
        
        if direction > 0:
            return entry_price + cost
        else:
            return entry_price - cost


def identify_order_blocks(ohlc: pd.DataFrame, lookback: int = 5):
    bullish_ob = pd.Series(False, index=ohlc.index)
    bearish_ob = pd.Series(False, index=ohlc.index)
    
    close_price = ohlc['Close']
    open_price = ohlc['Open']
    
    body = abs(close_price - open_price)
    avg_body = body.rolling(20).mean()
    
    strong_bullish = (close_price > open_price) & (body > avg_body * 1.5)
    strong_bearish = (close_price < open_price) & (body > avg_body * 1.5)
    
    for i in range(lookback, len(ohlc)):
        if strong_bullish.iloc[i]:
            for j in range(1, min(lookback, i)):
                if close_price.iloc[i-j] < open_price.iloc[i-j]:
                    bullish_ob.iloc[i-j] = True
                    break
        
        if strong_bearish.iloc[i]:
            for j in range(1, min(lookback, i)):
                if close_price.iloc[i-j] > open_price.iloc[i-j]:
                    bearish_ob.iloc[i-j] = True
                    break
    
    return bullish_ob, bearish_ob


def identify_structure(ohlc: pd.DataFrame, swing_length: int = 5):
    high = ohlc['High']
    low = ohlc['Low']
    
    rolling_high = high.rolling(swing_length).max()
    rolling_low = low.rolling(swing_length).min()
    
    structure = pd.Series(0, index=ohlc.index)
    structure[high > rolling_high.shift(1)] = 1
    structure[low < rolling_low.shift(1)] = -1
    
    return structure.ffill().fillna(0)


def smc_order_block_strategy(ohlc: pd.DataFrame) -> pd.Series:
    bullish_ob, bearish_ob = identify_order_blocks(ohlc, 5)
    structure = identify_structure(ohlc)
    
    signal = pd.Series(0, index=ohlc.index, dtype=float)
    signal[bullish_ob & (structure >= 0)] = 1
    signal[bearish_ob & (structure <= 0)] = -1
    
    return signal.shift(1).fillna(0)


def backtest_daily_tracking(ohlc: pd.DataFrame, starting_balance: float = 249.03):
    """Track day-by-day performance"""
    
    broker = OANDABroker(starting_balance, 50, 0.01)
    signals = smc_order_block_strategy(ohlc)
    atr = TechnicalIndicators.atr(ohlc, 14)
    
    position = 0
    entry_price = 0
    stop_loss = 0
    take_profit = 0
    position_size = 0
    
    daily_data = {}
    current_day = None
    
    max_loss_limit = starting_balance * 0.10
    daily_loss_limit = starting_balance * 0.05
    peak_balance = starting_balance
    
    for i in range(1, len(ohlc)):
        date_str = ohlc.index[i].strftime('%Y-%m-%d')
        current_price = ohlc['Close'].iloc[i]
        current_atr = atr.iloc[i]
        
        # Initialize day
        if date_str not in daily_data:
            daily_data[date_str] = {
                'start_balance': broker.capital,
                'trades': 0,
                'pnl': 0,
                'max_loss_pct': 0,
                'daily_loss_pct': 0,
                'violations': []
            }
        
        # Check for exit
        if position != 0:
            pnl = 0
            exit_reason = None
            
            if position > 0:
                if current_price <= stop_loss:
                    pnl = (stop_loss - entry_price) * position_size
                    exit_reason = 'SL'
                elif current_price >= take_profit:
                    pnl = (take_profit - entry_price) * position_size
                    exit_reason = 'TP'
            else:
                if current_price >= stop_loss:
                    pnl = (entry_price - stop_loss) * position_size
                    exit_reason = 'SL'
                elif current_price <= take_profit:
                    pnl = (entry_price - take_profit) * position_size
                    exit_reason = 'TP'
            
            if exit_reason:
                broker.capital += pnl
                peak_balance = max(peak_balance, broker.capital)
                
                # Update daily tracking
                daily_data[date_str]['trades'] += 1
                daily_data[date_str]['pnl'] += pnl
                daily_data[date_str]['end_balance'] = broker.capital
                
                # Check max loss
                total_loss = starting_balance - broker.capital
                max_loss_pct = (total_loss / starting_balance) * 100
                daily_data[date_str]['max_loss_pct'] = max_loss_pct
                
                if total_loss > max_loss_limit:
                    daily_data[date_str]['violations'].append(f"MAX LOSS: ${total_loss:.2f} > ${max_loss_limit:.2f}")
                
                # Check daily loss
                daily_loss = -daily_data[date_str]['pnl']
                daily_loss_pct = (daily_loss / starting_balance) * 100
                daily_data[date_str]['daily_loss_pct'] = daily_loss_pct
                
                if daily_loss > daily_loss_limit:
                    daily_data[date_str]['violations'].append(f"DAILY LOSS: ${daily_loss:.2f} > ${daily_loss_limit:.2f}")
                
                position = 0
        
        # Check for entry
        if position == 0 and signals.iloc[i] != 0:
            if pd.notna(current_atr) and current_atr > 0:
                direction = int(signals.iloc[i])
                
                stop_pips = current_atr * 10000
                sl_distance = stop_pips * 0.0001
                tp_distance = sl_distance * 3
                
                if direction > 0:
                    entry_price = broker.apply_costs(current_price, direction)
                    stop_loss = entry_price - sl_distance
                    take_profit = entry_price + tp_distance
                else:
                    entry_price = broker.apply_costs(current_price, direction)
                    stop_loss = entry_price + sl_distance
                    take_profit = entry_price - tp_distance
                
                position_size = broker.calculate_position_size(stop_pips, current_price)
                position = direction
        
        daily_data[date_str]['end_balance'] = broker.capital
    
    # Convert to DataFrame
    daily_df = []
    for date, data in daily_data.items():
        if data['trades'] > 0:
            daily_df.append({
                'date': date,
                'start_balance': data['start_balance'],
                'end_balance': data['end_balance'],
                'pnl': data['pnl'],
                'pnl_pct': (data['pnl'] / data['start_balance']) * 100,
                'trades': data['trades'],
                'max_loss_pct': data['max_loss_pct'],
                'daily_loss_pct': data['daily_loss_pct'],
                'violations': ', '.join(data['violations']) if data['violations'] else 'NONE'
            })
    
    return pd.DataFrame(daily_df)


def main():
    """Generate daily analysis"""
    print("="*100)
    print("FUNDED ACCOUNT - DAILY COMPLIANCE ANALYSIS")
    print("="*100)
    
    # Load data
    cache_dir = Path(__file__).parent.parent / 'data' / 'forex_cache'
    cache_file = cache_dir / 'EURUSD_2026_current_4h.parquet'
    
    ohlc = pd.read_parquet(cache_file)
    if 'open' in ohlc.columns:
        ohlc.columns = [c.capitalize() for c in ohlc.columns]
    
    # Run backtest
    daily_df = backtest_daily_tracking(ohlc, 249.03)
    
    print(f"\nTotal Trading Days: {len(daily_df)}")
    print(f"Days with Violations: {len(daily_df[daily_df['violations'] != 'NONE'])}")
    print(f"\n{'='*100}\n")
    
    # Show worst days
    print("📉 WORST 10 DAYS (Highest Loss %):\n")
    worst_days = daily_df.nsmallest(10, 'pnl_pct')
    print(worst_days[['date', 'pnl', 'pnl_pct', 'end_balance', 'violations']].to_string(index=False))
    
    print(f"\n{'='*100}\n")
    
    # Show best days
    print("📈 BEST 10 DAYS (Highest Gain %):\n")
    best_days = daily_df.nlargest(10, 'pnl_pct')
    print(best_days[['date', 'pnl', 'pnl_pct', 'end_balance', 'violations']].to_string(index=False))
    
    print(f"\n{'='*100}\n")
    
    # Statistics
    print("📊 DAILY STATISTICS:\n")
    print(f"  Average Daily PnL: ${daily_df['pnl'].mean():.2f} ({daily_df['pnl_pct'].mean():.2f}%)")
    print(f"  Best Day PnL: ${daily_df['pnl'].max():.2f} ({daily_df['pnl_pct'].max():.2f}%)")
    print(f"  Worst Day PnL: ${daily_df['pnl'].min():.2f} ({daily_df['pnl_pct'].min():.2f}%)")
    print(f"  Daily Win Rate: {(daily_df['pnl'] > 0).sum() / len(daily_df) * 100:.1f}%")
    print(f"\n  Max Drawdown Ever: {daily_df['max_loss_pct'].max():.2f}% (Limit: 10.00%)")
    print(f"  Worst Daily Loss: {daily_df['daily_loss_pct'].max():.2f}% (Limit: 5.00%)")
    
    print(f"\n{'='*100}\n")
    print(f"✅ COMPLIANCE: {'ALL RULES PASSED' if len(daily_df[daily_df['violations'] != 'NONE']) == 0 else 'VIOLATIONS FOUND'}")
    print(f"{'='*100}\n")
    
    # Create visualization
    fig, axes = plt.subplots(3, 1, figsize=(14, 10))
    
    # Equity curve
    axes[0].plot(daily_df['date'], daily_df['end_balance'], 'b-', linewidth=2, label='Account Balance')
    axes[0].axhline(y=249.03, color='gray', linestyle='--', label='Starting Balance')
    axes[0].axhline(y=249.03 * 1.10, color='green', linestyle='--', label='Profit Target (+10%)')
    axes[0].axhline(y=249.03 * 0.90, color='red', linestyle='--', label='Max Loss Limit (-10%)')
    axes[0].set_title('Account Balance Over Time', fontsize=14, fontweight='bold')
    axes[0].set_ylabel('Balance ($)')
    axes[0].legend()
    axes[0].grid(True, alpha=0.3)
    
    # Daily PnL
    colors = ['green' if x > 0 else 'red' for x in daily_df['pnl']]
    axes[1].bar(daily_df['date'], daily_df['pnl'], color=colors, alpha=0.7)
    axes[1].axhline(y=0, color='black', linestyle='-', linewidth=0.5)
    axes[1].axhline(y=-249.03*0.05, color='red', linestyle='--', label='Daily Loss Limit (-5%)')
    axes[1].set_title('Daily Profit/Loss', fontsize=14, fontweight='bold')
    axes[1].set_ylabel('Daily PnL ($)')
    axes[1].legend()
    axes[1].grid(True, alpha=0.3)
    
    # Cumulative drawdown %
    axes[2].fill_between(daily_df['date'], 0, -daily_df['max_loss_pct'], color='red', alpha=0.3)
    axes[2].plot(daily_df['date'], -daily_df['max_loss_pct'], 'r-', linewidth=2, label='Drawdown from Start')
    axes[2].axhline(y=-10, color='red', linestyle='--', linewidth=2, label='Max Loss Limit (-10%)')
    axes[2].set_title('Drawdown from Starting Balance', fontsize=14, fontweight='bold')
    axes[2].set_ylabel('Drawdown (%)')
    axes[2].set_xlabel('Date')
    axes[2].legend()
    axes[2].grid(True, alpha=0.3)
    
    plt.xticks(rotation=45)
    plt.tight_layout()
    
    # Save
    output_file = Path(__file__).parent.parent / 'results' / 'funded_account_daily_analysis.png'
    plt.savefig(output_file, dpi=150, bbox_inches='tight')
    print(f"📊 Chart saved to {output_file}")
    
    # Save CSV
    csv_file = Path(__file__).parent.parent / 'results' / 'funded_account_daily_data.csv'
    daily_df.to_csv(csv_file, index=False)
    print(f"📄 Daily data saved to {csv_file}")


if __name__ == '__main__':
    main()
