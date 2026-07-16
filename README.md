# unforwardtested

Forex strategy research package: implement the dual sniper/background system on **2020–2025 Dukascopy 4H data only**, then forward-test later on 2026.

## Main package

See [`historical_strategy_2020_2025/README.md`](historical_strategy_2020_2025/README.md) and the executive report [`historical_strategy_2020_2025/FINAL_REPORT.md`](historical_strategy_2020_2025/FINAL_REPORT.md).

Browsable HTML report: [`docs/index.html`](docs/index.html).

```bash
pip install -r requirements.txt
python historical_strategy_2020_2025/final_strategy/backtest_full_period.py
```

## Locked snapshot

- Config: `historical_strategy_2020_2025/final_strategy/config.json`
- Result: **+11.7%** over 2020–2025, max DD **17.8%**, OOS 2024–25 **+2.4%**
- Exact marketing brief on the same data: **−18%** (DD ~43%)

## Hard constraint

Strategy development **must not** use any data after `2025-12-31`. Enforced in `core/h4_data.py` and `core/data_handler.py`.
