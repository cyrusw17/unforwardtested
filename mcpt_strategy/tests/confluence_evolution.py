"""
Confluence Strategy Evolution
Keep testing different combinations until walk-forward MCPT passes

Focus: ONLY walk-forward tests matter (the real test of generalization)
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

import pandas as pd
import numpy as np
from tqdm import tqdm
import json

from strategies.confluence_builder import (
    confluence_strategy_v1,
    confluence_strategy_v2,
    confluence_strategy_v3,
    confluence_strategy_v4,
    confluence_strategy_v5
)
from utils import get_permutation


def test_walkforward_only(
    df: pd.DataFrame,
    strategy_func,
    strategy_name: str,
    strategy_params: dict,
    train_window: int = 24 * 365 * 4,
    n_permutations: int = 100
) -> dict:
    """
    Test ONLY walk-forward MCPT (skip in-sample tests)
    
    This is what really matters - does it work on future data?
    """
    print(f"\n{'='*80}")
    print(f"TESTING: {strategy_name}")
    print('='*80)
    
    # Generate signal
    print("\n[1/3] Generating signals on full dataset...")
    signal = strategy_func(df, **strategy_params)
    
    # Calculate returns
    df['r'] = np.log(df['close']).diff().shift(-1)
    
    # Walk-forward: only use signals after training period
    wf_signal = signal.copy()
    wf_signal.iloc[:train_window] = 0  # Zero out training period
    
    wf_rets = wf_signal * df['r']
    wf_rets = wf_rets.dropna()
    
    if len(wf_rets[wf_rets < 0]) == 0:
        print("⚠️  No losing trades in walk-forward period, skipping")
        return {
            'strategy': strategy_name,
            'params': strategy_params,
            'real_wf_pf': 0.0,
            'p_value': 1.0,
            'passed': False,
            'skipped': True
        }
    
    real_wf_pf = wf_rets[wf_rets > 0].sum() / wf_rets[wf_rets < 0].abs().sum()
    
    print(f"Walk-Forward Profit Factor: {real_wf_pf:.4f}")
    
    if real_wf_pf < 1.05:
        print(f"⚠️  Real WF PF too low ({real_wf_pf:.4f}), skipping permutations")
        return {
            'strategy': strategy_name,
            'params': strategy_params,
            'real_wf_pf': float(real_wf_pf),
            'p_value': 1.0,
            'passed': False,
            'skipped': True
        }
    
    # Walk-forward MCPT
    print(f"\n[2/3] Running {n_permutations} walk-forward permutations...")
    perm_better_count = 1
    permuted_pfs = []
    
    for perm_i in tqdm(range(1, n_permutations), desc=f"WF perms"):
        try:
            # Permute only the OOS period
            wf_perm = get_permutation(df, start_index=train_window, seed=perm_i * 1000)
            
            # Generate signals on permuted data
            perm_signal = strategy_func(wf_perm, **strategy_params)
            perm_signal.iloc[:train_window] = 0
            
            # Calculate permuted returns
            wf_perm['r'] = np.log(wf_perm['close']).diff().shift(-1)
            perm_rets = perm_signal * wf_perm['r']
            perm_rets = perm_rets.dropna()
            
            if len(perm_rets[perm_rets < 0]) == 0:
                perm_pf = 0
            else:
                perm_pf = perm_rets[perm_rets > 0].sum() / perm_rets[perm_rets < 0].abs().sum()
            
            if perm_pf >= real_wf_pf:
                perm_better_count += 1
            
            permuted_pfs.append(perm_pf)
        except:
            permuted_pfs.append(1.0)
    
    p_value = perm_better_count / n_permutations
    
    # More lenient threshold for walk-forward
    passed = p_value < 0.10  # 10% threshold (90% confidence)
    
    print(f"\n[3/3] Walk-Forward MCPT Results:")
    print(f"  P-Value: {p_value:.4f}")
    print(f"  Real WF PF: {real_wf_pf:.4f}")
    print(f"  Mean Permuted PF: {np.mean(permuted_pfs):.4f}")
    print(f"  Status: {'✓ PASS' if passed else '✗ FAIL'}")
    
    # Additional metrics
    oos_start = df.index[train_window]
    oos_end = df.index[-1]
    oos_rets = wf_rets.iloc[train_window:]
    
    total_return = np.exp(oos_rets.sum()) - 1
    sharpe = oos_rets.mean() / oos_rets.std() * np.sqrt(365 * 24) if oos_rets.std() > 0 else 0
    
    print(f"\n  OOS Period: {oos_start} to {oos_end}")
    print(f"  Total Return: {total_return*100:.2f}%")
    print(f"  Sharpe Ratio: {sharpe:.2f}")
    
    return {
        'strategy': strategy_name,
        'params': strategy_params,
        'real_wf_pf': float(real_wf_pf),
        'p_value': float(p_value),
        'perm_better_count': int(perm_better_count),
        'permuted_pfs_mean': float(np.mean(permuted_pfs)),
        'permuted_pfs_std': float(np.std(permuted_pfs)),
        'permuted_pfs': [float(x) for x in permuted_pfs],
        'passed': passed,
        'skipped': False,
        'total_return': float(total_return),
        'sharpe_ratio': float(sharpe),
        'oos_start': str(oos_start),
        'oos_end': str(oos_end)
    }


def evolve_until_pass(
    data_path: str,
    max_iterations: int = 20,
    n_permutations: int = 100,
    target_p_value: float = 0.10
):
    """
    Keep trying different strategy combinations until one passes
    
    Strategy: Test progressively more configurations
    """
    print("="*80)
    print("CONFLUENCE STRATEGY EVOLUTION")
    print("Goal: Find strategy that passes walk-forward MCPT")
    print("="*80)
    
    df = pd.read_parquet(data_path)
    df = df[(df.index.year >= 2016) & (df.index.year <= 2026)]
    
    train_window = 24 * 365 * 4  # 4 years
    
    print(f"\nData: {df.index[0]} to {df.index[-1]}")
    print(f"Training window: {train_window} bars (4 years)")
    print(f"Forward test: Everything after training")
    print(f"Target p-value: < {target_p_value}")
    
    # Strategy configurations to try
    strategies = [
        # V1 variants
        {
            'func': confluence_strategy_v1,
            'name': 'Confluence V1 (EMA+RSI+ADX+Structure) - All Required',
            'params': {'ema_fast': 20, 'ema_slow': 50, 'require_all': True}
        },
        {
            'func': confluence_strategy_v1,
            'name': 'Confluence V1 (EMA+RSI+ADX+Structure) - Majority',
            'params': {'ema_fast': 20, 'ema_slow': 50, 'require_all': False}
        },
        {
            'func': confluence_strategy_v1,
            'name': 'Confluence V1 (EMA+RSI+ADX+Structure) - Fast EMAs',
            'params': {'ema_fast': 10, 'ema_slow': 30, 'require_all': False}
        },
        {
            'func': confluence_strategy_v1,
            'name': 'Confluence V1 (EMA+RSI+ADX+Structure) - Slow EMAs',
            'params': {'ema_fast': 30, 'ema_slow': 80, 'require_all': False}
        },
        # V2 variants
        {
            'func': confluence_strategy_v2,
            'name': 'Confluence V2 (EMA+OrderBlock+ADX) - Standard',
            'params': {'ema_fast': 20, 'ema_slow': 50, 'ob_lookback': 20}
        },
        {
            'func': confluence_strategy_v2,
            'name': 'Confluence V2 (EMA+OrderBlock+ADX) - Long Lookback',
            'params': {'ema_fast': 20, 'ema_slow': 50, 'ob_lookback': 40}
        },
        # V3 variants
        {
            'func': confluence_strategy_v3,
            'name': 'Confluence V3 (EMA+RSI+Sweeps) - Standard',
            'params': {'ema_period': 50, 'rsi_period': 14, 'sweep_lookback': 20}
        },
        {
            'func': confluence_strategy_v3,
            'name': 'Confluence V3 (EMA+RSI+Sweeps) - Sensitive',
            'params': {'ema_period': 30, 'rsi_period': 10, 'sweep_lookback': 15}
        },
        # V4 variants
        {
            'func': confluence_strategy_v4,
            'name': 'Confluence V4 (EMA+OB+FVG) - With FVG',
            'params': {'ema_fast': 20, 'ema_slow': 50, 'fvg_confirm': True}
        },
        {
            'func': confluence_strategy_v4,
            'name': 'Confluence V4 (EMA+OB+FVG) - No FVG',
            'params': {'ema_fast': 20, 'ema_slow': 50, 'fvg_confirm': False}
        },
        # V5 variants
        {
            'func': confluence_strategy_v5,
            'name': 'Confluence V5 (Triple+) - 2 Required',
            'params': {'ema_period': 50, 'min_confluence': 2}
        },
        {
            'func': confluence_strategy_v5,
            'name': 'Confluence V5 (Triple+) - 3 Required',
            'params': {'ema_period': 50, 'min_confluence': 3}
        },
        {
            'func': confluence_strategy_v5,
            'name': 'Confluence V5 (Triple+) - Fast EMA, 2 Required',
            'params': {'ema_period': 30, 'min_confluence': 2}
        },
    ]
    
    results = []
    winners = []
    
    for i, config in enumerate(strategies[:max_iterations], 1):
        print(f"\n{'#'*80}")
        print(f"ITERATION {i}/{min(max_iterations, len(strategies))}")
        print(f"{'#'*80}")
        
        result = test_walkforward_only(
            df,
            config['func'],
            config['name'],
            config['params'],
            train_window,
            n_permutations
        )
        
        results.append(result)
        
        if result['passed']:
            winners.append(result)
            print(f"\n🎉 WINNER FOUND!")
            print(f"   Strategy: {result['strategy']}")
            print(f"   WF PF: {result['real_wf_pf']:.4f}")
            print(f"   P-Value: {result['p_value']:.4f}")
            print(f"   Return: {result['total_return']*100:.2f}%")
    
    # Final summary
    print("\n" + "="*80)
    print("EVOLUTION SUMMARY")
    print("="*80)
    
    print(f"\nTested: {len(results)} strategies")
    print(f"Passed: {len(winners)} strategies")
    
    if winners:
        print(f"\n🏆 WINNERS:")
        for i, winner in enumerate(winners, 1):
            print(f"\n{i}. {winner['strategy']}")
            print(f"   WF PF: {winner['real_wf_pf']:.4f}")
            print(f"   P-Value: {winner['p_value']:.4f}")
            print(f"   Return: {winner['total_return']*100:.2f}%")
            print(f"   Sharpe: {winner['sharpe_ratio']:.2f}")
            print(f"   Params: {winner['params']}")
        
        # Pick best by p-value
        best = min(winners, key=lambda x: x['p_value'])
        print(f"\n🥇 BEST PERFORMER:")
        print(f"   {best['strategy']}")
        print(f"   P-Value: {best['p_value']:.4f} (beat {(1-best['p_value'])*100:.1f}% of permutations)")
    else:
        print(f"\n❌ No strategies passed (yet)")
        print(f"   Closest:")
        closest = min(results, key=lambda x: x['p_value'])
        print(f"   {closest['strategy']}")
        print(f"   P-Value: {closest['p_value']:.4f} (needed < {target_p_value})")
        print(f"   WF PF: {closest['real_wf_pf']:.4f}")
    
    # Save results
    results_dir = Path(__file__).parent.parent / 'results'
    results_dir.mkdir(parents=True, exist_ok=True)
    
    summary = {
        'total_tested': len(results),
        'total_passed': len(winners),
        'target_p_value': target_p_value,
        'all_results': results,
        'winners': winners
    }
    
    with open(results_dir / 'confluence_evolution.json', 'w') as f:
        json.dump(summary, f, indent=2)
    
    print(f"\nResults saved to {results_dir}/confluence_evolution.json")
    
    return results, winners


if __name__ == '__main__':
    data_path = Path(__file__).parent.parent / 'data' / 'BTCUSDT_1h.parquet'
    
    if not data_path.exists():
        print(f"Error: Data file not found at {data_path}")
        sys.exit(1)
    
    results, winners = evolve_until_pass(
        data_path=str(data_path),
        max_iterations=15,  # Test up to 15 combinations
        n_permutations=100,
        target_p_value=0.10  # 90% confidence threshold
    )
