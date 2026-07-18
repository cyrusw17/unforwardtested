# Live Paper Trader — Causal 2-Pair ICT Portfolio (GBP/JPY + NZD/CAD)

A fully automated, live paper-trading simulation of the validated
**Causal 2-Pair ICT Portfolio** strategy. This replaces the earlier
"Enhanced ICT v2/v3" (AUD/USD) strategy, which was retired after a
lookahead bias was discovered in its backtests (see
`../mcpt_strategy/LOOKAHEAD_BIAS_FINDING.md`).

This strategy is genuinely causal (no lookahead) and was validated with a
strict train (2005-2020) / validation (2021-2024) / test (2025-2026)
split, never tuning anything on the test window. It passed a portfolio-
level Monte Carlo Permutation Test on the untouched test window
(p = 0.019, 1000 permutations). See
`../mcpt_strategy/PHASE10_15PCT_HONEST_RESULTS.md` for full methodology.

**Live dashboard:** enable GitHub Pages for this repo (Settings → Pages →
Source: Deploy from a branch → branch = this branch, folder = `/docs`) and
visit the Pages URL. See "Enabling GitHub Pages" below.

## How it works

- **Account:** $100,000 starting balance, 1:100 leverage available.
- **Two independent legs**, each an independent binary directional signal
  from `enhanced_ict_scoring_v2()` (Order Blocks + Fair Value Gaps +
  Liquidity Sweeps + Trend confluence, causal/lookahead-free):
  - **GBP/JPY**: `entry_threshold=2.5, ob_lookback=3, ob_weight=3.0, trend_weight=1.0`
  - **NZD/CAD**: `entry_threshold=2.0, ob_lookback=3, ob_weight=1.5, trend_weight=1.5`
- **Position sizing:** each leg sized as a fixed fraction of current
  equity (`weight=0.5 * SCALE=4.0`), i.e. up to 200% of equity notional
  per leg at peak -- well within the 1:100 leverage available. P&L is
  computed directly as `notional_usd * direction * log_return`, exactly
  mirroring the validated backtest's math (not lots/pips, since pip
  economics differ between JPY- and CAD-quoted pairs).
- **Why 4x scale:** Profit Factor and Sharpe (hence the MCPT p-value) are
  *exactly* scale-invariant to a uniform position-size multiplier -- only
  $ return and $ drawdown scale linearly with it. 4x was chosen to hit a
  ~15%+/yr return target (~16.2%/yr on the untouched test window) while
  keeping resulting drawdown (~12.7%) reasonable. See the docs above for
  the full derivation and scaling table.
- **Execution cadence:** a GitHub Actions workflow
  (`.github/workflows/paper_trader.yml`) runs every hour, for BOTH legs:
  1. Fetches the latest intraday price for each pair (for the live charts).
  2. If a new daily bar has closed for a pair since the last run,
     recomputes that leg's signal and transitions its position (open /
     close / flip) -- this is the only point at which real "trades"
     happen, exactly matching how the strategy was backtested.
  3. Marks all open positions to market against the latest live prices so
     equity updates continuously between daily closes.
  4. Commits the updated JSON state back to the repo, which the static
     dashboard (`docs/live/index.html`) reads directly -- no server
     required.
- **History:** the simulation was seeded 7 days in the past
  (`init_state.py`) using real historical daily bars for both legs, so the
  equity curve and trade log show a full week of activity before "live"
  mode took over.

## Files

| File | Purpose |
|---|---|
| `engine.py` | Data fetching, signal generation, notional-based P&L math for both legs |
| `portfolio.py` | Per-pair position/trade state transitions (open/close/flip), portfolio mark-to-market |
| `state.py` | JSON read/write helpers for `live/data/*.json` and `docs/live/data/*.json` |
| `init_state.py` | One-time: seed the 1-week backfill and initial state for both legs |
| `run_cycle.py` | Repeated: one live update cycle for both legs (called by the GH Action) |

## Running locally

```bash
pip install -r paper_trading/requirements.txt

# One-time setup (creates live/data/*.json + docs/live/data/*.json, backfills 7 days)
python paper_trading/init_state.py

# Simulate a live cycle (run this repeatedly / on a schedule)
python paper_trading/run_cycle.py
```

Then serve `docs/live/` locally to preview the dashboard:

```bash
cd docs/live && python3 -m http.server 8080
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

Delete `live/data/*.json` and `docs/live/data/*.json`, then re-run
`python paper_trading/init_state.py` to restart with a fresh $100,000
balance and a new 7-day backfill.

## Disclaimer

This is a **paper trading simulation** — no real money is traded, no broker
account is connected. It exists to observe how the statistically-validated
strategy behaves against live, streaming price action before any
consideration of real capital. Position sizing (4x scale) increases
drawdown proportionally to return -- reasonable for a standard account,
but would need adjustment (lower scale + kill-switches) for strict
funded-account daily-loss rules.
