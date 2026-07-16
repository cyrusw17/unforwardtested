# Robustness Report — Residual Momentum × Liquidity Sweep (2020–2025 H4)

## Configuration
- Residual mom long/short: 8 / 4 bars; z sniper/bg: 1.25 / 0.75
- Sweep swing long/short: 18 / 24; bg persist 2
- Sweep stops on; sniper TP 4.0 ATR; bg TP 2.5 ATR
- Risk 1.5% / 1.0%; soft DD 15%; hard halt 20%
- Data: Dukascopy 4H 2020-01-01 → 2025-12-31

## Full-Period
| Metric | Value |
|--------|------:|
| Total return | 13.54% |
| Sharpe | 0.44 |
| Max DD | 4.76% |
| Win rate | 36.84% |
| Profit factor | 1.543 |
| Trades / month | 1.32 |

Positive years: **5 / 6**

## OOS
- Train 2020–2023: +8.91%
- OOS 2024–2025: +4.25% | DD 2.47% | Sharpe 0.63

## Monte Carlo (200)
- Median return ~14.5%
- 5th pct ~−0.5%
- Median DD ~4.4%

## Checklist
- ≥4/6 positive years: **PASS** (5/6)
- Max DD < 20%: **PASS** (4.76%)
- OOS profitable: **PASS**
- No 2026 data: **PASS**
- Sharpe > 1.5: **FAIL** (0.44)
- WR > 55%: **FAIL** (36.8%) — acceptable for >1R targets with costs
