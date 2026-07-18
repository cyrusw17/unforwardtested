"""
One-time initialization: seed the paper trading state by simulating the
strategy over the past week using real historical daily bars, then hand
off to run_cycle.py for ongoing live updates.

Run this once to (re)start the live paper trading demo from scratch.
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent))
sys.path.append(str(Path(__file__).parent.parent))

import pandas as pd
from datetime import datetime, timezone, timedelta

from engine import (
    fetch_daily_history, fetch_recent_intraday, compute_atr_pips,
    STARTING_BALANCE
)
from mcpt_strategy.strategies.enhanced_ict_v3_adjusted import enhanced_ict_v3_adjusted
from portfolio import new_state, apply_daily_signal, mark_to_market
import state as st


BACKFILL_DAYS = 7


def run():
    print("Initializing live paper trading state...")
    print(f"  Starting balance: ${STARTING_BALANCE:,.0f}")
    print(f"  Backfilling {BACKFILL_DAYS} days of history\n")

    daily_df = fetch_daily_history(lookback_days=150)
    print(f"Fetched {len(daily_df)} days of history, {daily_df.index[0].date()} -> {daily_df.index[-1].date()}")

    # Compute the raw (unshifted-by-us; internally shifted-by-1) signal
    # across the whole series once, vectorized -- this is exactly the
    # signal the validated backtest uses.
    signal = enhanced_ict_v3_adjusted(daily_df)

    # Backfill window: last BACKFILL_DAYS closed daily bars
    backfill_start_idx = max(0, len(daily_df) - BACKFILL_DAYS)
    backfill_dates = daily_df.index[backfill_start_idx:]

    state = new_state()
    trades = []
    price_history = []
    equity_curve = []

    print(f"\nSimulating {len(backfill_dates)} days from {backfill_dates[0].date()}...")

    for date in backfill_dates:
        sig = float(signal.loc[date])
        close_price = float(daily_df.loc[date, 'Close'])
        time_iso = pd.Timestamp(date).strftime('%Y-%m-%dT21:00:00Z')  # approx daily close time (UTC)

        # ATR as of this date (use data up to and including this date)
        atr_pips = compute_atr_pips(daily_df.loc[:date])
        stop_distance = max(atr_pips * 1.5, 10.0)

        state = apply_daily_signal(state, sig, close_price, time_iso, stop_distance, trades)
        state = mark_to_market(state, close_price)
        state['meta']['last_daily_bar_processed'] = date.strftime('%Y-%m-%d')

        equity_curve.append({'t': time_iso, 'equity': state['account']['equity']})

        print(f"  {date.date()}: signal={sig:+.3f}, close={close_price:.5f}, "
              f"equity=${state['account']['equity']:,.2f}, "
              f"open_pos={'YES' if state['open_position'] else 'no'}")

    # Seed price history with real intraday data for the backfill week (for the chart)
    print("\nFetching intraday price history for chart display...")
    intraday = fetch_recent_intraday(period='7d', interval='1h')
    for ts, row in intraday.iterrows():
        price_history.append({
            't': ts.strftime('%Y-%m-%dT%H:%M:%SZ'),
            'o': round(float(row['Open']), 5),
            'h': round(float(row['High']), 5),
            'l': round(float(row['Low']), 5),
            'c': round(float(row['Close']), 5),
        })
    print(f"Loaded {len(price_history)} intraday price points")

    # Final mark-to-market against the very latest live price
    latest_price = float(intraday['Close'].iloc[-1])
    latest_time_iso = intraday.index[-1].strftime('%Y-%m-%dT%H:%M:%SZ')
    state = mark_to_market(state, latest_price)
    equity_curve.append({'t': latest_time_iso, 'equity': state['account']['equity']})

    state['meta']['start_time'] = backfill_dates[0].strftime('%Y-%m-%dT00:00:00Z')
    state['meta']['last_updated'] = st.now_iso()

    st.save_state(state)
    st.save_trades(trades)
    st.save_price_history(price_history)
    st.save_equity_curve(equity_curve)

    print(f"\n{'='*60}")
    print("INITIALIZATION COMPLETE")
    print(f"{'='*60}")
    print(f"  Starting Balance: ${STARTING_BALANCE:,.2f}")
    print(f"  Current Equity:   ${state['account']['equity']:,.2f}")
    print(f"  P&L:              ${state['account']['equity'] - STARTING_BALANCE:,.2f} "
          f"({(state['account']['equity']/STARTING_BALANCE - 1)*100:+.3f}%)")
    print(f"  Total Trades:     {state['account']['total_trades']}")
    print(f"  Open Position:    {state['open_position']}")
    print(f"  Data saved to:    docs/live/data/")


if __name__ == '__main__':
    run()
