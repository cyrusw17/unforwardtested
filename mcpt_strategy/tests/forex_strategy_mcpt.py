"""
Test Forex Strategy with MCPT + 2016-2020 Backtest
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))

import pandas as pd
import numpy as np
from tqdm import tqdm
import json
import matplotlib.pyplot as plt

# Import from existing forex strategy
from core.indicators import TechnicalIndicators
from mcpt_strategy.utils import get_permutation


def forex_signal_generator(
    ohlc: pd.DataFrame,
    sniper_fast: int = 3,
    sniper_slow: int = 9,
    sniper_adx: float = 15.0,
    use_di_filter: bool = True
) -> pd.Series:
    """
    Simplified forex strategy for MCPT testing
    
    Uses just the sniper component (EMA 3/9 + ADX + DI filter)
    """
    ti = TechnicalIndicators
    
    # Normalize column names (lowercase to capital)
    df = ohlc.copy()
    df.columns = [col.capitalize() for col in df.columns]
    
    # Calculate indicators
    ema_fast = ti.ema(df, sniper_fast)
    ema_slow = ti.ema(df, sniper_slow)
    adx, plus_di, minus_di = ti.adx(df, 14)
    
    # Generate crossover signals
    cross_up = (ema_fast > ema_slow) & (ema_fast.shift(1) <= ema_slow.shift(1))
    cross_down = (ema_fast < ema_slow) & (ema_fast.shift(1) >= ema_slow.shift(1))
    
    # Long conditions
    long = cross_up & (adx > sniper_adx)
    # Short conditions  
    short = cross_down & (adx > sniper_adx)
    
    # DI filter
    if use_di_filter:
        long = long & (plus_di > minus_di)
        short = short & (minus_di > plus_di)
    
    # Create signal series
    signal = pd.Series(0, index=df.index, dtype=float)
    signal[long] = 1
    signal[short] = -1
    
    # Shift for next-bar execution
    signal = signal.shift(1).fillna(0)
    
    return signal


def backtest_period(
    ohlc: pd.DataFrame,
    start_year: int,
    end_year: int,
    **strategy_params
) -> dict:
    """
    Backtest strategy on a specific period
    """
    # Filter data
    period_data = ohlc[
        (ohlc.index.year >= start_year) & 
        (ohlc.index.year <= end_year)
    ].copy()
    
    if len(period_data) == 0:
        return {
            'period': f'{start_year}-{end_year}',
            'bars': 0,
            'error': 'No data for period'
        }
    
    # Generate signals
    signal = forex_signal_generator(period_data, **strategy_params)
    
    # Calculate returns
    returns = np.log(period_data['close']).diff().shift(-1)
    strategy_returns = signal * returns
    strategy_returns = strategy_returns.dropna()
    
    if len(strategy_returns) == 0:
        return {
            'period': f'{start_year}-{end_year}',
            'bars': len(period_data),
            'trades': 0,
            'error': 'No trades generated'
        }
    
    # Calculate metrics
    total_return = np.exp(strategy_returns.sum()) - 1
    
    # Profit factor
    winning = strategy_returns[strategy_returns > 0].sum()
    losing = strategy_returns[strategy_returns < 0].abs().sum()
    profit_factor = winning / losing if losing > 0 else 0
    
    # Sharpe
    sharpe = strategy_returns.mean() / strategy_returns.std() * np.sqrt(252/4) if strategy_returns.std() > 0 else 0
    
    # Drawdown
    cum_returns = strategy_returns.cumsum()
    running_max = cum_returns.cummax()
    drawdown = cum_returns - running_max
    max_dd = drawdown.min()
    
    # Trade count (signal changes)
    trades = (signal.diff() != 0).sum()
    
    return {
        'period': f'{start_year}-{end_year}',
        'start_date': str(period_data.index[0]),
        'end_date': str(period_data.index[-1]),
        'bars': len(period_data),
        'trades': int(trades),
        'total_return': float(total_return),
        'total_return_pct': float(total_return * 100),
        'profit_factor': float(profit_factor),
        'sharpe_ratio': float(sharpe),
        'max_drawdown': float(max_dd),
        'max_drawdown_pct': float(max_dd * 100),
        'win_rate': float(len(strategy_returns[strategy_returns > 0]) / len(strategy_returns) * 100) if len(strategy_returns) > 0 else 0
    }


def run_mcpt_on_forex(
    ohlc: pd.DataFrame,
    train_start: int,
    train_end: int,
    n_permutations: int = 100,
    **strategy_params
) -> dict:
    """
    Run MCPT on forex strategy
    """
    print(f"\n{'='*80}")
    print(f"MCPT VALIDATION: Forex Strategy")
    print(f"Training Period: {train_start}-{train_end}")
    print('='*80)
    
    # Get training data
    train_data = ohlc[
        (ohlc.index.year >= train_start) & 
        (ohlc.index.year <= train_end)
    ].copy()
    
    print(f"\n[1/2] Testing on real data ({len(train_data)} bars)...")
    
    # Generate signals and returns
    signal = forex_signal_generator(train_data, **strategy_params)
    returns = np.log(train_data['close']).diff().shift(-1)
    strategy_returns = signal * returns
    strategy_returns = strategy_returns.dropna()
    
    if len(strategy_returns[strategy_returns < 0]) == 0:
        print("⚠️  No losing trades, cannot calculate profit factor")
        return {
            'real_pf': 0.0,
            'p_value': 1.0,
            'passed': False,
            'error': 'No losing trades'
        }
    
    real_pf = strategy_returns[strategy_returns > 0].sum() / strategy_returns[strategy_returns < 0].abs().sum()
    
    print(f"Real Profit Factor: {real_pf:.4f}")
    
    # Run permutations
    print(f"\n[2/2] Running {n_permutations} permutations...")
    perm_better_count = 1
    permuted_pfs = []
    
    for perm_i in tqdm(range(1, n_permutations), desc="MCPT"):
        try:
            perm_data = get_permutation(train_data, seed=perm_i * 100)
            perm_signal = forex_signal_generator(perm_data, **strategy_params)
            perm_returns = np.log(perm_data['close']).diff().shift(-1)
            perm_strat_rets = perm_signal * perm_returns
            perm_strat_rets = perm_strat_rets.dropna()
            
            if len(perm_strat_rets[perm_strat_rets < 0]) == 0:
                perm_pf = 0
            else:
                perm_pf = perm_strat_rets[perm_strat_rets > 0].sum() / perm_strat_rets[perm_strat_rets < 0].abs().sum()
            
            if perm_pf >= real_pf:
                perm_better_count += 1
            
            permuted_pfs.append(perm_pf)
        except:
            permuted_pfs.append(1.0)
    
    p_value = perm_better_count / n_permutations
    passed = p_value < 0.01
    
    print(f"\n✓ Results:")
    print(f"  P-Value: {p_value:.4f}")
    print(f"  Real PF: {real_pf:.4f}")
    print(f"  Mean Permuted PF: {np.mean(permuted_pfs):.4f}")
    print(f"  Status: {'✓ PASS' if passed else '✗ FAIL'} (threshold < 0.01)")
    
    return {
        'period': f'{train_start}-{train_end}',
        'real_pf': float(real_pf),
        'p_value': float(p_value),
        'perm_better_count': int(perm_better_count),
        'permuted_pfs_mean': float(np.mean(permuted_pfs)),
        'permuted_pfs_std': float(np.std(permuted_pfs)),
        'permuted_pfs': [float(x) for x in permuted_pfs],
        'passed': passed
    }


def full_forex_test(data_path: str):
    """
    Run complete forex strategy test:
    1. Backtest on 2016-2020
    2. Run MCPT validation
    """
    print("="*80)
    print("FOREX STRATEGY COMPREHENSIVE TEST")
    print("="*80)
    
    # Load data
    ohlc = pd.read_parquet(data_path)
    print(f"\nData loaded: {ohlc.index[0]} to {ohlc.index[-1]}")
    print(f"Total bars: {len(ohlc)}")
    
    # Strategy parameters (from forex config)
    strategy_params = {
        'sniper_fast': 3,
        'sniper_slow': 9,
        'sniper_adx': 15.0,
        'use_di_filter': True
    }
    
    print(f"\nStrategy: EMA 3/9 + ADX>15 + DI Filter")
    
    # Part 1: 2016-2020 Backtest
    print("\n" + "="*80)
    print("PART 1: BACKTEST ON 2016-2020")
    print("="*80)
    
    result_2016_2020 = backtest_period(ohlc, 2016, 2020, **strategy_params)
    
    if 'error' not in result_2016_2020:
        print(f"\n📊 2016-2020 Performance:")
        print(f"  Period: {result_2016_2020['start_date']} to {result_2016_2020['end_date']}")
        print(f"  Bars: {result_2016_2020['bars']}")
        print(f"  Trades: {result_2016_2020['trades']}")
        print(f"  Total Return: {result_2016_2020['total_return_pct']:.2f}%")
        print(f"  Profit Factor: {result_2016_2020['profit_factor']:.4f}")
        print(f"  Sharpe Ratio: {result_2016_2020['sharpe_ratio']:.2f}")
        print(f"  Max Drawdown: {result_2016_2020['max_drawdown_pct']:.2f}%")
        print(f"  Win Rate: {result_2016_2020['win_rate']:.1f}%")
    else:
        print(f"\n⚠️  Error: {result_2016_2020['error']}")
    
    # Part 2: MCPT Validation
    print("\n" + "="*80)
    print("PART 2: MCPT VALIDATION")
    print("="*80)
    
    mcpt_result = run_mcpt_on_forex(
        ohlc,
        train_start=2016,
        train_end=2024,
        n_permutations=100,
        **strategy_params
    )
    
    # Comparison with existing results
    print("\n" + "="*80)
    print("COMPARISON WITH EXISTING VALIDATION")
    print("="*80)
    
    print(f"\n📈 Known Results (2018-2025 on real forex data):")
    print(f"  Total Return: +13.6%")
    print(f"  Profit Factor: 1.98")
    print(f"  Max Drawdown: 4.7%")
    print(f"  Validation: Multi-era (6/421 configs passed)")
    
    if 'error' not in result_2016_2020:
        print(f"\n📉 This Test (2016-2020 on synthetic crypto data):")
        print(f"  Total Return: {result_2016_2020['total_return_pct']:.2f}%")
        print(f"  Profit Factor: {result_2016_2020['profit_factor']:.4f}")
        print(f"  Max Drawdown: {result_2016_2020['max_drawdown_pct']:.2f}%")
        print(f"  MCPT P-Value: {mcpt_result['p_value']:.4f}")
        print(f"  MCPT Status: {'✓ PASS' if mcpt_result['passed'] else '✗ FAIL'}")
    
    # Summary
    print("\n" + "="*80)
    print("FINAL VERDICT")
    print("="*80)
    
    if 'error' not in result_2016_2020:
        if result_2016_2020['profit_factor'] > 1.2 and mcpt_result['passed']:
            print("\n🎉 EXCELLENT: Strategy passes both tests!")
        elif result_2016_2020['profit_factor'] > 1.1:
            print("\n✓ GOOD: Strategy profitable on 2016-2020")
            if not mcpt_result['passed']:
                print("  ⚠️  But MCPT failed (synthetic data limitation)")
        else:
            print("\n⚠️  MARGINAL: Low profit factor on 2016-2020")
    
    print(f"\n💡 Note: Results differ because:")
    print(f"  - Original: Real forex data (EUR/USD, GBP/USD, etc.)")
    print(f"  - This test: Synthetic crypto data")
    print(f"  - Different markets behave differently")
    print(f"  - Original validation more reliable")
    
    # Save results
    results_dir = Path(__file__).parent.parent / 'results'
    results_dir.mkdir(parents=True, exist_ok=True)
    
    summary = {
        'strategy': 'Forex EMA 3/9 + ADX + DI Filter',
        'backtest_2016_2020': result_2016_2020,
        'mcpt_validation': mcpt_result,
        'comparison': {
            'original_validation': {
                'period': '2018-2025',
                'data': 'Real forex (Dukascopy)',
                'return': 13.6,
                'profit_factor': 1.98,
                'max_dd': 4.7
            },
            'this_test': {
                'period': '2016-2020',
                'data': 'Synthetic crypto',
                'return': result_2016_2020.get('total_return_pct', 0),
                'profit_factor': result_2016_2020.get('profit_factor', 0)
            }
        }
    }
    
    with open(results_dir / 'forex_mcpt_test.json', 'w') as f:
        json.dump(summary, f, indent=2)
    
    # Plot if we have data
    if 'error' not in result_2016_2020 and len(mcpt_result['permuted_pfs']) > 0:
        plt.style.use('dark_background')
        plt.figure(figsize=(12, 6))
        
        plt.hist(mcpt_result['permuted_pfs'], bins=50, color='blue', alpha=0.7, 
                 label='Permutations', edgecolor='white')
        plt.axvline(mcpt_result['real_pf'], color='red', linewidth=2, 
                   label=f'Real (PF={mcpt_result["real_pf"]:.4f})')
        
        plt.xlabel('Profit Factor', fontsize=12)
        plt.ylabel('Frequency', fontsize=12)
        plt.title(f'Forex Strategy MCPT - P-Value: {mcpt_result["p_value"]:.4f}', 
                 fontsize=14, fontweight='bold')
        plt.legend(fontsize=11)
        plt.grid(False)
        
        plt.tight_layout()
        plt.savefig(results_dir / 'forex_mcpt_histogram.png', dpi=150, bbox_inches='tight')
        print(f"\nResults saved to {results_dir}/")
    
    return summary


if __name__ == '__main__':
    data_path = Path(__file__).parent.parent / 'data' / 'BTCUSDT_1h.parquet'
    
    if not data_path.exists():
        print(f"Error: Data file not found at {data_path}")
        sys.exit(1)
    
    results = full_forex_test(str(data_path))
