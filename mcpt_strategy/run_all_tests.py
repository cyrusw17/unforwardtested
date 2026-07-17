"""
Main script to run all MCPT validation steps
Follows the 4-step process from neurotrader888:
1. In-sample excellence
2. In-sample MCPT
3. Walk-forward test
4. Walk-forward MCPT
"""
import sys
from pathlib import Path
import pandas as pd
import json

sys.path.append(str(Path(__file__).parent))

from tests import run_insample_mcpt, run_walkforward_mcpt
from data.fetch_data import load_data


def print_header(text):
    """Print formatted header"""
    print("\n" + "="*80)
    print(text.center(80))
    print("="*80 + "\n")


def run_complete_validation(
    data_path: str,
    train_start_year: int = 2016,
    train_end_year: int = 2024,
    test_end_year: int = 2026,
    n_insample_perms: int = 1000,
    n_walkforward_perms: int = 200
):
    """
    Run complete MCPT validation pipeline
    
    Args:
        data_path: Path to data file
        train_start_year: Start year for training
        train_end_year: End year for training (inclusive)
        test_end_year: End year for testing (inclusive)
        n_insample_perms: Number of in-sample permutations
        n_walkforward_perms: Number of walk-forward permutations
    """
    print_header("MCPT TRADING STRATEGY VALIDATION")
    print(f"Training period: {train_start_year} - {train_end_year}")
    print(f"Forward test period: {train_end_year + 1} - {test_end_year}")
    print(f"In-sample permutations: {n_insample_perms}")
    print(f"Walk-forward permutations: {n_walkforward_perms}")
    
    df = load_data(data_path)
    print(f"\nLoaded data: {len(df)} bars from {df.index[0]} to {df.index[-1]}")
    
    train_df = df[
        (df.index.year >= train_start_year) & 
        (df.index.year <= train_end_year)
    ]
    
    full_df = df[
        (df.index.year >= train_start_year) & 
        (df.index.year <= test_end_year)
    ]
    
    print_header("STEP 1 & 2: IN-SAMPLE OPTIMIZATION & MCPT")
    insample_results = run_insample_mcpt(
        train_df,
        n_permutations=n_insample_perms,
        save_results=True,
        results_dir='results'
    )
    
    train_window = 24 * 365 * 4
    
    print_header("STEP 3 & 4: WALK-FORWARD TEST & MCPT")
    walkforward_results = run_walkforward_mcpt(
        full_df,
        train_window=train_window,
        train_step=24 * 30,
        n_permutations=n_walkforward_perms,
        save_results=True,
        results_dir='results'
    )
    
    print_header("FINAL SUMMARY")
    
    print("IN-SAMPLE MCPT:")
    print(f"  ├─ Profit Factor: {insample_results['real_pf']:.4f}")
    print(f"  ├─ P-Value: {insample_results['p_value']:.4f}")
    print(f"  └─ Status: {'✓ PASS' if insample_results['passed'] else '✗ FAIL'}")
    
    print("\nWALK-FORWARD MCPT:")
    print(f"  ├─ Profit Factor: {walkforward_results['real_wf_pf']:.4f}")
    print(f"  ├─ P-Value: {walkforward_results['p_value']:.4f}")
    print(f"  ├─ Total Return: {walkforward_results['total_return']*100:.2f}%")
    print(f"  ├─ Sharpe Ratio: {walkforward_results['sharpe_ratio']:.2f}")
    print(f"  ├─ Max Drawdown: {walkforward_results['max_drawdown']*100:.2f}%")
    print(f"  └─ Status: {'✓ PASS' if walkforward_results['passed'] else '✗ FAIL'}")
    
    overall_pass = insample_results['passed'] and walkforward_results['passed']
    
    print("\n" + "="*80)
    if overall_pass:
        print("✓ OVERALL: STRATEGY PASSES ALL MCPT TESTS".center(80))
        print("Strategy shows statistical evidence of real edge".center(80))
    else:
        print("✗ OVERALL: STRATEGY FAILS MCPT VALIDATION".center(80))
        print("Strategy may be overfit or lacks robust edge".center(80))
    print("="*80)
    
    summary = {
        'overall_passed': overall_pass,
        'insample_mcpt': insample_results,
        'walkforward_mcpt': walkforward_results
    }
    
    with open('results/validation_summary.json', 'w') as f:
        json.dump(summary, f, indent=2)
    
    print("\nAll results saved to results/ directory")
    print("  - insample_mcpt_results.json")
    print("  - insample_mcpt_histogram.png")
    print("  - walkforward_mcpt_results.json")
    print("  - walkforward_mcpt_results.png")
    print("  - validation_summary.json")
    
    return summary


if __name__ == '__main__':
    data_path = Path(__file__).parent / 'data' / 'BTCUSDT_1h.parquet'
    
    if not data_path.exists():
        print("ERROR: Data file not found!")
        print(f"Expected: {data_path}")
        print("\nPlease run: python data/fetch_data.py")
        sys.exit(1)
    
    summary = run_complete_validation(
        data_path=str(data_path),
        train_start_year=2016,
        train_end_year=2024,
        test_end_year=2026,
        n_insample_perms=1000,
        n_walkforward_perms=200
    )
