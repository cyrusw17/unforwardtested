# Market Analysis 2020-2025

## Scope
- Pairs: EURUSD, GBPUSD, USDJPY, AUDUSD
- Timeframe: **daily** (Yahoo Finance long-history forex; 4H long history unavailable)
- Window: 2020-01-01 to 2025-12-31 (**no 2026 data**)

## Regime Context
Major episodes in-sample:
1. **2020 COVID shock** — extreme volatility spike, risk-off USD bid, then V-shaped recovery.
2. **2021 reflation / risk-on** — relatively orderly trends, lower crisis vol.
3. **2022 Fed hiking / USD strength** — strong USDJPY / DXY trends; mean-reversion traps frequent.
4. **2023 disinflation pivot hopes** — choppier FX, intermittent trend bursts.
5. **2024-2025** — policy divergence themes; mixed trending/ranging months.

A robust strategy must survive crisis vol (2020), strong trend years (2022), and chop (2023+).

## Pair Snapshot
- **EURUSD**: buy&hold 4.7%, ann vol 7.5%, ADX>20 on 57% of days, avg ATR% 0.790%.
- **GBPUSD**: buy&hold 1.5%, ann vol 8.9%, ADX>20 on 50% of days, avg ATR% 0.908%.
- **USDJPY**: buy&hold 43.9%, ann vol 9.3%, ADX>20 on 62% of days, avg ATR% 0.943%.
- **AUDUSD**: buy&hold -4.5%, ann vol 10.7%, ADX>20 on 47% of days, avg ATR% 1.147%.

## Indicator Notes
Correlations of classic features vs **next-day returns** are weak (as expected in FX), so edges must come from **filtered event signals** (crossovers + ADX + volatility targeting), not raw predictive R².

See `indicator_correlations.csv` for pair-level feature correlations.

## Implications for Strategy Design
1. Use **ADX** to avoid low-trend chop.
2. Use **ATR-based stops/targets** so risk scales with regime.
3. Prefer **dual frequency** (rare high-R:R + steadier background) to diversify trade timing.
4. Trade a **basket** — EURUSD/GBPUSD are correlated; USDJPY diversifies somewhat.
5. Keep costs realistic; daily FX edges are small after spreads.
