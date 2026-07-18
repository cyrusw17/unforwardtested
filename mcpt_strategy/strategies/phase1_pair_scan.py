"""
Phase 1: Scan multiple pairs with baseline parameters
Find which pairs show the strongest edge before deep parameter search
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
    print("PHASE 1: MULTI-PAIR SCAN")
    print("Testing baseline Enhanced ICT across many pairs")
    print("="*80)
    
    # Comprehensive pair list - forex majors, minors, crosses, commodities
    pairs = [
        'AUDUSD=X', 'NZDUSD=X', 'USDCAD=X', 'AUDNZD=X', 'AUDCAD=X',
        'AUDJPY=X', 'NZDJPY=X', 'CADJPY=X', 'AUDCHF=X', 'NZDCAD=X',
        'EURUSD=X', 'GBPUSD=X', 'USDJPY=X', 'USDCHF=X', 'EURGBP=X',
        'EURJPY=X', 'GBPJPY=X', 'EURAUD=X', 'GBPAUD=X', 'EURNZD=X',
    ]
    
    baseline_params = {
        'entry_threshold': 3.0,
        'ob_lookback': 5,
        'structure_length': 5,
    }
    
    results = []
    
    for pair in pairs:
        print(f"\n--- {pair} ---")
        df = fetch_daily_data(pair, '2018-01-01', '2026-12-31')
        
        if df is None or len(df) < 500:
            print(f"  ❌ Insufficient data")
            continue
        
        # Split
        train = df[df.index.year <= 2024]
        test = df[df.index.year >= 2025]
        
        if len(test) < 50:
            split_idx = int(len(df) * 0.75)
            train = df.iloc[:split_idx]
            test = df.iloc[split_idx:]
        
        signal_test = enhanced_ict_scoring_v2(test, **baseline_params)
        metrics_test = calculate_metrics(test, signal_test)
        
        if metrics_test is None:
            print(f"  ❌ No valid signal")
            continue
        
        print(f"  Return: {metrics_test['annual_return_pct']:.2f}%, PF: {metrics_test['profit_factor']:.3f}, "
              f"Trades: {metrics_test['trades']}, WinRate: {metrics_test['win_rate']:.1f}%")
        
        result = {
            'pair': pair,
            'test_metrics': metrics_test,
            'data_points': len(df),
            'test_points': len(test)
        }
        
        # Quick MCPT screen if promising
        if metrics_test['profit_factor'] >= 1.3 and metrics_test['annual_return'] >= 0.06:
            print(f"  Running quick MCPT screen (30 perms)...")
            p_val = quick_mcpt_screen(test, enhanced_ict_scoring_v2, baseline_params, n_permutations=30)
            print(f"  Quick P-Value: {p_val:.3f}")
            result['quick_p_value'] = p_val
        
        results.append(result)
    
    # Summary
    print(f"\n{'='*80}")
    print("PHASE 1 SUMMARY - Ranked by Annual Return")
    print("="*80)
    
    results.sort(key=lambda x: x['test_metrics']['annual_return_pct'], reverse=True)
    
    for r in results:
        qp = r.get('quick_p_value', None)
        qp_str = f", QuickP: {qp:.3f}" if qp is not None else ""
        print(f"\n{r['pair']}: Return {r['test_metrics']['annual_return_pct']:.2f}%, "
              f"PF {r['test_metrics']['profit_factor']:.3f}, "
              f"Trades {r['test_metrics']['trades']}{qp_str}")
    
    # Save
    results_dir = Path(__file__).parent.parent / 'results'
    results_dir.mkdir(parents=True, exist_ok=True)
    
    with open(results_dir / 'phase1_pair_scan.json', 'w') as f:
        json.dump(results, f, indent=2, default=str)
    
    print(f"\n💾 Saved to results/phase1_pair_scan.json")
    
    # Identify top candidates for phase 2
    candidates = [r for r in results if r.get('quick_p_value', 1.0) < 0.3]
    print(f"\n🎯 Top candidates for deep search (quick_p < 0.3): {len(candidates)}")
    for c in candidates:
        print(f"  - {c['pair']}: Return {c['test_metrics']['annual_return_pct']:.2f}%, QuickP {c.get('quick_p_value', 'N/A')}")


if __name__ == '__main__':
    main()
