# unforwardtested

Forex research package: **residual momentum × liquidity-sweep** dual system on Dukascopy 4H (**2020–2025 only**), ready for 2026 forward test.

## Live report
https://cyrusw17.github.io/unforwardtested/

## Locked snapshot
- Entry: residual momentum + liquidity sweep confluence (not EMA cross)
- Result: **+13.5%** / 6y · max DD **4.8%** · OOS 2024–25 **+4.3%** · PF **1.54**
- Config: `historical_strategy_2020_2025/final_strategy/config.json`

```bash
pip install -r requirements.txt
python historical_strategy_2020_2025/final_strategy/backtest_full_period.py
```

## Hard constraint
No data after `2025-12-31` (`core/h4_data.py`).
