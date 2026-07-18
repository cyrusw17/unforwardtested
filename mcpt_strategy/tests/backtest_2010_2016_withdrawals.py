"""
2010-2016 Backtest with Weekly Withdrawals
Tests SMC strategy on $100k account with profit withdrawals
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))

import pandas as pd
import numpy as np
from typing import Dict, List
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
import requests
from io import BytesIO

from core.indicators import TechnicalIndicators


def fetch_dukascopy_data(pair: str, year: int, month: int) -> pd.DataFrame:
    """Fetch monthly data from Dukascopy"""
    base_url = "https://datafeed.dukascopy.com/datafeed"
    pair_path = pair[:3] + "/" + pair[3:]
    
    all_data = []
    days_in_month = pd.Period(f"{year}-{month:02d}").days_in_month
    
    for day in range(1, days_in_month + 1):
        try:
            url = f"{base_url}/{pair_path}/{year}/{month-1:02d}/{day:02d}/04h_ticks.bi5"
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                # Parse bi5 format (simplified)
                data = response.content
                if len(data) > 0:
                    # Dukascopy bi5 format is compressed, we'll use a simpler approach
                    # For production, use proper bi5 parsing
                    pass
        except:
            pass
    
    return pd.DataFrame()


def fetch_2010_2016_data(pair: str = 'EURUSD') -> pd.DataFrame:
    """Fetch 2010-2016 data from Dukascopy or use cache"""
    cache_dir = Path(__file__).parent.parent / 'data' / 'forex_cache'
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f'{pair}_2010_2016_4h.parquet'
    
    if cache_file.exists():
        print(f"Loading cached data from {cache_file}")
        df = pd.read_parquet(cache_file)
        return df
    
    print(f"Fetching {pair} data for 2010-2016...")
    print("This may take several minutes...")
    
    all_data = []
    
    for year in range(2010, 2017):
        print(f"  Fetching {year}...")
        
        for month in range(1, 13):
            if year == 2016 and month > 12:
                break
            
            # Use Yahoo Finance as fallback since Dukascopy requires complex parsing
            try:
                import yfinance as yf
                ticker = f"{pair[:3]}{pair[3:]}=X"
                
                start_date = f"{year}-{month:02d}-01"
                if month == 12:
                    end_date = f"{year+1}-01-01"
                else:
                    end_date = f"{year}-{month+1:02d}-01"
                
                data = yf.download(ticker, start=start_date, end=end_date, interval='1h', progress=False)
                
                if not data.empty:
                    # Resample to 4H
                    data_4h = data.resample('4H').agg({
                        'Open': 'first',
                        'High': 'max',
                        'Low': 'min',
                        'Close': 'last',
                        'Volume': 'sum'
                    }).dropna()
                    
                    all_data.append(data_4h)
            except Exception as e:
                print(f"    Error fetching {year}-{month:02d}: {e}")
    
    if all_data:
        df = pd.concat(all_data)
        df = df.sort_index()
        df.columns = [c.capitalize() for c in df.columns]
        
        # Save to cache
        df.to_parquet(cache_file)
        print(f"Data cached to {cache_file}")
        return df
    
    return pd.DataFrame()


class OANDABroker:
    """Realistic OANDA broker model"""
    
    def __init__(self, initial_capital: float = 100000, leverage: int = 50, 
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


def backtest_with_weekly_withdrawals(ohlc: pd.DataFrame, starting_balance: float = 100000,
                                      withdrawal_threshold: float = 101000):
    """Backtest with weekly withdrawals above threshold"""
    
    broker = OANDABroker(starting_balance, 50, 0.01)
    signals = smc_order_block_strategy(ohlc)
    atr = TechnicalIndicators.atr(ohlc, 14)
    
    position = 0
    entry_price = 0
    stop_loss = 0
    take_profit = 0
    position_size = 0
    
    trades = []
    equity_curve = []
    withdrawals = []
    
    total_withdrawn = 0
    current_week_start = None
    last_withdrawal_week = None
    
    for i in range(1, len(ohlc)):
        current_date = ohlc.index[i]
        current_price = ohlc['Close'].iloc[i]
        current_atr = atr.iloc[i]
        
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
                
                trades.append({
                    'exit_date': current_date,
                    'exit_price': current_price,
                    'pnl': pnl,
                    'exit_reason': exit_reason,
                    'balance': broker.capital
                })
                
                position = 0
        
        # Check for weekly withdrawal
        current_week = current_date.isocalendar()[1]
        current_year = current_date.year
        week_id = f"{current_year}-W{current_week}"
        
        if last_withdrawal_week != week_id and broker.capital > withdrawal_threshold:
            withdrawal_amount = broker.capital - withdrawal_threshold
            total_withdrawn += withdrawal_amount
            broker.capital = withdrawal_threshold
            
            withdrawals.append({
                'date': current_date,
                'amount': withdrawal_amount,
                'balance_after': broker.capital,
                'total_withdrawn': total_withdrawn
            })
            
            last_withdrawal_week = week_id
        
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
                
                trades.append({
                    'entry_date': current_date,
                    'direction': 'LONG' if direction > 0 else 'SHORT',
                    'entry_price': entry_price,
                    'balance': broker.capital
                })
        
        equity_curve.append({
            'date': current_date,
            'equity': broker.capital,
            'total_withdrawn': total_withdrawn
        })
    
    return {
        'trades': pd.DataFrame(trades) if trades else pd.DataFrame(),
        'equity_curve': pd.DataFrame(equity_curve),
        'withdrawals': pd.DataFrame(withdrawals) if withdrawals else pd.DataFrame(),
        'final_balance': broker.capital,
        'total_withdrawn': total_withdrawn,
        'total_profit': (broker.capital - starting_balance) + total_withdrawn,
        'total_trades': len([t for t in trades if 'exit_date' in t])
    }


def main():
    print("="*80)
    print("2010-2016 BACKTEST - $100K WITH WEEKLY WITHDRAWALS")
    print("="*80)
    print("\nStrategy: SMC Order Block + Structure")
    print("Account: $100,000")
    print("Withdrawal Rule: Withdraw anything > $101,000 at end of each week\n")
    
    # Load the 2010-2016 data
    cache_dir = Path(__file__).parent.parent / 'data' / 'forex_cache'
    cache_file = cache_dir / 'EURUSD_2010_2016_4h.parquet'
    
    if not cache_file.exists():
        print("2010-2016 data not found. Fetching...")
        import subprocess
        result = subprocess.run(
            [sys.executable, str(Path(__file__).parent.parent / 'data' / 'fetch_historical_data.py')],
            capture_output=True,
            text=True
        )
        print(result.stdout)
        if result.returncode != 0:
            print(f"ERROR: Failed to fetch data\n{result.stderr}")
            return
    
    if not cache_file.exists():
        print("ERROR: Data file still not found after fetch attempt")
        return
    
    print(f"Loading 2010-2016 data from {cache_file}")
    ohlc = pd.read_parquet(cache_file)
    
    if ohlc.empty:
        print("ERROR: No data available for testing.")
        return
    
    if 'open' in ohlc.columns:
        ohlc.columns = [c.capitalize() for c in ohlc.columns]
    
    print(f"\nData loaded:")
    print(f"  Period: {ohlc.index[0]} to {ohlc.index[-1]}")
    print(f"  Bars: {len(ohlc)}")
    print(f"  Years: {ohlc.index[0].year} to {ohlc.index[-1].year}")
    
    print(f"\n{'='*80}\n")
    print("Running backtest...")
    
    results = backtest_with_weekly_withdrawals(ohlc, 100000, 101000)
    
    print("\n" + "="*80)
    print("RESULTS")
    print("="*80)
    
    print(f"\n💰 Financial Performance:")
    print(f"  Starting Balance: $100,000.00")
    print(f"  Final Balance: ${results['final_balance']:,.2f}")
    print(f"  Total Withdrawn: ${results['total_withdrawn']:,.2f}")
    print(f"  Total Profit: ${results['total_profit']:,.2f}")
    print(f"  Account Value: ${results['final_balance'] + results['total_withdrawn']:,.2f}")
    
    years = (ohlc.index[-1] - ohlc.index[0]).days / 365.25
    annual_profit = results['total_profit'] / years
    annual_return_pct = (annual_profit / 100000) * 100
    
    print(f"\n📊 Performance Metrics:")
    print(f"  Period: {years:.2f} years")
    print(f"  Total Trades: {results['total_trades']}")
    print(f"  Annual Profit: ${annual_profit:,.2f}")
    print(f"  Annual Return: {annual_return_pct:.2f}%")
    
    if not results['withdrawals'].empty:
        print(f"\n💸 Withdrawal Activity:")
        print(f"  Total Withdrawals: {len(results['withdrawals'])}")
        print(f"  Total Withdrawn: ${results['total_withdrawn']:,.2f}")
        print(f"  Avg per Withdrawal: ${results['total_withdrawn']/len(results['withdrawals']):,.2f}")
        print(f"  First Withdrawal: {results['withdrawals'].iloc[0]['date'].strftime('%Y-%m-%d')}")
        print(f"  Last Withdrawal: {results['withdrawals'].iloc[-1]['date'].strftime('%Y-%m-%d')}")
        
        print(f"\n  Top 5 Withdrawals:")
        top_5 = results['withdrawals'].nlargest(5, 'amount')
        for idx, row in top_5.iterrows():
            print(f"    {row['date'].strftime('%Y-%m-%d')}: ${row['amount']:,.2f}")
    
    print(f"\n{'='*80}\n")
    
    # Create visualization
    fig, axes = plt.subplots(3, 1, figsize=(14, 10))
    
    equity_df = results['equity_curve']
    
    # Account balance over time
    axes[0].plot(equity_df['date'], equity_df['equity'], 'b-', linewidth=2, label='Account Balance')
    axes[0].axhline(y=100000, color='gray', linestyle='--', alpha=0.5, label='Starting ($100K)')
    axes[0].axhline(y=101000, color='green', linestyle='--', alpha=0.5, label='Withdrawal Threshold ($101K)')
    axes[0].set_title('Account Balance Over Time (with Weekly Withdrawals)', fontsize=14, fontweight='bold')
    axes[0].set_ylabel('Balance ($)')
    axes[0].legend()
    axes[0].grid(True, alpha=0.3)
    axes[0].yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'${x/1000:.0f}K'))
    
    # Cumulative withdrawn
    axes[1].fill_between(equity_df['date'], 0, equity_df['total_withdrawn'], 
                         color='green', alpha=0.3, label='Total Withdrawn')
    axes[1].plot(equity_df['date'], equity_df['total_withdrawn'], 'g-', linewidth=2)
    axes[1].set_title('Cumulative Withdrawals', fontsize=14, fontweight='bold')
    axes[1].set_ylabel('Total Withdrawn ($)')
    axes[1].legend()
    axes[1].grid(True, alpha=0.3)
    axes[1].yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'${x/1000:.0f}K'))
    
    # Total value (balance + withdrawn)
    total_value = equity_df['equity'] + equity_df['total_withdrawn']
    axes[2].fill_between(equity_df['date'], 100000, total_value, 
                         where=total_value>=100000, color='green', alpha=0.3, label='Profit')
    axes[2].plot(equity_df['date'], total_value, 'b-', linewidth=2, label='Total Value')
    axes[2].axhline(y=100000, color='gray', linestyle='--', alpha=0.5, label='Starting Value')
    axes[2].set_title('Total Account Value (Balance + Withdrawn)', fontsize=14, fontweight='bold')
    axes[2].set_ylabel('Total Value ($)')
    axes[2].set_xlabel('Date')
    axes[2].legend()
    axes[2].grid(True, alpha=0.3)
    axes[2].yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'${x/1000:.0f}K'))
    
    plt.xticks(rotation=45)
    plt.tight_layout()
    
    output_file = Path(__file__).parent.parent / 'results' / 'backtest_2010_2016_withdrawals.png'
    plt.savefig(output_file, dpi=150, bbox_inches='tight')
    print(f"📊 Chart saved to {output_file}")
    
    # Save results
    import json
    results_file = Path(__file__).parent.parent / 'results' / 'backtest_2010_2016_results.json'
    with open(results_file, 'w') as f:
        json.dump({
            'period': f"{ohlc.index[0]} to {ohlc.index[-1]}",
            'years': years,
            'starting_balance': 100000,
            'final_balance': results['final_balance'],
            'total_withdrawn': results['total_withdrawn'],
            'total_profit': results['total_profit'],
            'total_trades': results['total_trades'],
            'annual_profit': annual_profit,
            'annual_return_pct': annual_return_pct,
            'total_withdrawals': len(results['withdrawals']) if not results['withdrawals'].empty else 0
        }, f, indent=2)
    
    print(f"✅ Results saved to {results_file}\n")


if __name__ == '__main__':
    main()
