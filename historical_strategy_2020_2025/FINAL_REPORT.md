# Forex Dual Strategy — Residual Momentum × Liquidity Sweep (2020–2025 H4)

## Executive Summary

Replaced the EMA-cross entry with **residual momentum + liquidity-sweep confluence**, still on Dukascopy **4H** for EURUSD/GBPUSD/USDJPY/AUDUSD (**2020–2025 only**, no 2026).

Locked result: **+13.5%** over 6 years, max DD **4.8%**, Sharpe **0.44**, OOS 2024–2025 **+4.3%**, profit factor **1.54**, **5/6** positive years.

vs prior EMA lock: higher return, **~4× lower drawdown**, better OOS and Sharpe.

## Entry model

**Long:** bullish liquidity sweep (pierce prior swing low → reclaim) **and** residual-z ≥ threshold (pair strength after removing basket factor) **and** +DI > −DI.

**Short:** bearish sweep + residual-z ≤ −threshold + −DI > +DI.

Sniper is stricter (z 1.25, same-bar); background is milder (z 0.75, 2-bar persistence). Stops sit beyond the sweep wick.

## Locked performance

| Metric | Value |
|--------|------:|
| Total return | +13.54% |
| Annualized | 2.14% |
| Sharpe | 0.44 |
| Max DD | 4.76% |
| Win rate | 36.84% |
| Profit factor | 1.543 |
| Trades | 95 |
| Trades / month | 1.32 |
| Final equity | $1,135.42 |

### Year-by-year
| Year | Return | Trades | WR |
|-----:|-------:|-------:|---:|
| 2020 | −2.03% | 13 | 23.1% |
| 2021 | +2.04% | 18 | 33.3% |
| 2022 | +2.84% | 24 | 37.5% |
| 2023 | +5.94% | 16 | 37.5% |
| 2024 | +2.31% | 11 | 54.5% |
| 2025 | +1.90% | 13 | 38.5% |

### Out-of-sample
- Train 2020–2023: **+8.9%**  
- Test 2024–2025: **+4.3%** (DD 2.5%)  

### Monte Carlo (200 bootstrap)
- Median return ~**+14.5%**  
- 5th pct return ~**−0.5%**  
- Median max DD ~**4.4%**  

## What was tested
- 76+ residual/sweep/risk configurations on causal H4 fills  
- Forward-return edge study for swing/mom/z combinations  
- Train/OOS split, yearly breakdown, Monte Carlo  

## Forward-test plan (2026)
1. Freeze `config.json` — no re-optimize on 2026.  
2. OANDA 4H close → next-bar market order with sweep-stop + ATR target.  
3. Kill if live DD ≥ 20% or rolling 3-month expectancy < 0 after ≥40 trades.  

## Bottom line
EMA cross was the wrong entry. Residual momentum with liquidity-sweep confluence is the locked model: selective, lower DD, positive OOS.
