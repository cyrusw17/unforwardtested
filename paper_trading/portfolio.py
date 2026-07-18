"""
Portfolio / position management for the live paper trader.
Pure functions operating on plain dicts (JSON-serializable state).
Two independent legs (GBP/JPY, NZD/CAD) share one account balance/equity.
"""
from typing import Dict, List, Optional
from engine import (
    leg_notional_usd, pnl_for_move, spread_slippage_cost,
    STARTING_BALANCE, LEVERAGE, SCALE, LEGS, PAIRS, LEG_BY_PAIR
)
from state import now_iso


def new_state() -> Dict:
    return {
        'meta': {
            'pairs': PAIRS,
            'pair_display': {leg['pair']: leg['display'] for leg in LEGS},
            'strategy': 'Causal 2-Pair ICT Portfolio (GBP/JPY + NZD/CAD, no-lookahead, '
                        f'walk-forward MCPT p=0.019, {SCALE:.1f}x scaled)',
            'starting_balance': STARTING_BALANCE,
            'leverage': LEVERAGE,
            'scale': SCALE,
            'start_time': now_iso(),
            'last_updated': now_iso(),
            'last_daily_bar_processed': {pair: None for pair in PAIRS},
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
        'open_positions': {pair: None for pair in PAIRS},
        'next_trade_id': 1,
    }


def close_position(state: Dict, pair: str, exit_price: float, exit_time: str, reason: str,
                    trades: List[Dict]) -> Dict:
    pos = state['open_positions'].get(pair)
    if pos is None:
        return state

    direction = 1 if pos['direction'] == 'long' else -1
    gross_pnl = pnl_for_move(pos['entry_price'], exit_price, pos['notional_usd'], direction)
    cost = spread_slippage_cost(pair, pos['notional_usd'])
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
        'pair': pair,
        'display': LEG_BY_PAIR[pair]['display'],
        'direction': pos['direction'],
        'entry_time': pos['entry_time'],
        'entry_price': pos['entry_price'],
        'exit_time': exit_time,
        'exit_price': exit_price,
        'notional_usd': round(pos['notional_usd'], 2),
        'signal': pos['signal'],
        'pnl': round(net_pnl, 2),
        'pnl_pct': round(100.0 * net_pnl / STARTING_BALANCE, 3),
        'reason': reason,
    })

    state['open_positions'][pair] = None
    return state


def open_position(state: Dict, pair: str, direction: str, raw_signal: float, entry_price: float,
                   entry_time: str) -> Dict:
    equity = state['account']['equity']
    notional_usd = leg_notional_usd(equity, pair, raw_signal)

    trade_id = state['next_trade_id']
    state['next_trade_id'] += 1

    state['open_positions'][pair] = {
        'id': trade_id,
        'pair': pair,
        'direction': direction,
        'notional_usd': round(notional_usd, 2),
        'entry_price': entry_price,
        'entry_time': entry_time,
        'signal': round(raw_signal, 3),
    }
    return state


def apply_daily_signal(state: Dict, pair: str, raw_signal: float, price: float, time_iso: str,
                        trades: List[Dict]) -> Dict:
    """
    Given the strategy's new target position for `pair` (raw_signal: +1
    long, -1 short, 0 flat), transition that leg's open position
    accordingly, booking realized P&L on any close. Other legs/positions
    are untouched.
    """
    target_direction = 'long' if raw_signal > 0 else ('short' if raw_signal < 0 else None)
    pos = state['open_positions'].get(pair)

    if pos is None:
        if target_direction is not None:
            state = open_position(state, pair, target_direction, raw_signal, price, time_iso)
        return state

    current_direction = pos['direction']

    if target_direction is None:
        state = close_position(state, pair, price, time_iso, 'signal_flat', trades)
        return state

    if target_direction != current_direction:
        state = close_position(state, pair, price, time_iso, 'signal_flip', trades)
        state = open_position(state, pair, target_direction, raw_signal, price, time_iso)
        return state

    # Same direction: this strategy's signal is binary (+-1), so there is
    # nothing to re-size -- keep the existing position as-is (no new cost).
    return state


def mark_to_market(state: Dict, prices: Dict[str, float]) -> Dict:
    """`prices`: {pair: current_price} for every pair with data available."""
    total_unrealized = 0.0
    for pair in PAIRS:
        pos = state['open_positions'].get(pair)
        if pos is None or pair not in prices:
            continue
        direction = 1 if pos['direction'] == 'long' else -1
        total_unrealized += pnl_for_move(pos['entry_price'], prices[pair], pos['notional_usd'], direction)

    equity = state['account']['balance'] + total_unrealized
    state['account']['unrealized_pnl'] = round(total_unrealized, 2)
    state['account']['equity'] = round(equity, 2)

    if equity > state['account']['peak_equity']:
        state['account']['peak_equity'] = round(equity, 2)

    peak = state['account']['peak_equity']
    dd_pct = ((equity - peak) / peak * 100) if peak > 0 else 0.0
    if dd_pct < state['account']['max_drawdown_pct']:
        state['account']['max_drawdown_pct'] = round(dd_pct, 3)

    return state
