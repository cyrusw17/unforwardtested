# Final Strategy Specification

## Name
`dual_ema_vol_regime_final`

## Universe & Constraints
- Pairs: EURUSD, GBPUSD, USDJPY, AUDUSD
- Timeframe: **Daily** (Yahoo Finance long-history FX; multi-year 4H unavailable)
- Development window: **2020-01-01 → 2025-12-31 only**
- Leverage cap: **50:1**
- Max portfolio drawdown halt: **20%**
- Costs: OANDA-like spreads + 0.75 pip slippage
- Platform target: OANDA-compatible signal logic (next-bar open fills)

## Dual System Overview
Capital split: **60% Sniper / 40% Background**

Both sleeves may hold positions on the same pair simultaneously (separate risk budgets).

### Sniper (high R:R)
| Item | Rule |
|------|------|
| Entry | EMA(5) crosses EMA(13) |
| Filters | ADX(14) > 12, DI direction agrees, RSI not extreme (<70 long / >30 short) |
| Stop | 1.0 × ATR(14) × regime multiplier |
| Target | 5.0 × ATR(14) × regime multiplier |
| Risk | 2.0% of sniper capital per trade |
| Frequency cap | Max 3 new sniper trades per pair per calendar month |

### Background (moderate R:R)
| Item | Rule |
|------|------|
| Entry | EMA(8) crosses EMA(21) |
| Filters | ADX(14) > 18, DI direction agrees, RSI bounds as above |
| Stop | 2.0 × ATR(14) × regime multiplier |
| Target | 3.0 × ATR(14) × regime multiplier |
| Risk | 1.0% of background capital per trade |
| Frequency cap | None |

## Volatility Regime Adaptation
1. Compute ATR z-score over 50 bars.
2. Classify:
   - high if z ≥ +1.0 → multiply SL/TP by **0.75**
   - low if z ≤ −1.0 → multiply SL/TP by **1.35**
   - else normal → **1.00**

## Execution Model (Causal)
1. Signal evaluated on bar **close**.
2. Order actionable on **next bar open**.
3. Stop/target checked on subsequent bar high/low.
4. If stop and target both touched same bar → **stop first** (conservative).

## Position Sizing
```
risk_dollars = equity * allocation_frac * (risk_pct / 100)
units = risk_dollars / stop_distance_in_account_ccy
units = min(units, equity * leverage * allocation_frac / entry_price)
```

## Why This Design
- Recreates the reference dual-sleeve idea without using 2026 data.
- High-R:R sniper captures infrequent trend extensions; background adds participation.
- ADX/DI filters reduce chop entries; ATR stops scale with volatility.
- Selected for **6/6 positive years** and DD < 20% under realistic costs.

## Parameter Count
~12 economically meaningful parameters (EMA lengths, ADX thresholds, ATR multiples, risk %, allocation, regime thresholds). Kept intentionally small to limit overfitting.
