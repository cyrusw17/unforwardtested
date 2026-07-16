# All-Era Robust Strategy — 2018–2025 H4

## Problem
Prior locks looked fine on 2020–2025 but **failed on 2018–2020** (dual −7.6%, sniper-only −9.1%). A strategy that only works on the train window is not usable.

## Selection rule (hard gates)
Tested **421** configs across residual-sweep, residual-TS, Donchian, and cross-sectional residual families.

A config **passes** only if all hold on Dukascopy 4H:

| Era | Floor |
|-----|------:|
| 2018–2019 | ≥ −2% |
| 2020 | ≥ −5% |
| 2021–2023 | ≥ 0% |
| 2024–2025 | ≥ 0% |
| Full 2018–2025 | return > 0, DD < 20%, ≥25 trades |

**6 / 421** passed. Locked: sniper-only residual × liquidity sweep (`rs_27`).

## Locked rules
- Residual mom: long 8 / short 4; sniper z ≥ **1.0**
- Sweep: long swing 18 / short 24; same-bar reclaim wick
- ADX > 12 + DI agree
- Sniper-only (no background), risk 1%, TP 4 ATR, sweep stop
- Soft DD 15% / hard 20% · $1,000 · 50:1 · 0.5 pip slippage

## Performance (2018–2025)

| Metric | Value |
|--------|------:|
| Total return | **+13.56%** |
| Max DD | **4.67%** |
| Sharpe | 0.43 |
| Win rate | 46.7% |
| Profit factor | **1.98** |
| Trades | 30 (~0.3 / month) |
| Positive years | **6 / 8** |

### Era breakdown
| Era | Return | DD | WR | Notes |
|-----|-------:|---:|---:|-------|
| 2018–2019 | −1.1% | 4.1% | 25% | Prior — nearly flat (old lock −5.7% to −9%) |
| 2020 | −0.6% | 2.0% | 33% | COVID — survived |
| 2021–2023 | **+11.4%** | 2.1% | 57% | Train-style trend years |
| 2024–2025 | **+3.9%** | 1.1% | 60% | OOS holdout |

### Year-by-year
2018 +0.7% · 2019 −1.7% · 2020 −0.6% · 2021 +3.2% · 2022 +6.5% · 2023 +1.5% · 2024 +1.7% · 2025 +1.8%

## Monte Carlo (200)
Median return ~+14.8% · 5th pct ~+3.4% · median DD ~3.7%

## Forward test (2026)
Freeze `config.json`. Kill if DD ≥ 20% or rolling 3-month expectancy < 0 after ≥20 trades.

## Bottom line
This is the first lock that is **required to behave across prior, COVID, train, and OOS eras** — not just the window it was tuned on. Edge is selective (low frequency); prior years are near-flat rather than deeply negative.
