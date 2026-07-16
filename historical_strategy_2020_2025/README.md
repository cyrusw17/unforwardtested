# Historical Forex Strategy Package (2020–2025)

Residual momentum × liquidity-sweep dual strategy on **Dukascopy 4H**, no 2026 look-ahead.

```bash
pip install -r ../requirements.txt
python final_strategy/backtest_full_period.py
python final_strategy/performance_charts.py
python development/run_residual_sweep.py
```

## Locked result
- **+13.5%** total · DD **4.8%** · Sharpe **0.44** · OOS **+4.3%** · **5/6** positive years
- Entry model in `final_strategy/strategy_implementation.py` + `core/residual_momentum.py`
