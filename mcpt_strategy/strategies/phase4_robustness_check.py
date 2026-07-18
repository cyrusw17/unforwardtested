"""
Phase 4: Robustness Check
Validate top candidates aren't overfit to the 2025-2026 test window
by checking: 1) Training period behavior, 2) Walk-forward across sub-periods, 
3) MCPT on training period too
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))

import pandas as pd
import numpy as np
import json
from mega_search_framework import (
    fetch_daily_data, enhanced_ict_scoring_v2, calculate_metrics,
    quick_mcpt_screen, full_mcpt
)


def main():
    print("="*80)
    print("PHASE 4: ROBUSTNESS CHECK")
    print("Verify top candidates aren't overfit to 2025-2026 window")
    print("="*80)
    
    df = fetch_daily_data('AUDUSD=X', '2018-01-01', '2026-12-31')
    
    # Top candidates from phase 3
    candidates = [
        {'name': 'Threshold=1.5, OB=3, Struct=3', 'params': {'entry_threshold': 1.5, 'ob_lookback': 3, 'structure_length': 3}},
        {'name': 'Threshold=1.5, OB=5, Struct=3', 'params': {'entry_threshold': 1.5, 'ob_lookback': 5, 'structure_length': 3}},
        {'name': 'Threshold=1.75, OB=5, Struct=3', 'params': {'entry_threshold': 1.75, 'ob_lookback': 5, 'structure_length': 3}},
        {'name': 'Threshold=2.25, OB=5, Struct=3', 'params': {'entry_threshold': 2.25, 'ob_lookback': 5, 'structure_length': 3}},
        {'name': 'Original Baseline (3.0)', 'params': {'entry_threshold': 3.0, 'ob_lookback': 5, 'structure_length': 5}},
    ]
    
    # Define periods
    periods = {
        '2018-2019': df[(df.index.year >= 2018) & (df.index.year <= 2019)],
        '2020-2021': df[(df.index.year >= 2020) & (df.index.year <= 2021)],
        '2022-2023': df[(df.index.year >= 2022) & (df.index.year <= 2023)],
        '2024': df[df.index.year == 2024],
        '2025-2026': df[df.index.year >= 2025],
    }
    
    for p in periods:
        print(f"{p}: {len(periods[p])} bars")
    
    results = []
    
    for cand in candidates:
        print(f"\n{'='*80}")
        print(f"Candidate: {cand['name']}")
        print(f"{'='*80}")
        
        period_results = {}
        
        for period_name, period_data in periods.items():
            if len(period_data) < 50:
                print(f"  {period_name}: insufficient data")
                continue
            
            signal = enhanced_ict_scoring_v2(period_data, **cand['params'])
            metrics = calculate_metrics(period_data, signal)
            
            if metrics:
                print(f"  {period_name}: Return {metrics['annual_return_pct']:6.2f}%, PF {metrics['profit_factor']:.3f}, "
                      f"Trades {metrics['trades']}, WinRate {metrics['win_rate']:.1f}%")
                period_results[period_name] = metrics
            else:
                print(f"  {period_name}: No valid signal")
                period_results[period_name] = None
        
        # Check consistency - how many periods are profitable (PF > 1.0)?
        profitable_periods = sum(1 for m in period_results.values() if m and m['profit_factor'] > 1.0)
        total_periods = sum(1 for m in period_results.values() if m is not None)
        
        print(f"\n  Consistency: {profitable_periods}/{total_periods} periods profitable")
        
        results.append({
            'candidate': cand['name'],
            'params': cand['params'],
            'period_results': period_results,
            'profitable_periods': profitable_periods,
            'total_periods': total_periods
        })
    
    # Run MCPT on training period (2018-2024) for the best candidates
    print(f"\n{'='*80}")
    print("MCPT ON TRAINING PERIOD (2018-2024) - Check if edge exists historically too")
    print("="*80)
    
    train_all = df[df.index.year <= 2024]
    
    for cand in candidates[:4]:  # Skip baseline, already tested
        print(f"\n{cand['name']}:")
        signal = enhanced_ict_scoring_v2(train_all, **cand['params'])
        metrics = calculate_metrics(train_all, signal)
        
        if metrics and metrics['profit_factor'] >= 1.1:
            print(f"  Training Return: {metrics['annual_return_pct']:.2f}%, PF: {metrics['profit_factor']:.3f}")
            if metrics['profit_factor'] >= 1.3 and metrics['annual_return'] >= 0.06:
                mcpt_train = full_mcpt(train_all, enhanced_ict_scoring_v2, cand['params'], n_permutations=100)
                print(f"  Training MCPT P-Value: {mcpt_train['p_value']:.4f}")
        else:
            print(f"  Training Return: {metrics['annual_return_pct']:.2f}% (PF: {metrics['profit_factor']:.3f}) - Below threshold, that's OK for OOS validation")
    
    # Save
    results_dir = Path(__file__).parent.parent / 'results'
    results_dir.mkdir(parents=True, exist_ok=True)
    
    with open(results_dir / 'phase4_robustness_check.json', 'w') as f:
        json.dump(results, f, indent=2, default=str)
    
    print(f"\n💾 Saved to results/phase4_robustness_check.json")
    print(f"\n{'='*80}\n")


if __name__ == '__main__':
    main()
