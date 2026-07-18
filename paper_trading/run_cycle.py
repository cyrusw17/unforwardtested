"""
Single execution cycle of the live paper trader.
Intended to be run repeatedly (e.g. hourly via GitHub Actions cron), for
BOTH legs of the portfolio (GBP/JPY, NZD/CAD):
  1. Fetch latest intraday price -> append to price_history (for the chart)
  2. If a new daily bar has closed since last run, recompute the strategy
     signal and transition the open position accordingly (real trade)
  3. Mark all open positions to market against the latest live prices
  4. Persist updated state/trades/price_history/equity_curve JSON
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent))
sys.path.append(str(Path(__file__).parent.parent))

import pandas as pd
from datetime import datetime, timezone

from engine import fetch_daily_history, fetch_recent_intraday, get_latest_signal, PAIRS, LEG_BY_PAIR
from portfolio import new_state, apply_daily_signal, mark_to_market
import state as st


MAX_PRICE_HISTORY_POINTS = 24 * 21  # ~3 weeks of hourly bars
MAX_EQUITY_POINTS = 24 * 21


def run():
    print(f"[{st.now_iso()}] Starting paper trader cycle...")

    state = st.load_state()
    if state is None:
        print("No existing state found -- run init_state.py first.")
        sys.exit(1)

    trades = st.load_trades()
    price_history = st.load_price_history()
    equity_curve = st.load_equity_curve()

    latest_prices = {}
    latest_time_iso = None
    new_points_total = 0

    for pair in PAIRS:
        print(f"\n--- {LEG_BY_PAIR[pair]['display']} ({pair}) ---")

        # --- 1. Fetch latest intraday price data ---
        intraday = fetch_recent_intraday(pair, period='7d', interval='1h')
        latest_price = float(intraday['Close'].iloc[-1])
        latest_time = intraday.index[-1]
        t_iso = latest_time.strftime('%Y-%m-%dT%H:%M:%SZ')
        latest_prices[pair] = latest_price
        latest_time_iso = t_iso
        print(f"  Latest price: {latest_price:.5f} @ {t_iso}")

        series = price_history.get(pair, [])
        existing_times = {p['t'] for p in series}
        new_points = 0
        for ts, row in intraday.iterrows():
            ti = ts.strftime('%Y-%m-%dT%H:%M:%SZ')
            if ti not in existing_times:
                series.append({
                    't': ti,
                    'o': round(float(row['Open']), 5),
                    'h': round(float(row['High']), 5),
                    'l': round(float(row['Low']), 5),
                    'c': round(float(row['Close']), 5),
                })
                new_points += 1
        price_history[pair] = series[-MAX_PRICE_HISTORY_POINTS:]
        new_points_total += new_points
        print(f"  Added {new_points} new price points (total: {len(price_history[pair])})")

        # --- 2. Check for newly closed daily bar -> recompute strategy signal ---
        daily_df = fetch_daily_history(pair, lookback_days=400)
        last_closed_date = daily_df.index[-1].strftime('%Y-%m-%d')
        last_processed = state['meta']['last_daily_bar_processed'].get(pair)

        if last_processed != last_closed_date:
            print(f"  New daily bar closed: {last_closed_date} (was: {last_processed}) -> recomputing signal")
            raw_signal = get_latest_signal(pair, daily_df)
            print(f"  Raw signal for today: {raw_signal:+.1f}")
            state = apply_daily_signal(state, pair, raw_signal, latest_price, t_iso, trades)
            state['meta']['last_daily_bar_processed'][pair] = last_closed_date
        else:
            print(f"  No new daily bar since last run ({last_closed_date}) -- no new trade decision")

    # --- 3. Mark all legs to market ---
    state = mark_to_market(state, latest_prices)
    state['meta']['last_updated'] = st.now_iso()

    last_equity_time = equity_curve[-1]['t'] if equity_curve else None
    if new_points_total > 0 or last_equity_time != latest_time_iso:
        equity_curve.append({'t': latest_time_iso, 'equity': state['account']['equity']})
    equity_curve = equity_curve[-MAX_EQUITY_POINTS:]

    # --- 4. Persist ---
    st.save_state(state)
    st.save_trades(trades)
    st.save_price_history(price_history)
    st.save_equity_curve(equity_curve)

    open_count = sum(1 for p in state['open_positions'].values() if p is not None)
    print(f"\nEquity: ${state['account']['equity']:,.2f}  "
          f"Balance: ${state['account']['balance']:,.2f}  "
          f"Unrealized: ${state['account']['unrealized_pnl']:,.2f}  "
          f"Open legs: {open_count}/{len(PAIRS)}  "
          f"Total trades: {state['account']['total_trades']}")
    print("Cycle complete.")


if __name__ == '__main__':
    run()
