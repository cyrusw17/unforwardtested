# unforwardtested

All-era robust forex system: **residual momentum × liquidity sweep** (sniper-only), selected under hard multi-era gates on Dukascopy 4H **2018–2025** (no 2026).

## Live report
https://cyrusw17.github.io/unforwardtested/

## Locked snapshot
- **+13.6%** over 2018–2025 · DD **4.7%** · PF **1.98**
- Eras: 2018–19 −1.1% · 2020 −0.6% · 2021–23 **+11.4%** · 2024–25 **+3.9%**
- Selection: 6 / 421 configs passed era floors

```bash
pip install -r requirements.txt
python historical_strategy_2020_2025/final_strategy/backtest_full_period.py
```

## Hard constraint
No data after `2025-12-31`.
