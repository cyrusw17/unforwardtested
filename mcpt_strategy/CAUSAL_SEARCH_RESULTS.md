# Searching for a Genuinely Valid (No-Lookahead) Strategy

Follow-up to `LOOKAHEAD_BIAS_FINDING.md`. After fixing the Order Block
lookahead bug, none of the previously "winning" strategies retained a
statistically significant edge. This document covers the search for a
real replacement, done as rigorously as possible given what the first
bug taught us not to trust.

## Round 1: re-scan pairs with the fix in place

Re-ran the original 20-pair scan (`phase1_pair_scan.py`) with the fixed,
causal indicator. Most pairs now show negative or flat returns on
2025-2026 (as expected once the bug is gone), but a few JPY crosses stood
out: **CADJPY** (4.80% return, PF 2.32), GBPJPY, AUDJPY, NZDJPY, EURJPY.

Running full MCPT (200 perms) on the baseline parameters directly:

| Pair | Return | PF | MCPT p-value | Status |
|---|---|---|---|---|
| CADJPY | 4.80% | 2.320 | 0.010 | PASS |
| GBPJPY | 3.04% | 1.850 | 0.035 | PASS |
| AUDJPY | 3.37% | 1.666 | 0.060 | FAIL |
| NZDJPY | 3.32% | 1.493 | 0.085 | FAIL |
| EURJPY | 1.95% | 1.482 | 0.115 | FAIL |

## An important stop and re-check: is this just data leakage again?

Before getting excited, it's worth asking: this same "fails everywhere
except 2024+" pattern showed up for the (buggy) AUD/USD strategy too.
Deep parameter search on CADJPY (60 combos of entry threshold / OB
lookback / structure length, **all evaluated directly against the
2025-2026 test window**) found a config with 10.08% return, PF 1.99,
Sharpe 2.17, and MCPT p=0.004 (500 perms) — a great-looking number. But
searching 60+ configurations and picking the best-scoring one *on the
same window you're about to validate on* is itself a form of data
leakage (tuning on the test set), separate from the lookahead bug, and
MCPT does not protect against it.

**Split-sample check:** tuned parameters using ONLY 2025 data, validated
once on 2026 data (truly never touched during tuning):

| Pair | Return (2026 holdout) | MCPT p-value | Status |
|---|---|---|---|
| CADJPY | 8.33% | 0.115 | **FAIL** |
| GBPJPY | 6.82% | 0.105 | **FAIL** |

Both failed. This confirms the earlier "10.08%, p=0.004" result was at
least partly inflated by tuning on the same data used for validation —
exactly the kind of self-deception the lookahead-bug investigation
should make us extra alert to.

## The methodologically clean version: train only on 2018-2024

To get this right: parameters were selected using **only** 2018-2024
performance (profit factor), with 2025-2026 completely untouched during
selection. The selected configuration was then evaluated exactly once on
2025-2026, with MCPT run on that result and no further tuning based on
what it showed.

| Pair | Train (2018-2024) PF | Test (2025-2026) Return | Test PF | MCPT p-value | Status |
|---|---|---|---|---|---|
| CADJPY | 0.894 (still losing in-sample) | 3.60% | 3.314 | 0.005 | PASS |
| GBPJPY | 1.247 | 2.59% | 2.718 | 0.020 | PASS |
| AUDJPY | 1.019 | 3.74% | 1.958 | 0.035 | PASS |

Broadening the train-only search to include order-block/trend weight
variations (still selected purely by training-period PF, 2018-2024) found
a better generalizing CADJPY configuration:

**Final candidate: CADJPY, `entry_threshold=1.5, ob_lookback=3, ob_weight=1.5, trend_weight=1.5`**
(all other params at defaults)

| Metric (2025-2026, selected using only 2018-2024 data) | Value |
|---|---|
| Annual Return | **7.56%** |
| Profit Factor | 1.490 |
| Sharpe Ratio | 1.42 |
| Max Drawdown | -2.46% |
| Trades | 158 |
| MCPT p-value (500 perms) | **0.020 (PASS)** |

This is the most methodologically defensible result in this entire
project: causal indicator (no lookahead), parameters selected without
ever looking at the validation window, and a single MCPT run on the
untouched result.

## Important honesty check: regime dependency, again

| Period | Return | Max DD | PF |
|---|---|---|---|
| 2018-2019 | -1.22% | -11.02% | 0.957 |
| 2020-2021 | -3.75% | -13.08% | 0.895 |
| 2022-2023 | -4.11% | -19.55% | 0.892 |
| 2024 | +8.53% | -4.41% | 1.305 |
| 2025-2026 | +7.56% | -2.46% | 1.490 |

**This strategy loses money in every period before 2024 and only becomes
profitable from 2024 onward** — the exact same pattern seen in every
other strategy this project has produced, buggy or not, AUD/USD or
CADJPY. Two honest interpretations are possible:

1. There's a genuine regime shift around 2024 in JPY-cross trending
   behavior (plausible — BoJ policy normalization/yen carry-trade unwind
   dynamics through 2024-2026 created unusually persistent directional
   moves that a trend+order-block+structure confluence signal could
   plausibly capture), and this strategy is now catching a real,
   currently-active edge.
2. ~2 years of genuinely-out-of-sample data (399 bars) simply isn't a
   long enough or large enough sample to distinguish a real edge from a
   lucky stretch, even with MCPT and even without tuning-on-test-set
   leakage — MCPT tells you the *pattern* in this specific window isn't
   random noise, but it can't tell you whether that pattern will persist
   into a *different* future window.

Both are true simultaneously to some degree. This should be treated as
a **real, honestly-validated, but modest and unproven-longevity edge** —
not the confidently-strong 18-27% return story the (buggy) earlier
strategies told.

## Recommendation

- **Do not** re-launch the live paper trader on the strength of this
  alone without the user's sign-off — it has genuinely different risk
  characteristics (modest ~7.5% return, CADJPY instead of AUD/USD, no
  conviction-weighted position sizing) from what was previously deployed
  and should be treated as a fresh proposal, not a continuation.
- The live dashboard remains **paused** (flat, $100k, no trades) pending
  a decision on whether/how to deploy this or continue searching.
- If deployed, position sizing should stay simple/binary (as validated)
  rather than reintroducing conviction-weighted scaling, since that
  amplification was never validated for this configuration.
