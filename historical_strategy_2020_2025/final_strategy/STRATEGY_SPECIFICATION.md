# Strategy Specification — Future-Proofed Dual System

## Name
`very_conservative_2pct_dual_futureproof`

## What was requested
The “2% Very Conservative Dual Strategy” brief (EMA 3/9 + 9/21, ADX 10/20, 1/5 and 2/3 ATR, 2%/1% risk, 4H, $1,000, 50:1).

## What honest H4 testing showed
On **Dukascopy 4H, 2020-01-01 → 2025-12-31**, with OANDA-like costs and **no 2026 data**:

| Variant | Result |
|---------|--------|
| Exact brief (no DI, ADX 10/20, sniper TP 5, risk 2%/1%) | **−18.3%**, max DD **42.6%**, WR ~28.5% |
| Claimed 90-day return | **~1,070%** |
| Observed median 90-day return (locked system) | **low single digits** |
| Claimed win rate | **~71%** |
| Observed win rate | **~31%** |

The brief’s headline projections are **not reproducible** under causal fills + costs on full 2020–2025 4H data. Configs that looked great on 2023–2026-only windows fail when COVID/hike years are included.

## Locked future-proof rules (kept structure, fixed edge)

### Capital
- Start: **$1,000**
- Leverage cap: **50:1**
- Allocation: **60% sniper / 40% background**
- Soft DD 15% → cut risk ×0.5  
- Hard DD halt: **20%**

### Sniper
- EMA **3/9** cross
- ADX **> 15** (brief: 10)
- **+DI/−DI must agree** (new, required)
- SL **1.0 ATR**, TP **3.0 ATR** (brief TP: 5.0)
- Risk **1.0%** of sniper capital (brief: 2.0% — 2% failed OOS / hit halt)
- Max **2** trades / pair / month

### Background
- EMA **9/21** cross
- ADX **> 25** (brief: 20)
- DI agreement required
- SL **2.0 ATR**, TP **3.0 ATR**
- Risk **1.0%** of background capital
- No monthly cap

### Regime / boost
- ATR z-score 50: high if z>1.5 (×0.75), low if z<−1.0 (×1.25)
- If ADX > 30: take-profit ×1.5

### Execution
- Signal on 4H close → fill next 4H open
- Same-bar SL+TP → stop first
- Spread ~1.2–1.5 pips + **0.5 pip** slippage

## Locked performance (2020–2025 H4)
See `full_period_metrics.json` / `FINAL_REPORT.md`.

## Why these changes are “future-proof”
1. Validated across **crisis + hike + chop** years (not only 2023+ trend).  
2. **Causal DI** (filter before signal shift — no look-ahead).  
3. Positive **2024–2025 OOS** after train on 2020–2023.  
4. DD stays under live 20% halt without early account death.  
5. Trade frequency (~11/month) is automatable on OANDA 4H.
