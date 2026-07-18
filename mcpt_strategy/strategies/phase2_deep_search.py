"""
Phase 2: Deep Parameter Search
Focus on AUD/USD (confirmed) + retest near-candidates with varied thresholds
Goal: find highest return configuration that still passes MCPT
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
    print("PHASE 2: DEEP PARAMETER SEARCH")
    print("="*80)
    
    # Pairs to deep search (confirmed + near-candidates)
    pairs = ['AUDUSD=X', 'USDCHF=X', 'USDJPY=X', 'EURAUD=X', 'EURUSD=X', 'AUDCHF=X']
    
    # Parameter grid
    thresholds = [1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0]
    ob_lookbacks = [3, 5, 7]
    structure_lengths = [3, 5, 7]
    
    all_candidates = []
    
    for pair in pairs:
        print(f"\n{'='*80}")
        print(f"Pair: {pair}")
        print(f"{'='*80}")
        
        df = fetch_daily_data(pair, '2018-01-01', '2026-12-31')
        if df is None or len(df) < 500:
            print(f"  ❌ Insufficient data")
            continue
        
        test = df[df.index.year >= 2025]
        if len(test) < 50:
            split_idx = int(len(df) * 0.75)
            test = df.iloc[split_idx:]
        
        print(f"  Test period: {test.index[0].date()} to {test.index[-1].date()} ({len(test)} bars)")
        
        pair_results = []
        
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
                pair_results.append({
                    'pair': pair,
                    'params': params,
                    'metrics': metrics
                })
        
        print(f"  Found {len(pair_results)} configs meeting min requirements")
        
        # Sort by annual return, take top 10 for MCPT screening
        pair_results.sort(key=lambda x: x['metrics']['annual_return_pct'], reverse=True)
        top_candidates = pair_results[:10]
        
        for cand in top_candidates:
            print(f"\n  Testing: threshold={cand['params']['entry_threshold']}, "
                  f"ob_lb={cand['params']['ob_lookback']}, struct={cand['params']['structure_length']}")
            print(f"    Return: {cand['metrics']['annual_return_pct']:.2f}%, PF: {cand['metrics']['profit_factor']:.3f}, "
                  f"Trades: {cand['metrics']['trades']}")
            
            p_val = quick_mcpt_screen(test, enhanced_ict_scoring_v2, cand['params'], n_permutations=30)
            print(f"    Quick P-Value: {p_val:.3f}")
            
            cand['quick_p_value'] = p_val
            all_candidates.append(cand)
    
    # Overall summary
    print(f"\n{'='*80}")
    print("PHASE 2 SUMMARY")
    print("="*80)
    
    # Filter promising ones
    promising = [c for c in all_candidates if c.get('quick_p_value', 1.0) < 0.15]
    promising.sort(key=lambda x: x['metrics']['annual_return_pct'], reverse=True)
    
    print(f"\n🎯 Promising candidates (quick_p < 0.15): {len(promising)}")
    for c in promising[:20]:
        print(f"\n  {c['pair']} - threshold={c['params']['entry_threshold']}, "
              f"ob_lb={c['params']['ob_lookback']}, struct={c['params']['structure_length']}")
        print(f"    Return: {c['metrics']['annual_return_pct']:.2f}%, PF: {c['metrics']['profit_factor']:.3f}, "
              f"QuickP: {c['quick_p_value']:.3f}")
    
    # Save
    results_dir = Path(__file__).parent.parent / 'results'
    results_dir.mkdir(parents=True, exist_ok=True)
    
    with open(results_dir / 'phase2_deep_search.json', 'w') as f:
        json.dump({
            'all_candidates': all_candidates,
            'promising': promising
        }, f, indent=2, default=str)
    
    print(f"\n💾 Saved to results/phase2_deep_search.json")
    print(f"\nTotal configs tested: {len(all_candidates)}")


if __name__ == '__main__':
    main()
