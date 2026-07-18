"""
One-time initialization: seed the paper trading state by simulating the
2-leg portfolio strategy over the past week using real historical daily
bars, then hand off to run_cycle.py for ongoing live updates.

Run this once to (re)start the live paper trading demo from scratch.
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent))
sys.path.append(str(Path(__file__).parent.parent))

import pandas as pd
from datetime import datetime, timezone, timedelta

from engine import fetch_daily_history, fetch_recent_intraday, get_latest_signal, STARTING_BALANCE, PAIRS, LEG_BY_PAIR
from mcpt_strategy.strategies.mega_search_framework import enhanced_ict_scoring_v2
from portfolio import new_state, apply_daily_signal, mark_to_market
import state as st


BACKFILL_DAYS = 7


def run():
    print("Initializing live paper trading state (2-leg causal ICT portfolio)...")
    print(f"  Starting balance: ${STARTING_BALANCE:,.0f}")
    print(f"  Legs: {', '.join(LEG_BY_PAIR[p]['display'] for p in PAIRS)}")
    print(f"  Backfilling {BACKFILL_DAYS} days of history\n")

    daily_data = {pair: fetch_daily_history(pair, lookback_days=400) for pair in PAIRS}
    for pair, df in daily_data.items():
        print(f"  {pair}: fetched {len(df)} days, {df.index[0].date()} -> {df.index[-1].date()}")

    # Vectorized signal across the whole series once per leg -- exactly the
    # signal the validated backtest uses (already internally shift(1)'d).
    signals = {
        pair: enhanced_ict_scoring_v2(daily_data[pair], **LEG_BY_PAIR[pair]['params'])
        for pair in PAIRS
    }

    state = new_state()
    trades = []
    price_history = {pair: [] for pair in PAIRS}
    equity_curve = []

    # Use the shorter of the two legs' recent date ranges as the common
    # backfill calendar (they trade on slightly different market holidays).
    common_dates = daily_data[PAIRS[0]].index
    for pair in PAIRS[1:]:
        common_dates = common_dates.intersection(daily_data[pair].index)
    backfill_dates = common_dates[-BACKFILL_DAYS:]

    print(f"\nSimulating {len(backfill_dates)} days from {backfill_dates[0].date()}...")

    for date in backfill_dates:
        time_iso = pd.Timestamp(date).strftime('%Y-%m-%dT21:00:00Z')  # approx daily close time (UTC)
        prices_today = {}
        for pair in PAIRS:
            sig = float(signals[pair].loc[date]) if date in signals[pair].index else 0.0
            close_price = float(daily_data[pair].loc[date, 'Close'])
            prices_today[pair] = close_price
            state = apply_daily_signal(state, pair, sig, close_price, time_iso, trades)
            print(f"  {date.date()} {LEG_BY_PAIR[pair]['display']}: signal={sig:+.1f}, close={close_price:.5f}")

        state = mark_to_market(state, prices_today)
        for pair in PAIRS:
            state['meta']['last_daily_bar_processed'][pair] = date.strftime('%Y-%m-%d')

        equity_curve.append({'t': time_iso, 'equity': state['account']['equity']})
        print(f"    -> equity=${state['account']['equity']:,.2f}, "
              f"open_legs={sum(1 for p in state['open_positions'].values() if p)}/{len(PAIRS)}")

    # Seed price history with real intraday data for the backfill week (for the charts)
    print("\nFetching intraday price history for chart display...")
    latest_prices = {}
    latest_time_iso = None
    for pair in PAIRS:
        intraday = fetch_recent_intraday(pair, period='7d', interval='1h')
        for ts, row in intraday.iterrows():
            price_history[pair].append({
                't': ts.strftime('%Y-%m-%dT%H:%M:%SZ'),
                'o': round(float(row['Open']), 5),
                'h': round(float(row['High']), 5),
                'l': round(float(row['Low']), 5),
                'c': round(float(row['Close']), 5),
            })
        latest_prices[pair] = float(intraday['Close'].iloc[-1])
        latest_time_iso = intraday.index[-1].strftime('%Y-%m-%dT%H:%M:%SZ')
        print(f"  {pair}: loaded {len(price_history[pair])} intraday points")

    # Final mark-to-market against the very latest live prices
    state = mark_to_market(state, latest_prices)
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
    print(f"  Open Legs:        {sum(1 for p in state['open_positions'].values() if p)}/{len(PAIRS)}")
    print(f"  Data saved to:    docs/live/data/")


if __name__ == '__main__':
    run()
