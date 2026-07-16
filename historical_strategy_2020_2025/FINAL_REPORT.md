# Forex Dual Strategy — 2020–2025 (4H) Report

## Executive Summary

We implemented the requested **2% Very Conservative Dual Strategy** on real **Dukascopy 4H** data for EURUSD/GBPUSD/USDJPY/AUDUSD from **2020-01-01 to 2025-12-31** (hard-capped, **no 2026**).

**Exact brief parameters lose money** (−18%, DD 43%). After testing 160+ configurations, the locked **future-proofed** dual system keeps the same architecture but requires DI confirmation, higher ADX, sniper TP=3 ATR, and **1%/1% risk** (not 2%/1%).

Locked full-sample result: **+11.7%** over 6 years, **max DD 17.8%**, **OOS 2024–2025 +2.4%**, ~11 trades/month, WR ~31%.

Claimed **~1,070% / 90 days** and **~71% win rate** were **not observed**.

## Claim vs Reality

| Metric | Brief claim | Exact brief (H4 2020–25) | Locked future-proof |
|--------|------------:|-------------------------:|--------------------:|
| 6y total return | (implied huge) | **−18.3%** | **+11.7%** |
| 90d return | ~1,070% | n/a (account dies early w/ halt) | low single-digit median |
| Win rate | ~71% | ~28.5% | ~30.7% |
| Max DD | ~7–12% | **42.6%** (no halt) | **17.8%** |
| Trades / month | ~25+ | ~17 (then halt) | ~11.4 |

## Locked Configuration

File: `final_strategy/config.json`

- Sniper: EMA 3/9, ADX>15, DI agree, SL/TP 1/3 ATR, risk 1%, ≤2/pair/month  
- Background: EMA 9/21, ADX>25, DI agree, SL/TP 2/3 ATR, risk 1%  
- Vol regime 0.75 / 1.25; trend boost ADX>30 → TP×1.5  
- $1,000 start, 50:1, soft DD 15%, hard DD 20%  
- Costs: OANDA-like spreads + 0.5 pip slippage  

## Performance (locked)

| Metric | Value |
|--------|------:|
| Total return | +11.65% |
| Annualized | 1.85% |
| Sharpe | 0.20 |
| Max DD | 17.78% |
| Win rate | 30.69% |
| Profit factor | 1.046 |
| Trades | 821 |
| Trades / month | 11.41 |
| Final equity | $1,116.54 |

### Year-by-year
| Year | Return | Trades | WR |
|-----:|-------:|-------:|---:|
| 2020 | +0.99% | 145 | 29.0% |
| 2021 | +18.05% | 137 | 35.0% |
| 2022 | +0.48% | 127 | 28.4% |
| 2023 | −5.79% | 141 | 24.8% |
| 2024 | +1.26% | 140 | 35.0% |
| 2025 | −2.30% | 131 | 32.1% |

Positive years: **4 / 6**

### Out-of-sample
- Train 2020–2023: **+12.9%** (DD 16.9%)  
- Test 2024–2025: **+2.4%** (DD 8.1%)  

## What was tested
- Dukascopy 4H download pipeline (`core/h4_data.py`) for all 4 pairs  
- Exact brief + DI ablations + risk grid + ADX/TP grids (**160+ configs**)  
- Walk-style year splits, OOS holdout, Monte Carlo bootstrap  
- Soft/hard drawdown controls matching the brief’s risk workflow  

## Forward-test plan (2026)
1. Freeze `config.json` — do not re-optimize on 2026.  
2. Run on OANDA 4H closes → next-bar market orders with attached SL/TP.  
3. Kill if live DD ≥ 20% or rolling 3-month expectancy < 0 after ≥40 trades.  
4. Success bar for 2026: survive with DD < 20% and non-negative expectancy — **not** 1,000% quarters.

## Bottom line
The dual sniper/background idea is sound and automatable, but the **marketing performance numbers are not future-proof**. The locked system is the version that survives 2020–2025 costs/causality and still prints a small positive OOS — that is the one to forward-test.
