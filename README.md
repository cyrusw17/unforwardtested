# unforwardtested

Forex strategy research package: recreate a dual EMA system on **2020–2025 data only**, then forward-test later on 2026.

## Main package

See [`historical_strategy_2020_2025/README.md`](historical_strategy_2020_2025/README.md) and the executive report [`historical_strategy_2020_2025/FINAL_REPORT.md`](historical_strategy_2020_2025/FINAL_REPORT.md).

```bash
pip install -r requirements.txt
python historical_strategy_2020_2025/run_pipeline.py
```

## Hard constraint

Strategy development **must not** use any data after `2025-12-31`. Enforced in `core/data_handler.py`.
