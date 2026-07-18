"""
Phase 12: Portfolio-level MCPT for the GBPJPY + NZDCAD combo
==================================================================
Individually, on the untouched TEST window (2025-2026), both candidates
found by the strict train/validation robustness search (phase11) show a
real, positive edge but don't clear p<0.05 alone (limited ~18 months of
daily data => low statistical power):
    GBPJPY  entry_threshold=2.5, ob_lookback=3,  ob_weight=3.0, trend_weight=1.0   p=0.096
    NZDCAD  entry_threshold=2.0, ob_lookback=3,  ob_weight=1.5, trend_weight=1.5   p=0.084

They are only -0.24 correlated (near-independent bets), so an equal-weight
portfolio increases statistical power. This uses the project's canonical
multi-market permutation function (`utils.bar_permute.get_permutation`),
which applies the SAME random permutation across both markets per draw --
correctly preserving cross-pair contemporaneous correlation while
destroying temporal/serial predictability (the right null hypothesis for
a multi-asset portfolio test, as opposed to permuting each leg fully
independently).
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))

import numpy as np
import pandas as pd
from mega_search_framework import fetch_daily_data, enhanced_ict_scoring_v2
from mcpt_strategy.utils.bar_permute import get_permutation

LEGS = [
    ('GBPJPY=X', dict(entry_threshold=2.5, ob_lookback=3, ob_weight=3.0, trend_weight=1.0)),
    ('NZDCAD=X', dict(entry_threshold=2.0, ob_lookback=3, ob_weight=1.5, trend_weight=1.5)),
]


def strat_returns(ohlc_lower: pd.DataFrame, params: dict) -> pd.Series:
    """`ohlc_lower` has lowercase columns (open/high/low/close); rename to
    the capitalized columns `enhanced_ict_scoring_v2` expects."""
    ohlc = ohlc_lower.rename(columns=str.title)
    sig = enhanced_ict_scoring_v2(ohlc, **params)  # already internally shift(1)'d
    returns = np.log(ohlc['Close']).diff().shift(-1)
    return (sig * returns).fillna(0)


def portfolio_metrics(port_ret: pd.Series) -> dict:
    cum = port_ret.cumsum()
    dd = (cum - cum.cummax()).min() * 100
    total_ret = port_ret.sum()
    ann_ret = total_ret * (252 / len(port_ret)) * 100
    pos_sum = port_ret[port_ret > 0].sum()
    neg_sum = abs(port_ret[port_ret < 0].sum())
    pf = pos_sum / neg_sum if neg_sum > 0 else np.inf
    sharpe = port_ret.mean() / port_ret.std() * np.sqrt(252) if port_ret.std() > 0 else 0
    return dict(annual_return_pct=ann_ret, max_drawdown_pct=dd, profit_factor=pf, sharpe_ratio=sharpe)


def main():
    print("=" * 90)
    print("PHASE 12: PORTFOLIO MCPT -- GBPJPY + NZDCAD (equal weight), TEST 2025-2026")
    print("Using canonical multi-market get_permutation (shared draw across both legs)")
    print("=" * 90)

    ohlc_data = {}
    for pair, params in LEGS:
        df = fetch_daily_data(pair, '2005-01-01', '2026-12-31')
        test = df[df.index.year >= 2025]
        ohlc_data[pair] = test

    common_idx = ohlc_data[LEGS[0][0]].index.intersection(ohlc_data[LEGS[1][0]].index)
    ohlc_data = {p: d.reindex(common_idx).rename(columns=str.lower) for p, d in ohlc_data.items()}

    real_rets = [strat_returns(ohlc_data[pair], params) for pair, params in LEGS]
    real_port = 0.5 * real_rets[0] + 0.5 * real_rets[1]
    real_m = portfolio_metrics(real_port)
    real_pf = real_m['profit_factor']
    print(f"REAL portfolio: Return={real_m['annual_return_pct']:.2f}%, "
          f"DD={real_m['max_drawdown_pct']:.2f}%, Sharpe={real_m['sharpe_ratio']:.2f}, PF={real_pf:.3f}")

    n_perm = 1000
    np.random.seed(42)
    ohlc_list = [ohlc_data[pair] for pair, _ in LEGS]
    perm_pfs = []
    for i in range(n_perm):
        perm_list = get_permutation(ohlc_list, seed=None)  # advances the global np.random state each call
        leg_rets = []
        for (pair, params), perm_ohlc in zip(LEGS, perm_list):
            leg_rets.append(strat_returns(perm_ohlc, params))
        port = 0.5 * leg_rets[0] + 0.5 * leg_rets[1]
        m = portfolio_metrics(port)
        perm_pfs.append(m['profit_factor'])
        if (i + 1) % 200 == 0:
            print(f"  ... {i+1}/{n_perm} permutations done")

    perm_pfs = np.array(perm_pfs)
    p_value = (np.sum(perm_pfs >= real_pf) + 1) / (n_perm + 1)
    print(f"\nPermutation PF distribution: mean={perm_pfs.mean():.3f}, std={perm_pfs.std():.3f}, "
          f"95th pct={np.percentile(perm_pfs, 95):.3f}")
    print(f"Real PF={real_pf:.3f} vs {n_perm} permutations -> p-value = {p_value:.4f}")
    print(f"Result: {'PASS (p<0.05)' if p_value < 0.05 else 'FAIL (p>=0.05)'}")


if __name__ == '__main__':
    main()
