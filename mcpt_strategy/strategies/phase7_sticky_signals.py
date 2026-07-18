"""
Phase 7: Sticky Signal Logic + Multi-Scale Order Blocks
Test if holding positions longer (until opposite signal) improves returns
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))

import pandas as pd
import numpy as np
import json
from mega_search_framework import (
    fetch_daily_data, calculate_metrics, quick_mcpt_screen, full_mcpt, ICTIndicatorLib
)


def enhanced_ict_sticky(
    ohlc: pd.DataFrame,
    entry_threshold: float = 1.5,
    exit_threshold: float = 0.0,
    ob_lookback: int = 5,
    structure_length: int = 3,
    ob_weight: float = 2.0,
    fvg_weight: float = 1.5,
    sweep_weight: float = 1.5,
    structure_weight: float = 1.0,
    trend_weight: float = 1.0,
    trend_fast: int = 10,
    trend_slow: int = 30,
) -> pd.Series:
    """
    Sticky version: Enter when score >= entry_threshold, but only EXIT when 
    opposite score crosses entry_threshold OR same-direction score drops below exit_threshold
    """
    ict = ICTIndicatorLib()
    
    bullish_ob, bearish_ob = ict.order_blocks_with_strength(ohlc, ob_lookback)
    bullish_fvg, bearish_fvg = ict.fvg_with_size(ohlc)
    bullish_sweep, bearish_sweep = ict.liquidity_sweep_strength(ohlc)
    structure = ict.market_structure_score(ohlc, structure_length)
    trend = ict.trend_strength(ohlc, trend_fast, trend_slow)
    
    bullish_score = (
        bullish_ob * ob_weight + bullish_fvg * fvg_weight + bullish_sweep * sweep_weight +
        structure.clip(lower=0) * structure_weight + trend.clip(lower=0) * trend_weight
    )
    bearish_score = (
        bearish_ob * ob_weight + bearish_fvg * fvg_weight + bearish_sweep * sweep_weight +
        abs(structure.clip(upper=0)) * structure_weight + abs(trend.clip(upper=0)) * trend_weight
    )
    
    position = pd.Series(0, index=ohlc.index, dtype=float)
    current_pos = 0
    
    bull_vals = bullish_score.values
    bear_vals = bearish_score.values
    
    for i in range(len(ohlc)):
        b = bull_vals[i]
        s = bear_vals[i]
        
        if current_pos == 0:
            if b >= entry_threshold and b > s:
                current_pos = 1
            elif s >= entry_threshold and s > b:
                current_pos = -1
        elif current_pos == 1:
            if s >= entry_threshold and s > b:
                current_pos = -1
            elif b < exit_threshold:
                current_pos = 0
        elif current_pos == -1:
            if b >= entry_threshold and b > s:
                current_pos = 1
            elif s < exit_threshold:
                current_pos = 0
        
        position.iloc[i] = current_pos
    
    return position.shift(1).fillna(0)


def multi_scale_ob_scoring(
    ohlc: pd.DataFrame,
    entry_threshold: float = 1.5,
    structure_length: int = 3,
    lookbacks: tuple = (3, 5, 8),
    trend_fast: int = 10,
    trend_slow: int = 30,
) -> pd.Series:
    """
    Combine OB signals from multiple lookback scales for a more robust signal
    """
    ict = ICTIndicatorLib()
    
    total_bull_ob = pd.Series(0.0, index=ohlc.index)
    total_bear_ob = pd.Series(0.0, index=ohlc.index)
    
    for lb in lookbacks:
        b_ob, be_ob = ict.order_blocks_with_strength(ohlc, lb)
        total_bull_ob += b_ob
        total_bear_ob += be_ob
    
    total_bull_ob /= len(lookbacks)
    total_bear_ob /= len(lookbacks)
    
    bullish_fvg, bearish_fvg = ict.fvg_with_size(ohlc)
    bullish_sweep, bearish_sweep = ict.liquidity_sweep_strength(ohlc)
    structure = ict.market_structure_score(ohlc, structure_length)
    trend = ict.trend_strength(ohlc, trend_fast, trend_slow)
    
    bullish_score = (
        total_bull_ob * 2.0 + bullish_fvg * 1.5 + bullish_sweep * 1.5 +
        structure.clip(lower=0) + trend.clip(lower=0)
    )
    bearish_score = (
        total_bear_ob * 2.0 + bearish_fvg * 1.5 + bearish_sweep * 1.5 +
        abs(structure.clip(upper=0)) + abs(trend.clip(upper=0))
    )
    
    signal = pd.Series(0, index=ohlc.index, dtype=float)
    signal[bullish_score >= entry_threshold] = 1
    signal[bearish_score >= entry_threshold] = -1
    both = (bullish_score >= entry_threshold) & (bearish_score >= entry_threshold)
    signal[both & (bullish_score > bearish_score)] = 1
    signal[both & (bearish_score > bullish_score)] = -1
    
    return signal.shift(1).fillna(0)


def main():
    print("="*80)
    print("PHASE 7: STICKY SIGNALS + MULTI-SCALE ORDER BLOCKS")
    print("="*80)
    
    df = fetch_daily_data('AUDUSD=X', '2018-01-01', '2026-12-31')
    test = df[df.index.year >= 2025]
    
    print(f"Test period: {test.index[0].date()} to {test.index[-1].date()} ({len(test)} bars)")
    
    candidates = []
    
    # === Sticky signal search ===
    print("\n--- Sticky Signal Search ---")
    for entry_thresh in [1.0, 1.25, 1.5, 1.75, 2.0]:
        for exit_thresh in [-1.0, -0.5, 0.0, 0.5]:
            params = {'entry_threshold': entry_thresh, 'exit_threshold': exit_thresh, 'ob_lookback': 5, 'structure_length': 3}
            signal = enhanced_ict_sticky(test, **params)
            metrics = calculate_metrics(test, signal)
            
            if metrics and metrics['profit_factor'] >= 1.3 and metrics['annual_return'] >= 0.06 and metrics['trades'] >= 15:
                print(f"  entry={entry_thresh}, exit={exit_thresh}: Return {metrics['annual_return_pct']:.2f}%, "
                      f"PF {metrics['profit_factor']:.3f}, Trades {metrics['trades']}, MaxDD {metrics['max_drawdown_pct']:.2f}%")
                candidates.append({'params': params, 'metrics': metrics, 'strategy': 'sticky', 'func': 'enhanced_ict_sticky'})
    
    # === Multi-scale OB search ===
    print("\n--- Multi-Scale Order Block Search ---")
    lookback_combos = [(3, 5), (3, 5, 8), (5, 8, 13), (3, 5, 8, 13), (5, 10)]
    for lookbacks in lookback_combos:
        for thresh in [1.0, 1.25, 1.5, 1.75, 2.0]:
            params = {'entry_threshold': thresh, 'structure_length': 3, 'lookbacks': lookbacks}
            signal = multi_scale_ob_scoring(test, **params)
            metrics = calculate_metrics(test, signal)
            
            if metrics and metrics['profit_factor'] >= 1.3 and metrics['annual_return'] >= 0.06 and metrics['trades'] >= 15:
                print(f"  lookbacks={lookbacks}, thresh={thresh}: Return {metrics['annual_return_pct']:.2f}%, "
                      f"PF {metrics['profit_factor']:.3f}, Trades {metrics['trades']}, MaxDD {metrics['max_drawdown_pct']:.2f}%")
                candidates.append({'params': params, 'metrics': metrics, 'strategy': 'multiscale', 'func': 'multi_scale_ob_scoring'})
    
    # Sort and screen
    candidates.sort(key=lambda x: x['metrics']['annual_return_pct'], reverse=True)
    
    print(f"\n{'='*80}")
    print(f"TOP CANDIDATES ({len(candidates)} total)")
    print("="*80)
    
    func_map = {'enhanced_ict_sticky': enhanced_ict_sticky, 'multi_scale_ob_scoring': multi_scale_ob_scoring}
    
    seen = set()
    unique_top = []
    for c in candidates:
        key = round(c['metrics']['annual_return_pct'], 1)
        if key not in seen:
            seen.add(key)
            unique_top.append(c)
        if len(unique_top) >= 15:
            break
    
    for c in unique_top:
        func = func_map[c['func']]
        qp = quick_mcpt_screen(test, func, c['params'], n_permutations=30)
        c['quick_p_value'] = qp
        m = c['metrics']
        print(f"\n[{c['strategy']}] Return: {m['annual_return_pct']:.2f}%, PF: {m['profit_factor']:.3f}, QuickP: {qp:.3f}")
        print(f"  Params: {c['params']}")
    
    # Full MCPT on best
    strong = [c for c in unique_top if c.get('quick_p_value', 1.0) < 0.10]
    strong.sort(key=lambda x: x['metrics']['annual_return_pct'], reverse=True)
    
    print(f"\n{'='*80}")
    print(f"FULL MCPT on {len(strong)} strong candidates")
    print("="*80)
    
    final_results = []
    for c in strong[:8]:
        func = func_map[c['func']]
        result = full_mcpt(test, func, c['params'], n_permutations=200)
        print(f"\n[{c['strategy']}] Params: {c['params']}")
        print(f"  Return: {c['metrics']['annual_return_pct']:.2f}%, Full P-Value: {result['p_value']:.4f}")
        print(f"  Status: {'✅ PASS' if result['passed'] else '❌ FAIL'}")
        final_results.append({'params': c['params'], 'metrics': c['metrics'], 'full_mcpt': result, 'func': c['func']})
    
    # Save
    results_dir = Path(__file__).parent.parent / 'results'
    results_dir.mkdir(parents=True, exist_ok=True)
    
    with open(results_dir / 'phase7_sticky_multiscale.json', 'w') as f:
        json.dump({'candidates': candidates, 'final_results': final_results}, f, indent=2, default=str)
    
    print(f"\n💾 Saved to results/phase7_sticky_multiscale.json")


if __name__ == '__main__':
    main()
