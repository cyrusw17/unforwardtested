# Strategy Concepts (2020-2025 Research)

## Concept A — Dual EMA Sniper + Background (Primary)
- Sniper: EMA 3/9 cross, ADX filter, 1–5 ATR R:R, capped frequency, 2% risk
- Background: EMA 9/21 cross, stricter ADX, 2–3 ATR R:R, 1% risk
- Why: Balances lottery-ticket trend capture with steadier participation
- Risk: Overtrading if ADX too low; correlated entries across EUR/GBP

## Concept B — Volatility-Regime Adaptive Targets
- ATR z-score classifies high/normal/low vol
- Tighten targets in high vol; widen in low vol
- Why: 2020-style spikes stop out fixed wide targets; quiet markets need room
- Risk: Misclassified regimes around transitions

## Concept C — DI-Confirmed Trend Following
- EMA cross only when +DI/-DI agrees
- Optional RSI ceiling/floor to avoid late chase
- Why: Improves directional alignment vs raw cross
- Risk: Fewer trades; missed early moves

## Concept D — Session / Event Avoidance (Secondary)
- On daily data, session filters are limited
- Practical proxy: skip entries when ATR z-score extreme AND ADX collapsing
- Why: Avoid exhausting climax bars
- Risk: Hard to validate without intraday history

## Concept E — Momentum Breakout + ATR Channel
- Enter on close beyond N-day high/low with ADX rising
- Exit on opposite channel or ATR stop
- Why: Captures 2022-style trend legs
- Risk: Whipsaw in 2023 chop; may fail WR target without filters

## Selected Path
Prioritize **A + B + C** (dual system with vol-adaptive targets and DI/RSI filters),
then validate with walk-forward / OOS / Monte Carlo on 2020-2025 only.
