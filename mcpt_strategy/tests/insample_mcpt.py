"""
In-Sample Monte Carlo Permutation Test
Tests whether strategy performance on training data is significantly better than random
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from tqdm import tqdm
import json

from strategies.donchian_strategy import optimize_donchian
from utils import get_permutation


def run_insample_mcpt(
    train_df: pd.DataFrame,
    n_permutations: int = 1000,
    save_results: bool = True,
    results_dir: str = '../results'
):
    """
    Run in-sample Monte Carlo Permutation Test
    
    Args:
        train_df: Training data DataFrame
        n_permutations: Number of permutations to test
        save_results: Whether to save results
        results_dir: Directory to save results
        
    Returns:
        Dict with test results
    """
    print("="*80)
    print("IN-SAMPLE MONTE CARLO PERMUTATION TEST")
    print("="*80)
    
    print("\n[1/3] Optimizing on real training data...")
    best_params, best_real_pf = optimize_donchian(train_df)
    
    print(f"\nBest parameters: {best_params}")
    print(f"In-sample Profit Factor: {best_real_pf:.4f}")
    
    print(f"\n[2/3] Running {n_permutations} permutations...")
    perm_better_count = 1
    permuted_pfs = []
    
    for perm_i in tqdm(range(1, n_permutations), desc="Permutations"):
        train_perm = get_permutation(train_df, seed=perm_i)
        
        _, best_perm_pf = optimize_donchian(train_perm)
        
        if best_perm_pf >= best_real_pf:
            perm_better_count += 1
        
        permuted_pfs.append(best_perm_pf)
    
    insample_mcpt_pval = perm_better_count / n_permutations
    
    print("\n[3/3] Test Results:")
    print(f"  P-Value: {insample_mcpt_pval:.4f}")
    print(f"  Permutations better than real: {perm_better_count}/{n_permutations}")
    print(f"  Real PF: {best_real_pf:.4f}")
    print(f"  Mean Permuted PF: {np.mean(permuted_pfs):.4f}")
    print(f"  Std Permuted PF: {np.std(permuted_pfs):.4f}")
    
    if insample_mcpt_pval < 0.01:
        print("\n  ✓ PASS: P-value < 0.01 (strategy has real edge)")
    else:
        print("\n  ✗ FAIL: P-value >= 0.01 (strategy may be overfit)")
    
    results = {
        'test_type': 'in_sample_mcpt',
        'n_permutations': n_permutations,
        'real_pf': float(best_real_pf),
        'best_params': best_params,
        'p_value': float(insample_mcpt_pval),
        'perm_better_count': int(perm_better_count),
        'permuted_pfs_mean': float(np.mean(permuted_pfs)),
        'permuted_pfs_std': float(np.std(permuted_pfs)),
        'permuted_pfs': [float(x) for x in permuted_pfs],
        'passed': insample_mcpt_pval < 0.01
    }
    
    if save_results:
        results_path = Path(results_dir)
        results_path.mkdir(parents=True, exist_ok=True)
        
        with open(results_path / 'insample_mcpt_results.json', 'w') as f:
            json.dump(results, f, indent=2)
        
        plt.style.use('dark_background')
        plt.figure(figsize=(12, 6))
        
        plt.hist(permuted_pfs, bins=50, color='blue', alpha=0.7, label='Permutations', edgecolor='white')
        plt.axvline(best_real_pf, color='red', linewidth=2, label=f'Real (PF={best_real_pf:.4f})')
        
        plt.xlabel("Profit Factor", fontsize=12)
        plt.ylabel("Frequency", fontsize=12)
        plt.title(f"In-Sample MCPT - P-Value: {insample_mcpt_pval:.4f}", fontsize=14, fontweight='bold')
        plt.legend(fontsize=11)
        plt.grid(False)
        
        plt.tight_layout()
        plt.savefig(results_path / 'insample_mcpt_histogram.png', dpi=150, bbox_inches='tight')
        print(f"\nResults saved to {results_path}/")
    
    return results


if __name__ == '__main__':
    data_path = Path(__file__).parent.parent / 'data' / 'BTCUSDT_1h.parquet'
    
    if not data_path.exists():
        print(f"Error: Data file not found at {data_path}")
        print("Please run data/fetch_data.py first to download data")
        sys.exit(1)
    
    df = pd.read_parquet(data_path)
    
    train_df = df[(df.index.year >= 2016) & (df.index.year <= 2024)]
    
    print(f"Training data: {train_df.index[0]} to {train_df.index[-1]}")
    print(f"Total bars: {len(train_df)}")
    
    results = run_insample_mcpt(
        train_df,
        n_permutations=1000,
        save_results=True,
        results_dir='../results'
    )
