# Forex Trading Strategy - 2020-2025 Backtest

## Executive Summary

This package recreates a dual EMA forex strategy (Sniper + Background) using **only 2020-01-01 to 2025-12-31** data for EURUSD, GBPUSD, USDJPY, and AUDUSD. No 2026 bars were used at any stage.

On the full sample with OANDA-like costs, 50:1 leverage, and a 20% drawdown halt, the locked configuration returned **+42.9%** (~6.1% annualized), with **max drawdown 15.1%**, profit factor **1.24**, and **positive returns in all 6 years**. Out-of-sample 2024–2025 (after 2020–2023 train window) remained profitable (+9.7%).

Ambition targets from the brief (Sharpe > 1.5, win rate > 55%) were **not achieved** under realistic daily FX costs. Those targets conflict with a high-R:R sniper design and appear inconsistent with honest 2020–2025 daily backtests. The locked system prioritizes robustness (6/6 green years, DD < 20%, positive OOS) over curve-fit headline metrics.

## Strategy Specification

See [`final_strategy/STRATEGY_SPECIFICATION.md`](final_strategy/STRATEGY_SPECIFICATION.md) and [`final_strategy/config.json`](final_strategy/config.json).

Summary:
- Sniper: EMA 5/13, ADX>12, 1/5 ATR, 2% risk, ≤3 trades/pair/month
- Background: EMA 8/21, ADX>18, 2/3 ATR, 1% risk
- Dynamic SL/TP via ATR z-score regime
- Allocation 60/40, leverage ≤50:1

## Performance Summary (2020-2025)

| Metric | Value |
|--------|------:|
| Total return | **42.87%** |
| Annualized return | 6.13% |
| Sharpe (daily, rf=0) | 0.40 |
| Max drawdown | **15.08%** |
| Win rate | 28.29% |
| Profit factor | 1.244 |
| Total trades | 258 |
| Trades / month | 3.58 |
| Final equity ($10k start) | $14,286.81 |

## Year-by-Year Breakdown

| Year | Return | Trades | Win rate |
|-----:|-------:|-------:|---------:|
| 2020 | +3.31% | 40 | 25.0% |
| 2021 | +6.10% | 39 | 23.1% |
| 2022 | +0.58% | 49 | 30.6% |
| 2023 | +19.35% | 37 | 29.7% |
| 2024 | +0.47% | 49 | 32.7% |
| 2025 | +8.07% | 44 | 27.3% |

**Positive years: 6 / 6**

## Robustness Validation

### Walk-forward (locked params, 12 windows)
- Positive test windows: 6/12
- Median test return: ~0.3%
- Median test max DD: ~3.3%

### Out-of-sample
- Train 2020–2023: +35.76% | Sharpe 0.50 | DD 13.8%
- Test 2024–2025: **+9.65%** | Sharpe 0.32 | DD 14.3%

### Monte Carlo (200 bootstrap runs)
- Median return ≈ +41%
- 5th percentile return ≈ −16%
- Median max DD ≈ 20%
- Win-rate −10% stress: median DD ≈ 27% (elevated; expect degradation if edge weakens)

### Cost sensitivity
Strategy remains profitable at 1×–3× spread/slippage assumptions (path-dependent fills can change outcomes; treat as stability check, not free lunch).

### Pair correlation
EUR/GBP/AUD returns correlated; USDJPY diversifies (negative correlation in-sample). Basket still warranted.

## Comparison vs Reference Strategy (2023–2026 claim)

| Item | Reference claim | This recreation (2020–2025) |
|------|-----------------|-----------------------------|
| Data | 2023–2026 (includes future) | 2020–2025 only |
| Dual EMA + ADX + ATR | Yes | Yes (re-tuned) |
| 90d / multi-year returns | ~1,070% / ~1,800% | **+43% over 6y** |
| Win rate | ~70% | ~28% (expected for ~5R sniper) |
| Max DD | ~12% | ~15% |
| Realistic costs | Unclear | Explicit spreads + slippage |

Interpretation: reference headline performance is not reproducible on clean 2020–2025 daily data with costs. This package keeps the **economic structure** that generalized (dual sleeves, ADX filter, ATR targets, vol regime) and rejects unattainable metrics.

## Forward Testing Plan (2026 — separate)

1. Freeze `final_strategy/config.json` (no re-optimization on 2026).
2. Stream daily bars; generate signals on close; place orders for next open via OANDA.
3. Track identical metrics: equity, DD, WR, PF, trades/month, year-to-date.
4. Kill-switch if live DD ≥ 20% or 3-month rolling expectancy turns negative after ≥40 trades.
5. Do **not** retune EMA/ADX/ATR on 2026 until a pre-registered review date.

## Risk Disclosures
- Past backtests ≠ future performance.
- Daily FX edges are thin after costs; sequence risk remains (MC left tail).
- AUDUSD sleeve was weakest historically.
- Yahoo FX prints are research-grade, not broker fills.
- High-R:R systems endure long losing streaks despite positive expectancy.
- 50:1 leverage amplifies operational/gap risk beyond modeled stops.

## Implementation Notes
- Code entrypoint: `final_strategy/strategy_implementation.py`
- Full backtest: `final_strategy/backtest_full_period.py`
- Charts: `final_strategy/performance_charts.py`
- Validation suite: `validation/run_validation.py`
- End-to-end: `run_pipeline.py`
- Ready for API wiring: signals are unambiguous {-1,0,+1} per sleeve with ATR stops/targets.

## Success Criteria Scorecard

| Criterion | Result |
|-----------|--------|
| Only 2020–2025 data | PASS |
| All 4 majors | PASS |
| Realistic costs | PASS |
| Max DD < 20% | PASS (15.1%) |
| ≥4/6 positive years | PASS (6/6) |
| Positive OOS 2024–2025 | PASS |
| Walk-forward + Monte Carlo | PASS (completed) |
| Sharpe > 1.5 | FAIL (0.40) |
| Win rate > 55% | FAIL (28.3%; incompatible with 5R sniper) |
| 5–20 trades/month | PARTIAL (3.6/month) |
| Ready for 2026 forward test | PASS |
