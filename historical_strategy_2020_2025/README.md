# Historical Forex Strategy Package (2020–2025)

Recreates and validates a dual EMA forex strategy using **only 2020–2025 data** (no 2026 look-ahead).

## Quick Start

```bash
pip install -r ../requirements.txt
python run_pipeline.py
```

Or step-by-step:

```bash
python research/run_market_analysis.py
python development/test_strategy_variants.py
python development/optimize_parameters.py
python validation/run_validation.py
python final_strategy/backtest_full_period.py
python final_strategy/performance_charts.py
```

## Layout

```
historical_strategy_2020_2025/
├── research/               # Market analysis + strategy concepts
├── development/            # Variant tests, grid search, CSVs
├── validation/             # Walk-forward, OOS, Monte Carlo, stress
├── final_strategy/         # Locked spec, config, implementation, charts
├── FINAL_REPORT.md         # Executive results + forward-test plan
└── run_pipeline.py         # End-to-end runner
```

## Locked Result (snapshot)

- Total return 2020–2025: **+42.9%**
- Max DD: **15.1%**
- Positive years: **6/6**
- OOS 2024–2025: **+9.7%**
- Sharpe / win-rate ambition targets: not met under realistic daily costs (see report)

## Core Library

Shared engine lives in `/workspace/core/`:
- `data_handler.py` — Yahoo fetch + hard 2025-12-31 cap
- `indicators.py` — EMA/ADX/ATR/RSI/...
- `backtest.py` — multi-pair portfolio backtester
