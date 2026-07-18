"""
SMC Strategy - 3% Risk Per Trade Test
Test with higher risk on 2025+ data and check for margin call scenarios
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import json

from core.indicators import TechnicalIndicators


class OANDABroker:
    """Simulate OANDA trading with margin call tracking"""
    
    AVG_SPREAD_PIPS = 1.0
    SLIPPAGE_PIPS = 0.3
    PIP_VALUE_PER_LOT = 10.0
    
    # OANDA margin requirements
    MAX_LEVERAGE = 50.0  # 50:1 leverage
    MARGIN_CALL_LEVEL = 1.0  # 100% (when used margin = equity)
    CLOSEOUT_LEVEL = 0.5     # 50% (OANDA auto-closes at 50% margin level)
    
    def __init__(self, initial_capital: float = 1000.0, leverage: float = 50.0):
        self.initial_capital = initial_capital
        self.max_leverage = leverage
        self.equity = initial_capital
        self.balance = initial_capital
        self.total_spread_cost = 0.0
        self.total_slippage_cost = 0.0
        
        # Margin call tracking
        self.margin_calls = []
        self.closeouts = []
        self.max_leverage_used = 0.0
        
    def calculate_position_size(self, price: float, risk_pct: float = 0.03, 
                               stop_distance_pips: float = 10.0) -> float:
        """Calculate position size with 3% risk"""
        risk_amount = self.equity * risk_pct
        position_size_lots = risk_amount / (self.PIP_VALUE_PER_LOT * stop_distance_pips)
        
        # Check leverage limit
        max_position_value = self.equity * self.max_leverage
        max_position_lots = max_position_value / (100000 * price)
        
        position_size_lots = min(position_size_lots, max_position_lots)
        return max(position_size_lots, 0.001)
    
    def calculate_leverage_used(self, position_size_lots: float, price: float) -> float:
        """Calculate actual leverage being used"""
        position_value = position_size_lots * 100000 * price
        if self.equity <= 0:
            return 999.99  # Infinite leverage (bad)
        leverage_used = position_value / self.equity
        return leverage_used
    
    def check_margin_call(self, position_size_lots: float, price: float, 
                         current_time, equity_before_trade: float) -> dict:
        """Check if this trade would trigger margin call"""
        position_value = position_size_lots * 100000 * price
        required_margin = position_value / self.max_leverage
        leverage_used = self.calculate_leverage_used(position_size_lots, price)
        
        # Track max leverage
        self.max_leverage_used = max(self.max_leverage_used, leverage_used)
        
        margin_status = {
            'time': current_time,
            'equity': self.equity,
            'position_value': position_value,
            'required_margin': required_margin,
            'leverage_used': leverage_used,
            'margin_level': (self.equity / required_margin * 100) if required_margin > 0 else 999,
            'would_margin_call': False,
            'would_closeout': False
        }
        
        # Check for margin call (equity < required margin = 100% margin level)
        if self.equity < required_margin:
            margin_status['would_margin_call'] = True
            self.margin_calls.append(margin_status.copy())
        
        # Check for closeout (margin level < 50%)
        margin_level = (self.equity / required_margin * 100) if required_margin > 0 else 999
        if margin_level < 50:
            margin_status['would_closeout'] = True
            self.closeouts.append(margin_status.copy())
        
        return margin_status
    
    def calculate_spread_cost(self, position_size_lots: float) -> float:
        return self.AVG_SPREAD_PIPS * self.PIP_VALUE_PER_LOT * position_size_lots
    
    def calculate_slippage_cost(self, position_size_lots: float) -> float:
        return self.SLIPPAGE_PIPS * self.PIP_VALUE_PER_LOT * position_size_lots
    
    def execute_trade(self, entry_price: float, exit_price: float, 
                     position_size_lots: float, direction: int) -> float:
        if direction == 1:
            pip_movement = (exit_price - entry_price) * 10000
        else:
            pip_movement = (entry_price - exit_price) * 10000
        
        gross_pnl = pip_movement * self.PIP_VALUE_PER_LOT * position_size_lots
        spread_cost = self.calculate_spread_cost(position_size_lots)
        slippage_cost = self.calculate_slippage_cost(position_size_lots)
        net_pnl = gross_pnl - spread_cost - slippage_cost
        
        self.total_spread_cost += spread_cost
        self.total_slippage_cost += slippage_cost
        
        return net_pnl


def identify_order_blocks(ohlc: pd.DataFrame, lookback: int = 5):
    """Identify Smart Money order blocks"""
    bullish_ob = pd.Series(False, index=ohlc.index)
    bearish_ob = pd.Series(False, index=ohlc.index)
    
    close = ohlc['Close']
    open_price = ohlc['Open']
    
    body = abs(close - open_price)
    avg_body = body.rolling(20).mean()
    strong_bullish = (close > open_price) & (body > avg_body * 1.5)
    strong_bearish = (close < open_price) & (body > avg_body * 1.5)
    
    for i in range(lookback, len(ohlc)):
        if strong_bullish.iloc[i]:
            for j in range(1, min(lookback, i)):
                if close.iloc[i-j] < open_price.iloc[i-j]:
                    bullish_ob.iloc[i-j] = True
                    break
        
        if strong_bearish.iloc[i]:
            for j in range(1, min(lookback, i)):
                if close.iloc[i-j] > open_price.iloc[i-j]:
                    bearish_ob.iloc[i-j] = True
                    break
    
    return bullish_ob, bearish_ob


def identify_structure(ohlc: pd.DataFrame, swing_length: int = 5):
    """Identify market structure"""
    high = ohlc['High']
    low = ohlc['Low']
    close = ohlc['Close']
    
    structure = pd.Series(0, index=ohlc.index)
    recent_high = high.rolling(swing_length).max()
    recent_low = low.rolling(swing_length).min()
    
    structure[close > recent_high.shift(1)] = 1
    structure[close < recent_low.shift(1)] = -1
    
    return structure.ffill().fillna(0)


def smc_order_block_strategy(ohlc: pd.DataFrame, ob_lookback: int = 5, 
                             use_structure: bool = True) -> pd.Series:
    """SMC Order Block + Structure strategy"""
    bullish_ob, bearish_ob = identify_order_blocks(ohlc, ob_lookback)
    structure = identify_structure(ohlc) if use_structure else pd.Series(0, index=ohlc.index)
    
    signal = pd.Series(0, index=ohlc.index, dtype=float)
    signal[bullish_ob & (structure >= 0)] = 1
    signal[bearish_ob & (structure <= 0)] = -1
    
    return signal.shift(1).fillna(0)


def backtest_with_margin_tracking(
    ohlc: pd.DataFrame,
    initial_capital: float = 1000.0,
    leverage: float = 50.0,
    risk_per_trade: float = 0.03,  # 3% risk
    atr_sl_mult: float = 1.0,
    atr_tp_mult: float = 3.0
):
    """Backtest with margin call tracking"""
    print(f"\n{'='*80}")
    print(f"SMC STRATEGY - 3% RISK TEST WITH MARGIN TRACKING")
    print(f"{'='*80}")
    print(f"Initial Capital:      ${initial_capital:.2f}")
    print(f"Max Leverage:         {leverage}:1")
    print(f"Risk Per Trade:       {risk_per_trade*100:.1f}% ⚠️  (HIGH)")
    print(f"Period:               {ohlc.index[0]} to {ohlc.index[-1]}")
    print(f"Bars:                 {len(ohlc)}")
    print(f"{'='*80}\n")
    
    broker = OANDABroker(initial_capital, leverage)
    signal = smc_order_block_strategy(ohlc, ob_lookback=5, use_structure=True)
    
    ti = TechnicalIndicators
    atr = ti.atr(ohlc, 14)
    
    equity_curve = []
    trades = []
    margin_events = []
    
    position = 0
    position_size_lots = 0
    entry_price = 0
    entry_time = None
    stop_loss = 0
    take_profit = 0
    
    for i in range(len(ohlc)):
        current_price = ohlc['Close'].iloc[i]
        current_signal = signal.iloc[i]
        current_atr = atr.iloc[i]
        current_time = ohlc.index[i]
        
        if position != 0:
            exit_triggered = False
            exit_price = current_price
            exit_reason = ''
            
            if position == 1 and current_price <= stop_loss:
                exit_triggered = True
                exit_price = stop_loss
                exit_reason = 'STOP_LOSS'
            elif position == -1 and current_price >= stop_loss:
                exit_triggered = True
                exit_price = stop_loss
                exit_reason = 'STOP_LOSS'
            elif position == 1 and current_price >= take_profit:
                exit_triggered = True
                exit_price = take_profit
                exit_reason = 'TAKE_PROFIT'
            elif position == -1 and current_price <= take_profit:
                exit_triggered = True
                exit_price = take_profit
                exit_reason = 'TAKE_PROFIT'
            
            if exit_triggered:
                pnl = broker.execute_trade(entry_price, exit_price, 
                                          position_size_lots, position)
                broker.equity += pnl
                broker.balance += pnl
                
                trades.append({
                    'entry_time': entry_time,
                    'exit_time': current_time,
                    'direction': 'LONG' if position == 1 else 'SHORT',
                    'entry_price': entry_price,
                    'exit_price': exit_price,
                    'position_size_lots': position_size_lots,
                    'pnl': pnl,
                    'equity_after': broker.equity,
                    'exit_reason': exit_reason
                })
                
                position = 0
        
        equity_curve.append({
            'time': current_time,
            'equity': broker.equity,
            'balance': broker.balance,
            'position': position
        })
        
        if position == 0 and current_signal != 0 and not np.isnan(current_atr):
            stop_distance_pips = (current_atr * atr_sl_mult) * 10000
            equity_before = broker.equity
            position_size_lots = broker.calculate_position_size(
                current_price, risk_per_trade, stop_distance_pips
            )
            
            # Check margin BEFORE entering
            margin_check = broker.check_margin_call(position_size_lots, current_price,
                                                    current_time, equity_before)
            
            if margin_check['would_margin_call'] or margin_check['would_closeout']:
                margin_events.append(margin_check)
                print(f"\n⚠️  MARGIN WARNING at {current_time}")
                print(f"   Equity: ${broker.equity:.2f}")
                print(f"   Position Value: ${margin_check['position_value']:.2f}")
                print(f"   Leverage: {margin_check['leverage_used']:.2f}:1")
                print(f"   Margin Level: {margin_check['margin_level']:.1f}%")
                if margin_check['would_closeout']:
                    print(f"   ❌ WOULD BE CLOSED OUT (< 50%)")
                    continue  # Skip this trade
                elif margin_check['would_margin_call']:
                    print(f"   ⚠️  MARGIN CALL WARNING (< 100%)")
            
            entry_price = current_price
            entry_time = current_time
            
            if current_signal == 1:
                position = 1
                stop_loss = entry_price - (current_atr * atr_sl_mult)
                take_profit = entry_price + (current_atr * atr_tp_mult)
            else:
                position = -1
                stop_loss = entry_price + (current_atr * atr_sl_mult)
                take_profit = entry_price - (current_atr * atr_tp_mult)
    
    if position != 0:
        final_price = ohlc['Close'].iloc[-1]
        pnl = broker.execute_trade(entry_price, final_price, 
                                   position_size_lots, position)
        broker.equity += pnl
        broker.balance += pnl
        
        trades.append({
            'entry_time': entry_time,
            'exit_time': ohlc.index[-1],
            'direction': 'LONG' if position == 1 else 'SHORT',
            'entry_price': entry_price,
            'exit_price': final_price,
            'position_size_lots': position_size_lots,
            'pnl': pnl,
            'equity_after': broker.equity,
            'exit_reason': 'END_OF_DATA'
        })
    
    equity_df = pd.DataFrame(equity_curve)
    trades_df = pd.DataFrame(trades) if trades else pd.DataFrame()
    
    final_equity = broker.equity
    total_return = (final_equity - initial_capital) / initial_capital * 100
    duration_years = (ohlc.index[-1] - ohlc.index[0]).days / 365.25
    annual_return = ((final_equity / initial_capital) ** (1 / duration_years) - 1) * 100
    
    if len(trades) > 0:
        winning_trades = trades_df[trades_df['pnl'] > 0]
        losing_trades = trades_df[trades_df['pnl'] < 0]
        
        win_rate = len(winning_trades) / len(trades) * 100
        avg_win = winning_trades['pnl'].mean() if len(winning_trades) > 0 else 0
        avg_loss = losing_trades['pnl'].mean() if len(losing_trades) > 0 else 0
        
        total_wins = winning_trades['pnl'].sum() if len(winning_trades) > 0 else 0
        total_losses = abs(losing_trades['pnl'].sum()) if len(losing_trades) > 0 else 0
        profit_factor = total_wins / total_losses if total_losses > 0 else 0
        
        avg_trade = trades_df['pnl'].mean()
        best_trade = trades_df['pnl'].max()
        worst_trade = trades_df['pnl'].min()
    else:
        win_rate = avg_win = avg_loss = profit_factor = 0
        avg_trade = best_trade = worst_trade = 0
        total_wins = total_losses = 0
    
    equity_series = equity_df['equity']
    running_max = equity_series.cummax()
    drawdown = equity_series - running_max
    max_dd = drawdown.min()
    max_dd_pct = (max_dd / running_max[drawdown.idxmin()]) * 100 if len(drawdown) > 0 else 0
    
    # Print results
    print(f"\n{'='*80}")
    print(f"RESULTS - 3% RISK PER TRADE")
    print(f"{'='*80}")
    print(f"\n💰 Account Performance:")
    print(f"  Starting Capital:     ${initial_capital:.2f}")
    print(f"  Final Equity:         ${final_equity:.2f}")
    print(f"  Total Return:         {total_return:+.2f}%")
    print(f"  Annual Return:        {annual_return:+.2f}%")
    print(f"  Max Drawdown:         ${max_dd:.2f} ({max_dd_pct:.2f}%)")
    
    print(f"\n📊 Trading Stats:")
    print(f"  Total Trades:         {len(trades)}")
    print(f"  Win Rate:             {win_rate:.1f}%")
    print(f"  Profit Factor:        {profit_factor:.2f}")
    print(f"  Average Trade:        ${avg_trade:.2f}")
    
    print(f"\n⚠️  MARGIN ANALYSIS:")
    print(f"  Max Leverage Used:    {broker.max_leverage_used:.2f}:1")
    print(f"  Available Leverage:   {leverage}:1")
    print(f"  Margin Calls:         {len(broker.margin_calls)}")
    print(f"  Closeouts:            {len(broker.closeouts)}")
    
    if len(broker.margin_calls) > 0:
        print(f"\n  ⚠️  WARNING: {len(broker.margin_calls)} margin call events!")
        for i, mc in enumerate(broker.margin_calls[:3]):  # Show first 3
            print(f"     {i+1}. {mc['time']}: Margin Level {mc['margin_level']:.1f}%")
    
    if len(broker.closeouts) > 0:
        print(f"\n  ❌ CRITICAL: {len(broker.closeouts)} closeout events!")
        for i, co in enumerate(broker.closeouts[:3]):
            print(f"     {i+1}. {co['time']}: Would be closed out!")
    
    if len(broker.margin_calls) == 0 and len(broker.closeouts) == 0:
        print(f"  ✅ No margin issues detected!")
    
    print(f"\n{'='*80}")
    
    return {
        'initial_capital': initial_capital,
        'final_equity': float(final_equity),
        'total_return_pct': float(total_return),
        'annual_return_pct': float(annual_return),
        'max_drawdown_pct': float(max_dd_pct),
        'total_trades': len(trades),
        'win_rate': float(win_rate),
        'profit_factor': float(profit_factor),
        'max_leverage_used': float(broker.max_leverage_used),
        'margin_calls': len(broker.margin_calls),
        'closeouts': len(broker.closeouts),
        'margin_call_events': broker.margin_calls,
        'closeout_events': broker.closeouts,
        'trades': trades,
        'equity_curve': equity_curve
    }, equity_df, trades_df


def main():
    """Main test function"""
    cache_dir = Path(__file__).parent.parent / 'data' / 'forex_cache'
    cache_2026 = cache_dir / 'EURUSD_2026_current_4h.parquet'
    
    if not cache_2026.exists():
        print(f"Error: 2026 data not found: {cache_2026}")
        return None
    
    ohlc = pd.read_parquet(cache_2026)
    if 'open' in ohlc.columns:
        ohlc.columns = [c.capitalize() for c in ohlc.columns]
    
    print(f"\nLoaded {len(ohlc)} bars from {ohlc.index[0]} to {ohlc.index[-1]}")
    
    # Run backtest with 3% risk
    results, equity_df, trades_df = backtest_with_margin_tracking(
        ohlc,
        initial_capital=1000.0,
        leverage=50.0,
        risk_per_trade=0.03,  # 3% risk
        atr_sl_mult=1.0,
        atr_tp_mult=3.0
    )
    
    # Save results
    results_dir = Path(__file__).parent.parent / 'results'
    results_dir.mkdir(parents=True, exist_ok=True)
    
    summary = {k: v for k, v in results.items() 
              if k not in ['equity_curve', 'trades', 'margin_call_events', 'closeout_events']}
    
    with open(results_dir / 'smc_3pct_risk_summary.json', 'w') as f:
        json.dump(summary, f, indent=2)
    
    print(f"\n💾 Results saved to {results_dir}/smc_3pct_risk_summary.json")
    
    return results


if __name__ == '__main__':
    main()
