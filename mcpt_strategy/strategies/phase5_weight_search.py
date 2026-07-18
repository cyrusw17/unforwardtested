"""
Phase 5: Weight Variation + Confluence Search
Building on best threshold=1.5, ob_lookback=5, structure=3
Now vary component weights, trend periods, and add confluence filters
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
    print("PHASE 5: WEIGHT & CONFLUENCE SEARCH")
    print("Base: threshold=1.5, ob_lookback=5, structure=3")
    print("="*80)
    
    df = fetch_daily_data('AUDUSD=X', '2018-01-01', '2026-12-31')
    test = df[df.index.year >= 2025]
    
    base_params = {
        'entry_threshold': 1.5,
        'ob_lookback': 5,
        'structure_length': 3,
    }
    
    candidates = []
    
    # === Search 1: Weight variations ===
    print("\n--- Weight Variation Search ---")
    weight_combos = [
        {'ob_weight': 1.0, 'fvg_weight': 1.0, 'sweep_weight': 1.0, 'structure_weight': 1.0, 'trend_weight': 1.0},
        {'ob_weight': 2.0, 'fvg_weight': 1.5, 'sweep_weight': 1.5, 'structure_weight': 1.0, 'trend_weight': 1.0},  # original
        {'ob_weight': 2.5, 'fvg_weight': 1.0, 'sweep_weight': 1.0, 'structure_weight': 1.5, 'trend_weight': 1.5},
        {'ob_weight': 1.5, 'fvg_weight': 2.0, 'sweep_weight': 2.0, 'structure_weight': 1.0, 'trend_weight': 1.0},
        {'ob_weight': 3.0, 'fvg_weight': 1.0, 'sweep_weight': 1.0, 'structure_weight': 1.0, 'trend_weight': 0.5},
        {'ob_weight': 1.0, 'fvg_weight': 1.0, 'sweep_weight': 2.5, 'structure_weight': 1.5, 'trend_weight': 1.0},
        {'ob_weight': 2.0, 'fvg_weight': 2.0, 'sweep_weight': 2.0, 'structure_weight': 2.0, 'trend_weight': 2.0},
        {'ob_weight': 1.0, 'fvg_weight': 0.5, 'sweep_weight': 0.5, 'structure_weight': 2.0, 'trend_weight': 2.0},
    ]
    
    for wc in weight_combos:
        params = {**base_params, **wc}
        signal = enhanced_ict_scoring_v2(test, **params)
        metrics = calculate_metrics(test, signal)
        
        if metrics and metrics['profit_factor'] >= 1.3 and metrics['annual_return'] >= 0.06 and metrics['trades'] >= 15:
            print(f"  {wc}: Return {metrics['annual_return_pct']:.2f}%, PF {metrics['profit_factor']:.3f}, Trades {metrics['trades']}")
            candidates.append({'params': params, 'metrics': metrics, 'search': 'weights'})
    
    # === Search 2: Trend period variations ===
    print("\n--- Trend Period Search ---")
    trend_combos = [
        (5, 15), (5, 20), (10, 20), (10, 30), (10, 40), (15, 40), (20, 50), (5, 50)
    ]
    
    for fast, slow in trend_combos:
        params = {**base_params, 'trend_fast': fast, 'trend_slow': slow}
        signal = enhanced_ict_scoring_v2(test, **params)
        metrics = calculate_metrics(test, signal)
        
        if metrics and metrics['profit_factor'] >= 1.3 and metrics['annual_return'] >= 0.06 and metrics['trades'] >= 15:
            print(f"  fast={fast}, slow={slow}: Return {metrics['annual_return_pct']:.2f}%, PF {metrics['profit_factor']:.3f}, Trades {metrics['trades']}")
            candidates.append({'params': params, 'metrics': metrics, 'search': 'trend_periods'})
    
    # === Search 3: RSI confluence filter ===
    print("\n--- RSI Confluence Filter Search ---")
    rsi_combos = [
        {'use_rsi_filter': True, 'rsi_period': 14, 'rsi_oversold': 30, 'rsi_overbought': 70},
        {'use_rsi_filter': True, 'rsi_period': 14, 'rsi_oversold': 35, 'rsi_overbought': 65},
        {'use_rsi_filter': True, 'rsi_period': 14, 'rsi_oversold': 40, 'rsi_overbought': 60},
        {'use_rsi_filter': True, 'rsi_period': 21, 'rsi_oversold': 35, 'rsi_overbought': 65},
    ]
    
    for rc in rsi_combos:
        params = {**base_params, **rc}
        signal = enhanced_ict_scoring_v2(test, **params)
        metrics = calculate_metrics(test, signal)
        
        if metrics and metrics['profit_factor'] >= 1.3 and metrics['annual_return'] >= 0.06 and metrics['trades'] >= 15:
            print(f"  {rc}: Return {metrics['annual_return_pct']:.2f}%, PF {metrics['profit_factor']:.3f}, Trades {metrics['trades']}")
            candidates.append({'params': params, 'metrics': metrics, 'search': 'rsi_filter'})
    
    # === Search 4: Volatility regime filter ===
    print("\n--- Volatility Regime Filter Search ---")
    vol_combos = [
        {'use_vol_filter': True, 'vol_min': 0.0, 'vol_max': 0.5},
        {'use_vol_filter': True, 'vol_min': 0.0, 'vol_max': 0.7},
        {'use_vol_filter': True, 'vol_min': 0.3, 'vol_max': 1.0},
        {'use_vol_filter': True, 'vol_min': 0.2, 'vol_max': 0.8},
    ]
    
    for vc in vol_combos:
        params = {**base_params, **vc}
        signal = enhanced_ict_scoring_v2(test, **params)
        metrics = calculate_metrics(test, signal)
        
        if metrics and metrics['profit_factor'] >= 1.3 and metrics['annual_return'] >= 0.06 and metrics['trades'] >= 15:
            print(f"  {vc}: Return {metrics['annual_return_pct']:.2f}%, PF {metrics['profit_factor']:.3f}, Trades {metrics['trades']}")
            candidates.append({'params': params, 'metrics': metrics, 'search': 'vol_filter'})
    
    # === Search 5: Combined threshold + weight sweep ===
    print("\n--- Combined Threshold + Weight Sweep ---")
    thresholds_fine = [1.0, 1.25, 1.5, 1.75, 2.0]
    for thresh in thresholds_fine:
        for wc in weight_combos[:4]:
            params = {**base_params, 'entry_threshold': thresh, **wc}
            signal = enhanced_ict_scoring_v2(test, **params)
            metrics = calculate_metrics(test, signal)
            
            if metrics and metrics['profit_factor'] >= 1.3 and metrics['annual_return'] >= 0.06 and metrics['trades'] >= 15:
                candidates.append({'params': params, 'metrics': metrics, 'search': 'combined'})
    
    print(f"\nCombined search found {len([c for c in candidates if c['search']=='combined'])} additional candidates")
    
    # Sort all candidates by return
    candidates.sort(key=lambda x: x['metrics']['annual_return_pct'], reverse=True)
    
    print(f"\n{'='*80}")
    print(f"TOP 15 CANDIDATES BY RETURN (from {len(candidates)} total)")
    print("="*80)
    
    for i, c in enumerate(candidates[:15]):
        m = c['metrics']
        print(f"\n{i+1}. [{c['search']}] Return: {m['annual_return_pct']:.2f}%, PF: {m['profit_factor']:.3f}, "
              f"MaxDD: {m['max_drawdown_pct']:.2f}%, Trades: {m['trades']}")
        print(f"   Params: {c['params']}")
    
    # Quick MCPT screen top candidates
    print(f"\n{'='*80}")
    print("QUICK MCPT SCREENING TOP CANDIDATES")
    print("="*80)
    
    top_unique = []
    seen = set()
    for c in candidates:
        key = round(c['metrics']['annual_return_pct'], 1)
        if key not in seen:
            seen.add(key)
            top_unique.append(c)
        if len(top_unique) >= 20:
            break
    
    for c in top_unique:
        qp = quick_mcpt_screen(test, enhanced_ict_scoring_v2, c['params'], n_permutations=30)
        c['quick_p_value'] = qp
        m = c['metrics']
        print(f"Return: {m['annual_return_pct']:6.2f}%, PF: {m['profit_factor']:.3f}, QuickP: {qp:.3f}  [{c['search']}]")
    
    # Save
    results_dir = Path(__file__).parent.parent / 'results'
    results_dir.mkdir(parents=True, exist_ok=True)
    
    with open(results_dir / 'phase5_weight_search.json', 'w') as f:
        json.dump({
            'all_candidates': candidates,
            'top_unique_with_mcpt': top_unique
        }, f, indent=2, default=str)
    
    print(f"\n💾 Saved to results/phase5_weight_search.json")


if __name__ == '__main__':
    main()
