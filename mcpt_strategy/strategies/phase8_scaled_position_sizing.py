"""
Phase 8: Score-Weighted Position Sizing
Instead of binary +1/-1/0 signal, scale position size with signal strength
This should increase returns proportionally to conviction while keeping trade-level stats similar
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


def scaled_position_strategy(
    ohlc: pd.DataFrame,
    entry_threshold: float = 1.5,
    max_score_cap: float = 6.0,
    ob_lookback: int = 5,
    structure_length: int = 3,
    ob_weight: float = 2.0,
    fvg_weight: float = 1.5,
    sweep_weight: float = 1.5,
    structure_weight: float = 1.0,
    trend_weight: float = 1.0,
    trend_fast: int = 10,
    trend_slow: int = 30,
    max_position: float = 2.0,
) -> pd.Series:
    """
    Position size scales with score strength between entry_threshold and max_score_cap
    Position = clip(score / max_score_cap, entry_threshold/max_score_cap, max_position)
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
    
    # Scaled position: proportional to score, capped at max_position
    signal = pd.Series(0.0, index=ohlc.index)
    
    bull_active = bullish_score >= entry_threshold
    bear_active = bearish_score >= entry_threshold
    
    bull_size = (bullish_score / max_score_cap).clip(upper=max_position)
    bear_size = (bearish_score / max_score_cap).clip(upper=max_position)
    
    signal[bull_active] = bull_size[bull_active]
    signal[bear_active] = -bear_size[bear_active]
    
    both = bull_active & bear_active
    signal[both & (bullish_score > bearish_score)] = bull_size[both & (bullish_score > bearish_score)]
    signal[both & (bearish_score > bullish_score)] = -bear_size[both & (bearish_score > bullish_score)]
    
    return signal.shift(1).fillna(0)


def main():
    print("="*80)
    print("PHASE 8: SCORE-WEIGHTED POSITION SIZING")
    print("="*80)
    
    df = fetch_daily_data('AUDUSD=X', '2018-01-01', '2026-12-31')
    test = df[df.index.year >= 2025]
    
    print(f"Test period: {test.index[0].date()} to {test.index[-1].date()} ({len(test)} bars)")
    
    candidates = []
    
    for entry_thresh in [1.0, 1.25, 1.5, 1.75, 2.0]:
        for max_pos in [1.0, 1.5, 2.0, 2.5, 3.0]:
            for max_cap in [4.0, 6.0, 8.0]:
                params = {
                    'entry_threshold': entry_thresh,
                    'max_score_cap': max_cap,
                    'ob_lookback': 5,
                    'structure_length': 3,
                    'max_position': max_pos,
                }
                signal = scaled_position_strategy(test, **params)
                metrics = calculate_metrics(test, signal)
                
                if metrics and metrics['profit_factor'] >= 1.3 and metrics['annual_return'] >= 0.06 and metrics['trades'] >= 15:
                    candidates.append({'params': params, 'metrics': metrics})
    
    candidates.sort(key=lambda x: x['metrics']['annual_return_pct'], reverse=True)
    
    print(f"\nFound {len(candidates)} configs meeting requirements")
    print(f"\n{'='*80}")
    print("TOP 15 CANDIDATES")
    print("="*80)
    
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
        m = c['metrics']
        print(f"\nReturn: {m['annual_return_pct']:.2f}%, PF: {m['profit_factor']:.3f}, MaxDD: {m['max_drawdown_pct']:.2f}%, "
              f"Calmar: {m['calmar_ratio']:.2f}, Trades: {m['trades']}")
        print(f"  Params: {c['params']}")
    
    # Quick MCPT screen
    print(f"\n{'='*80}")
    print("QUICK MCPT SCREENING")
    print("="*80)
    
    for c in unique_top:
        qp = quick_mcpt_screen(test, scaled_position_strategy, c['params'], n_permutations=30)
        c['quick_p_value'] = qp
        m = c['metrics']
        print(f"Return: {m['annual_return_pct']:6.2f}%, MaxDD: {m['max_drawdown_pct']:6.2f}%, QuickP: {qp:.3f}")
    
    # Full MCPT
    strong = [c for c in unique_top if c.get('quick_p_value', 1.0) < 0.10]
    strong.sort(key=lambda x: x['metrics']['annual_return_pct'], reverse=True)
    
    print(f"\n{'='*80}")
    print(f"FULL MCPT on {len(strong)} strong candidates")
    print("="*80)
    
    final_results = []
    for c in strong[:8]:
        result = full_mcpt(test, scaled_position_strategy, c['params'], n_permutations=200)
        print(f"\nParams: {c['params']}")
        print(f"  Return: {c['metrics']['annual_return_pct']:.2f}%, MaxDD: {c['metrics']['max_drawdown_pct']:.2f}%, "
              f"Full P-Value: {result['p_value']:.4f}")
        print(f"  Status: {'✅ PASS' if result['passed'] else '❌ FAIL'}")
        final_results.append({'params': c['params'], 'metrics': c['metrics'], 'full_mcpt': result})
    
    # Save
    results_dir = Path(__file__).parent.parent / 'results'
    results_dir.mkdir(parents=True, exist_ok=True)
    
    with open(results_dir / 'phase8_scaled_position.json', 'w') as f:
        json.dump({'candidates': candidates, 'final_results': final_results}, f, indent=2, default=str)
    
    print(f"\n💾 Saved to results/phase8_scaled_position.json")


if __name__ == '__main__':
    main()
