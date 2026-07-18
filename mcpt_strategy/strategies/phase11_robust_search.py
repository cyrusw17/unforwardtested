"""
Phase 11: Stricter Robustness Search (TEST still untouched)
================================================================
Phase 10 selected by aggregate train/validation PF, which can hide a
config that's regime-dependent within train (works in some sub-periods,
loses badly in others) as long as the aggregate nets out positive. That's
exactly the failure mode that has bitten this project before (every prior
"winner" only worked from ~2024 onward).

This phase requires PF > 1.0 in EVERY one of 6 sub-periods spanning
2005-2024 (all before the 2025-2026 TEST window, which remains
completely untouched) -- a much higher bar for a genuinely persistent,
regime-independent edge.
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))

import json
from mega_search_framework import fetch_daily_data, enhanced_ict_scoring_v2, calculate_metrics

PAIRS = [
    'CADJPY=X', 'GBPJPY=X', 'AUDJPY=X', 'EURJPY=X', 'NZDJPY=X', 'CHFJPY=X',
    'USDJPY=X', 'AUDUSD=X', 'NZDUSD=X', 'GBPUSD=X', 'EURUSD=X', 'USDCAD=X',
    'AUDCAD=X', 'AUDNZD=X', 'AUDCHF=X', 'EURGBP=X', 'EURAUD=X', 'GBPAUD=X',
    'NZDCAD=X', 'GBPCAD=X', 'EURCAD=X', 'GBPCHF=X', 'EURCHF=X', 'CADCHF=X',
]

SUBPERIODS = [
    (2005, 2008), (2009, 2012), (2013, 2016), (2017, 2020), (2021, 2022), (2023, 2024),
]


def main():
    print("=" * 90)
    print("PHASE 11: STRICT ROBUSTNESS SEARCH (PF>1.0 required in ALL 6 sub-periods, 2005-2024)")
    print("TEST (2025-2026) remains completely untouched")
    print("=" * 90)

    param_grid = []
    for eth in [2.0, 2.5, 3.0, 3.5]:
        for obl in [3, 5, 10]:
            for obw in [1.5, 2.0, 3.0]:
                for tw in [1.0, 1.5]:
                    param_grid.append(dict(entry_threshold=eth, ob_lookback=obl, ob_weight=obw, trend_weight=tw))

    survivors = []

    for pair in PAIRS:
        df = fetch_daily_data(pair, '2005-01-01', '2026-12-31')
        if df is None or len(df) < 2000:
            continue

        sub_data = [df[(df.index.year >= a) & (df.index.year <= b)] for a, b in SUBPERIODS]
        if any(len(sd) < 200 for sd in sub_data):
            continue

        pair_survivors = 0
        for params in param_grid:
            ok = True
            metrics_list = []
            for sd in sub_data:
                m = calculate_metrics(sd, enhanced_ict_scoring_v2(sd, **params))
                if not m or m['trades'] < 15 or m['profit_factor'] <= 1.0:
                    ok = False
                    break
                metrics_list.append(m)
            if not ok:
                continue
            pair_survivors += 1
            avg_return = sum(m['annual_return_pct'] for m in metrics_list) / len(metrics_list)
            min_pf = min(m['profit_factor'] for m in metrics_list)
            worst_dd = min(m['max_drawdown_pct'] for m in metrics_list)
            total_trades = sum(m['trades'] for m in metrics_list)
            survivors.append({
                'pair': pair, 'params': params, 'avg_return_across_subperiods': avg_return,
                'min_pf_across_subperiods': min_pf, 'worst_dd_across_subperiods': worst_dd,
                'total_trades': total_trades,
                'per_period': [{'period': f'{a}-{b}', 'return': m['annual_return_pct'], 'pf': m['profit_factor'],
                                 'dd': m['max_drawdown_pct'], 'trades': m['trades']}
                                for (a, b), m in zip(SUBPERIODS, metrics_list)],
            })
        print(f"{pair}: {pair_survivors} / {len(param_grid)} configs survive PF>1.0 in all 6 sub-periods")

    survivors.sort(key=lambda x: -x['avg_return_across_subperiods'])

    print(f"\n{'='*90}")
    print(f"TOTAL SURVIVORS: {len(survivors)}")
    print("=" * 90)
    for s in survivors[:15]:
        print(f"  {s['pair']}: avg_return={s['avg_return_across_subperiods']:+.2f}%, "
              f"min_pf={s['min_pf_across_subperiods']:.3f}, worst_dd={s['worst_dd_across_subperiods']:.2f}%, "
              f"trades={s['total_trades']}, params={s['params']}")

    results_dir = Path(__file__).parent.parent / 'results'
    results_dir.mkdir(parents=True, exist_ok=True)
    with open(results_dir / 'phase11_robust_search.json', 'w') as f:
        json.dump(survivors, f, indent=2, default=str)
    print(f"\nSaved {len(survivors)} survivors to results/phase11_robust_search.json")


if __name__ == '__main__':
    main()
