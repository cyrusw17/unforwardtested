"""
Portfolio / position management for the live paper trader.
Pure functions operating on plain dicts (JSON-serializable state).
"""
from typing import Dict, List, Optional, Tuple
from engine import (
    calculate_position_size_lots, pnl_for_move, spread_slippage_cost,
    STARTING_BALANCE, LEVERAGE, PAIR_DISPLAY
)
from state import now_iso


def new_state() -> Dict:
    return {
        'meta': {
            'pair': PAIR_DISPLAY,
            'strategy': 'Enhanced ICT v2 (conviction-weighted position sizing)',
            'starting_balance': STARTING_BALANCE,
            'leverage': LEVERAGE,
            'start_time': now_iso(),
            'last_updated': now_iso(),
            'last_daily_bar_processed': None,
        },
        'account': {
            'balance': STARTING_BALANCE,
            'equity': STARTING_BALANCE,
            'unrealized_pnl': 0.0,
            'peak_equity': STARTING_BALANCE,
            'max_drawdown_pct': 0.0,
            'total_trades': 0,
            'wins': 0,
            'losses': 0,
            'win_rate': 0.0,
        },
        'open_position': None,
        'next_trade_id': 1,
    }


def close_position(state: Dict, exit_price: float, exit_time: str, reason: str, trades: List[Dict]) -> Dict:
    pos = state['open_position']
    if pos is None:
        return state

    direction = 1 if pos['direction'] == 'long' else -1
    gross_pnl = pnl_for_move(pos['entry_price'], exit_price, pos['size_lots'], direction)
    cost = spread_slippage_cost(pos['size_lots'])
    net_pnl = gross_pnl - cost

    state['account']['balance'] = round(state['account']['balance'] + net_pnl, 2)
    state['account']['total_trades'] += 1
    if net_pnl > 0:
        state['account']['wins'] += 1
    else:
        state['account']['losses'] += 1
    total = state['account']['total_trades']
    state['account']['win_rate'] = round(100.0 * state['account']['wins'] / total, 1) if total > 0 else 0.0

    trades.append({
        'id': pos['id'],
        'direction': pos['direction'],
        'entry_time': pos['entry_time'],
        'entry_price': pos['entry_price'],
        'exit_time': exit_time,
        'exit_price': exit_price,
        'size_lots': round(pos['size_lots'], 3),
        'signal_strength': pos['signal_strength'],
        'pnl': round(net_pnl, 2),
        'pnl_pct': round(100.0 * net_pnl / STARTING_BALANCE, 3),
        'reason': reason,
    })

    state['open_position'] = None
    return state


def open_position(state: Dict, direction: str, signal_strength: float, entry_price: float,
                   entry_time: str, stop_distance_pips: float) -> Dict:
    equity = state['account']['equity']
    size_lots = calculate_position_size_lots(equity, signal_strength, stop_distance_pips, entry_price)

    trade_id = state['next_trade_id']
    state['next_trade_id'] += 1

    state['open_position'] = {
        'id': trade_id,
        'direction': direction,
        'size_lots': round(size_lots, 3),
        'entry_price': entry_price,
        'entry_time': entry_time,
        'signal_strength': round(signal_strength, 3),
    }
    return state


def apply_daily_signal(state: Dict, signal_strength: float, price: float, time_iso: str,
                        stop_distance_pips: float, trades: List[Dict]) -> Dict:
    """
    Given the strategy's new target position (signal_strength: positive=long,
    negative=short, 0=flat), transition the open position accordingly,
    booking realized P&L on any close, matching the backtest's logic of
    re-evaluating direction+size once per daily bar close.
    """
    target_direction = 'long' if signal_strength > 0 else ('short' if signal_strength < 0 else None)
    pos = state['open_position']

    if pos is None:
        if target_direction is not None:
            state = open_position(state, target_direction, signal_strength, price, time_iso, stop_distance_pips)
        return state

    current_direction = pos['direction']

    if target_direction is None:
        # Signal went flat -> close
        state = close_position(state, price, time_iso, 'signal_flat', trades)
        return state

    if target_direction != current_direction:
        # Flip: close then reopen opposite direction (incurs real spread/slippage cost)
        state = close_position(state, price, time_iso, 'signal_flip', trades)
        state = open_position(state, target_direction, signal_strength, price, time_iso, stop_distance_pips)
        return state

    # Same direction: just re-size for the new day's conviction level.
    # Keep the original entry_price/entry_time so unrealized P&L accrues
    # correctly against the true average entry -- no new spread cost is
    # charged for a pure re-sizing (no round-trip actually occurs).
    equity = state['account']['equity']
    new_size = calculate_position_size_lots(equity, signal_strength, stop_distance_pips, price)
    pos['size_lots'] = round(new_size, 3)
    pos['signal_strength'] = round(signal_strength, 3)
    return state


def mark_to_market(state: Dict, current_price: float) -> Dict:
    pos = state['open_position']
    if pos is None:
        unrealized = 0.0
    else:
        direction = 1 if pos['direction'] == 'long' else -1
        unrealized = pnl_for_move(pos['entry_price'], current_price, pos['size_lots'], direction)

    equity = state['account']['balance'] + unrealized
    state['account']['unrealized_pnl'] = round(unrealized, 2)
    state['account']['equity'] = round(equity, 2)

    if equity > state['account']['peak_equity']:
        state['account']['peak_equity'] = round(equity, 2)

    peak = state['account']['peak_equity']
    dd_pct = ((equity - peak) / peak * 100) if peak > 0 else 0.0
    if dd_pct < state['account']['max_drawdown_pct']:
        state['account']['max_drawdown_pct'] = round(dd_pct, 3)

    return state
