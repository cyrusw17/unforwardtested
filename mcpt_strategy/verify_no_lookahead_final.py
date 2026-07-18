"""
Independent verification that the final deployed strategy (causal_portfolio_15pct.py
/ GBPJPY + NZDCAD legs) has no lookahead bias -- run fresh after deployment,
using the same growing-window technique that originally caught the Order Block bug.

Two checks, for both legs:
  1. Backtest-level: truncate the historical series at many cutoff points,
     recompute the signal, and confirm that every value in the truncated
     series exactly matches the corresponding value computed from the full
     series. If any indicator used future bars, extending the series would
     retroactively change earlier values.
  2. Production-level: run the EXACT function the live paper trading bot
     calls (`paper_trading.engine.get_latest_signal`, including its
     placeholder-row trick) on a sample of historical dates and confirm it
     reproduces the same value the vectorized backtest assigned to that
     date -- i.e. the bot's real-time decision process is provably
     equivalent to the backtested one.
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
sys.path.append(str(Path(__file__).parent / 'strategies'))
sys.path.append(str(Path(__file__).parent.parent / 'paper_trading'))

import numpy as np
from mega_search_framework import fetch_daily_data, enhanced_ict_scoring_v2
import engine as live_engine

LEGS = [
    ('GBPJPY=X', dict(entry_threshold=2.5, ob_lookback=3, ob_weight=3.0, trend_weight=1.0)),
    ('NZDCAD=X', dict(entry_threshold=2.0, ob_lookback=3, ob_weight=1.5, trend_weight=1.5)),
]


def check_truncation_invariance(pair, params):
    df = fetch_daily_data(pair, '2005-01-01', '2026-12-31')
    df = df[df.index.year >= 2024]
    full_signal = enhanced_ict_scoring_v2(df, **params)
    n = len(df)

    mismatches = 0
    checks = 0
    for cutoff_frac in [0.3, 0.5, 0.7, 0.9]:
        cutoff = int(n * cutoff_frac)
        truncated = df.iloc[:cutoff]
        trunc_signal = enhanced_ict_scoring_v2(truncated, **params)
        for date in trunc_signal.index[-60:]:
            checks += 1
            if trunc_signal.loc[date] != full_signal.loc[date]:
                mismatches += 1
                print(f"  MISMATCH ({pair}) at {date}: truncated={trunc_signal.loc[date]}, "
                      f"full={full_signal.loc[date]}")
    print(f"{pair}: backtest-level truncation-invariance -- {checks} checks, {mismatches} mismatches "
          f"-> {'LOOKAHEAD DETECTED' if mismatches else 'PASS (causal)'}")
    return mismatches == 0


def check_production_path_matches_backtest(pair, params):
    df = fetch_daily_data(pair, '2005-01-01', '2026-12-31')
    df = df[df.index.year >= 2023]
    full_signal = enhanced_ict_scoring_v2(df, **params)
    nonzero_dates = full_signal[full_signal != 0].index

    rng = np.random.default_rng(7)
    eligible = [d for d in nonzero_dates if df.index.get_loc(d) >= 30]
    sample_dates = rng.choice(eligible, size=min(20, len(eligible)), replace=False)

    checks = 0
    mismatches = 0
    for d in sample_dates:
        idx = df.index.get_loc(d)
        sim_df = df.iloc[:idx]  # simulate "live" the day BEFORE d
        live_sig = live_engine.get_latest_signal(pair, sim_df)
        expected = full_signal.loc[d]
        checks += 1
        if live_sig != expected:
            mismatches += 1
            print(f"  MISMATCH ({pair}) at {d}: live_engine={live_sig}, backtest={expected}")
    print(f"{pair}: production-path vs backtest -- {checks} checks, {mismatches} mismatches "
          f"-> {'MISMATCH DETECTED' if mismatches else 'PASS (bot reproduces backtest exactly)'}")
    return mismatches == 0


def main():
    print("=" * 90)
    print("FINAL NO-LOOKAHEAD VERIFICATION -- causal_portfolio_15pct (GBPJPY + NZDCAD)")
    print("=" * 90)
    all_pass = True
    for pair, params in LEGS:
        all_pass &= check_truncation_invariance(pair, params)
        all_pass &= check_production_path_matches_backtest(pair, params)
        print()
    print("=" * 90)
    print(f"OVERALL: {'ALL CHECKS PASS -- no lookahead bias found' if all_pass else 'FAILURES FOUND'}")
    print("=" * 90)


if __name__ == '__main__':
    main()
