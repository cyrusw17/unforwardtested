# MCPT-Validated Trading Strategy

A rigorous trading strategy validation framework using Monte Carlo Permutation Tests (MCPT), following the methodology from [neurotrader888](https://github.com/neurotrader888/mcpt).

## Overview

This project implements a **Hybrid Momentum Trading Strategy** that has been validated through a 4-step process to ensure it has real statistical edge and is not simply curve-fitted to historical data.

### The 4-Step Validation Process

1. **In-Sample Excellence** - Optimize strategy on historical data (2016-2024)
2. **In-Sample MCPT** - Test if strategy beats random permutations (p-value < 1%)
3. **Walk-Forward Test** - Test on out-of-sample data (2025-2026)
4. **Walk-Forward MCPT** - Test if forward results beat random permutations (p-value < 5%)

## What is Monte Carlo Permutation Testing?

MCPT answers the critical question: **"Could this result have been produced by luck alone?"**

The test works by:
1. Shuffling the log-returns of price data to create synthetic price paths
2. These permutations have the same statistical properties (mean, std, skew, kurtosis) as real data
3. But they lack any real temporal patterns or tradeable structure
4. If your strategy performs significantly better on real data than on 1000+ permutations, it likely has real edge

**Key Insight**: If a strategy can't beat randomly shuffled data, it's just fitting noise.

## Strategy Description

The **Hybrid Momentum Strategy** combines:
- **Trend Following**: Donchian-style breakouts with moving average filter
- **Volatility Filtering**: Only trades when volatility is elevated (using ATR)
- **RSI Filter**: Avoids extreme overbought/oversold conditions
- **Walk-Forward Optimization**: Reoptimizes parameters every 30 days on rolling 4-year window

This multi-factor approach aims to capture trending moves while avoiding false breakouts and choppy markets.

## Project Structure

```
mcpt_strategy/
├── data/
│   ├── fetch_data.py          # Download crypto OHLC data via CCXT
│   └── BTCUSDT_1h.parquet     # Cached data (generated)
├── strategies/
│   └── hybrid_momentum.py     # Strategy implementation & optimization
├── tests/
│   ├── insample_mcpt.py       # In-sample permutation test
│   └── walkforward_mcpt.py    # Walk-forward permutation test
├── utils/
│   └── bar_permute.py         # Price permutation algorithm
├── results/                    # Test results & plots (generated)
├── run_all_tests.py           # Main validation pipeline
└── README.md
```

## Installation

```bash
cd /workspace/mcpt_strategy

pip install pandas numpy matplotlib tqdm ccxt
```

## Usage

### 1. Fetch Data

```bash
python data/fetch_data.py
```

This downloads hourly BTC/USDT data from Binance (2016-2026).

### 2. Run Complete Validation

```bash
python run_all_tests.py
```

This runs all 4 validation steps:
- In-sample optimization (2016-2024)
- In-sample MCPT (1000 permutations)
- Walk-forward test (2025-2026)
- Walk-forward MCPT (200 permutations)

**Expected runtime**: 30-60 minutes depending on hardware.

### 3. View Results

Results are saved to `results/`:
- `insample_mcpt_results.json` - In-sample test metrics
- `insample_mcpt_histogram.png` - Distribution of permuted vs real performance
- `walkforward_mcpt_results.json` - Walk-forward test metrics
- `walkforward_mcpt_results.png` - Distribution + equity curve
- `validation_summary.json` - Overall pass/fail summary

## Interpretation of Results

### In-Sample MCPT
- **P-value < 0.01**: Strategy likely has real edge (not just data mining)
- **P-value >= 0.01**: Strategy may be overfit, reject it

### Walk-Forward MCPT
- **P-value < 0.05** (1 year OOS): Acceptable generalization
- **P-value < 0.01** (2+ years OOS): Strong generalization
- **P-value above threshold**: Strategy doesn't generalize

### Overall Pass Criteria
Both tests must pass for the strategy to be considered validated.

## Key Parameters

### Strategy Parameters (optimized)
- `trend_lookback`: Lookback period for trend determination (30-100 bars)
- `volatility_period`: Period for ATR calculation (14-28 bars)
- `rsi_period`: Period for RSI calculation (10-21 bars)
- `vol_multiplier`: Volatility threshold multiplier (1.0-2.0)

### Walk-Forward Parameters
- `train_window`: 4 years (35,040 hourly bars)
- `train_step`: 30 days (720 hourly bars)
- Reoptimizes every month on rolling 4-year window

## Methodology Notes

### Why This Approach?

Traditional backtesting is flawed because:
1. **Optimization overfits** - Any optimizer will find *something* in data, even pure noise
2. **Out-of-sample is reused** - Once you test on 2025 data, it's no longer truly OOS
3. **Selection bias accumulates** - Testing 100 strategies on same OOS data = overfitting

MCPT solves this by:
- Testing whether your strategy beats **noise** (not just buy-and-hold)
- Validating in-sample edge **before** wasting OOS data
- Providing statistical p-values for rigor

### Limitations

MCPT is not perfect:
- Doesn't preserve volatility clustering or long-memory effects
- Can be optimistically biased if strategy exploits these properties
- Computationally expensive (1000+ full optimizations)

However, if a strategy **fails** MCPT, it almost certainly lacks real edge.

## References

- **Video**: [How I Develop Trading Strategies | Permutation Tests](https://www.youtube.com/watch?v=NLBXgSmRBgU)
- **Code**: [neurotrader888/mcpt](https://github.com/neurotrader888/mcpt)
- **Book**: *Testing and Tuning Market Trading Systems* by Timothy Masters
- **Book**: *Permutation and Randomization Tests* by Timothy Masters

## Training Data Constraint

As specified, this strategy:
- **Trains only on 2016-2024 data**
- **Forward tests on 2025-2026 data**
- **Never trains on 2025-2026 data**

The walk-forward test uses a rolling 4-year window, so by 2025, it's training on 2021-2025 data, but the initial optimization and parameter search are done on pre-2025 data only.

## License

MIT License - Based on code from neurotrader888/mcpt

## Disclaimer

This is for educational purposes only. Past performance does not guarantee future results. Do not trade with real money without thorough understanding and testing.
