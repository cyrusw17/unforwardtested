# Historical Forex Strategy Package (2020–2025)

Implements and validates the dual sniper/background EMA strategy using **only 2020–2025 Dukascopy 4H data** (no 2026 look-ahead).

## Quick Start

```bash
pip install -r ../requirements.txt
python final_strategy/backtest_full_period.py
python final_strategy/performance_charts.py
```

Or full pipeline:

```bash
python run_pipeline.py
```

## Layout

```
historical_strategy_2020_2025/
├── research/               # Market analysis + strategy concepts
├── development/            # Variant tests, H4 sweeps, claim checks
├── validation/             # OOS, Monte Carlo, yearly breakdown
├── final_strategy/         # Locked spec, config, implementation, charts
├── FINAL_REPORT.md         # Executive results + forward-test plan
└── run_pipeline.py         # End-to-end runner
```

## Locked Result (H4 future-proof)

- Total return 2020–2025: **+11.7%**
- Max DD: **17.8%** (hard halt 20%, soft cut 15%)
- Positive years: **4/6**
- OOS 2024–2025: **+2.4%**
- Exact brief params: **−18%** (not tradeable)
- Claimed ~1,070% / 90d and ~71% WR: **not reproducible**

## Core Library

Shared engine lives in `/workspace/core/`:
- `h4_data.py` — Dukascopy freeserv 4H download + cache (hard 2025-12-31 cap)
- `data_handler.py` — Yahoo daily fetch + hard date cap
- `indicators.py` — EMA/ADX/ATR/RSI/...
- `backtest.py` — multi-pair portfolio backtester (soft/hard DD)
