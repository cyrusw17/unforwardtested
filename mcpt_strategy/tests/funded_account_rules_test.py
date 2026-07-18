"""
Funded Account Rules Compliance Test
Tests SMC strategy against strict funded account rules
Breaking ANY rule = account closure and total loss
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple
from datetime import datetime, timedelta

from core.indicators import TechnicalIndicators


class FundedAccountRules:
    """Strict funded account rules - breaking any = account loss"""
    
    def __init__(self, starting_balance: float = 249.03):
        self.starting_balance = starting_balance
        self.current_balance = starting_balance
        
        # RULES FROM IMAGE (typical prop firm rules)
        # These appear to be the rules based on the screenshot
        self.max_loss_pct = 0.10  # 10% max loss
        self.daily_loss_pct = 0.05  # 5% daily loss limit
        self.max_loss_dollars = starting_balance * self.max_loss_pct
        self.daily_loss_dollars = starting_balance * self.daily_loss_pct
        
        self.profit_target_pct = 0.10  # 10% profit target
        self.profit_target_dollars = starting_balance * self.profit_target_pct
        
        self.min_trading_days = 3  # Minimum trading days
        self.consistency_rule_pct = 0.50  # No single day > 50% of total profit
        
        # Tracking
        self.daily_pnl: Dict[str, float] = {}
        self.daily_trades: Dict[str, int] = {}
        self.peak_balance = starting_balance
        self.max_drawdown = 0
        self.trading_days = set()
        self.violations: List[str] = []
        self.account_blown = False
        self.violation_date = None
        
    def check_max_loss_rule(self, current_balance: float, date: str) -> bool:
        """Check if max loss exceeded"""
        total_loss = self.starting_balance - current_balance
        if total_loss > self.max_loss_dollars:
            self.violations.append(
                f"❌ MAX LOSS VIOLATED on {date}: "
                f"Loss ${total_loss:.2f} > Max ${self.max_loss_dollars:.2f}"
            )
            self.account_blown = True
            self.violation_date = date
            return False
        return True
    
    def check_daily_loss_rule(self, date: str) -> bool:
        """Check if daily loss limit exceeded"""
        if date in self.daily_pnl:
            daily_loss = -self.daily_pnl[date]  # Negative PnL = loss
            if daily_loss > self.daily_loss_dollars:
                self.violations.append(
                    f"❌ DAILY LOSS VIOLATED on {date}: "
                    f"Loss ${daily_loss:.2f} > Max ${self.daily_loss_dollars:.2f}"
                )
                self.account_blown = True
                self.violation_date = date
                return False
        return True
    
    def check_all_rules(self, current_balance: float, date: str) -> bool:
        """Check all rules - return False if any violated"""
        if self.account_blown:
            return False
        
        if not self.check_max_loss_rule(current_balance, date):
            return False
        
        if not self.check_daily_loss_rule(date):
            return False
        
        return True
    
    def update_daily_pnl(self, date: str, pnl: float):
        """Update daily PnL tracking"""
        if date not in self.daily_pnl:
            self.daily_pnl[date] = 0
            self.daily_trades[date] = 0
        self.daily_pnl[date] += pnl
        self.daily_trades[date] += 1
        if pnl != 0:
            self.trading_days.add(date)
    
    def check_min_trading_days(self) -> bool:
        """Check if minimum trading days met"""
        if len(self.trading_days) < self.min_trading_days:
            return False
        return True
    
    def check_consistency_rule(self) -> bool:
        """Check if any single day exceeded 50% of total profit"""
        total_profit = sum([pnl for pnl in self.daily_pnl.values() if pnl > 0])
        if total_profit <= 0:
            return True
        
        for date, pnl in self.daily_pnl.items():
            if pnl > 0 and pnl > (total_profit * self.consistency_rule_pct):
                self.violations.append(
                    f"⚠️  CONSISTENCY WARNING: {date} profit ${pnl:.2f} "
                    f"is {(pnl/total_profit)*100:.1f}% of total (max 50%)"
                )
                return False
        return True
    
    def get_summary(self) -> Dict:
        """Get compliance summary"""
        total_profit = self.current_balance - self.starting_balance
        return {
            'starting_balance': self.starting_balance,
            'final_balance': self.current_balance,
            'total_profit': total_profit,
            'total_profit_pct': (total_profit / self.starting_balance) * 100,
            'profit_target': self.profit_target_dollars,
            'profit_target_met': total_profit >= self.profit_target_dollars,
            'max_loss_limit': self.max_loss_dollars,
            'daily_loss_limit': self.daily_loss_dollars,
            'peak_balance': self.peak_balance,
            'max_drawdown': self.max_drawdown,
            'max_drawdown_pct': (self.max_drawdown / self.starting_balance) * 100,
            'trading_days': len(self.trading_days),
            'min_trading_days_met': self.check_min_trading_days(),
            'consistency_check': self.check_consistency_rule(),
            'account_blown': self.account_blown,
            'violation_date': self.violation_date,
            'violations': self.violations,
            'all_rules_passed': not self.account_blown and len(self.violations) == 0
        }


class OANDABroker:
    """Realistic OANDA broker model for forex"""
    
    def __init__(self, initial_capital: float = 1000, leverage: int = 50, 
                 risk_per_trade: float = 0.01):
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.leverage = leverage
        self.risk_per_trade = risk_per_trade
        
        # OANDA spreads (pips) for EURUSD
        self.spread_pips = 0.8
        
        # OANDA commission: $0 (spread only)
        self.commission_per_lot = 0
        
        # Slippage model
        self.slippage_pips = 0.2
        
    def calculate_position_size(self, stop_loss_pips: float, price: float) -> float:
        """Calculate position size based on risk per trade"""
        risk_amount = self.capital * self.risk_per_trade
        pip_value = 10  # For 1 standard lot EURUSD
        max_position_lots = (risk_amount / stop_loss_pips) / pip_value
        max_position_value = max_position_lots * 100000  # Standard lot size
        
        # Apply leverage constraint
        max_with_leverage = self.capital * self.leverage
        if max_position_value > max_with_leverage:
            max_position_value = max_with_leverage
        
        return max_position_value / price
    
    def apply_costs(self, entry_price: float, direction: int) -> float:
        """Apply spread + slippage"""
        total_cost_pips = self.spread_pips + self.slippage_pips
        pip_size = 0.0001
        cost = total_cost_pips * pip_size
        
        if direction > 0:  # Long
            return entry_price + cost
        else:  # Short
            return entry_price - cost


def identify_order_blocks(ohlc: pd.DataFrame, lookback: int = 5):
    """Identify order blocks"""
    bullish_ob = pd.Series(False, index=ohlc.index)
    bearish_ob = pd.Series(False, index=ohlc.index)
    
    close_price = ohlc['Close']
    open_price = ohlc['Open']
    
    body = abs(close_price - open_price)
    avg_body = body.rolling(20).mean()
    
    strong_bullish = (close_price > open_price) & (body > avg_body * 1.5)
    strong_bearish = (close_price < open_price) & (body > avg_body * 1.5)
    
    for i in range(lookback, len(ohlc)):
        if strong_bullish.iloc[i]:
            for j in range(1, min(lookback, i)):
                if close_price.iloc[i-j] < open_price.iloc[i-j]:
                    bullish_ob.iloc[i-j] = True
                    break
        
        if strong_bearish.iloc[i]:
            for j in range(1, min(lookback, i)):
                if close_price.iloc[i-j] > open_price.iloc[i-j]:
                    bearish_ob.iloc[i-j] = True
                    break
    
    return bullish_ob, bearish_ob


def identify_structure(ohlc: pd.DataFrame, swing_length: int = 5):
    """Identify market structure"""
    high = ohlc['High']
    low = ohlc['Low']
    
    rolling_high = high.rolling(swing_length).max()
    rolling_low = low.rolling(swing_length).min()
    
    structure = pd.Series(0, index=ohlc.index)
    structure[high > rolling_high.shift(1)] = 1
    structure[low < rolling_low.shift(1)] = -1
    
    return structure.ffill().fillna(0)


def smc_order_block_strategy(ohlc: pd.DataFrame, ob_lookback: int = 5, 
                              use_structure: bool = True) -> pd.Series:
    """SMC Order Block Strategy"""
    bullish_ob, bearish_ob = identify_order_blocks(ohlc, ob_lookback)
    structure = identify_structure(ohlc) if use_structure else 0
    
    signal = pd.Series(0, index=ohlc.index, dtype=float)
    signal[bullish_ob & (structure >= 0)] = 1
    signal[bearish_ob & (structure <= 0)] = -1
    
    return signal.shift(1).fillna(0)


def backtest_with_funded_rules(ohlc: pd.DataFrame, starting_balance: float = 249.03,
                                leverage: int = 50, risk_pct: float = 0.01):
    """Backtest SMC strategy with funded account rule tracking"""
    
    # Initialize
    broker = OANDABroker(starting_balance, leverage, risk_pct)
    rules = FundedAccountRules(starting_balance)
    
    # Generate signals
    signals = smc_order_block_strategy(ohlc, ob_lookback=5, use_structure=True)
    
    # Calculate ATR for stops/targets
    atr = TechnicalIndicators.atr(ohlc, 14)
    
    # Tracking
    position = 0
    entry_price = 0
    stop_loss = 0
    take_profit = 0
    position_size = 0
    
    trades = []
    equity_curve = []
    
    for i in range(1, len(ohlc)):
        current_date = ohlc.index[i].strftime('%Y-%m-%d')
        current_price = ohlc['Close'].iloc[i]
        current_atr = atr.iloc[i]
        
        # Check for exit
        if position != 0:
            pnl = 0
            exit_reason = None
            
            if position > 0:  # Long
                if current_price <= stop_loss:
                    pnl = (stop_loss - entry_price) * position_size
                    exit_reason = 'SL'
                elif current_price >= take_profit:
                    pnl = (take_profit - entry_price) * position_size
                    exit_reason = 'TP'
            else:  # Short
                if current_price >= stop_loss:
                    pnl = (entry_price - stop_loss) * position_size
                    exit_reason = 'SL'
                elif current_price <= take_profit:
                    pnl = (entry_price - take_profit) * position_size
                    exit_reason = 'TP'
            
            if exit_reason:
                # Update capital
                broker.capital += pnl
                rules.current_balance = broker.capital
                rules.peak_balance = max(rules.peak_balance, broker.capital)
                
                # Track drawdown
                drawdown = rules.peak_balance - broker.capital
                rules.max_drawdown = max(rules.max_drawdown, drawdown)
                
                # Update daily PnL
                rules.update_daily_pnl(current_date, pnl)
                
                # Check rules IMMEDIATELY after each trade
                if not rules.check_all_rules(broker.capital, current_date):
                    # RULE VIOLATED - STOP TRADING IMMEDIATELY
                    trades.append({
                        'exit_date': ohlc.index[i],
                        'exit_price': current_price,
                        'pnl': pnl,
                        'exit_reason': exit_reason,
                        'balance': broker.capital,
                        'rule_violation': True
                    })
                    equity_curve.append({
                        'date': ohlc.index[i],
                        'equity': broker.capital,
                        'account_blown': True
                    })
                    break
                
                trades.append({
                    'exit_date': ohlc.index[i],
                    'exit_price': current_price,
                    'pnl': pnl,
                    'exit_reason': exit_reason,
                    'balance': broker.capital,
                    'rule_violation': False
                })
                
                position = 0
                entry_price = 0
                stop_loss = 0
                take_profit = 0
                position_size = 0
        
        # Check for entry
        if position == 0 and signals.iloc[i] != 0:
            if pd.notna(current_atr) and current_atr > 0:
                direction = int(signals.iloc[i])
                
                # Calculate stop loss and take profit
                stop_pips = current_atr * 10000  # Convert to pips
                sl_distance = stop_pips * 0.0001
                tp_distance = sl_distance * 3
                
                if direction > 0:  # Long
                    entry_price = broker.apply_costs(current_price, direction)
                    stop_loss = entry_price - sl_distance
                    take_profit = entry_price + tp_distance
                else:  # Short
                    entry_price = broker.apply_costs(current_price, direction)
                    stop_loss = entry_price + sl_distance
                    take_profit = entry_price - tp_distance
                
                position_size = broker.calculate_position_size(stop_pips, current_price)
                position = direction
                
                trades.append({
                    'entry_date': ohlc.index[i],
                    'direction': 'LONG' if direction > 0 else 'SHORT',
                    'entry_price': entry_price,
                    'stop_loss': stop_loss,
                    'take_profit': take_profit,
                    'position_size': position_size,
                    'balance': broker.capital
                })
        
        equity_curve.append({
            'date': ohlc.index[i],
            'equity': broker.capital,
            'account_blown': rules.account_blown
        })
    
    return {
        'trades': pd.DataFrame(trades) if trades else pd.DataFrame(),
        'equity_curve': pd.DataFrame(equity_curve),
        'rules_summary': rules.get_summary(),
        'final_balance': broker.capital,
        'total_trades': len([t for t in trades if 'exit_date' in t])
    }


def main():
    """Run funded account rules test"""
    print("="*80)
    print("FUNDED ACCOUNT RULES COMPLIANCE TEST")
    print("="*80)
    print("\n⚠️  CRITICAL: Breaking ANY rule = Account Closed + Total Loss\n")
    
    # Load 2026 data
    cache_dir = Path(__file__).parent.parent / 'data' / 'forex_cache'
    cache_file = cache_dir / 'EURUSD_2026_current_4h.parquet'
    
    if not cache_file.exists():
        print(f"Error: Data not found: {cache_file}")
        return
    
    ohlc = pd.read_parquet(cache_file)
    if 'open' in ohlc.columns:
        ohlc.columns = [c.capitalize() for c in ohlc.columns]
    
    print(f"Data: EUR/USD 4H")
    print(f"Period: {ohlc.index[0]} to {ohlc.index[-1]}")
    print(f"Bars: {len(ohlc)}\n")
    
    # Test with funded account starting balance
    starting_balance = 249.03
    leverage = 50
    risk_pct = 0.01  # 1% risk per trade
    
    print(f"Account Settings:")
    print(f"  Starting Balance: ${starting_balance:.2f}")
    print(f"  Leverage: {leverage}:1")
    print(f"  Risk per Trade: {risk_pct*100}%")
    print(f"\nFunded Account Rules:")
    print(f"  ❌ Max Loss: ${starting_balance * 0.10:.2f} (10% of balance)")
    print(f"  ❌ Daily Loss: ${starting_balance * 0.05:.2f} (5% of balance)")
    print(f"  ✅ Profit Target: ${starting_balance * 0.10:.2f} (10% gain)")
    print(f"  ✅ Min Trading Days: 3")
    print(f"  ✅ Consistency: No day > 50% of total profit")
    print(f"\n{'='*80}\n")
    
    # Run backtest
    print("Running backtest with rule monitoring...\n")
    results = backtest_with_funded_rules(ohlc, starting_balance, leverage, risk_pct)
    
    # Display results
    rules = results['rules_summary']
    
    print("="*80)
    print("RESULTS")
    print("="*80)
    
    print(f"\n💰 Financial Performance:")
    print(f"  Starting Balance: ${rules['starting_balance']:.2f}")
    print(f"  Final Balance: ${rules['final_balance']:.2f}")
    print(f"  Total Profit: ${rules['total_profit']:.2f} ({rules['total_profit_pct']:.2f}%)")
    print(f"  Profit Target: ${rules['profit_target']:.2f}")
    print(f"  Target Met: {'✅ YES' if rules['profit_target_met'] else '❌ NO'}")
    
    print(f"\n📊 Risk Metrics:")
    print(f"  Peak Balance: ${rules['peak_balance']:.2f}")
    print(f"  Max Drawdown: ${rules['max_drawdown']:.2f} ({rules['max_drawdown_pct']:.2f}%)")
    print(f"  Max Loss Limit: ${rules['max_loss_limit']:.2f}")
    print(f"  Daily Loss Limit: ${rules['daily_loss_limit']:.2f}")
    
    print(f"\n📅 Trading Activity:")
    print(f"  Total Trades: {results['total_trades']}")
    print(f"  Trading Days: {rules['trading_days']}")
    print(f"  Min Days Required: 3")
    print(f"  Min Days Met: {'✅ YES' if rules['min_trading_days_met'] else '❌ NO'}")
    
    print(f"\n🎯 Rule Compliance:")
    print(f"  Max Loss Rule: {'✅ PASS' if not rules['account_blown'] else '❌ VIOLATED'}")
    print(f"  Daily Loss Rule: {'✅ PASS' if len([v for v in rules['violations'] if 'DAILY' in v]) == 0 else '❌ VIOLATED'}")
    print(f"  Consistency Rule: {'✅ PASS' if rules['consistency_check'] else '⚠️  WARNING'}")
    
    if rules['violations']:
        print(f"\n⚠️  VIOLATIONS DETECTED:")
        for violation in rules['violations']:
            print(f"  {violation}")
        if rules['account_blown']:
            print(f"\n💥 ACCOUNT BLOWN on {rules['violation_date']}")
            print(f"   All funds lost. Account closed.")
    
    print(f"\n{'='*80}")
    print(f"FINAL VERDICT")
    print(f"{'='*80}")
    
    if rules['account_blown']:
        print(f"\n❌ ACCOUNT FAILED")
        print(f"   Rule violation detected - account would be closed")
        print(f"   Total loss: ${starting_balance:.2f}")
    elif rules['all_rules_passed'] and rules['profit_target_met']:
        print(f"\n✅ ACCOUNT PASSED")
        print(f"   All rules followed")
        print(f"   Profit target achieved")
        print(f"   Account is compliant and profitable")
    elif rules['all_rules_passed']:
        print(f"\n⚠️  ACCOUNT SAFE BUT TARGET NOT MET")
        print(f"   All rules followed (no violations)")
        print(f"   Profit target not yet achieved")
        print(f"   Can continue trading")
    else:
        print(f"\n⚠️  WARNINGS DETECTED")
        print(f"   Account safe but has warnings")
        print(f"   Review violations above")
    
    print(f"\n{'='*80}\n")
    
    # Save results
    results_file = Path(__file__).parent.parent / 'results' / 'funded_account_test_results.json'
    import json
    with open(results_file, 'w') as f:
        json.dump({
            'starting_balance': starting_balance,
            'final_balance': rules['final_balance'],
            'total_profit': rules['total_profit'],
            'profit_pct': rules['total_profit_pct'],
            'account_blown': rules['account_blown'],
            'violation_date': rules['violation_date'],
            'violations': rules['violations'],
            'all_rules_passed': rules['all_rules_passed']
        }, f, indent=2)
    
    print(f"✅ Results saved to {results_file}")


if __name__ == '__main__':
    main()
