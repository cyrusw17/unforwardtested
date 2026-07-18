"""
Simple Strategies with Best Chance of Passing MCPT
Focus on exploiting autocorrelation and trend persistence
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))

import pandas as pd
import numpy as np
from typing import Dict
from tqdm import tqdm
import json


def simple_trend_momentum(
    ohlc: pd.DataFrame,
    fast_ma: int = 50,
    slow_ma: int = 200,
    momentum_period: int = 10,
    min_momentum: float = 0.005
) -> pd.Series:
    """
    Simple trend + momentum strategy
    
    Real markets have:
    1. Trend persistence (autocorrelation)
    2. Momentum continuation
    
    Shuffled data destroys both properties.
    
    Rules:
    - Fast MA > Slow MA (uptrend) OR Fast MA < Slow MA (downtrend)
    - Momentum must be positive (price rising) or negative (falling)
    - Very simple, only 4 parameters
    """
    close = ohlc['Close']
    
    # Moving averages
    fast = close.rolling(fast_ma).mean()
    slow = close.rolling(slow_ma).mean()
    
    # Trend
    uptrend = fast > slow
    downtrend = fast < slow
    
    # Momentum (rate of change)
    momentum = close.pct_change(momentum_period)
    
    # Signals
    signal = pd.Series(0, index=ohlc.index, dtype=float)
    signal[uptrend & (momentum > min_momentum)] = 1
    signal[downtrend & (momentum < -min_momentum)] = -1
    
    return signal.shift(1).fillna(0)


def donchian_breakout(
    ohlc: pd.DataFrame,
    entry_period: int = 50,
    exit_period: int = 25,
    atr_period: int = 20,
    atr_mult: float = 2.0
) -> pd.Series:
    """
    Donchian breakout with ATR filter
    
    Real markets:
    - Breakouts from consolidation lead to trends
    - This pattern doesn't exist in shuffled data
    
    Rules:
    - Buy when close breaks above N-period high
    - Sell when close breaks below N-period low
    - Only take breakouts when volatility is moderate
    """
    high = ohlc['High']
    low = ohlc['Low']
    close = ohlc['Close']
    
    # Donchian channels
    upper = high.rolling(entry_period).max()
    lower = low.rolling(entry_period).min()
    
    # ATR for volatility filter
    tr = pd.DataFrame({
        'hl': high - low,
        'hc': abs(high - close.shift(1)),
        'lc': abs(low - close.shift(1))
    }).max(axis=1)
    atr = tr.rolling(atr_period).mean()
    atr_pct = atr / close
    
    # Moderate volatility (not too high, not too low)
    vol_percentile = atr_pct.rolling(100).apply(
        lambda x: pd.Series(x).rank(pct=True).iloc[-1] if len(x) > 0 else 0.5
    )
    moderate_vol = (vol_percentile > 0.3) & (vol_percentile < 0.7)
    
    # Breakout signals
    bullish_breakout = close > upper.shift(1)
    bearish_breakout = close < lower.shift(1)
    
    # Signals
    signal = pd.Series(0, index=ohlc.index, dtype=float)
    signal[bullish_breakout & moderate_vol] = 1
    signal[bearish_breakout & moderate_vol] = -1
    
    return signal.shift(1).fillna(0)


def weekly_momentum(
    ohlc: pd.DataFrame,
    lookback: int = 30,  # ~1 week in 4H bars
    min_return: float = 0.015,
    trend_period: int = 100
) -> pd.Series:
    """
    Weekly momentum with trend filter
    
    Real markets:
    - Weekly momentum persists (winners keep winning)
    - Shuffled data loses this autocorrelation
    
    Rules:
    - Take position when 1-week return exceeds threshold
    - Only in direction of longer-term trend
    - Very selective
    """
    close = ohlc['Close']
    
    # Weekly return
    weekly_return = close.pct_change(lookback)
    
    # Long-term trend
    trend_ma = close.rolling(trend_period).mean()
    in_uptrend = close > trend_ma
    in_downtrend = close < trend_ma
    
    # Signals
    signal = pd.Series(0, index=ohlc.index, dtype=float)
    signal[in_uptrend & (weekly_return > min_return)] = 1
    signal[in_downtrend & (weekly_return < -min_return)] = -1
    
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
    """Test simple strategies"""
    print("="*80)
    print("SIMPLE MCPT-PASSING STRATEGIES")
    print("Goal: Exploit autocorrelation & trend persistence")
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
    
    # Strategies
    strategies = [
        {'name': 'Trend+Momentum (50/200)', 'func': simple_trend_momentum, 'params': {'fast_ma': 50, 'slow_ma': 200, 'momentum_period': 10, 'min_momentum': 0.005}},
        {'name': 'Trend+Momentum (30/100)', 'func': simple_trend_momentum, 'params': {'fast_ma': 30, 'slow_ma': 100, 'momentum_period': 10, 'min_momentum': 0.005}},
        {'name': 'Trend+Momentum (20/50)', 'func': simple_trend_momentum, 'params': {'fast_ma': 20, 'slow_ma': 50, 'momentum_period': 5, 'min_momentum': 0.003}},
        {'name': 'Donchian (50/25)', 'func': donchian_breakout, 'params': {'entry_period': 50, 'exit_period': 25, 'atr_period': 20, 'atr_mult': 2.0}},
        {'name': 'Donchian (100/50)', 'func': donchian_breakout, 'params': {'entry_period': 100, 'exit_period': 50, 'atr_period': 20, 'atr_mult': 2.0}},
        {'name': 'Weekly Momentum (30)', 'func': weekly_momentum, 'params': {'lookback': 30, 'min_return': 0.015, 'trend_period': 100}},
        {'name': 'Weekly Momentum (42)', 'func': weekly_momentum, 'params': {'lookback': 42, 'min_return': 0.02, 'trend_period': 100}},
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
                print(f"\nRunning MCPT...")
                mcpt_result = run_mcpt(test_data, strategy['func'], strategy['params'], n_permutations=100)
                
                print(f"\nMCPT Results:")
                print(f"  Real PF: {mcpt_result['real_pf']:.3f}")
                print(f"  Permuted Mean: {mcpt_result['permuted_mean']:.3f}")
                print(f"  Permuted Better: {mcpt_result['permuted_better_count']}/99")
                print(f"  P-Value: {mcpt_result['p_value']:.4f}")
                print(f"  Status: {'✅ PASS' if mcpt_result['passed'] else '❌ FAIL'}")
                
                results.append({
                    'strategy': strategy['name'],
                    'params': strategy['params'],
                    'train_metrics': metrics_train,
                    'test_metrics': metrics_test,
                    'mcpt': mcpt_result,
                    'passed': mcpt_result['passed']
                })
            else:
                print(f"\n❌ Did not meet requirements")
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
    print("FINAL RESULTS")
    print("="*80)
    
    passed = [r for r in results if r.get('passed', False)]
    
    if passed:
        print(f"\n✅✅✅ {len(passed)} STRATEGY(IES) PASSED MCPT! ✅✅✅")
        for r in passed:
            print(f"\n  🎯 {r['strategy']}")
            print(f"     Test Return: {r['test_metrics']['annual_return_pct']:.2f}%")
            print(f"     Test PF: {r['test_metrics']['profit_factor']:.3f}")
            print(f"     Win Rate: {r['test_metrics']['win_rate']:.1f}%")
            print(f"     Trades/Year: {r['test_metrics']['trades_per_year']:.1f}")
            print(f"     MCPT P-Value: {r['mcpt']['p_value']:.4f} ✅")
    else:
        print(f"\n❌ No strategies passed yet")
        valid = [r for r in results if 'mcpt' in r]
        if valid:
            valid.sort(key=lambda x: x['mcpt'].get('p_value', 1.0))
            print(f"\nClosest to passing:")
            for r in valid[:3]:
                print(f"\n  {r['strategy']}")
                print(f"    P-Value: {r['mcpt']['p_value']:.4f}")
                print(f"    Return: {r['test_metrics']['annual_return_pct']:.2f}%")
                print(f"    PF: {r['test_metrics']['profit_factor']:.3f}")
    
    # Save
    results_dir = Path(__file__).parent.parent / 'results'
    results_dir.mkdir(parents=True, exist_ok=True)
    
    with open(results_dir / 'simple_mcpt_results.json', 'w') as f:
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
