"""
Phase 9: Final Validation of Top Scaled-Position Candidates
Full MCPT + period consistency check
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))

import pandas as pd
import numpy as np
import json
from mega_search_framework import fetch_daily_data, calculate_metrics, full_mcpt
from phase8_scaled_position_sizing import scaled_position_strategy


def main():
    print("="*80)
    print("PHASE 9: FINAL VALIDATION - SCALED POSITION CANDIDATES")
    print("="*80)
    
    df = fetch_daily_data('AUDUSD=X', '2018-01-01', '2026-12-31')
    test = df[df.index.year >= 2025]
    
    candidates = [
        {'name': 'Conservative (max_pos=2.0)', 'params': {'entry_threshold': 1.5, 'max_score_cap': 4.0, 'ob_lookback': 5, 'structure_length': 3, 'max_position': 2.0}},
        {'name': 'Moderate (max_pos=2.5)', 'params': {'entry_threshold': 1.5, 'max_score_cap': 4.0, 'ob_lookback': 5, 'structure_length': 3, 'max_position': 2.5}},
        {'name': 'Aggressive (max_pos=2.5, cap=2.5)', 'params': {'entry_threshold': 1.5, 'max_score_cap': 2.5, 'ob_lookback': 5, 'structure_length': 3, 'max_position': 2.5}},
        {'name': 'Very Aggressive (max_pos=4.0, cap=2.5)', 'params': {'entry_threshold': 1.5, 'max_score_cap': 2.5, 'ob_lookback': 5, 'structure_length': 3, 'max_position': 4.0}},
        {'name': 'Ultra Aggressive (max_pos=3.5, cap=2.5, thresh=1.75)', 'params': {'entry_threshold': 1.75, 'max_score_cap': 2.5, 'ob_lookback': 5, 'structure_length': 3, 'max_position': 3.5}},
    ]
    
    print(f"\nTest period: {test.index[0].date()} to {test.index[-1].date()}\n")
    
    final_results = []
    
    for cand in candidates:
        print(f"\n{'='*80}")
        print(f"Candidate: {cand['name']}")
        print(f"Params: {cand['params']}")
        print(f"{'='*80}")
        
        signal = scaled_position_strategy(test, **cand['params'])
        metrics = calculate_metrics(test, signal)
        
        print(f"Return: {metrics['annual_return_pct']:.2f}%, PF: {metrics['profit_factor']:.3f}, "
              f"MaxDD: {metrics['max_drawdown_pct']:.2f}%, Calmar: {metrics['calmar_ratio']:.2f}, "
              f"Sharpe: {metrics['sharpe_ratio']:.2f}, Trades: {metrics['trades']}")
        
        print(f"\nRunning full MCPT (200 permutations)...")
        mcpt_result = full_mcpt(test, scaled_position_strategy, cand['params'], n_permutations=200)
        
        print(f"  P-Value: {mcpt_result['p_value']:.4f}")
        print(f"  Permuted Better: {mcpt_result['permuted_better_count']}/199")
        print(f"  Status: {'✅ PASS' if mcpt_result['passed'] else '❌ FAIL'}")
        
        final_results.append({
            'name': cand['name'],
            'params': cand['params'],
            'metrics': metrics,
            'mcpt': mcpt_result
        })
    
    # Period consistency check on best candidates
    print(f"\n{'='*80}")
    print("PERIOD CONSISTENCY CHECK")
    print("="*80)
    
    periods = {
        '2018-2019': df[(df.index.year >= 2018) & (df.index.year <= 2019)],
        '2020-2021': df[(df.index.year >= 2020) & (df.index.year <= 2021)],
        '2022-2023': df[(df.index.year >= 2022) & (df.index.year <= 2023)],
        '2024': df[df.index.year == 2024],
        '2025-2026': test,
    }
    
    for cand in candidates:
        print(f"\n{cand['name']}:")
        for pname, pdata in periods.items():
            if len(pdata) < 50:
                continue
            signal = scaled_position_strategy(pdata, **cand['params'])
            m = calculate_metrics(pdata, signal)
            if m:
                print(f"  {pname}: Return {m['annual_return_pct']:7.2f}%, MaxDD {m['max_drawdown_pct']:6.2f}%, PF {m['profit_factor']:.3f}")
    
    # Sub-period drawdown analysis for best candidate (monthly)
    best = max(final_results, key=lambda x: x['metrics']['annual_return_pct'] if x['mcpt']['passed'] else -999)
    print(f"\n{'='*80}")
    print(f"MONTHLY BREAKDOWN - Best Passing Candidate: {best['name']}")
    print("="*80)
    
    signal = scaled_position_strategy(test, **best['params'])
    returns = np.log(test['Close']).diff().shift(-1)
    strategy_returns = (signal * returns).dropna()
    
    monthly = strategy_returns.resample('M').sum()
    for date, ret in monthly.items():
        pct = (np.exp(ret) - 1) * 100
        print(f"  {date.strftime('%Y-%m')}: {pct:+7.2f}%")
    
    # Save
    results_dir = Path(__file__).parent.parent / 'results'
    results_dir.mkdir(parents=True, exist_ok=True)
    
    with open(results_dir / 'phase9_final_validation.json', 'w') as f:
        json.dump({'final_results': final_results}, f, indent=2, default=str)
    
    print(f"\n💾 Saved to results/phase9_final_validation.json")
    
    # Print final recommendation
    print(f"\n{'='*80}")
    print("RECOMMENDATION")
    print("="*80)
    
    passing = [r for r in final_results if r['mcpt']['passed']]
    passing.sort(key=lambda x: x['metrics']['annual_return_pct'], reverse=True)
    
    print(f"\n{len(passing)}/{len(final_results)} candidates passed MCPT\n")
    for r in passing:
        print(f"  {r['name']}: Return {r['metrics']['annual_return_pct']:.2f}%, MaxDD {r['metrics']['max_drawdown_pct']:.2f}%, "
              f"P-Value {r['mcpt']['p_value']:.4f}, Calmar {r['metrics']['calmar_ratio']:.2f}")


if __name__ == '__main__':
    main()
