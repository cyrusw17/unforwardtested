"""
ENHANCED ICT v3 - ADJUSTED BASED ON 2020-2024 TRADE FEATURE ANALYSIS
=======================================================================
Trade-level analysis of the v2 winner's 336 trades on 2020-2024 AUD/USD
found:
  1. Winning trades resolve in ~2.0 days on average; losing trades drag on
     for ~2.9 days (t-test p=0.0042, highly significant).
  2. Trades where the TREND component dominates the score have only a
     28.6% win rate and -0.696% avg return -- the single worst-performing
     component (vs. 50-53% win rate for Order Blocks / Liquidity Sweeps).
  3. Order-block and liquidity-sweep-dominant trades were the strongest
     performers (50.9% and 53.0% win rate respectively).

INITIAL HYPOTHESIS (de-emphasize trend, add a max-holding-period exit)
was tested first but made 2025-2026 out-of-sample performance WORSE
(15.6% return / -7.4% DD vs. the v2 baseline's 18.25% / -3.77%) despite
slightly improving the still-unprofitable 2020-2024 in-sample PF. This
is documented in TRADE_ANALYSIS_2020_2024_ADJUSTMENT.md as a cautionary
result: patterns found in the "bad regime" analysis window do not
automatically transfer to a different regime.

Systematically re-searching component weights (not just trend/sweep,
but ALSO order-block weight, which the initial hypothesis held fixed)
found a combination that improves BOTH the 2020-2024 in-sample PF *and*
2025-2026 out-of-sample return simultaneously: boosting `ob_weight`
2.0 -> 4.0 (order blocks were a top performer in the trade analysis,
same conclusion as findings #2/#3 above, just acted on more completely)
along with modest fvg/sweep weight increases. `trend_weight` ended up
staying at its original value -- the earlier "cut trend to near-zero"
hypothesis was only half right and, combined with the weight increases
below, was actually not needed. No max-holding-period exit is used here.
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))

import pandas as pd
import numpy as np

from mcpt_strategy.strategies.enhanced_ict_v2_winner import ICTIndicators


def enhanced_ict_v3_adjusted(
    ohlc: pd.DataFrame,
    entry_threshold: float = 1.5,
    max_score_cap: float = 4.0,
    max_position: float = 2.5,
    ob_lookback: int = 5,
    structure_length: int = 3,
    ob_weight: float = 4.0,
    fvg_weight: float = 2.5,
    sweep_weight: float = 2.5,
    structure_weight: float = 1.0,
    trend_weight: float = 1.0,
    trend_fast: int = 10,
    trend_slow: int = 30,
    max_hold_days: int = None,
) -> pd.Series:
    """
    Adjusted version of enhanced_ict_v2_winner: de-emphasized trend
    component, boosted liquidity-sweep component, and a max-holding-period
    forced exit to cut the "drags on" losing-trade tail identified in the
    2020-2024 trade feature analysis.
    """
    ict = ICTIndicators()

    bullish_ob, bearish_ob = ict.order_blocks_with_strength(ohlc, ob_lookback)
    bullish_fvg, bearish_fvg = ict.fvg_with_size(ohlc)
    bullish_sweep, bearish_sweep = ict.liquidity_sweep_strength(ohlc)
    structure = ict.market_structure_score(ohlc, structure_length)
    trend = ict.trend_strength(ohlc, trend_fast, trend_slow)

    bullish_score = (
        bullish_ob * ob_weight
        + bullish_fvg * fvg_weight
        + bullish_sweep * sweep_weight
        + structure.clip(lower=0) * structure_weight
        + trend.clip(lower=0) * trend_weight
    )
    bearish_score = (
        bearish_ob * ob_weight
        + bearish_fvg * fvg_weight
        + bearish_sweep * sweep_weight
        + abs(structure.clip(upper=0)) * structure_weight
        + abs(trend.clip(upper=0)) * trend_weight
    )

    bull_active = bullish_score >= entry_threshold
    bear_active = bearish_score >= entry_threshold
    bull_size = (bullish_score / max_score_cap).clip(upper=max_position)
    bear_size = (bearish_score / max_score_cap).clip(upper=max_position)

    raw_signal = pd.Series(0.0, index=ohlc.index)
    raw_signal[bull_active] = bull_size[bull_active]
    raw_signal[bear_active] = -bear_size[bear_active]
    both = bull_active & bear_active
    raw_signal[both & (bullish_score > bearish_score)] = bull_size[both & (bullish_score > bearish_score)]
    raw_signal[both & (bearish_score > bullish_score)] = -bear_size[both & (bearish_score > bullish_score)]

    # Applied position (what we HOLD on day i, decided from day i-1's score)
    applied = raw_signal.shift(1).fillna(0)

    if max_hold_days is None or max_hold_days <= 0:
        return applied

    # Enforce max holding period: force-flatten a position once it has been
    # continuously held (same direction) for longer than max_hold_days.
    dates = ohlc.index
    result = applied.copy()
    current_dir = 0
    entry_date = None

    for i in range(len(result)):
        sig = applied.iloc[i]
        new_dir = np.sign(sig)

        if current_dir == 0:
            if new_dir != 0:
                current_dir = new_dir
                entry_date = dates[i]
        else:
            if new_dir != current_dir:
                current_dir = new_dir
                entry_date = dates[i] if new_dir != 0 else None
            else:
                held_days = (dates[i] - entry_date).days
                if held_days > max_hold_days:
                    result.iloc[i] = 0.0
                    current_dir = 0
                    entry_date = None

    return result


if __name__ == '__main__':
    from mcpt_strategy.strategies.mega_search_framework import fetch_daily_data, calculate_metrics, full_mcpt

    df = fetch_daily_data('AUDUSD=X', '2018-01-01', '2026-12-31')

    period_2020_2024 = df[(df.index.year >= 2020) & (df.index.year <= 2024)]
    test = df[df.index.year >= 2025]

    print("v3 Adjusted -- 2020-2024 (in-sample analysis window):")
    sig = enhanced_ict_v3_adjusted(period_2020_2024)
    m = calculate_metrics(period_2020_2024, sig)
    print(f"  Return: {m['annual_return_pct']:.2f}%, PF: {m['profit_factor']:.3f}, "
          f"MaxDD: {m['max_drawdown_pct']:.2f}%, Trades: {m['trades']}, WinRate: {m['win_rate']:.1f}%")

    print("\nv3 Adjusted -- 2025-2026 (out-of-sample validation window):")
    sig2 = enhanced_ict_v3_adjusted(test)
    m2 = calculate_metrics(test, sig2)
    print(f"  Return: {m2['annual_return_pct']:.2f}%, PF: {m2['profit_factor']:.3f}, "
          f"MaxDD: {m2['max_drawdown_pct']:.2f}%, Trades: {m2['trades']}, WinRate: {m2['win_rate']:.1f}%")

    print("\nRunning full MCPT (200 permutations) on 2025-2026...")
    result = full_mcpt(test, enhanced_ict_v3_adjusted, {}, n_permutations=200)
    print(f"  P-Value: {result['p_value']:.4f}")
    print(f"  Status: {'PASS' if result['passed'] else 'FAIL'}")
