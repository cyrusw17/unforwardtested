"""
Trade-Level Feature Analysis: Winners vs Losers (2020-2024)
==============================================================
Extracts every discrete trade the winning strategy (enhanced_ict_v2_winner)
takes on AUD/USD daily bars during 2020-2024, tags each with contextual
features (signal component breakdown, day-of-week, month, volatility
regime, trend alignment, direction, duration, etc.), and statistically
compares winners vs losers to find genuine differentiators.

IMPORTANT: 2020-2024 is used here as the "training"/analysis window (as
instructed) -- any filter we design will then be validated OUT OF SAMPLE
on the untouched 2025-2026 window via full MCPT, to avoid fooling ourselves
with patterns that only "worked" in hindsight on the analysis window.
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))

import pandas as pd
import numpy as np
import json
from scipy import stats

from mcpt_strategy.strategies.mega_search_framework import fetch_daily_data
from mcpt_strategy.strategies.enhanced_ict_v2_winner import ICTIndicators


def compute_all_components(ohlc: pd.DataFrame,
                            ob_lookback: int = 5,
                            structure_length: int = 3,
                            trend_fast: int = 10,
                            trend_slow: int = 30) -> pd.DataFrame:
    """Compute every raw component of the scoring engine, unshifted, for feature analysis."""
    ict = ICTIndicators()

    bullish_ob, bearish_ob = ict.order_blocks_with_strength(ohlc, ob_lookback)
    bullish_fvg, bearish_fvg = ict.fvg_with_size(ohlc)
    bullish_sweep, bearish_sweep = ict.liquidity_sweep_strength(ohlc)
    structure = ict.market_structure_score(ohlc, structure_length)
    trend = ict.trend_strength(ohlc, trend_fast, trend_slow)

    # ATR percentile (volatility regime)
    high, low, close = ohlc['High'], ohlc['Low'], ohlc['Close']
    tr = pd.concat([high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14).mean()
    atr_pct_rank = atr.rolling(100, min_periods=20).apply(lambda x: pd.Series(x).rank(pct=True).iloc[-1])

    # RSI
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = (100 - (100 / (1 + rs))).fillna(50)

    ob_weight, fvg_weight, sweep_weight, structure_weight, trend_weight = 2.0, 1.5, 1.5, 1.0, 1.0

    bullish_score = (bullish_ob * ob_weight + bullish_fvg * fvg_weight + bullish_sweep * sweep_weight +
                      structure.clip(lower=0) * structure_weight + trend.clip(lower=0) * trend_weight)
    bearish_score = (bearish_ob * ob_weight + bearish_fvg * fvg_weight + bearish_sweep * sweep_weight +
                      abs(structure.clip(upper=0)) * structure_weight + abs(trend.clip(upper=0)) * trend_weight)

    df = pd.DataFrame({
        'close': close, 'day_of_week': ohlc.index.dayofweek, 'month': ohlc.index.month,
        'bullish_ob': bullish_ob, 'bearish_ob': bearish_ob,
        'bullish_fvg': bullish_fvg, 'bearish_fvg': bearish_fvg,
        'bullish_sweep': bullish_sweep, 'bearish_sweep': bearish_sweep,
        'structure': structure, 'trend': trend,
        'bullish_score': bullish_score, 'bearish_score': bearish_score,
        'atr_pct_rank': atr_pct_rank, 'rsi': rsi,
    }, index=ohlc.index)

    return df


def extract_trades(ohlc: pd.DataFrame, components: pd.DataFrame,
                    entry_threshold: float = 1.5, max_score_cap: float = 4.0,
                    max_position: float = 2.5) -> list:
    """
    Reconstruct discrete trades from the daily signal (same logic as
    enhanced_ict_v2_winner), tagging each trade with entry-bar context.
    """
    bullish_score = components['bullish_score']
    bearish_score = components['bearish_score']

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

    # Applied signal (what position we HOLD on day i, decided using day i-1's score)
    applied_signal = raw_signal.shift(1).fillna(0)
    close = ohlc['Close']

    trades = []
    current_dir = 0
    entry_idx = None

    dates = ohlc.index

    for i in range(1, len(ohlc)):
        sig = applied_signal.iloc[i]
        new_dir = np.sign(sig)

        if current_dir == 0 and new_dir != 0:
            entry_idx = i
            current_dir = new_dir
        elif current_dir != 0 and new_dir != current_dir:
            # closing (or flipping) -- book a trade from entry_idx to i
            entry_date = dates[entry_idx]
            exit_date = dates[i]
            entry_price = close.iloc[entry_idx]
            exit_price = close.iloc[i]

            ret = (exit_price / entry_price - 1) if current_dir == 1 else (entry_price / exit_price - 1)

            # entry-bar context comes from the CLOSED bar that generated the
            # decision: that's dates[entry_idx - 1] (score computed there)
            ctx_idx = entry_idx - 1
            ctx = components.iloc[ctx_idx]

            dominant = max(
                [('ob', ctx['bullish_ob'] if current_dir == 1 else ctx['bearish_ob']),
                 ('fvg', ctx['bullish_fvg'] if current_dir == 1 else ctx['bearish_fvg']),
                 ('sweep', ctx['bullish_sweep'] if current_dir == 1 else ctx['bearish_sweep']),
                 ('structure', abs(ctx['structure'])),
                 ('trend', abs(ctx['trend']))],
                key=lambda x: x[1] * {'ob': 2.0, 'fvg': 1.5, 'sweep': 1.5, 'structure': 1.0, 'trend': 1.0}[x[0]]
            )[0]

            trades.append({
                'direction': 'long' if current_dir == 1 else 'short',
                'entry_date': entry_date,
                'exit_date': exit_date,
                'entry_price': float(entry_price),
                'exit_price': float(exit_price),
                'duration_days': (exit_date - entry_date).days,
                'return_pct': float(ret * 100),
                'win': ret > 0,
                'signal_strength': float(abs(sig)) if entry_idx == i - 1 else None,
                'day_of_week_entry': int(ctx['day_of_week']),
                'month_entry': int(ctx['month']),
                'atr_pct_rank_entry': float(ctx['atr_pct_rank']) if not pd.isna(ctx['atr_pct_rank']) else None,
                'rsi_entry': float(ctx['rsi']),
                'trend_entry': float(ctx['trend']),
                'structure_entry': float(ctx['structure']),
                'dominant_component': dominant,
                'score_entry': float(ctx['bullish_score'] if current_dir == 1 else ctx['bearish_score']),
                'trend_aligned': bool(np.sign(ctx['trend']) == current_dir) if ctx['trend'] != 0 else None,
            })

            if new_dir != 0:
                entry_idx = i
                current_dir = new_dir
            else:
                current_dir = 0
                entry_idx = None

    return trades


def main():
    print("=" * 80)
    print("TRADE-LEVEL FEATURE ANALYSIS: 2020-2024")
    print("=" * 80)

    df = fetch_daily_data('AUDUSD=X', '2018-01-01', '2026-12-31')
    period = df[(df.index.year >= 2020) & (df.index.year <= 2024)]
    # Include lookback context before 2020 for indicator warmup
    lookback_start = df.index[df.index.get_indexer([period.index[0]], method='nearest')[0] - 30]
    analysis_df = df.loc[lookback_start:period.index[-1]]

    print(f"Analysis period: {period.index[0].date()} to {period.index[-1].date()} ({len(period)} bars)")

    components = compute_all_components(analysis_df)
    trades = extract_trades(analysis_df, components)

    # Keep only trades whose entry_date falls within 2020-2024 (trim warmup)
    trades = [t for t in trades if t['entry_date'] >= period.index[0]]

    print(f"\nExtracted {len(trades)} discrete trades")

    wins = [t for t in trades if t['win']]
    losses = [t for t in trades if not t['win']]
    print(f"Wins: {len(wins)} ({len(wins)/len(trades)*100:.1f}%)  Losses: {len(losses)} ({len(losses)/len(trades)*100:.1f}%)")

    total_win_pnl = sum(t['return_pct'] for t in wins)
    total_loss_pnl = sum(t['return_pct'] for t in losses)
    print(f"Avg win: {total_win_pnl/len(wins):+.3f}%  Avg loss: {total_loss_pnl/len(losses):+.3f}%")
    print(f"Profit factor: {total_win_pnl / abs(total_loss_pnl):.3f}")

    # === Statistical comparison ===
    print(f"\n{'='*80}")
    print("FEATURE COMPARISON: WINNERS vs LOSERS")
    print("=" * 80)

    numeric_features = ['duration_days', 'atr_pct_rank_entry', 'rsi_entry', 'score_entry',
                         'trend_entry', 'structure_entry']

    comparison = {}
    for feat in numeric_features:
        win_vals = [t[feat] for t in wins if t[feat] is not None]
        loss_vals = [t[feat] for t in losses if t[feat] is not None]
        if len(win_vals) < 3 or len(loss_vals) < 3:
            continue
        t_stat, p_val = stats.ttest_ind(win_vals, loss_vals, equal_var=False)
        win_mean, loss_mean = np.mean(win_vals), np.mean(loss_vals)
        comparison[feat] = {
            'win_mean': float(win_mean), 'loss_mean': float(loss_mean),
            'diff': float(win_mean - loss_mean), 't_stat': float(t_stat), 'p_value': float(p_val)
        }
        sig = '***' if p_val < 0.01 else ('**' if p_val < 0.05 else ('*' if p_val < 0.10 else ''))
        print(f"\n{feat}: win_mean={win_mean:.3f}, loss_mean={loss_mean:.3f}, diff={win_mean-loss_mean:+.3f}, "
              f"p={p_val:.4f} {sig}")

    # Categorical features
    print(f"\n--- Direction ---")
    for d in ['long', 'short']:
        subset = [t for t in trades if t['direction'] == d]
        win_rate = sum(1 for t in subset if t['win']) / len(subset) * 100 if subset else 0
        avg_ret = np.mean([t['return_pct'] for t in subset]) if subset else 0
        print(f"  {d}: n={len(subset)}, win_rate={win_rate:.1f}%, avg_return={avg_ret:+.3f}%")

    print(f"\n--- Dominant Component ---")
    for comp in ['ob', 'fvg', 'sweep', 'structure', 'trend']:
        subset = [t for t in trades if t['dominant_component'] == comp]
        if not subset:
            continue
        win_rate = sum(1 for t in subset if t['win']) / len(subset) * 100
        avg_ret = np.mean([t['return_pct'] for t in subset])
        print(f"  {comp}: n={len(subset)}, win_rate={win_rate:.1f}%, avg_return={avg_ret:+.3f}%")

    print(f"\n--- Trend Alignment ---")
    for aligned in [True, False]:
        subset = [t for t in trades if t['trend_aligned'] == aligned]
        if not subset:
            continue
        win_rate = sum(1 for t in subset if t['win']) / len(subset) * 100
        avg_ret = np.mean([t['return_pct'] for t in subset])
        print(f"  trend_aligned={aligned}: n={len(subset)}, win_rate={win_rate:.1f}%, avg_return={avg_ret:+.3f}%")

    print(f"\n--- Day of Week (0=Mon..4=Fri) ---")
    for dow in range(5):
        subset = [t for t in trades if t['day_of_week_entry'] == dow]
        if not subset:
            continue
        win_rate = sum(1 for t in subset if t['win']) / len(subset) * 100
        avg_ret = np.mean([t['return_pct'] for t in subset])
        print(f"  day={dow}: n={len(subset)}, win_rate={win_rate:.1f}%, avg_return={avg_ret:+.3f}%")

    print(f"\n--- Volatility Regime (ATR percentile rank, quartiles) ---")
    vol_vals = [t['atr_pct_rank_entry'] for t in trades if t['atr_pct_rank_entry'] is not None]
    if vol_vals:
        quartiles = np.percentile(vol_vals, [25, 50, 75])
        for lo, hi, label in [(-1, quartiles[0], 'Q1 (low vol)'), (quartiles[0], quartiles[1], 'Q2'),
                                (quartiles[1], quartiles[2], 'Q3'), (quartiles[2], 2, 'Q4 (high vol)')]:
            subset = [t for t in trades if t['atr_pct_rank_entry'] is not None and lo < t['atr_pct_rank_entry'] <= hi]
            if not subset:
                continue
            win_rate = sum(1 for t in subset if t['win']) / len(subset) * 100
            avg_ret = np.mean([t['return_pct'] for t in subset])
            print(f"  {label}: n={len(subset)}, win_rate={win_rate:.1f}%, avg_return={avg_ret:+.3f}%")

    print(f"\n--- Score Strength (quartiles) ---")
    score_vals = [t['score_entry'] for t in trades]
    quartiles = np.percentile(score_vals, [25, 50, 75])
    for lo, hi, label in [(-1, quartiles[0], 'Q1 (weak)'), (quartiles[0], quartiles[1], 'Q2'),
                            (quartiles[1], quartiles[2], 'Q3'), (quartiles[2], 100, 'Q4 (strong)')]:
        subset = [t for t in trades if lo < t['score_entry'] <= hi]
        if not subset:
            continue
        win_rate = sum(1 for t in subset if t['win']) / len(subset) * 100
        avg_ret = np.mean([t['return_pct'] for t in subset])
        print(f"  {label} (score {lo:.2f}-{hi:.2f}): n={len(subset)}, win_rate={win_rate:.1f}%, avg_return={avg_ret:+.3f}%")

    # Save
    results_dir = Path(__file__).parent.parent / 'results'
    results_dir.mkdir(parents=True, exist_ok=True)
    with open(results_dir / 'trade_feature_analysis_2020_2024.json', 'w') as f:
        json.dump({'trades': trades, 'comparison': comparison}, f, indent=2, default=str)

    print(f"\nSaved {len(trades)} trades to results/trade_feature_analysis_2020_2024.json")


if __name__ == '__main__':
    main()
