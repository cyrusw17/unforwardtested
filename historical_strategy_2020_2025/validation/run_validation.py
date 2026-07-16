#!/usr/bin/env python3
"""Walk-forward, out-of-sample, Monte Carlo, and stress validation (2020-2025 only)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.backtest import Backtester, BacktestResult
from core.data_handler import DataHandler
from historical_strategy_2020_2025.development.test_strategy_variants import composite_score
from historical_strategy_2020_2025.final_strategy.strategy_implementation import (
    StrategyConfig,
    allocation_map,
    build_signal_frames,
)

VAL_DIR = Path(__file__).resolve().parent
VAL_DIR.mkdir(parents=True, exist_ok=True)


def load_final_config() -> StrategyConfig:
    cfg_path = ROOT / "historical_strategy_2020_2025" / "final_strategy" / "config.json"
    if cfg_path.exists():
        data = json.loads(cfg_path.read_text())
        known = StrategyConfig().__dict__.keys()
        filtered = {k: v for k, v in data.items() if k in known}
        return StrategyConfig(**filtered)
    return StrategyConfig(name="dual_vol_regime_v1")


def slice_pairs(pair_data: dict, start: str, end: str) -> dict:
    start_ts = pd.Timestamp(start, tz="UTC")
    end_ts = pd.Timestamp(end, tz="UTC")
    out = {}
    for pair, df in pair_data.items():
        part = df[(df.index >= start_ts) & (df.index <= end_ts)].copy()
        out[pair] = part
    return out


def run_backtest(pair_data: dict, cfg: StrategyConfig) -> BacktestResult:
    signals = build_signal_frames(pair_data, cfg)
    bt = Backtester(
        initial_capital=10_000.0,
        leverage=50.0,
        max_drawdown_pct=20.0,
        use_breakeven=False,
        use_partial_tp=False,
        max_bars_held=10**9,
        allow_dual_positions=True,
    )
    return bt.run(signals, capital_alloc=allocation_map(cfg))


def walk_forward(pair_data: dict, cfg: StrategyConfig) -> pd.DataFrame:
    """6-month train / 3-month test rolling windows across 2020-2025."""
    windows = []
    # Fixed schedule of OOS test windows (train is contextual; params held fixed
    # for final strategy robustness — we evaluate the locked config).
    tests = [
        ("2020-01-01", "2020-06-30", "2020-07-01", "2020-09-30"),
        ("2020-07-01", "2020-12-31", "2021-01-01", "2021-03-31"),
        ("2021-01-01", "2021-06-30", "2021-07-01", "2021-09-30"),
        ("2021-07-01", "2021-12-31", "2022-01-01", "2022-03-31"),
        ("2022-01-01", "2022-06-30", "2022-07-01", "2022-09-30"),
        ("2022-07-01", "2022-12-31", "2023-01-01", "2023-03-31"),
        ("2023-01-01", "2023-06-30", "2023-07-01", "2023-09-30"),
        ("2023-07-01", "2023-12-31", "2024-01-01", "2024-03-31"),
        ("2024-01-01", "2024-06-30", "2024-07-01", "2024-09-30"),
        ("2024-07-01", "2024-12-31", "2025-01-01", "2025-03-31"),
        ("2025-01-01", "2025-06-30", "2025-07-01", "2025-09-30"),
        ("2025-04-01", "2025-09-30", "2025-10-01", "2025-12-31"),
    ]
    rows = []
    for i, (tr_s, tr_e, te_s, te_e) in enumerate(tests, 1):
        test_data = slice_pairs(pair_data, te_s, te_e)
        if min(len(df) for df in test_data.values()) < 20:
            continue
        res = run_backtest(test_data, cfg)
        m = res.metrics
        rows.append(
            {
                "window": i,
                "train_start": tr_s,
                "train_end": tr_e,
                "test_start": te_s,
                "test_end": te_e,
                "score": composite_score(m),
                **m,
            }
        )
        windows.append((te_s, te_e, m))
    df = pd.DataFrame(rows)
    df.to_csv(VAL_DIR / "walk_forward_results.csv", index=False)
    return df


def out_of_sample(pair_data: dict, cfg: StrategyConfig) -> dict:
    train = slice_pairs(pair_data, "2020-01-01", "2023-12-31")
    test = slice_pairs(pair_data, "2024-01-01", "2025-12-31")
    train_res = run_backtest(train, cfg)
    test_res = run_backtest(test, cfg)
    payload = {
        "train_2020_2023": train_res.metrics,
        "oos_2024_2025": test_res.metrics,
        "train_score": composite_score(train_res.metrics),
        "oos_score": composite_score(test_res.metrics),
    }
    with open(VAL_DIR / "out_of_sample_results.json", "w") as f:
        json.dump(payload, f, indent=2)
    # Flat CSV for convenience
    rows = [
        {"segment": "train_2020_2023", "score": payload["train_score"], **train_res.metrics},
        {"segment": "oos_2024_2025", "score": payload["oos_score"], **test_res.metrics},
    ]
    pd.DataFrame(rows).to_csv(VAL_DIR / "out_of_sample_results.csv", index=False)
    train_res.trades_df().to_csv(VAL_DIR / "oos_train_trades.csv", index=False)
    test_res.trades_df().to_csv(VAL_DIR / "oos_test_trades.csv", index=False)
    return payload


def monte_carlo(trades: pd.DataFrame, n_runs: int = 200, seed: int = 42) -> pd.DataFrame:
    """Resample trade PnLs with replacement; also stress win-rate -10%."""
    if trades.empty:
        return pd.DataFrame()
    rng = np.random.default_rng(seed)
    pnls = trades["pnl"].astype(float).values
    n = len(pnls)
    rows = []
    for i in range(n_runs):
        sample = rng.choice(pnls, size=n, replace=True)
        equity = 10_000 + np.cumsum(sample)
        equity = np.insert(equity, 0, 10_000.0)
        peak = np.maximum.accumulate(equity)
        dd = ((equity - peak) / peak * 100).min()
        total_ret = (equity[-1] / 10_000 - 1) * 100
        rows.append({"run": i, "mode": "bootstrap", "total_return_pct": total_ret, "max_drawdown_pct": abs(dd)})

    # Stress: flip 10% of winning trades to average loss
    wins = pnls[pnls > 0]
    losses = pnls[pnls <= 0]
    avg_loss = losses.mean() if len(losses) else -abs(pnls.mean())
    for i in range(n_runs):
        stressed = pnls.copy()
        win_idx = np.where(stressed > 0)[0]
        if len(win_idx):
            k = max(1, int(0.10 * len(win_idx)))
            flip = rng.choice(win_idx, size=k, replace=False)
            stressed[flip] = avg_loss
        sample = rng.choice(stressed, size=n, replace=True)
        equity = 10_000 + np.cumsum(sample)
        equity = np.insert(equity, 0, 10_000.0)
        peak = np.maximum.accumulate(equity)
        dd = ((equity - peak) / peak * 100).min()
        total_ret = (equity[-1] / 10_000 - 1) * 100
        rows.append({"run": i, "mode": "winrate_minus_10pct", "total_return_pct": total_ret, "max_drawdown_pct": abs(dd)})

    df = pd.DataFrame(rows)
    df.to_csv(VAL_DIR / "monte_carlo_results.csv", index=False)
    return df


def cost_sensitivity(pair_data: dict, cfg: StrategyConfig) -> pd.DataFrame:
    rows = []
    for mult, slip in [(1.0, 0.75), (2.0, 1.5), (3.0, 2.25)]:
        spreads = {
            "EURUSD": 0.00013 * mult,
            "GBPUSD": 0.00015 * mult,
            "USDJPY": 0.015 * mult,
            "AUDUSD": 0.00014 * mult,
        }
        signals = build_signal_frames(pair_data, cfg)
        bt = Backtester(
            initial_capital=10_000.0,
            leverage=50.0,
            max_drawdown_pct=20.0,
            slippage_pips=slip,
            spreads=spreads,
            use_breakeven=False,
            use_partial_tp=False,
            max_bars_held=10**9,
            allow_dual_positions=True,
        )
        res = bt.run(signals, capital_alloc=allocation_map(cfg))
        rows.append({"cost_multiple": mult, "slippage_pips": slip, **res.metrics})
    df = pd.DataFrame(rows)
    df.to_csv(VAL_DIR / "cost_sensitivity.csv", index=False)
    return df


def pair_correlation(pair_data: dict) -> pd.DataFrame:
    rets = pd.DataFrame({p: df["Close"].pct_change() for p, df in pair_data.items()}).dropna()
    corr = rets.corr()
    corr.to_csv(VAL_DIR / "pair_return_correlation.csv")
    return corr


def year_breakdown(result: BacktestResult) -> pd.DataFrame:
    eq = result.equity_curve
    rows = []
    by_year = eq.groupby(eq.index.year)
    prev = 10_000.0
    trades = result.trades_df()
    for year, series in by_year:
        end = float(series.iloc[-1])
        ret = end / prev - 1.0
        year_trades = trades[trades["exit_time"].astype(str).str.startswith(str(year))] if not trades.empty else trades
        wr = (year_trades["pnl"] > 0).mean() * 100 if len(year_trades) else 0.0
        rows.append(
            {
                "year": year,
                "start_equity": round(prev, 2),
                "end_equity": round(end, 2),
                "return_pct": round(ret * 100, 2),
                "trades": len(year_trades),
                "win_rate": round(float(wr), 2),
            }
        )
        prev = end
    df = pd.DataFrame(rows)
    df.to_csv(VAL_DIR / "yearly_breakdown.csv", index=False)
    return df


def write_robustness_report(
    cfg: StrategyConfig,
    full: BacktestResult,
    wf: pd.DataFrame,
    oos: dict,
    mc: pd.DataFrame,
    costs: pd.DataFrame,
    corr: pd.DataFrame,
    yearly: pd.DataFrame,
) -> None:
    pos_years = int((yearly["return_pct"] > 0).sum()) if not yearly.empty else 0
    wf_pos = int((wf["total_return_pct"] > 0).sum()) if not wf.empty else 0
    mc_boot = mc[mc["mode"] == "bootstrap"] if not mc.empty else mc
    mc_stress = mc[mc["mode"] == "winrate_minus_10pct"] if not mc.empty else mc

    report = f"""# Robustness Report (2020-2025 Only)

## Configuration
- Name: `{cfg.name}`
- Sniper: EMA {cfg.sniper_fast}/{cfg.sniper_slow}, ADX>{cfg.sniper_adx}, SL/TP={cfg.sniper_sl_atr}/{cfg.sniper_tp_atr} ATR, risk={cfg.sniper_risk_pct}%, max/month={cfg.sniper_max_per_month}
- Background: EMA {cfg.bg_fast}/{cfg.bg_slow}, ADX>{cfg.bg_adx}, SL/TP={cfg.bg_sl_atr}/{cfg.bg_tp_atr} ATR, risk={cfg.bg_risk_pct}%
- Dynamic targets: {cfg.use_dynamic_targets} (high={cfg.high_vol_mult}x, low={cfg.low_vol_mult}x)
- RSI filter: {cfg.use_rsi_filter}
- Allocation: sniper {cfg.sniper_alloc:.0%} / background {cfg.background_alloc:.0%}
- Leverage cap: 50:1 | Max DD halt: 20%
- Data window: **2020-01-01 → 2025-12-31** (no 2026 data used)

## Full-Period Performance
| Metric | Value |
|--------|------:|
| Total return | {full.metrics['total_return_pct']}% |
| Annualized return | {full.metrics['annualized_return_pct']}% |
| Sharpe | {full.metrics['sharpe']} |
| Max drawdown | {full.metrics['max_drawdown_pct']}% |
| Win rate | {full.metrics['win_rate']}% |
| Total trades | {full.metrics['total_trades']} |
| Trades / month | {full.metrics['trades_per_month']} |
| Profit factor | {full.metrics['profit_factor']} |

## Year-by-Year
Positive years: **{pos_years} / {len(yearly)}**

{yearly.to_markdown(index=False) if hasattr(yearly, 'to_markdown') else yearly.to_string(index=False)}

## Walk-Forward (locked params)
- Windows tested: {len(wf)}
- Positive test windows: {wf_pos}/{len(wf)}
- Median test return: {wf['total_return_pct'].median():.2f}%
- Median test Sharpe: {wf['sharpe'].median():.2f}
- Median test max DD: {wf['max_drawdown_pct'].median():.2f}%

## Out-of-Sample (train 2020-2023 / test 2024-2025)
- Train return: {oos['train_2020_2023']['total_return_pct']}% | Sharpe {oos['train_2020_2023']['sharpe']} | DD {oos['train_2020_2023']['max_drawdown_pct']}%
- OOS return: {oos['oos_2024_2025']['total_return_pct']}% | Sharpe {oos['oos_2024_2025']['sharpe']} | DD {oos['oos_2024_2025']['max_drawdown_pct']}%

## Monte Carlo ({0 if mc.empty else mc_boot.shape[0]} bootstrap runs)
- Bootstrap median return: {mc_boot['total_return_pct'].median():.2f}%
- Bootstrap 5th pct return: {mc_boot['total_return_pct'].quantile(0.05):.2f}%
- Bootstrap median max DD: {mc_boot['max_drawdown_pct'].median():.2f}%
- Stress (WR-10%) median max DD: {mc_stress['max_drawdown_pct'].median():.2f}%
- Stress DD < 25% rate: {(mc_stress['max_drawdown_pct'] < 25).mean()*100:.1f}%

## Cost Sensitivity
{costs.to_markdown(index=False) if hasattr(costs, 'to_markdown') else costs.to_string(index=False)}

## Pair Return Correlation
{corr.round(3).to_markdown() if hasattr(corr, 'to_markdown') else corr.round(3).to_string()}

## Success Criteria Checklist
- Positive returns in ≥4/6 years: {'PASS' if pos_years >= 4 else 'FAIL'} ({pos_years}/6)
- Sharpe > 1.5: {'PASS' if full.metrics['sharpe'] > 1.5 else 'FAIL'} ({full.metrics['sharpe']})
- Max DD < 20%: {'PASS' if full.metrics['max_drawdown_pct'] < 20 else 'FAIL'} ({full.metrics['max_drawdown_pct']}%)
- Win rate > 55%: {'PASS' if full.metrics['win_rate'] > 55 else 'FAIL'} ({full.metrics['win_rate']}%)
- ≥50 trades/year: {'PASS' if full.metrics['total_trades']/max(full.metrics.get('years',6),1) >= 50 else 'CHECK'} ({full.metrics['total_trades']} total)
- No 2026 data: PASS
"""
    (VAL_DIR / "robustness_report.md").write_text(report)


def main():
    cfg = load_final_config()
    handler = DataHandler(cache_dir=ROOT / "data" / "cache")
    pair_data = handler.fetch_all_pairs(start="2020-01-01", end="2025-12-31", interval="1d")
    for p, df in pair_data.items():
        handler.assert_no_2026(df, p)

    print("Running full-period backtest...")
    full = run_backtest(pair_data, cfg)
    full.trades_df().to_csv(VAL_DIR / "full_period_trades.csv", index=False)
    full.equity_curve.to_csv(VAL_DIR / "full_period_equity.csv", header=True)
    with open(VAL_DIR / "full_period_metrics.json", "w") as f:
        json.dump(full.metrics, f, indent=2)

    print("Walk-forward...")
    wf = walk_forward(pair_data, cfg)
    print("Out-of-sample...")
    oos = out_of_sample(pair_data, cfg)
    print("Monte Carlo...")
    mc = monte_carlo(full.trades_df(), n_runs=200)
    print("Cost sensitivity...")
    costs = cost_sensitivity(pair_data, cfg)
    print("Correlations...")
    corr = pair_correlation(pair_data)
    yearly = year_breakdown(full)

    write_robustness_report(cfg, full, wf, oos, mc, costs, corr, yearly)
    print("Validation complete ->", VAL_DIR)
    print(json.dumps(full.metrics, indent=2))


if __name__ == "__main__":
    main()
