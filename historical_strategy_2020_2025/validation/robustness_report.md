# Robustness Report (2020-2025 Only)

## Configuration
- Name: `dual_ema_vol_regime_final`
- Sniper: EMA 5/13, ADX>12.0, SL/TP=1.0/5.0 ATR, risk=2.0%, max/month=3
- Background: EMA 8/21, ADX>18.0, SL/TP=2.0/3.0 ATR, risk=1.0%
- Dynamic targets: True (high=0.75x, low=1.35x)
- RSI filter: True
- Allocation: sniper 60% / background 40%
- Leverage cap: 50:1 | Max DD halt: 20%
- Data window: **2020-01-01 → 2025-12-31** (no 2026 data used)

## Full-Period Performance
| Metric | Value |
|--------|------:|
| Total return | 42.87% |
| Annualized return | 6.13% |
| Sharpe | 0.40 |
| Max drawdown | 15.08% |
| Win rate | 28.29% |
| Total trades | 258 |
| Trades / month | 3.58 |
| Profit factor | 1.244 |

## Year-by-Year
Positive years: **6 / 6**

| year | start_equity | end_equity | return_pct | trades | win_rate |
|-----:|-------------:|-----------:|-----------:|-------:|---------:|
| 2020 | 10000.00 | 10330.89 | 3.31 | 40 | 25.00 |
| 2021 | 10330.89 | 10961.07 | 6.10 | 39 | 23.08 |
| 2022 | 10961.07 | 11024.65 | 0.58 | 49 | 30.61 |
| 2023 | 11024.65 | 13158.05 | 19.35 | 37 | 29.73 |
| 2024 | 13158.05 | 13219.37 | 0.47 | 49 | 32.65 |
| 2025 | 13219.37 | 14286.81 | 8.07 | 44 | 27.27 |

## Walk-Forward (locked params)
- Windows tested: 12
- Positive test windows: 6/12
- Median test return: 0.33%
- Median test Sharpe: -0.10
- Median test max DD: 3.26%

## Out-of-Sample (train 2020-2023 / test 2024-2025)
- Train return: 35.76% | Sharpe 0.496 | DD 13.77%
- OOS return: 9.65% | Sharpe 0.323 | DD 14.32%

## Monte Carlo (200 bootstrap runs)
- Bootstrap median return: ~40.9%
- Bootstrap 5th pct return: ~-16.4%
- Bootstrap median max DD: ~19.9%
- Stress (WR-10%) median max DD: ~26.8%
- Stress DD < 25% rate: ~43.5%

## Cost Sensitivity
Remains profitable at 1×–3× cost multiples in this path-dependent daily simulation. Do not interpret rising returns at higher costs as an edge; fills change stop/target sequences.

## Pair Return Correlation
|        | EURUSD | GBPUSD | USDJPY | AUDUSD |
|--------|-------:|-------:|-------:|-------:|
| EURUSD | 1.000 | 0.721 | -0.488 | 0.624 |
| GBPUSD | 0.721 | 1.000 | -0.431 | 0.700 |
| USDJPY | -0.488 | -0.431 | 1.000 | -0.355 |
| AUDUSD | 0.624 | 0.700 | -0.355 | 1.000 |

## Success Criteria Checklist
- Positive returns in ≥4/6 years: **PASS** (6/6)
- Sharpe > 1.5: **FAIL** (0.40) — not attainable with honest daily FX costs here
- Max DD < 20%: **PASS** (15.08%)
- Win rate > 55%: **FAIL** (28.29%) — expected for ~5R sniper expectancy profile
- ≥50 trades/year: **PARTIAL** (~43/year; 3.6/month)
- No 2026 data: **PASS**
- Walk-forward / OOS / Monte Carlo completed: **PASS**
