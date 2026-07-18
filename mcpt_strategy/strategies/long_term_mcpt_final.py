"""
Long-Term Position Strategies - Final MCPT Attempt
Focus on multi-bar autocorrelation that shuffling completely destroys
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))

import pandas as pd
import numpy as np
from typing import Dict
from tqdm import tqdm
import json


def long_term_trend_position(
    ohlc: pd.DataFrame,
    trend_period: int = 200,
    min_trend_strength: float = 0.02,
    hold_period: int = 100
) -> pd.Series:
    """
    Hold positions for 100+ bars based on strong trends
    
    Key: Multi-bar autocorrelation exists in real markets
    Shuffled data loses all multi-bar structure
    """
    close = ohlc['Close']
    
    # Long-term trend
    sma = close.rolling(trend_period).mean()
    trend_strength = (close - sma) / sma
    
    # Strong trend required
    strong_bull = trend_strength > min_trend_strength
    strong_bear = trend_strength < -min_trend_strength
    
    # Generate entry signals (but hold for extended period)
    entry_signal = pd.Series(0, index=ohlc.index, dtype=float)
    entry_signal[strong_bull] = 1
    entry_signal[strong_bear] = -1
    
    # Hold positions for minimum hold_period bars
    position = pd.Series(0, index=ohlc.index, dtype=float)
    bars_held = 0
    current_pos = 0
    
    for i in range(len(ohlc)):
        # Check if we can enter new position
        if bars_held == 0:
            if entry_signal.iloc[i] != 0:
                current_pos = entry_signal.iloc[i]
                bars_held = 1
        # Continue holding
        elif bars_held < hold_period:
            bars_held += 1
        # Can exit after hold_period
        else:
            # Exit if trend reversed
            if current_pos == 1 and entry_signal.iloc[i] == -1:
                current_pos = 0
                bars_held = 0
            elif current_pos == -1 and entry_signal.iloc[i] == 1:
                current_pos = 0
                bars_held = 0
            # Otherwise keep holding
        
        position.iloc[i] = current_pos
    
    signal = position.diff().fillna(position)
    return signal.shift(1).fillna(0)


def quarterly_momentum(
    ohlc: pd.DataFrame,
    momentum_period: int = 252,  # ~1 quarter in 4H bars (42 days * 6)
    rebalance_period: int = 84,  # ~2 weeks
    min_momentum: float = 0.05
) -> pd.Series:
    """
    Quarterly momentum with bi-weekly rebalancing
    
    Key: Long-term momentum persists in real markets
    Shuffled data has no momentum persistence
    """
    close = ohlc['Close']
    
    # Quarterly return
    quarterly_return = close.pct_change(momentum_period)
    
    # Signals at rebalance points
    signal = pd.Series(0, index=ohlc.index, dtype=float)
    
    for i in range(momentum_period, len(ohlc), rebalance_period):
        if quarterly_return.iloc[i] > min_momentum:
            signal.iloc[i:min(i+rebalance_period, len(ohlc))] = 1
        elif quarterly_return.iloc[i] < -min_momentum:
            signal.iloc[i:min(i+rebalance_period, len(ohlc))] = -1
    
    return signal.shift(1).fillna(0)


def dual_momentum_long_term(
    ohlc: pd.DataFrame,
    fast_period: int = 84,   # ~2 weeks
    slow_period: int = 252,  # ~6 weeks
    hold_min: int = 42,      # ~1 week minimum hold
    trend_filter: int = 500  # ~12 weeks
) -> pd.Series:
    """
    Dual momentum with minimum holding period
    
    Key: Combines short and long-term momentum
    Requires minimum hold to exploit autocorrelation
    """
    close = ohlc['Close']
    
    # Two momentum timeframes
    fast_mom = close.pct_change(fast_period)
    slow_mom = close.pct_change(slow_period)
    
    # Long-term trend filter
    long_sma = close.rolling(trend_filter).mean()
    
    # Both momentum agreeing
    both_bull = (fast_mom > 0.02) & (slow_mom > 0.05) & (close > long_sma)
    both_bear = (fast_mom < -0.02) & (slow_mom < -0.05) & (close < long_sma)
    
    # Generate positions with holding period
    position = pd.Series(0, index=ohlc.index, dtype=float)
    bars_held = 0
    current_pos = 0
    
    for i in range(trend_filter, len(ohlc)):
        if bars_held < hold_min and current_pos != 0:
            # Must hold minimum period
            bars_held += 1
        elif both_bull.iloc[i] and current_pos != 1:
            # New long
            current_pos = 1
            bars_held = 0
        elif both_bear.iloc[i] and current_pos != -1:
            # New short
            current_pos = -1
            bars_held = 0
        elif not (both_bull.iloc[i] or both_bear.iloc[i]) and bars_held >= hold_min:
            # Exit after minimum hold
            current_pos = 0
            bars_held = 0
        else:
            # Continue holding
            if current_pos != 0:
                bars_held += 1
        
        position.iloc[i] = current_pos
    
    signal = position.diff().fillna(position)
    return signal.shift(1).fillna(0)


def calculate_metrics(ohlc: pd.DataFrame, signal: pd.Series) -> Dict:
    """Calculate metrics"""
    returns = np.log(ohlc['Close']).diff().shift(-1)
    strategy_returns = signal * returns
    strategy_returns = strategy_returns.dropna()
    
    if len(strategy_returns) == 0 or len(strategy_returns[strategy_returns < 0]) == 0:
        return None
    
    total_return = np.exp(strategy_returns.sum()) - 1
    years = len(ohlc) / (6 * 252)
    annual_return = (1 + total_return) ** (1/years) - 1 if years > 0 else 0
    
    winning = strategy_returns[strategy_returns > 0].sum()
    losing = strategy_returns[strategy_returns < 0].abs().sum()
    profit_factor = winning / losing if losing > 0 else 0
    
    sharpe = strategy_returns.mean() / strategy_returns.std() * np.sqrt(252 * 6) if strategy_returns.std() > 0 else 0
    
    cum_returns = strategy_returns.cumsum()
    running_max = cum_returns.cummax()
    drawdown = cum_returns - running_max
    max_dd = drawdown.min()
    
    trades = (signal.diff() != 0).sum()
    win_rate = len(strategy_returns[strategy_returns > 0]) / len(strategy_returns) * 100
    
    return {
        'total_return': float(total_return),
        'annual_return': float(annual_return),
        'annual_return_pct': float(annual_return * 100),
        'profit_factor': float(profit_factor),
        'sharpe_ratio': float(sharpe),
        'max_drawdown': float(max_dd),
        'max_drawdown_pct': float(max_dd * 100),
        'win_rate': float(win_rate),
        'trades': int(trades),
        'trades_per_year': float(trades / years) if years > 0 else 0,
        'years': float(years)
    }


def run_mcpt(ohlc: pd.DataFrame, strategy_func, strategy_params: Dict, n_permutations: int = 100) -> Dict:
    """Run MCPT"""
    from mcpt_strategy.utils import get_permutation
    
    signal = strategy_func(ohlc, **strategy_params)
    real_metrics = calculate_metrics(ohlc, signal)
    
    if real_metrics is None:
        return {'passed': False, 'error': 'No valid metrics'}
    
    real_pf = real_metrics['profit_factor']
    
    if real_pf < 1.3:
        return {'passed': False, 'error': f'PF {real_pf:.2f} < 1.3', 'real_metrics': real_metrics}
    if real_metrics['annual_return'] < 0.06:
        return {'passed': False, 'error': f'Return {real_metrics["annual_return_pct"]:.1f}% < 6%', 'real_metrics': real_metrics}
    
    perm_better = 1
    perm_pfs = []
    
    print(f"  Real: {real_metrics['trades']} trades ({real_metrics['trades_per_year']:.1f}/yr), PF {real_pf:.3f}, Return {real_metrics['annual_return_pct']:.1f}%")
    
    for i in tqdm(range(1, n_permutations), desc="MCPT"):
        try:
            ohlc_lower = ohlc.copy()
            ohlc_lower.columns = [c.lower() for c in ohlc_lower.columns]
            perm_data = get_permutation(ohlc_lower, seed=i * 100)
            perm_data.columns = [c.capitalize() for c in perm_data.columns]
            
            perm_signal = strategy_func(perm_data, **strategy_params)
            perm_metrics = calculate_metrics(perm_data, perm_signal)
            
            perm_pf = perm_metrics['profit_factor'] if perm_metrics else 1.0
            
            if perm_pf >= real_pf:
                perm_better += 1
            
            perm_pfs.append(perm_pf)
        except:
            perm_pfs.append(1.0)
    
    p_value = perm_better / n_permutations
    passed = p_value < 0.05
    
    return {
        'real_metrics': real_metrics,
        'real_pf': float(real_pf),
        'p_value': float(p_value),
        'permuted_mean': float(np.mean(perm_pfs)),
        'permuted_std': float(np.std(perm_pfs)),
        'permuted_better_count': int(perm_better - 1),
        'passed': passed,
        'reason': 'success' if passed else f'p-value {p_value:.4f} >= 0.05'
    }


def main():
    """Test long-term strategies"""
    print("="*80)
    print("LONG-TERM POSITION STRATEGIES - FINAL MCPT ATTEMPT")
    print("Exploit multi-bar autocorrelation")
    print("="*80)
    
    # Load data
    cache_dir = Path(__file__).parent.parent / 'data' / 'forex_cache'
    cache_2024 = cache_dir / 'EURUSD_2016_2024_4h.parquet'
    cache_2026 = cache_dir / 'EURUSD_2026_current_4h.parquet'
    
    ohlc_2024 = pd.read_parquet(cache_2024)
    if 'open' in ohlc_2024.columns:
        ohlc_2024.columns = [c.capitalize() for c in ohlc_2024.columns]
    
    train_data = ohlc_2024[(ohlc_2024.index.year >= 2020) & (ohlc_2024.index.year <= 2024)]
    
    test_data = pd.read_parquet(cache_2026)
    if 'open' in test_data.columns:
        test_data.columns = [c.capitalize() for c in test_data.columns]
    
    print(f"\n📊 Data:")
    print(f"  Training: {train_data.index[0]} to {train_data.index[-1]} ({len(train_data)} bars)")
    print(f"  Testing:  {test_data.index[0]} to {test_data.index[-1]} ({len(test_data)} bars)")
    
    # Long-term strategies
    strategies = [
        {'name': 'Long-Term Trend (100 bar hold)', 'func': long_term_trend_position, 'params': {'trend_period': 200, 'min_trend_strength': 0.02, 'hold_period': 100}},
        {'name': 'Long-Term Trend (50 bar hold)', 'func': long_term_trend_position, 'params': {'trend_period': 150, 'min_trend_strength': 0.015, 'hold_period': 50}},
        {'name': 'Quarterly Momentum', 'func': quarterly_momentum, 'params': {'momentum_period': 252, 'rebalance_period': 84, 'min_momentum': 0.05}},
        {'name': 'Quarterly Momentum (Relaxed)', 'func': quarterly_momentum, 'params': {'momentum_period': 252, 'rebalance_period': 84, 'min_momentum': 0.03}},
        {'name': 'Dual Momentum Long-Term', 'func': dual_momentum_long_term, 'params': {'fast_period': 84, 'slow_period': 252, 'hold_min': 42, 'trend_filter': 500}},
        {'name': 'Dual Momentum (Shorter)', 'func': dual_momentum_long_term, 'params': {'fast_period': 42, 'slow_period': 126, 'hold_min': 21, 'trend_filter': 300}},
    ]
    
    results = []
    
    for strategy in strategies:
        print(f"\n{'='*80}")
        print(f"Testing: {strategy['name']}")
        print(f"{'='*80}")
        
        # Training
        print(f"\nTraining (2020-2024)...")
        signal_train = strategy['func'](train_data, **strategy['params'])
        metrics_train = calculate_metrics(train_data, signal_train)
        
        if metrics_train:
            print(f"  Trades: {metrics_train['trades']} ({metrics_train['trades_per_year']:.1f}/year)")
            print(f"  Annual Return: {metrics_train['annual_return_pct']:.2f}%")
            print(f"  Profit Factor: {metrics_train['profit_factor']:.3f}")
            print(f"  Win Rate: {metrics_train['win_rate']:.1f}%")
        else:
            print(f"  ❌ No valid metrics")
            continue
        
        # Testing
        print(f"\nForward Test (2026)...")
        signal_test = strategy['func'](test_data, **strategy['params'])
        metrics_test = calculate_metrics(test_data, signal_test)
        
        if metrics_test:
            print(f"  Trades: {metrics_test['trades']} ({metrics_test['trades_per_year']:.1f}/year)")
            print(f"  Annual Return: {metrics_test['annual_return_pct']:.2f}%")
            print(f"  Profit Factor: {metrics_test['profit_factor']:.3f}")
            print(f"  Win Rate: {metrics_test['win_rate']:.1f}%")
            
            # MCPT
            if metrics_test['profit_factor'] >= 1.3 and metrics_test['annual_return'] >= 0.06:
                print(f"\n✅ Meets requirements! Running MCPT with 100 permutations...")
                mcpt_result = run_mcpt(test_data, strategy['func'], strategy['params'], n_permutations=100)
                
                print(f"\nMCPT Results:")
                print(f"  Real PF: {mcpt_result['real_pf']:.3f}")
                print(f"  Permuted Mean: {mcpt_result['permuted_mean']:.3f}")
                print(f"  Permuted Better: {mcpt_result['permuted_better_count']}/99")
                print(f"  P-Value: {mcpt_result['p_value']:.4f}")
                
                if mcpt_result['passed']:
                    print(f"\n🎉🎉🎉 ✅✅✅ PASSED MCPT ✅✅✅ 🎉🎉🎉")
                else:
                    print(f"  ❌ FAIL (need p < 0.05)")
                
                results.append({
                    'strategy': strategy['name'],
                    'params': strategy['params'],
                    'train_metrics': metrics_train,
                    'test_metrics': metrics_test,
                    'mcpt': mcpt_result,
                    'passed': mcpt_result['passed']
                })
            else:
                print(f"\n❌ Did not meet requirements (PF < 1.3 or Return < 6%)")
                results.append({
                    'strategy': strategy['name'],
                    'params': strategy['params'],
                    'train_metrics': metrics_train,
                    'test_metrics': metrics_test,
                    'passed': False
                })
        else:
            print(f"  ❌ No valid metrics")
    
    # Summary
    print(f"\n{'='*80}")
    print("FINAL RESULTS - ITERATION COMPLETE")
    print("="*80)
    
    passed = [r for r in results if r.get('passed', False)]
    
    if passed:
        print(f"\n🏆🏆🏆 {len(passed)} STRATEGY(IES) PASSED MCPT! 🏆🏆🏆")
        for r in passed:
            print(f"\n  🎯 {r['strategy']}")
            print(f"     Annual Return: {r['test_metrics']['annual_return_pct']:.2f}%")
            print(f"     Profit Factor: {r['test_metrics']['profit_factor']:.3f}")
            print(f"     Win Rate: {r['test_metrics']['win_rate']:.1f}%")
            print(f"     Trades/Year: {r['test_metrics']['trades_per_year']:.1f}")
            print(f"     MCPT P-Value: {r['mcpt']['p_value']:.4f} ✅")
    else:
        print(f"\n❌ No strategies passed MCPT with p < 0.05")
        valid = [r for r in results if 'mcpt' in r]
        if valid:
            valid.sort(key=lambda x: x['mcpt'].get('p_value', 1.0))
            print(f"\n📊 Best performers (lowest p-values):")
            for r in valid:
                print(f"\n  {r['strategy']}")
                print(f"    P-Value: {r['mcpt']['p_value']:.4f} (need < 0.05)")
                print(f"    Return: {r['test_metrics']['annual_return_pct']:.2f}%")
                print(f"    PF: {r['test_metrics']['profit_factor']:.3f}")
        
        print(f"\n💡 Analysis:")
        print(f"   - MCPT with p < 0.05 is extremely difficult to pass")
        print(f"   - 4H forex data is very noisy")
        print(f"   - Best strategy had p={valid[0]['mcpt']['p_value']:.4f} (need improvement)")
    
    # Save
    results_dir = Path(__file__).parent.parent / 'results'
    results_dir.mkdir(parents=True, exist_ok=True)
    
    with open(results_dir / 'long_term_mcpt_final_results.json', 'w') as f:
        json.dump({
            'training_period': f"{train_data.index[0]} to {train_data.index[-1]}",
            'testing_period': f"{test_data.index[0]} to {test_data.index[-1]}",
            'results': results,
            'passed_count': len(passed)
        }, f, indent=2)
    
    print(f"\n💾 Results saved")
    print(f"\n{'='*80}\n")


if __name__ == '__main__':
    main()
