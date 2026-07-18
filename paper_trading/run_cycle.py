"""
Single execution cycle of the live paper trader.
Intended to be run repeatedly (e.g. hourly via GitHub Actions cron):
  1. Fetch latest intraday price -> append to price_history (for the chart)
  2. If a new daily bar has closed since last run, recompute the strategy
     signal and transition the open position accordingly (real trade)
  3. Mark the open position to market against the latest live price
  4. Persist updated state/trades/price_history/equity_curve JSON
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent))
sys.path.append(str(Path(__file__).parent.parent))

import pandas as pd
from datetime import datetime, timezone

from engine import fetch_daily_history, fetch_recent_intraday, compute_atr_pips, get_latest_signal
from portfolio import new_state, apply_daily_signal, mark_to_market
import state as st


MAX_PRICE_HISTORY_POINTS = 24 * 21  # ~3 weeks of hourly bars
MAX_EQUITY_POINTS = 24 * 21

# TRADING PAUSED: a lookahead bias was found in the Order Block indicator
# this strategy's validation relied on (see
# mcpt_strategy/LOOKAHEAD_BIAS_FINDING.md). Once fixed, the strategy no
# longer passes MCPT. Force flat (no new positions, close anything open)
# until a genuinely validated replacement signal is wired in here. Price
# history / chart / equity mark-to-market continue to update normally.
TRADING_PAUSED = True


def run():
    print(f"[{st.now_iso()}] Starting paper trader cycle...")

    state = st.load_state()
    if state is None:
        print("No existing state found -- run init_state.py first.")
        sys.exit(1)

    trades = st.load_trades()
    price_history = st.load_price_history()
    equity_curve = st.load_equity_curve()

    # --- 1. Fetch latest intraday price data ---
    intraday = fetch_recent_intraday(period='7d', interval='1h')
    latest_price = float(intraday['Close'].iloc[-1])
    latest_time = intraday.index[-1]
    latest_time_iso = latest_time.strftime('%Y-%m-%dT%H:%M:%SZ')
    print(f"  Latest price: {latest_price:.5f} @ {latest_time_iso}")

    # Append any new intraday points not already recorded
    existing_times = {p['t'] for p in price_history}
    new_points = 0
    for ts, row in intraday.iterrows():
        t_iso = ts.strftime('%Y-%m-%dT%H:%M:%SZ')
        if t_iso not in existing_times:
            price_history.append({
                't': t_iso,
                'o': round(float(row['Open']), 5),
                'h': round(float(row['High']), 5),
                'l': round(float(row['Low']), 5),
                'c': round(float(row['Close']), 5),
            })
            new_points += 1
    price_history = price_history[-MAX_PRICE_HISTORY_POINTS:]
    print(f"  Added {new_points} new price points (total: {len(price_history)})")

    # --- 2. Check for newly closed daily bar -> recompute strategy signal ---
    daily_df = fetch_daily_history(lookback_days=150)
    last_closed_date = daily_df.index[-1].strftime('%Y-%m-%d')
    last_processed = state['meta'].get('last_daily_bar_processed')

    if last_processed != last_closed_date:
        print(f"  New daily bar closed: {last_closed_date} (was: {last_processed}) -> recomputing signal")
        signal_strength, signal_date = get_latest_signal(daily_df)
        atr_pips = compute_atr_pips(daily_df)
        stop_distance = max(atr_pips * 1.5, 10.0)

        if TRADING_PAUSED:
            print(f"  TRADING PAUSED (strategy failed re-validation) -- forcing flat "
                  f"(raw signal would have been {signal_strength:+.3f})")
            signal_strength = 0.0
        else:
            print(f"  Signal strength for today: {signal_strength:+.3f} (ATR stop distance: {stop_distance:.1f} pips)")

        state = apply_daily_signal(
            state, signal_strength, latest_price, latest_time_iso, stop_distance, trades
        )
        state['meta']['last_daily_bar_processed'] = last_closed_date
    else:
        print(f"  No new daily bar since last run ({last_closed_date}) -- no new trade decision")

    # --- 3. Mark to market ---
    state = mark_to_market(state, latest_price)
    state['meta']['last_updated'] = st.now_iso()

    # Avoid bloating the equity curve with duplicate points when the market
    # is closed (weekends) and no new price data has arrived.
    last_equity_time = equity_curve[-1]['t'] if equity_curve else None
    if new_points > 0 or last_equity_time != latest_time_iso:
        equity_curve.append({'t': latest_time_iso, 'equity': state['account']['equity']})
    equity_curve = equity_curve[-MAX_EQUITY_POINTS:]

    # --- 4. Persist ---
    st.save_state(state)
    st.save_trades(trades)
    st.save_price_history(price_history)
    st.save_equity_curve(equity_curve)

    print(f"  Equity: ${state['account']['equity']:,.2f}  "
          f"Balance: ${state['account']['balance']:,.2f}  "
          f"Unrealized: ${state['account']['unrealized_pnl']:,.2f}  "
          f"Open trades: {1 if state['open_position'] else 0}  "
          f"Total trades: {state['account']['total_trades']}")
    print("Cycle complete.")


if __name__ == '__main__':
    run()
