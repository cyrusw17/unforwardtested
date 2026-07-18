"""
ICT Strategy Battle - Test Multiple ICT Concepts Against MCPT
Find which strategy passes the rigorous MCPT validation
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

import pandas as pd
import numpy as np
from tqdm import tqdm
import json
import matplotlib.pyplot as plt

from strategies.ict_strategies import (
    optimize_ict_order_block,
    optimize_ict_fvg,
    optimize_ict_liquidity_sweep,
    optimize_ict_hybrid
)
from utils import get_permutation


def test_strategy_mcpt(
    train_df: pd.DataFrame,
    optimize_func,
    strategy_name: str,
    n_permutations: int = 100
) -> dict:
    """
    Test a single strategy with MCPT
    
    Args:
        train_df: Training data
        optimize_func: Optimization function to test
        strategy_name: Name of strategy
        n_permutations: Number of permutations
        
    Returns:
        Dict with test results
    """
    print(f"\n{'='*80}")
    print(f"TESTING: {strategy_name}")
    print('='*80)
    
    print("\n[1/2] Optimizing on real data...")
    best_params, best_real_pf = optimize_func(train_df)
    
    print(f"Best parameters: {best_params}")
    print(f"Real Profit Factor: {best_real_pf:.4f}")
    
    if best_real_pf < 1.01:
        print(f"⚠️  Real PF too low ({best_real_pf:.4f}), skipping permutations")
        return {
            'strategy': strategy_name,
            'real_pf': float(best_real_pf),
            'params': best_params,
            'p_value': 1.0,
            'passed': False,
            'skipped': True
        }
    
    print(f"\n[2/2] Running {n_permutations} permutations...")
    perm_better_count = 1
    permuted_pfs = []
    
    for perm_i in tqdm(range(1, n_permutations), desc=f"{strategy_name} perms"):
        try:
            train_perm = get_permutation(train_df, seed=perm_i * 100)
            _, perm_pf = optimize_func(train_perm)
            
            if perm_pf >= best_real_pf:
                perm_better_count += 1
            
            permuted_pfs.append(perm_pf)
        except:
            permuted_pfs.append(1.0)
    
    p_value = perm_better_count / n_permutations
    passed = p_value < 0.01
    
    print(f"\n✓ P-Value: {p_value:.4f}")
    print(f"  Real PF: {best_real_pf:.4f}")
    print(f"  Mean Permuted PF: {np.mean(permuted_pfs):.4f}")
    print(f"  Status: {'✓ PASS' if passed else '✗ FAIL'}")
    
    return {
        'strategy': strategy_name,
        'real_pf': float(best_real_pf),
        'params': best_params,
        'p_value': float(p_value),
        'perm_better_count': int(perm_better_count),
        'permuted_pfs_mean': float(np.mean(permuted_pfs)),
        'permuted_pfs_std': float(np.std(permuted_pfs)),
        'permuted_pfs': [float(x) for x in permuted_pfs],
        'passed': passed,
        'skipped': False
    }


def run_ict_battle(
    data_path: str,
    train_start_year: int = 2016,
    train_end_year: int = 2024,
    n_permutations: int = 100,
    save_results: bool = True
):
    """
    Run all ICT strategies against MCPT and find the winner
    
    Args:
        data_path: Path to data file
        train_start_year: Start year for training
        train_end_year: End year for training
        n_permutations: Number of permutations per strategy
        save_results: Whether to save results
    """
    print("="*80)
    print("ICT STRATEGY BATTLE - MCPT VALIDATION")
    print("="*80)
    
    df = pd.read_parquet(data_path)
    train_df = df[
        (df.index.year >= train_start_year) & 
        (df.index.year <= train_end_year)
    ]
    
    print(f"\nTraining data: {train_df.index[0]} to {train_df.index[-1]}")
    print(f"Total bars: {len(train_df)}")
    print(f"Permutations per strategy: {n_permutations}")
    
    # Test all strategies
    strategies = [
        (optimize_ict_order_block, "ICT Order Block"),
        (optimize_ict_fvg, "ICT Fair Value Gap"),
        (optimize_ict_liquidity_sweep, "ICT Liquidity Sweep"),
        (optimize_ict_hybrid, "ICT Hybrid (Combined)")
    ]
    
    results = []
    for optimize_func, name in strategies:
        result = test_strategy_mcpt(train_df, optimize_func, name, n_permutations)
        results.append(result)
    
    # Summary
    print("\n" + "="*80)
    print("FINAL RESULTS")
    print("="*80)
    
    passed_strategies = [r for r in results if r['passed']]
    
    print("\n📊 Strategy Comparison:")
    print(f"{'Strategy':<30} {'Real PF':<12} {'P-Value':<12} {'Status'}")
    print("-" * 80)
    
    for r in results:
        status = "✓ PASS" if r['passed'] else ("⊘ SKIP" if r.get('skipped') else "✗ FAIL")
        print(f"{r['strategy']:<30} {r['real_pf']:<12.4f} {r['p_value']:<12.4f} {status}")
    
    if passed_strategies:
        print(f"\n🎉 {len(passed_strategies)} strategy(ies) PASSED MCPT!")
        
        # Find best by PF
        best = max(passed_strategies, key=lambda x: x['real_pf'])
        print(f"\n🏆 WINNER: {best['strategy']}")
        print(f"   Real PF: {best['real_pf']:.4f}")
        print(f"   P-Value: {best['p_value']:.4f}")
        print(f"   Parameters: {best['params']}")
    else:
        print("\n❌ No strategies passed MCPT")
        print("   This is normal - MCPT is very strict!")
        
        # Show closest
        best_attempt = min(results, key=lambda x: x['p_value'])
        print(f"\n🥈 CLOSEST: {best_attempt['strategy']}")
        print(f"   Real PF: {best_attempt['real_pf']:.4f}")
        print(f"   P-Value: {best_attempt['p_value']:.4f} (needed < 0.01)")
        print(f"   Parameters: {best_attempt['params']}")
    
    # Save results
    if save_results:
        results_dir = Path(__file__).parent.parent / 'results'
        results_dir.mkdir(parents=True, exist_ok=True)
        
        summary = {
            'test_type': 'ict_strategy_battle',
            'n_permutations': n_permutations,
            'train_period': f"{train_start_year}-{train_end_year}",
            'strategies_tested': len(results),
            'strategies_passed': len(passed_strategies),
            'results': results
        }
        
        with open(results_dir / 'ict_battle_results.json', 'w') as f:
            json.dump(summary, f, indent=2)
        
        # Plot comparison
        plt.style.use('dark_background')
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))
        
        # Profit factors
        names = [r['strategy'].replace('ICT ', '') for r in results]
        pfs = [r['real_pf'] for r in results]
        colors = ['green' if r['passed'] else 'red' for r in results]
        
        ax1.barh(names, pfs, color=colors, alpha=0.7)
        ax1.axvline(1.0, color='white', linestyle='--', linewidth=1, alpha=0.5)
        ax1.set_xlabel('Profit Factor', fontsize=12)
        ax1.set_title('Real Profit Factors', fontsize=14, fontweight='bold')
        ax1.grid(axis='x', alpha=0.3)
        
        # P-values
        p_values = [r['p_value'] for r in results]
        ax2.barh(names, p_values, color=colors, alpha=0.7)
        ax2.axvline(0.01, color='yellow', linestyle='--', linewidth=2, label='Pass Threshold')
        ax2.set_xlabel('P-Value', fontsize=12)
        ax2.set_title('MCPT P-Values (lower is better)', fontsize=14, fontweight='bold')
        ax2.legend()
        ax2.grid(axis='x', alpha=0.3)
        
        plt.tight_layout()
        plt.savefig(results_dir / 'ict_battle_comparison.png', dpi=150, bbox_inches='tight')
        
        print(f"\nResults saved to {results_dir}/")
    
    return results


if __name__ == '__main__':
    data_path = Path(__file__).parent.parent / 'data' / 'BTCUSDT_1h.parquet'
    
    if not data_path.exists():
        print(f"Error: Data file not found at {data_path}")
        print("Please run data/generate_synthetic_data.py first")
        sys.exit(1)
    
    results = run_ict_battle(
        data_path=str(data_path),
        train_start_year=2016,
        train_end_year=2024,
        n_permutations=100,
        save_results=True
    )
