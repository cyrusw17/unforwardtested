"""
Phase 10: Honest Search for a 15%+ No-Lookahead Strategy
============================================================
Methodology fix from CAUSAL_SEARCH_RESULTS.md: use a strict 3-way split
so the final MCPT validation is spent on a window NEVER used for any
parameter selection.

  TRAIN:      2005-2020  (broad parameter search, selection by PF/Sharpe)
  VALIDATION: 2021-2024  (candidate filtering -- require robustness here
              too, not just on TRAIN, before ever looking at TEST)
  TEST:       2025-2026  (touched exactly once per candidate, at the end,
              for the final MCPT report)
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))

import json
import numpy as np
from mega_search_framework import (
    fetch_daily_data, enhanced_ict_scoring_v2, calculate_metrics,
    full_mcpt
)

PAIRS = [
    'CADJPY=X', 'GBPJPY=X', 'AUDJPY=X', 'EURJPY=X', 'NZDJPY=X', 'CHFJPY=X',
    'USDJPY=X', 'AUDUSD=X', 'NZDUSD=X', 'GBPUSD=X', 'EURUSD=X', 'USDCAD=X',
    'AUDCAD=X', 'AUDNZD=X', 'AUDCHF=X', 'EURGBP=X', 'EURAUD=X', 'GBPAUD=X',
    'NZDCAD=X', 'GBPCAD=X', 'EURCAD=X', 'GBPCHF=X', 'EURCHF=X', 'CADCHF=X',
]


def split_periods(df):
    train = df[(df.index.year >= 2005) & (df.index.year <= 2020)]
    val = df[(df.index.year >= 2021) & (df.index.year <= 2024)]
    test = df[df.index.year >= 2025]
    return train, val, test


def main():
    print("=" * 90)
    print("PHASE 10: HONEST SEARCH (train 2005-2020 / validation 2021-2024 / test 2025-2026)")
    print("=" * 90)

    param_grid = []
    for eth in [1.5, 2.0, 2.5, 3.0, 3.5]:
        for obl in [3, 5, 7, 10]:
            for obw in [1.5, 2.0, 3.0]:
                param_grid.append(dict(entry_threshold=eth, ob_lookback=obl, ob_weight=obw))

    all_results = []

    for pair in PAIRS:
        df = fetch_daily_data(pair, '2005-01-01', '2026-12-31')
        if df is None or len(df) < 2000:
            print(f"{pair}: insufficient data, skipping")
            continue
        train, val, test = split_periods(df)
        if len(train) < 500 or len(val) < 200:
            print(f"{pair}: insufficient split data, skipping")
            continue

        pair_best = None
        for params in param_grid:
            m_train = calculate_metrics(train, enhanced_ict_scoring_v2(train, **params))
            if not m_train or m_train['trades'] < 100:
                continue
            if m_train['profit_factor'] < 1.05:  # require genuine edge on train
                continue
            m_val = calculate_metrics(val, enhanced_ict_scoring_v2(val, **params))
            if not m_val or m_val['trades'] < 30:
                continue
            # Require robustness: positive-ish PF on BOTH train and validation
            score = min(m_train['profit_factor'], m_val['profit_factor'])
            if pair_best is None or score > pair_best['score']:
                pair_best = {
                    'pair': pair, 'params': params, 'score': score,
                    'train_pf': m_train['profit_factor'], 'train_return': m_train['annual_return_pct'],
                    'val_pf': m_val['profit_factor'], 'val_return': m_val['annual_return_pct'],
                    'val_trades': m_val['trades'], 'val_dd': m_val['max_drawdown_pct'],
                }

        if pair_best:
            print(f"{pair}: best train+val-robust config -> train_pf={pair_best['train_pf']:.3f} "
                  f"({pair_best['train_return']:+.2f}%), val_pf={pair_best['val_pf']:.3f} "
                  f"({pair_best['val_return']:+.2f}%), params={pair_best['params']}")
            all_results.append(pair_best)
        else:
            print(f"{pair}: no config with PF>1.05 on both train and validation")

    all_results.sort(key=lambda x: -x['score'])

    print(f"\n{'='*90}")
    print("TOP CANDIDATES (ranked by min(train_pf, val_pf), i.e. robust on BOTH, TEST untouched)")
    print("=" * 90)
    for r in all_results[:10]:
        print(f"  {r['pair']}: score={r['score']:.3f}, train_pf={r['train_pf']:.3f}, "
              f"val_pf={r['val_pf']:.3f}, val_return={r['val_return']:+.2f}%, params={r['params']}")

    results_dir = Path(__file__).parent.parent / 'results'
    results_dir.mkdir(parents=True, exist_ok=True)
    with open(results_dir / 'phase10_honest_search.json', 'w') as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\nSaved {len(all_results)} candidates to results/phase10_honest_search.json")


if __name__ == '__main__':
    main()
