# Critical Finding: Lookahead Bias in the Order Block Indicator

## The question that triggered this

"and this strategy doesn't look ahead at all?"

This deserved a rigorous, empirical answer rather than a reflexive "no" —
so it was tested directly: **compute the signal on a dataset, then
compute it again on a truncated version of the same dataset (removing
the most recent bars), and check whether earlier signal values change.**
If a bar's value depends on whether *future* bars are present in the
input, that bar is looking ahead. This test was run against all five ICT
indicators feeding the strategy.

## Result: one indicator fails this test

| Indicator | Lookahead? |
|---|---|
| Fair Value Gap (`fvg_with_size`) | causal — no lookahead |
| Liquidity Sweep (`liquidity_sweep_strength`) | causal — no lookahead |
| Market Structure (`market_structure_score`) | causal — no lookahead |
| EMA Trend (`trend_strength`) | causal — no lookahead |
| **Order Block (`order_blocks_with_strength`)** | **LOOKAHEAD BIAS — confirmed** |

## The bug

```python
for i in range(lookback, len(ohlc)):
    if strong_bullish.iloc[i]:
        for j in range(1, min(lookback, i)):
            if close.iloc[i - j] < open_price.iloc[i - j]:
                bullish_ob.iloc[i - j] = strength.iloc[i]   # <-- BUG
                break
```

When a strong "displacement" candle appears at bar `i`, the code walks
*backward* up to `lookback` bars and assigns that candle's strength onto
the most recent opposite-colored candle at `i - j`. This is the standard
ICT "order block" idea (a strong move away from a level retroactively
confirms that level was an order block) — but implemented this way, it
backdates information onto a historical bar before that information
could possibly have existed. At the moment bar `i - j` closes, nobody
knows a strong displacement candle will appear up to `lookback - 1` bars
later. Every single nonzero value this function ever produces is
assigned this way — it is not a rare edge case, it is the function's only
mode of operation.

**Empirical confirmation:** on the 2025-2026 AUD/USD test set, adding or
removing bars at the end of the series changed already-reported historical
`bullish_ob`/`bearish_ob` values by up to 3.0 (out of a typical 0-3 range) —
i.e. the "same" historical bar gets a completely different score depending
on what data window you happen to be running on. That is lookahead by
definition.

## How much did it matter? A LOT.

The fix: attribute the strength to the *confirming* bar (`i`) itself,
which uses only information available at the time, instead of backdating
it to `i - j`. Verified empirically to eliminate the truncation-sensitivity
entirely (0.000000000 diff across 10 different truncation points).

Re-running every strategy built in this project so far with the fix
(all other code, weights, and thresholds held identical):

| Strategy | Metric (2025-2026 out-of-sample) | With bug (as reported) | With fix (causal) |
|---|---|---|---|
| Original "Enhanced ICT Scoring" baseline | Return | 9.97%* | **-2.75%** |
| | MCPT p-value | 0.01 (PASS) | **0.795 (FAIL)** |
| Enhanced ICT v2 winner | Return | 18.25% | **2.90%** |
| | Max Drawdown | -3.77% | **-7.80%** |
| | Profit Factor | 2.114 | **1.126** |
| | MCPT p-value | 0.004 (PASS) | *(not re-run — see v3 below, same magnitude of collapse)* |
| Enhanced ICT v3 (round 2, deployed live) | Return | 19.47% | **0.17%** |
| | Max Drawdown | -3.74% | **-13.21%** |
| | MCPT p-value | 0.006 (PASS) | **0.500 (FAIL — statistically indistinguishable from random)** |

*(the original baseline's 9.97%/p=0.01 figures were themselves already
computed with the buggy indicator from the very start of this project)*

**Every "successful," MCPT-passing result in this entire project traced
back to this one function.** Once it's fixed, none of the tested
configurations retain a statistically significant edge — they all fail
MCPT (p ≈ 0.5-0.8, consistent with random chance).

## Why does removing 3-4 bars of future info matter so much?

This strategy's edge was concentrated in a fairly small number of
high-conviction Order-Block-driven signals (`ob_weight` was the single
largest weight in every winning configuration — 2.0 in v2, boosted to
4.0 in v3 specifically *because* Order Blocks looked like the best
performer in the trade analysis). An indicator that gets to "see" whether
a large displacement candle is about to occur 1-4 bars in the future is
functionally previewing near-term momentum before it happens — exactly
the kind of information a real edge would need, and exactly what MCPT is
designed to catch if you test it correctly. It didn't catch it here
because the SAME (buggy) indicator was used to build both the real
returns and the permuted returns — the permutation test correctly showed
the real data's *pattern-matching-with-a-peek* beat randomly shuffled
data, but that's not the same as beating randomly shuffled data with a
legitimate, real-time-executable signal.

## Status

- The indicator bug is fixed in both copies of the code
  (`enhanced_ict_v2_winner.py::ICTIndicators` and
  `mega_search_framework.py::ICTIndicatorLib`), with `causal=True` as the
  new default. `causal=False` is kept only to reproduce the historical
  (buggy) numbers for comparison, as done in this document.
- The live paper trading dashboard's **signal generation itself was
  already free of true lookahead** in the sense that matters live (it
  only ever computes on real, already-closed price data) — but the
  *statistical validation* that justified deploying it is now known to
  be invalid, so **trading has been paused** (`TRADING_PAUSED = True` in
  `paper_trading/run_cycle.py` / `init_state.py`) until a genuinely
  validated replacement is found. The dashboard now shows a warning
  banner explaining this.
- See `mcpt_strategy/CAUSAL_SEARCH_RESULTS.md` for the attempt to find a
  genuinely valid (non-lookahead) replacement strategy.
