"""
Run MCPT validation on the SMC Order Block Strategy
Tests on multiple periods: 2016-2020 and 2020-2024
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))

import pandas as pd
import numpy as np
from tqdm import tqdm
import json

# Import MCPT tools
from mcpt_strategy.utils.bar_permute import get_permutation


class OANDABroker:
    """Realistic OANDA broker model"""
    
    AVG_SPREAD_PIPS = 1.0
    SLIPPAGE_PIPS = 0.3
    PIP_VALUE_PER_LOT = 10.0
    MAX_LEVERAGE = 50.0
    
    def __init__(self, initial_capital: float = 1000.0, leverage: float = 50.0):
        self.initial_capital = initial_capital
        self.max_leverage = leverage
        self.equity = initial_capital
        self.balance = initial_capital
        self.total_spread_cost = 0.0
        self.total_slippage_cost = 0.0
        
    def calculate_position_size(self, price: float, risk_pct: float = 0.01, 
                               stop_distance_pips: float = 10.0) -> float:
        risk_amount = self.equity * risk_pct
        position_size_lots = risk_amount / (self.PIP_VALUE_PER_LOT * stop_distance_pips)
        max_position_value = self.equity * self.max_leverage
        max_position_lots = max_position_value / (100000 * price)
        position_size_lots = min(position_size_lots, max_position_lots)
        return max(position_size_lots, 0.001)
    
    def execute_trade(self, entry_price: float, exit_price: float, 
                     position_size_lots: float, direction: int) -> float:
        if direction == 1:
            pip_movement = (exit_price - entry_price) * 10000
        else:
            pip_movement = (entry_price - exit_price) * 10000
        
        gross_pnl = pip_movement * self.PIP_VALUE_PER_LOT * position_size_lots
        spread_cost = self.AVG_SPREAD_PIPS * self.PIP_VALUE_PER_LOT * position_size_lots
        slippage_cost = self.SLIPPAGE_PIPS * self.PIP_VALUE_PER_LOT * position_size_lots
        net_pnl = gross_pnl - spread_cost - slippage_cost
        
        self.total_spread_cost += spread_cost
        self.total_slippage_cost += slippage_cost
        
        return net_pnl


def identify_order_blocks(ohlc: pd.DataFrame, lookback: int = 5):
    """Identify Order Blocks (retroactive labeling)"""
    close_price = ohlc['Close']
    open_price = ohlc['Open']
    high = ohlc['High']
    low = ohlc['Low']
    
    body = abs(close_price - open_price)
    avg_body = body.rolling(20).mean()
    strong_bullish = (close_price > open_price) & (body > avg_body * 1.5)
    strong_bearish = (close_price < open_price) & (body > avg_body * 1.5)
    
    bullish_ob = pd.Series(False, index=ohlc.index)
    bearish_ob = pd.Series(False, index=ohlc.index)
    
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
    """Identify market structure"""
    high = ohlc['High']
    low = ohlc['Low']
    
    swing_highs = high.rolling(window=swing_length*2+1, center=True).max() == high
    swing_lows = low.rolling(window=swing_length*2+1, center=True).min() == low
    
    structure = pd.Series(0, index=ohlc.index)
    
    last_high = None
    last_low = None
    
    for i in range(len(ohlc)):
        if swing_highs.iloc[i]:
            if last_high is None or high.iloc[i] > last_high:
                structure.iloc[i] = 1
                last_high = high.iloc[i]
            elif high.iloc[i] < last_high:
                structure.iloc[i] = -1
                last_high = high.iloc[i]
        
        if swing_lows.iloc[i]:
            if last_low is None or low.iloc[i] < last_low:
                structure.iloc[i] = 1
                last_low = low.iloc[i]
            elif low.iloc[i] > last_low:
                structure.iloc[i] = -1
                last_low = low.iloc[i]
    
    structure = structure.replace(0, np.nan).ffill().fillna(0)
    return structure


def smc_order_block_strategy(ohlc: pd.DataFrame, ob_lookback: int = 5, 
                            use_structure: bool = True) -> pd.Series:
    """
    SMC Order Block Strategy
    Returns signal series: 1 for long, -1 for short, 0 for neutral
    """
    bullish_ob, bearish_ob = identify_order_blocks(ohlc, ob_lookback)
    
    if use_structure:
        structure = identify_structure(ohlc)
    else:
        structure = pd.Series(0, index=ohlc.index)
    
    signal = pd.Series(0, index=ohlc.index, dtype=float)
    signal[bullish_ob & (structure >= 0)] = 1
    signal[bearish_ob & (structure <= 0)] = -1
    
    return signal.shift(1).fillna(0)


def backtest_strategy(ohlc: pd.DataFrame, signal: pd.Series, 
                     initial_capital: float = 1000.0,
                     risk_per_trade: float = 0.01,
                     atr_mult: float = 1.0,
                     tp_mult: float = 3.0):
    """Run backtest with given signals"""
    
    broker = OANDABroker(initial_capital)
    
    # Calculate ATR
    high = ohlc['High']
    low = ohlc['Low']
    close = ohlc['Close']
    
    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(14).mean()
    
    trades = []
    position = 0
    position_size_lots = 0
    entry_price = 0
    stop_loss = 0
    take_profit = 0
    
    for i in range(len(ohlc)):
        current_price = close.iloc[i]
        current_signal = signal.iloc[i]
        current_atr = atr.iloc[i]
        
        # Exit logic
        if position != 0:
            exit_triggered = False
            exit_price = current_price
            
            if position == 1 and current_price <= stop_loss:
                exit_triggered = True
                exit_price = stop_loss
            elif position == -1 and current_price >= stop_loss:
                exit_triggered = True
                exit_price = stop_loss
            elif position == 1 and current_price >= take_profit:
                exit_triggered = True
                exit_price = take_profit
            elif position == -1 and current_price <= take_profit:
                exit_triggered = True
                exit_price = take_profit
            
            if exit_triggered:
                pnl = broker.execute_trade(entry_price, exit_price, 
                                          position_size_lots, position)
                broker.equity += pnl
                broker.balance += pnl
                
                trades.append({
                    'pnl': pnl,
                    'return': pnl / (position_size_lots * 100000 * entry_price)
                })
                
                position = 0
        
        # Entry logic
        if position == 0 and current_signal != 0 and not np.isnan(current_atr):
            stop_distance_pips = (current_atr * atr_mult) * 10000
            position_size_lots = broker.calculate_position_size(
                current_price, risk_per_trade, stop_distance_pips
            )
            
            entry_price = current_price
            
            if current_signal == 1:
                position = 1
                stop_loss = entry_price - (current_atr * atr_mult)
                take_profit = entry_price + (current_atr * tp_mult)
            else:
                position = -1
                stop_loss = entry_price + (current_atr * atr_mult)
                take_profit = entry_price - (current_atr * tp_mult)
    
    # Close final position
    if position != 0:
        final_price = close.iloc[-1]
        pnl = broker.execute_trade(entry_price, final_price, 
                                   position_size_lots, position)
        broker.equity += pnl
        broker.balance += pnl
        
        trades.append({
            'pnl': pnl,
            'return': pnl / (position_size_lots * 100000 * entry_price)
        })
    
    # Calculate metrics
    if len(trades) == 0:
        return {
            'total_return': 0,
            'profit_factor': 0,
            'win_rate': 0,
            'total_trades': 0
        }
    
    trades_df = pd.DataFrame(trades)
    winning_trades = trades_df[trades_df['pnl'] > 0]
    losing_trades = trades_df[trades_df['pnl'] < 0]
    
    total_return = (broker.equity - initial_capital) / initial_capital * 100
    win_rate = len(winning_trades) / len(trades) * 100 if len(trades) > 0 else 0
    
    total_wins = winning_trades['pnl'].sum() if len(winning_trades) > 0 else 0
    total_losses = abs(losing_trades['pnl'].sum()) if len(losing_trades) > 0 else 0
    profit_factor = total_wins / total_losses if total_losses > 0 else 0
    
    return {
        'total_return': total_return,
        'profit_factor': profit_factor,
        'win_rate': win_rate,
        'total_trades': len(trades),
        'final_equity': broker.equity
    }


def run_mcpt(ohlc: pd.DataFrame, risk_per_trade: float = 0.01, 
            n_permutations: int = 1000):
    """
    Run Monte Carlo Permutation Test on SMC strategy
    """
    
    print(f"\n{'='*80}")
    print(f"MONTE CARLO PERMUTATION TEST")
    print(f"{'='*80}")
    print(f"Period: {ohlc.index[0]} to {ohlc.index[-1]}")
    print(f"Bars: {len(ohlc)}")
    print(f"Duration: {(ohlc.index[-1] - ohlc.index[0]).days / 365.25:.2f} years")
    print(f"Risk per trade: {risk_per_trade*100}%")
    print(f"Permutations: {n_permutations}")
    print(f"{'='*80}\n")
    
    # Run on real data
    print("Running strategy on REAL data...")
    real_signal = smc_order_block_strategy(ohlc)
    real_results = backtest_strategy(ohlc, real_signal, 
                                     risk_per_trade=risk_per_trade)
    
    print(f"\nREAL DATA RESULTS:")
    print(f"  Total Return:     {real_results['total_return']:+.2f}%")
    print(f"  Profit Factor:    {real_results['profit_factor']:.3f}")
    print(f"  Win Rate:         {real_results['win_rate']:.1f}%")
    print(f"  Total Trades:     {real_results['total_trades']}")
    print(f"  Final Equity:     ${real_results['final_equity']:,.2f}")
    
    # Run on permuted data
    print(f"\nRunning strategy on {n_permutations} PERMUTED datasets...")
    
    permuted_returns = []
    permuted_pfs = []
    
    # Prepare lowercase columns for permutation
    ohlc_lower = ohlc.copy()
    ohlc_lower.columns = [c.lower() for c in ohlc_lower.columns]
    
    for i in tqdm(range(n_permutations), desc="MCPT Progress"):
        # Get permuted data
        permuted_ohlc = get_permutation(ohlc_lower, i)
        
        # Capitalize columns back
        permuted_ohlc.columns = [c.capitalize() for c in permuted_ohlc.columns]
        
        # Run strategy on permuted data
        perm_signal = smc_order_block_strategy(permuted_ohlc)
        perm_results = backtest_strategy(permuted_ohlc, perm_signal,
                                        risk_per_trade=risk_per_trade)
        
        permuted_returns.append(perm_results['total_return'])
        permuted_pfs.append(perm_results['profit_factor'])
    
    # Calculate p-values
    permuted_returns = np.array(permuted_returns)
    permuted_pfs = np.array(permuted_pfs)
    
    p_value_return = np.mean(permuted_returns >= real_results['total_return'])
    p_value_pf = np.mean(permuted_pfs >= real_results['profit_factor'])
    
    print(f"\n{'='*80}")
    print(f"MCPT RESULTS")
    print(f"{'='*80}")
    
    print(f"\nREAL vs PERMUTED:")
    print(f"  Real Return:            {real_results['total_return']:+.2f}%")
    print(f"  Permuted Avg Return:    {np.mean(permuted_returns):+.2f}%")
    print(f"  Permuted Median Return: {np.median(permuted_returns):+.2f}%")
    print(f"  Permuted Std Return:    {np.std(permuted_returns):.2f}%")
    
    print(f"\n  Real Profit Factor:     {real_results['profit_factor']:.3f}")
    print(f"  Permuted Avg PF:        {np.mean(permuted_pfs):.3f}")
    print(f"  Permuted Median PF:     {np.median(permuted_pfs):.3f}")
    print(f"  Permuted Std PF:        {np.std(permuted_pfs):.3f}")
    
    print(f"\nP-VALUES:")
    print(f"  Return p-value:         {p_value_return:.4f}")
    print(f"  Profit Factor p-value:  {p_value_pf:.4f}")
    
    # Determine if passed
    alpha = 0.05  # 5% significance level for forex
    passed_return = p_value_return < alpha
    passed_pf = p_value_pf < alpha
    passed_overall = passed_return and passed_pf
    
    print(f"\nVALIDATION (α = {alpha}):")
    print(f"  Return:        {'✅ PASS' if passed_return else '❌ FAIL'} (p={p_value_return:.4f})")
    print(f"  Profit Factor: {'✅ PASS' if passed_pf else '❌ FAIL'} (p={p_value_pf:.4f})")
    print(f"  Overall:       {'✅ PASS' if passed_overall else '❌ FAIL'}")
    
    print(f"{'='*80}")
    
    return {
        'real_results': real_results,
        'p_value_return': p_value_return,
        'p_value_pf': p_value_pf,
        'permuted_returns': permuted_returns.tolist(),
        'permuted_pfs': permuted_pfs.tolist(),
        'passed': passed_overall
    }


def main():
    # Load data
    cache_dir = Path(__file__).parent.parent / 'data' / 'forex_cache'
    cache_file = cache_dir / 'EURUSD_2016_2024_4h.parquet'
    
    df = pd.read_parquet(cache_file)
    df.columns = [c.capitalize() for c in df.columns]
    
    print("="*80)
    print("SMC STRATEGY - MONTE CARLO PERMUTATION TEST VALIDATION")
    print("="*80)
    print("\nThis validates the SMC Order Block Strategy using MCPT")
    print("Testing statistical significance of returns and profit factor")
    print("="*80)
    
    all_results = {}
    
    # Test 1: 2016-2020 (1% risk)
    print("\n" + "="*80)
    print("TEST 1: 2016-2020 (1% RISK)")
    print("="*80)
    
    df_2016 = df[(df.index >= '2016-01-01') & (df.index <= '2020-12-31')]
    results_2016 = run_mcpt(df_2016, risk_per_trade=0.01, n_permutations=1000)
    all_results['2016-2020_1pct'] = results_2016
    
    # Test 2: 2020-2024 (1% risk first, then 3%)
    print("\n" + "="*80)
    print("TEST 2: 2020-2024 (1% RISK)")
    print("="*80)
    
    df_2020 = df[(df.index >= '2020-01-01') & (df.index <= '2024-12-31')]
    results_2020_1pct = run_mcpt(df_2020, risk_per_trade=0.01, n_permutations=1000)
    all_results['2020-2024_1pct'] = results_2020_1pct
    
    print("\n" + "="*80)
    print("TEST 3: 2020-2024 (3% RISK)")
    print("="*80)
    
    results_2020_3pct = run_mcpt(df_2020, risk_per_trade=0.03, n_permutations=1000)
    all_results['2020-2024_3pct'] = results_2020_3pct
    
    # Summary
    print("\n" + "="*80)
    print("OVERALL SUMMARY")
    print("="*80)
    
    print(f"\n{'Period':<20} {'Risk':<6} {'Return':<12} {'PF':<8} {'p(ret)':<10} {'p(PF)':<10} {'Status':<10}")
    print("-" * 85)
    
    for name, results in all_results.items():
        period = name.split('_')[0]
        risk = name.split('_')[1]
        real = results['real_results']
        p_ret = results['p_value_return']
        p_pf = results['p_value_pf']
        status = '✅ PASS' if results['passed'] else '❌ FAIL'
        
        print(f"{period:<20} {risk:<6} {real['total_return']:>+10.1f}% {real['profit_factor']:>6.2f} {p_ret:>9.4f} {p_pf:>9.4f} {status:<10}")
    
    # Overall assessment
    passed_count = sum(1 for r in all_results.values() if r['passed'])
    total_count = len(all_results)
    
    print("\n" + "="*80)
    print("FINAL VERDICT")
    print("="*80)
    
    print(f"\nTests Passed: {passed_count}/{total_count}")
    
    if passed_count == total_count:
        print("\n✅ STRATEGY FULLY VALIDATED!")
        print("   All periods pass MCPT at α=0.05 significance level")
        print("   Returns are statistically significant vs random permutations")
    elif passed_count >= total_count / 2:
        print("\n⚠️  PARTIAL VALIDATION")
        print("   Some periods pass MCPT, strategy shows promise")
    else:
        print("\n❌ VALIDATION FAILED")
        print("   Most periods fail MCPT, returns may not be statistically significant")
    
    print("\n" + "="*80)
    
    # Save results
    results_dir = Path(__file__).parent.parent / 'results'
    results_dir.mkdir(parents=True, exist_ok=True)
    
    with open(results_dir / 'smc_mcpt_validation.json', 'w') as f:
        json.dump(all_results, f, indent=2)
    
    print(f"\nResults saved to: {results_dir}/smc_mcpt_validation.json")


if __name__ == '__main__':
    main()
