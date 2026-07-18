"""
CADJPY Causal-Validated Strategy (candidate, NOT yet deployed live)
=====================================================================
Found via the search documented in CAUSAL_SEARCH_RESULTS.md, after
fixing the lookahead bug documented in LOOKAHEAD_BIAS_FINDING.md.

METHODOLOGY (the important part): unlike every previous strategy in this
project, parameters here were selected using ONLY 2018-2024 training
data (by profit factor), with 2025-2026 completely untouched during
selection. The result below is a single, un-re-tuned evaluation on that
previously-untouched window.

PERFORMANCE (2025-2026 out-of-sample, selected without seeing this data):
  Annual Return:  7.56%
  Profit Factor:  1.490
  Sharpe Ratio:   1.42
  Max Drawdown:   -2.46%
  Trades:         158
  MCPT p-value (500 perms): 0.020  -- PASS

CAVEAT: this strategy loses money in every historical period before
2024 (2018-2019, 2020-2021, 2022-2023 all show PF < 1) and is only
profitable from 2024 onward. This exact pattern shows up in every
strategy this project has produced. It may reflect a genuine 2024+
regime shift in JPY-cross trending behavior, or it may simply be that
~2 years of data isn't enough to fully distinguish a real edge from a
lucky stretch. Treat this as a modest, honestly-validated, but
NOT long-track-record-proven edge -- not a repeat of the (bugged)
18-27% return claims made earlier in this project.
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))

from mcpt_strategy.strategies.mega_search_framework import enhanced_ict_scoring_v2

PAIR = 'CADJPY=X'
PARAMS = dict(entry_threshold=1.5, ob_lookback=3, ob_weight=1.5, trend_weight=1.5)


def cadjpy_causal_validated(ohlc):
    """Simple binary directional signal (+1/0/-1), no conviction-weighted sizing."""
    return enhanced_ict_scoring_v2(ohlc, **PARAMS)


if __name__ == '__main__':
    from mcpt_strategy.strategies.mega_search_framework import fetch_daily_data, calculate_metrics, full_mcpt

    df = fetch_daily_data(PAIR, '2018-01-01', '2026-12-31')
    test = df[df.index.year >= 2025]

    sig = cadjpy_causal_validated(test)
    m = calculate_metrics(test, sig)
    print("CADJPY causal-validated strategy -- 2025-2026:")
    print(f"  Return: {m['annual_return_pct']:.2f}%, PF: {m['profit_factor']:.3f}, "
          f"MaxDD: {m['max_drawdown_pct']:.2f}%, Sharpe: {m['sharpe_ratio']:.2f}, Trades: {m['trades']}")

    print("\nRunning full MCPT (500 permutations)...")
    result = full_mcpt(test, enhanced_ict_scoring_v2, PARAMS, n_permutations=500)
    print(f"  P-Value: {result['p_value']:.4f}")
    print(f"  Status: {'PASS' if result['passed'] else 'FAIL'}")
