"""
Walk-Forward Monte Carlo Permutation Test
Tests whether strategy performance on out-of-sample data is significantly better than random
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from tqdm import tqdm
import json

from strategies.donchian_strategy import walkforward_donchian
from utils import get_permutation


def run_walkforward_mcpt(
    df: pd.DataFrame,
    train_window: int = 24 * 365 * 4,
    train_step: int = 24 * 30,
    n_permutations: int = 200,
    save_results: bool = True,
    results_dir: str = '../results'
):
    """
    Run walk-forward Monte Carlo Permutation Test
    
    Args:
        df: Full DataFrame including train and test periods
        train_window: Number of bars for training window
        train_step: Number of bars between reoptimizations
        n_permutations: Number of permutations to test
        save_results: Whether to save results
        results_dir: Directory to save results
        
    Returns:
        Dict with test results
    """
    print("="*80)
    print("WALK-FORWARD MONTE CARLO PERMUTATION TEST")
    print("="*80)
    
    print("\n[1/4] Computing walk-forward signal on real data...")
    df['r'] = np.log(df['close']).diff().shift(-1)
    
    wf_signal = walkforward_donchian(df, train_lookback=train_window, train_step=train_step)
    
    donch_rets = wf_signal * df['r']
    donch_rets = donch_rets.dropna()
    
    real_wf_pf = donch_rets[donch_rets > 0].sum() / donch_rets[donch_rets < 0].abs().sum()
    
    oos_start_idx = train_window
    oos_rets = donch_rets.iloc[oos_start_idx:]
    oos_start_date = df.index[oos_start_idx]
    oos_end_date = df.index[-1]
    
    print(f"\nWalk-Forward Profit Factor: {real_wf_pf:.4f}")
    print(f"Out-of-sample period: {oos_start_date} to {oos_end_date}")
    print(f"Out-of-sample bars: {len(oos_rets)}")
    
    print(f"\n[2/4] Running {n_permutations} permutations...")
    perm_better_count = 1
    permuted_pfs = []
    
    for perm_i in tqdm(range(1, n_permutations), desc="Walk-forward permutations"):
        wf_perm = get_permutation(df, start_index=train_window, seed=perm_i * 1000)
        
        wf_perm['r'] = np.log(wf_perm['close']).diff().shift(-1)
        wf_perm_sig = walkforward_donchian(wf_perm, train_lookback=train_window, train_step=train_step)
        
        perm_rets = wf_perm['r'] * wf_perm_sig
        perm_rets = perm_rets.dropna()
        
        if perm_rets[perm_rets < 0].sum() == 0:
            perm_pf = 0
        else:
            perm_pf = perm_rets[perm_rets > 0].sum() / perm_rets[perm_rets < 0].abs().sum()
        
        if perm_pf >= real_wf_pf:
            perm_better_count += 1
        
        permuted_pfs.append(perm_pf)
    
    walkforward_mcpt_pval = perm_better_count / n_permutations
    
    print("\n[3/4] Test Results:")
    print(f"  P-Value: {walkforward_mcpt_pval:.4f}")
    print(f"  Permutations better than real: {perm_better_count}/{n_permutations}")
    print(f"  Real WF PF: {real_wf_pf:.4f}")
    print(f"  Mean Permuted PF: {np.mean(permuted_pfs):.4f}")
    print(f"  Std Permuted PF: {np.std(permuted_pfs):.4f}")
    
    oos_years = (oos_end_date - oos_start_date).days / 365.25
    threshold = 0.05 if oos_years < 2 else 0.01
    
    print(f"\n  Out-of-sample duration: {oos_years:.1f} years")
    print(f"  Threshold for pass: {threshold:.2f}")
    
    if walkforward_mcpt_pval < threshold:
        print(f"\n  ✓ PASS: P-value < {threshold} (strategy generalizes well)")
    else:
        print(f"\n  ✗ FAIL: P-value >= {threshold} (strategy may not generalize)")
    
    print("\n[4/4] Computing equity curve...")
    cumulative_rets = oos_rets.cumsum()
    total_return = np.exp(cumulative_rets.iloc[-1]) - 1
    sharpe = oos_rets.mean() / oos_rets.std() * np.sqrt(365 * 24) if oos_rets.std() > 0 else 0
    
    drawdowns = cumulative_rets - cumulative_rets.cummax()
    max_dd = drawdowns.min()
    
    print(f"\n  Total Return: {total_return*100:.2f}%")
    print(f"  Sharpe Ratio: {sharpe:.2f}")
    print(f"  Max Drawdown: {max_dd*100:.2f}%")
    
    results = {
        'test_type': 'walkforward_mcpt',
        'n_permutations': n_permutations,
        'real_wf_pf': float(real_wf_pf),
        'p_value': float(walkforward_mcpt_pval),
        'perm_better_count': int(perm_better_count),
        'permuted_pfs_mean': float(np.mean(permuted_pfs)),
        'permuted_pfs_std': float(np.std(permuted_pfs)),
        'permuted_pfs': [float(x) for x in permuted_pfs],
        'oos_years': float(oos_years),
        'threshold': float(threshold),
        'passed': walkforward_mcpt_pval < threshold,
        'total_return': float(total_return),
        'sharpe_ratio': float(sharpe),
        'max_drawdown': float(max_dd),
        'oos_start': str(oos_start_date),
        'oos_end': str(oos_end_date)
    }
    
    if save_results:
        results_path = Path(results_dir)
        results_path.mkdir(parents=True, exist_ok=True)
        
        with open(results_path / 'walkforward_mcpt_results.json', 'w') as f:
            json.dump(results, f, indent=2)
        
        plt.style.use('dark_background')
        fig, axes = plt.subplots(2, 1, figsize=(14, 10))
        
        axes[0].hist(permuted_pfs, bins=50, color='blue', alpha=0.7, label='Permutations', edgecolor='white')
        axes[0].axvline(real_wf_pf, color='red', linewidth=2, label=f'Real (PF={real_wf_pf:.4f})')
        axes[0].set_xlabel("Profit Factor", fontsize=12)
        axes[0].set_ylabel("Frequency", fontsize=12)
        axes[0].set_title(f"Walk-Forward MCPT - P-Value: {walkforward_mcpt_pval:.4f}", fontsize=14, fontweight='bold')
        axes[0].legend(fontsize=11)
        axes[0].grid(False)
        
        cumulative_rets.plot(ax=axes[1], color='cyan', linewidth=2)
        axes[1].fill_between(cumulative_rets.index, 0, cumulative_rets.values, alpha=0.3, color='cyan')
        axes[1].set_xlabel("Date", fontsize=12)
        axes[1].set_ylabel("Cumulative Log Return", fontsize=12)
        axes[1].set_title(f"Out-of-Sample Equity Curve (Return: {total_return*100:.2f}%, Sharpe: {sharpe:.2f})", 
                         fontsize=14, fontweight='bold')
        axes[1].grid(True, alpha=0.3)
        
        plt.tight_layout()
        plt.savefig(results_path / 'walkforward_mcpt_results.png', dpi=150, bbox_inches='tight')
        print(f"\nResults saved to {results_path}/")
    
    return results


if __name__ == '__main__':
    data_path = Path(__file__).parent.parent / 'data' / 'BTCUSDT_1h.parquet'
    
    if not data_path.exists():
        print(f"Error: Data file not found at {data_path}")
        print("Please run data/fetch_data.py first to download data")
        sys.exit(1)
    
    df = pd.read_parquet(data_path)
    
    df = df[(df.index.year >= 2016) & (df.index.year <= 2026)]
    
    print(f"Full data: {df.index[0]} to {df.index[-1]}")
    print(f"Total bars: {len(df)}")
    
    train_window = 24 * 365 * 4
    
    results = run_walkforward_mcpt(
        df,
        train_window=train_window,
        train_step=24 * 30,
        n_permutations=200,
        save_results=True,
        results_dir='../results'
    )
