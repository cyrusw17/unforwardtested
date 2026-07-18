"""
Phase 6: Multi-Pair AUD Confluence Strategy
Use AUD strength across multiple pairs (AUDUSD, AUDCHF, AUDCAD, AUDJPY, AUDNZD)
to build a stronger, more robust directional signal
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))

import pandas as pd
import numpy as np
import json
from mega_search_framework import (
    fetch_daily_data, enhanced_ict_scoring_v2, calculate_metrics,
    quick_mcpt_screen, full_mcpt, ICTIndicatorLib
)


def build_aud_strength_score(pairs_data: dict, trend_fast: int = 10, trend_slow: int = 30) -> pd.Series:
    """
    Build an AUD strength index by averaging trend direction across multiple AUD crosses
    Returns a score from -N to +N (N = number of pairs) indicating AUD strength consensus
    """
    ict = ICTIndicatorLib()
    scores = []
    
    for pair_name, df in pairs_data.items():
        trend = ict.trend_strength(df, trend_fast, trend_slow)
        # Normalize direction: +1 AUD strong, -1 AUD weak (need to account for AUD being base or quote)
        is_aud_base = pair_name.startswith('AUD')
        direction = np.sign(trend) if is_aud_base else -np.sign(trend)
        scores.append(direction)
    
    # Align all to same index (use first pair's index as reference)
    ref_index = list(pairs_data.values())[0].index
    aligned_scores = []
    for s in scores:
        aligned_scores.append(s.reindex(ref_index, method='ffill').fillna(0))
    
    combined = sum(aligned_scores)
    return combined


def confluence_strategy(
    primary_ohlc: pd.DataFrame,
    aud_strength: pd.Series,
    entry_threshold: float = 1.5,
    ob_lookback: int = 5,
    structure_length: int = 3,
    min_aud_confluence: int = 2,
) -> pd.Series:
    """
    Primary signal from AUDUSD ICT scoring, filtered by broader AUD strength confluence
    """
    base_signal = enhanced_ict_scoring_v2(
        primary_ohlc,
        entry_threshold=entry_threshold,
        ob_lookback=ob_lookback,
        structure_length=structure_length,
    )
    
    # Align aud_strength to primary index
    aud_aligned = aud_strength.reindex(primary_ohlc.index, method='ffill').fillna(0)
    # Shift to avoid lookahead (aud_strength based on same-day data, shift like base signal already shifted)
    aud_aligned_shifted = aud_aligned.shift(1).fillna(0)
    
    # Only take longs when AUD strength confirms (positive), shorts when AUD weak (negative)
    filtered_signal = base_signal.copy()
    filtered_signal[(base_signal == 1) & (aud_aligned_shifted < min_aud_confluence)] = 0
    filtered_signal[(base_signal == -1) & (aud_aligned_shifted > -min_aud_confluence)] = 0
    
    return filtered_signal


def main():
    print("="*80)
    print("PHASE 6: MULTI-PAIR AUD CONFLUENCE STRATEGY")
    print("="*80)
    
    # Fetch AUD crosses for confluence
    aud_pairs = ['AUDUSD=X', 'AUDCHF=X', 'AUDCAD=X', 'AUDJPY=X', 'AUDNZD=X']
    pairs_data = {}
    
    for pair in aud_pairs:
        df = fetch_daily_data(pair, '2018-01-01', '2026-12-31')
        if df is not None and len(df) > 500:
            pairs_data[pair.replace('=X', '')] = df
            print(f"  Loaded {pair}: {len(df)} bars")
    
    if len(pairs_data) < 2:
        print("Insufficient pairs for confluence")
        return
    
    # Build AUD strength index
    print("\nBuilding AUD strength confluence index...")
    aud_strength = build_aud_strength_score(pairs_data)
    
    # Primary pair for trading
    primary = pairs_data['AUDUSD']
    test = primary[primary.index.year >= 2025]
    
    print(f"\nTest period: {test.index[0].date()} to {test.index[-1].date()}")
    
    # Test different confluence thresholds
    candidates = []
    
    for min_confluence in [0, 1, 2, 3]:
        for threshold in [1.0, 1.25, 1.5, 1.75, 2.0]:
            params = {
                'entry_threshold': threshold,
                'ob_lookback': 5,
                'structure_length': 3,
                'min_aud_confluence': min_confluence,
            }
            
            signal = confluence_strategy(test, aud_strength, **params)
            metrics = calculate_metrics(test, signal)
            
            if metrics and metrics['profit_factor'] >= 1.3 and metrics['annual_return'] >= 0.06 and metrics['trades'] >= 15:
                print(f"  min_conf={min_confluence}, thresh={threshold}: Return {metrics['annual_return_pct']:.2f}%, "
                      f"PF {metrics['profit_factor']:.3f}, Trades {metrics['trades']}, MaxDD {metrics['max_drawdown_pct']:.2f}%")
                candidates.append({'params': params, 'metrics': metrics})
    
    # Sort and screen top candidates
    candidates.sort(key=lambda x: x['metrics']['annual_return_pct'], reverse=True)
    
    print(f"\n{'='*80}")
    print(f"TOP CANDIDATES ({len(candidates)} total)")
    print("="*80)
    
    def confluence_wrapper(ohlc, **params):
        return confluence_strategy(ohlc, aud_strength, **params)
    
    for c in candidates[:10]:
        qp = quick_mcpt_screen(test, confluence_wrapper, c['params'], n_permutations=30)
        c['quick_p_value'] = qp
        m = c['metrics']
        print(f"\nReturn: {m['annual_return_pct']:.2f}%, PF: {m['profit_factor']:.3f}, QuickP: {qp:.3f}")
        print(f"  Params: {c['params']}")
    
    # Full MCPT on best
    strong = [c for c in candidates[:10] if c.get('quick_p_value', 1.0) < 0.10]
    strong.sort(key=lambda x: x['metrics']['annual_return_pct'], reverse=True)
    
    print(f"\n{'='*80}")
    print(f"FULL MCPT on {len(strong)} strong candidates")
    print("="*80)
    
    final_results = []
    for c in strong[:5]:
        result = full_mcpt(test, confluence_wrapper, c['params'], n_permutations=200)
        print(f"\nParams: {c['params']}")
        print(f"  Return: {c['metrics']['annual_return_pct']:.2f}%, Full P-Value: {result['p_value']:.4f}")
        print(f"  Status: {'✅ PASS' if result['passed'] else '❌ FAIL'}")
        final_results.append({'params': c['params'], 'metrics': c['metrics'], 'full_mcpt': result})
    
    # Save
    results_dir = Path(__file__).parent.parent / 'results'
    results_dir.mkdir(parents=True, exist_ok=True)
    
    with open(results_dir / 'phase6_multi_pair_confluence.json', 'w') as f:
        json.dump({
            'candidates': candidates,
            'final_results': final_results
        }, f, indent=2, default=str)
    
    print(f"\n💾 Saved to results/phase6_multi_pair_confluence.json")


if __name__ == '__main__':
    main()
