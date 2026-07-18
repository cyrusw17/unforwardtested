# Live Paper Trader — Enhanced ICT v3 (AUD/USD)

A fully automated, live paper-trading simulation of the validated
**Enhanced ICT v3** strategy (19.47% backtested annual return, MCPT
p = 0.006 on out-of-sample 2025–2026 data, with better drawdown/Sharpe/
Calmar than the earlier v2 — see
`../mcpt_strategy/TRADE_ANALYSIS_2020_2024_ADJUSTMENT.md`).

**Live dashboard:** enable GitHub Pages for this repo (Settings → Pages →
Source: Deploy from a branch → branch = this branch, folder = `/docs`) and
visit the Pages URL. See "Enabling GitHub Pages" below.

## How it works

- **Account:** $100,000 starting balance, 1:100 leverage, AUD/USD.
- **Signal:** the exact same `enhanced_ict_v3_adjusted()` function used in
  backtesting — Order Blocks + Fair Value Gaps + Liquidity Sweeps + Market
  Structure + Trend confluence, recomputed once per closed daily bar.
- **Position sizing:** risk-based, scaled by signal conviction (0–1.5x),
  using ATR-based stop distance — mirrors the OANDA broker model used in
  backtesting, including realistic spread/slippage costs.
- **Execution cadence:** a GitHub Actions workflow
  (`.github/workflows/paper_trader.yml`) runs every hour:
  1. Fetches the latest intraday AUD/USD price (for the live chart).
  2. If a new daily bar has closed since the last run, recomputes the
     strategy signal and transitions the open position (opens / closes /
     flips / re-sizes) — this is the only point at which real "trades"
     happen, exactly matching how the strategy was backtested.
  3. Marks the open position to market against the latest live price so
     equity updates continuously between daily closes.
  4. Commits the updated JSON state back to the repo, which the static
     dashboard (`docs/index.html`) reads directly — no server required.
- **History:** the simulation was seeded 7 days in the past
  (`init_state.py`) using real historical daily bars, so the equity curve
  and trade log show a full week of activity before "live" mode took over.

## Files

| File | Purpose |
|---|---|
| `engine.py` | Data fetching, ATR calc, position sizing, P&L math |
| `portfolio.py` | Position/trade state transitions (open/close/flip/resize) |
| `state.py` | JSON read/write helpers for `docs/data/*.json` |
| `init_state.py` | One-time: seed the 1-week backfill and initial state |
| `run_cycle.py` | Repeated: one live update cycle (called by the GH Action) |

## Running locally

```bash
pip install -r paper_trading/requirements.txt

# One-time setup (creates docs/data/*.json, backfills 7 days)
python paper_trading/init_state.py

# Simulate a live cycle (run this repeatedly / on a schedule)
python paper_trading/run_cycle.py
```

Then serve `docs/` locally to preview the dashboard:

```bash
cd docs && python3 -m http.server 8080
# open http://localhost:8080
```

## Enabling GitHub Pages

GitHub Pages and scheduled (`on: schedule`) GitHub Actions **only run
automatically from the repository's default branch**. Until this branch is
merged there:

1. You can still preview the dashboard by enabling Pages with
   **Source: Deploy from a branch**, branch = this feature branch, folder =
   `/docs` — Pages itself doesn't require the default branch.
2. The hourly auto-trading workflow, however, will only fire on its cron
   schedule once merged into the default branch. Until then, trigger it
   manually from the Actions tab ("Run workflow" / `workflow_dispatch`) to
   advance the simulation.

## Resetting the simulation

Delete `docs/data/*.json` and re-run `python paper_trading/init_state.py`
to restart with a fresh $100,000 balance and a new 7-day backfill.

## Disclaimer

This is a **paper trading simulation** — no real money is traded, no broker
account is connected. It exists to observe how the statistically-validated
strategy behaves against live, streaming price action before any
consideration of real capital.
