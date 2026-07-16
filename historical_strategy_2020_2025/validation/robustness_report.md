# Robustness Report (2020–2025 H4 Only)

## Configuration
- Name: `very_conservative_2pct_dual_futureproof`
- Sniper: EMA 3/9, ADX>15, DI agree, SL/TP=1.0/3.0 ATR, risk=1.0%, max/month=2
- Background: EMA 9/21, ADX>25, DI agree, SL/TP=2.0/3.0 ATR, risk=1.0%
- Dynamic targets: True (high z>1.5 → 0.75×, low z<−1.0 → 1.25×)
- Trend boost: ADX>30 → TP ×1.5
- Allocation: sniper 60% / background 40%
- Capital: $1,000 · Leverage cap 50:1 · Soft DD 15% · Hard halt 20%
- Data: Dukascopy freeserv **4H**, **2020-01-01 → 2025-12-31** (no 2026)

## Full-Period Performance
| Metric | Value |
|--------|------:|
| Total return | 11.65% |
| Annualized return | 1.85% |
| Sharpe | 0.20 |
| Max drawdown | 17.78% |
| Win rate | 30.69% |
| Total trades | 821 |
| Trades / month | 11.41 |
| Profit factor | 1.046 |
| Final equity | $1,116.54 |

## Year-by-Year
Positive years: **4 / 6**

| year | start_equity | end_equity | return_pct | trades | win_rate |
|-----:|-------------:|-----------:|-----------:|-------:|---------:|
| 2020 | 1000.00 | 1009.93 | 0.99 | 145 | 28.97 |
| 2021 | 1009.93 | 1192.20 | 18.05 | 137 | 35.04 |
| 2022 | 1192.20 | 1197.96 | 0.48 | 127 | 28.35 |
| 2023 | 1197.96 | 1128.64 | -5.79 | 141 | 24.82 |
| 2024 | 1128.64 | 1142.88 | 1.26 | 140 | 35.00 |
| 2025 | 1142.88 | 1116.54 | -2.30 | 131 | 32.06 |

## Out-of-Sample (train 2020–2023 / test 2024–2025)
- Train return: 12.86% | Sharpe 0.285 | DD 16.93%
- OOS return: 2.35% | Sharpe 0.132 | DD 8.14%

## Monte Carlo (200 bootstrap runs)
- Bootstrap median return: ~10.3%
- Bootstrap 5th pct return: ~−27.0%
- Bootstrap median max DD: ~20.5%

## Claim vs Reality
| Item | Value |
|------|------:|
| Exact brief (no DI, ADX 10/20, TP5, risk 2/1) | −18.26%, DD 42.57% |
| Claimed 90-day return | ~1,070% |
| Claimed win rate | ~71% |
| Locked observed WR | ~30.7% |

## Success Criteria Checklist
- Positive returns in ≥4/6 years: **PASS** (4/6)
- Sharpe > 1.5: **FAIL** (0.20)
- Max DD < 20%: **PASS** (17.78% with hard halt)
- Win rate > 55%: **FAIL** (30.69%) — expected for ATR R:R profile with costs
- ≥50 trades/year: **PASS** (~137/year; 11.4/month)
- No 2026 data: **PASS**
- Causal DI (filter before shift): **PASS**
- OOS / Monte Carlo completed: **PASS**
