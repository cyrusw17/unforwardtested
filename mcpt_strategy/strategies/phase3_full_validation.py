"""
Phase 3: Full MCPT Validation on Top Candidates + Extended Threshold Search
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))

import pandas as pd
import numpy as np
import json
import itertools
from mega_search_framework import (
    fetch_daily_data, enhanced_ict_scoring_v2, calculate_metrics,
    quick_mcpt_screen, full_mcpt
)


def main():
    print("="*80)
    print("PHASE 3: EXTENDED THRESHOLD SEARCH + FULL VALIDATION")
    print("="*80)
    
    df = fetch_daily_data('AUDUSD=X', '2018-01-01', '2026-12-31')
    test = df[df.index.year >= 2025]
    train = df[df.index.year <= 2024]
    
    print(f"Test period: {test.index[0].date()} to {test.index[-1].date()} ({len(test)} bars)")
    
    # Extended threshold search - go even lower
    thresholds = [0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.25, 2.5]
    ob_lookbacks = [3, 5, 7, 10]
    structure_lengths = [3, 5]
    
    candidates = []
    
    for threshold, ob_lb, struct_len in itertools.product(thresholds, ob_lookbacks, structure_lengths):
        params = {
            'entry_threshold': threshold,
            'ob_lookback': ob_lb,
            'structure_length': struct_len,
        }
        
        signal = enhanced_ict_scoring_v2(test, **params)
        metrics = calculate_metrics(test, signal)
        
        if metrics is None:
            continue
        
        if metrics['profit_factor'] >= 1.3 and metrics['annual_return'] >= 0.06 and metrics['trades'] >= 15:
            candidates.append({
                'params': params,
                'metrics': metrics
            })
    
    print(f"\nFound {len(candidates)} configs meeting min requirements")
    
    # Sort by return, dedupe similar performance
    candidates.sort(key=lambda x: x['metrics']['annual_return_pct'], reverse=True)
    
    seen_returns = set()
    unique_candidates = []
    for c in candidates:
        key = round(c['metrics']['annual_return_pct'], 1)
        if key not in seen_returns:
            seen_returns.add(key)
            unique_candidates.append(c)
    
    print(f"Unique configs (by return): {len(unique_candidates)}")
    
    # Quick MCPT screen top 15
    top_15 = unique_candidates[:15]
    
    print(f"\n{'='*80}")
    print("QUICK MCPT SCREENING (30 perms)")
    print("="*80)
    
    for cand in top_15:
        p = cand['params']
        m = cand['metrics']
        print(f"\nthreshold={p['entry_threshold']}, ob_lb={p['ob_lookback']}, struct={p['structure_length']}")
        print(f"  Return: {m['annual_return_pct']:.2f}%, PF: {m['profit_factor']:.3f}, Trades: {m['trades']}")
        
        qp = quick_mcpt_screen(test, enhanced_ict_scoring_v2, p, n_permutations=30)
        cand['quick_p_value'] = qp
        print(f"  Quick P: {qp:.3f}")
    
    # Full MCPT on best candidates with quick_p < 0.1
    strong_candidates = [c for c in top_15 if c.get('quick_p_value', 1.0) < 0.10]
    strong_candidates.sort(key=lambda x: x['metrics']['annual_return_pct'], reverse=True)
    
    print(f"\n{'='*80}")
    print(f"FULL MCPT VALIDATION (200 perms) on {len(strong_candidates)} strong candidates")
    print("="*80)
    
    final_results = []
    
    for cand in strong_candidates[:8]:
        p = cand['params']
        m = cand['metrics']
        print(f"\nthreshold={p['entry_threshold']}, ob_lb={p['ob_lookback']}, struct={p['structure_length']}")
        print(f"  Return: {m['annual_return_pct']:.2f}%, PF: {m['profit_factor']:.3f}")
        
        result = full_mcpt(test, enhanced_ict_scoring_v2, p, n_permutations=200)
        
        print(f"  Full MCPT P-Value: {result['p_value']:.4f} (permuted better: {result['permuted_better_count']}/199)")
        print(f"  Status: {'✅ PASS' if result['passed'] else '❌ FAIL'}")
        
        final_results.append({
            'params': p,
            'metrics': m,
            'full_mcpt': result
        })
    
    # Summary
    print(f"\n{'='*80}")
    print("PHASE 3 FINAL SUMMARY")
    print("="*80)
    
    passed = [r for r in final_results if r['full_mcpt']['passed']]
    passed.sort(key=lambda x: x['metrics']['annual_return_pct'], reverse=True)
    
    if passed:
        print(f"\n🏆 {len(passed)} configs passed FULL MCPT (200 perms, p<0.05)!")
        for r in passed:
            print(f"\n  Threshold={r['params']['entry_threshold']}, OB_lb={r['params']['ob_lookback']}, Struct={r['params']['structure_length']}")
            print(f"    Return: {r['metrics']['annual_return_pct']:.2f}%")
            print(f"    PF: {r['metrics']['profit_factor']:.3f}")
            print(f"    Win Rate: {r['metrics']['win_rate']:.1f}%")
            print(f"    Trades: {r['metrics']['trades']}")
            print(f"    P-Value: {r['full_mcpt']['p_value']:.4f}")
    else:
        print("\n❌ No configs passed full MCPT")
        final_results.sort(key=lambda x: x['full_mcpt']['p_value'])
        for r in final_results[:5]:
            print(f"\n  Threshold={r['params']['entry_threshold']}: P={r['full_mcpt']['p_value']:.4f}, Return={r['metrics']['annual_return_pct']:.2f}%")
    
    # Save
    results_dir = Path(__file__).parent.parent / 'results'
    results_dir.mkdir(parents=True, exist_ok=True)
    
    with open(results_dir / 'phase3_full_validation.json', 'w') as f:
        json.dump({
            'all_candidates': unique_candidates,
            'final_results': final_results,
            'passed_count': len(passed)
        }, f, indent=2, default=str)
    
    print(f"\n💾 Saved to results/phase3_full_validation.json")


if __name__ == '__main__':
    main()
