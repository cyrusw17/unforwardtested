# Strategy Specification — Residual Momentum × Liquidity Sweep

## Name
`residual_momentum_liquidity_sweep`

## Why the entry model changed
EMA cross is a lagged trend toggle. The locked system replaces it with **confluence**:

1. **Residual momentum** — idiosyncratic strength after removing the equal-weight majors basket factor  
2. **Liquidity sweep** — pierce a prior swing extreme, then reclaim with a rejection wick  
3. **DI / mild ADX** — direction must agree; skip dead ranges  

## Rules (locked)

### Residual momentum
- Factor: equal-weight mean log-return of EURUSD/GBPUSD/USDJPY/AUDUSD  
- Residual: rolling OLS `r − β·factor` (β lookback 60)  
- Long momentum sum: **8** bars → z-score  
- Short momentum sum: **4** bars → z-score  
- Sniper z-threshold: **±1.25**  
- Background z-threshold: **±0.75**

### Liquidity sweep
- Long swing lookback: **18** bars  
- Short swing lookback: **24** bars  
- Bullish: Low < prior swing low, Close reclaims above it, lower wick ≥ 0.1 ATR  
- Bearish: High > prior swing high, Close reclaims below it, upper wick ≥ 0.1 ATR  
- Sniper: same-bar sweep only  
- Background: sweep may persist **2** bars  

### Dual sleeves
| Sleeve | Risk | SL / TP | Cap |
|--------|-----:|---------|-----|
| Sniper (60%) | 1.5% | sweep-stop / 4.0 ATR | ≤3 / pair / month |
| Background (40%) | 1.0% | sweep-stop / 2.5 ATR | none |

- Sweep stop: beyond wick ±0.1 ATR, capped at 2.25 ATR  
- Vol regime: z>1.5 → ×0.75, z<−1.0 → ×1.25  
- Soft DD 15% (risk ×0.5) · Hard halt 20%  
- $1,000 · 50:1 · OANDA-like spread + 0.5 pip slippage  
- Signal on 4H close → fill next open  

## Locked performance (2020–2025 H4)
See `full_period_metrics.json` / `FINAL_REPORT.md`.

## vs prior EMA lock
| | EMA dual | Residual × Sweep |
|--|---------:|-----------------:|
| Return | +11.7% | **+13.5%** |
| Max DD | 17.8% | **4.8%** |
| Sharpe | 0.20 | **0.44** |
| OOS 2024–25 | +2.4% | **+4.3%** |
| PF | 1.05 | **1.54** |
