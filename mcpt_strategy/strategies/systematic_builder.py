"""
Systematic Strategy Builder
Goal: Find strategies that pass MCPT with 6%+ annual returns (target 15%)

Approach:
1. Test multiple strategy types
2. Optimize parameters on training data
3. Validate on out-of-sample with MCPT
4. Iterate until passing strategy is found
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))

import pandas as pd
import numpy as np
from typing import Dict, Tuple, List
from tqdm import tqdm
import json

from core.indicators import TechnicalIndicators
from mcpt_strategy.utils import get_permutation


class StrategyGenerator:
    """Generate and test various trading strategies"""
    
    @staticmethod
    def rsi_mean_reversion(
        ohlc: pd.DataFrame,
        rsi_period: int = 14,
        rsi_oversold: float = 30,
        rsi_overbought: float = 70,
        hold_bars: int = 5
    ) -> pd.Series:
        """
        RSI Mean Reversion: Buy oversold, sell overbought, hold for fixed period
        """
        ti = TechnicalIndicators
        rsi = ti.rsi(ohlc, rsi_period)
        
        signal = pd.Series(0, index=ohlc.index, dtype=float)
        
        # Entry signals
        buy_signal = rsi < rsi_oversold
        sell_signal = rsi > rsi_overbought
        
        # Hold for fixed bars after entry
        for i in range(len(ohlc)):
            if buy_signal.iloc[i]:
                signal.iloc[i:min(i+hold_bars, len(ohlc))] = 1
            elif sell_signal.iloc[i]:
                signal.iloc[i:min(i+hold_bars, len(ohlc))] = -1
        
        return signal.shift(1).fillna(0)
    
    @staticmethod
    def bollinger_breakout(
        ohlc: pd.DataFrame,
        bb_period: int = 20,
        bb_std: float = 2.0,
        min_atr: float = 0.0005
    ) -> pd.Series:
        """
        Bollinger Band Breakout: Enter on band touches with volatility filter
        """
        ti = TechnicalIndicators
        
        close = ohlc['Close']
        sma = ti.sma(ohlc, bb_period)
        std = close.rolling(bb_period).std()
        
        upper = sma + bb_std * std
        lower = sma - bb_std * std
        
        atr = ti.atr(ohlc, 14)
        vol_filter = atr > min_atr
        
        signal = pd.Series(0, index=ohlc.index, dtype=float)
        
        # Long on lower band touch
        signal[(close <= lower) & vol_filter] = 1
        # Short on upper band touch
        signal[(close >= upper) & vol_filter] = -1
        
        return signal.shift(1).fillna(0)
    
    @staticmethod
    def momentum_with_filters(
        ohlc: pd.DataFrame,
        fast_ma: int = 10,
        slow_ma: int = 30,
        rsi_period: int = 14,
        rsi_min: float = 45,
        rsi_max: float = 55,
        adx_period: int = 14,
        adx_min: float = 20
    ) -> pd.Series:
        """
        Momentum with multiple filters: MA cross + RSI + ADX
        """
        ti = TechnicalIndicators
        
        fast = ti.ema(ohlc, fast_ma)
        slow = ti.ema(ohlc, slow_ma)
        rsi = ti.rsi(ohlc, rsi_period)
        adx, plus_di, minus_di = ti.adx(ohlc, adx_period)
        
        # Trend direction
        uptrend = fast > slow
        downtrend = fast < slow
        
        # RSI filter (not extreme)
        rsi_neutral = (rsi > rsi_min) & (rsi < rsi_max)
        
        # ADX filter (trending)
        trending = adx > adx_min
        
        # DI filter
        di_long = plus_di > minus_di
        di_short = minus_di > plus_di
        
        signal = pd.Series(0, index=ohlc.index, dtype=float)
        signal[uptrend & rsi_neutral & trending & di_long] = 1
        signal[downtrend & rsi_neutral & trending & di_short] = -1
        
        return signal.shift(1).fillna(0)
    
    @staticmethod
    def volatility_channel_breakout(
        ohlc: pd.DataFrame,
        lookback: int = 20,
        atr_mult: float = 1.5,
        hold_bars: int = 10
    ) -> pd.Series:
        """
        Volatility Channel: Buy/sell on channel breakouts with ATR-based stops
        """
        ti = TechnicalIndicators
        
        close = ohlc['Close']
        atr = ti.atr(ohlc, 14)
        
        # Create channel
        mid = close.rolling(lookback).mean()
        upper = mid + atr_mult * atr
        lower = mid - atr_mult * atr
        
        signal = pd.Series(0, index=ohlc.index, dtype=float)
        
        # Breakout signals
        for i in range(lookback, len(ohlc)):
            if close.iloc[i] > upper.iloc[i-1]:
                signal.iloc[i:min(i+hold_bars, len(ohlc))] = 1
            elif close.iloc[i] < lower.iloc[i-1]:
                signal.iloc[i:min(i+hold_bars, len(ohlc))] = -1
        
        return signal.shift(1).fillna(0)
    
    @staticmethod
    def range_trading(
        ohlc: pd.DataFrame,
        lookback: int = 50,
        quantile_low: float = 0.2,
        quantile_high: float = 0.8,
        vol_lookback: int = 20
    ) -> pd.Series:
        """
        Range Trading: Buy at support, sell at resistance in low volatility
        """
        ti = TechnicalIndicators
        close = ohlc['Close']
        
        # Calculate support/resistance from rolling quantiles
        support = close.rolling(lookback).quantile(quantile_low)
        resistance = close.rolling(lookback).quantile(quantile_high)
        
        # Volatility filter (prefer ranging markets)
        returns_vol = close.pct_change().rolling(vol_lookback).std()
        low_vol = returns_vol < returns_vol.rolling(100).mean()
        
        signal = pd.Series(0, index=ohlc.index, dtype=float)
        
        # Buy near support in low vol
        signal[(close <= support * 1.001) & low_vol] = 1
        # Sell near resistance in low vol
        signal[(close >= resistance * 0.999) & low_vol] = -1
        
        return signal.shift(1).fillna(0)
    
    @staticmethod
    def macd_crossover(
        ohlc: pd.DataFrame,
        fast: int = 12,
        slow: int = 26,
        signal_period: int = 9,
        min_hist: float = 0.00001
    ) -> pd.Series:
        """
        MACD Crossover with histogram threshold
        """
        close = ohlc['Close']
        
        # Calculate MACD
        ema_fast = close.ewm(span=fast, adjust=False).mean()
        ema_slow = close.ewm(span=slow, adjust=False).mean()
        macd = ema_fast - ema_slow
        macd_signal = macd.ewm(span=signal_period, adjust=False).mean()
        histogram = macd - macd_signal
        
        signal = pd.Series(0, index=ohlc.index, dtype=float)
        
        # Buy on crossover above zero with positive histogram
        signal[(histogram > min_hist) & (histogram.shift(1) <= min_hist)] = 1
        # Sell on crossover below zero with negative histogram
        signal[(histogram < -min_hist) & (histogram.shift(1) >= -min_hist)] = -1
        
        return signal.shift(1).fillna(0)
    
    @staticmethod
    def keltner_channel(
        ohlc: pd.DataFrame,
        ema_period: int = 20,
        atr_period: int = 10,
        atr_mult: float = 2.0,
        hold_bars: int = 5
    ) -> pd.Series:
        """
        Keltner Channel breakout strategy
        """
        ti = TechnicalIndicators
        close = ohlc['Close']
        
        ema = close.ewm(span=ema_period, adjust=False).mean()
        atr = ti.atr(ohlc, atr_period)
        
        upper = ema + atr_mult * atr
        lower = ema - atr_mult * atr
        
        signal = pd.Series(0, index=ohlc.index, dtype=float)
        
        # Breakout signals with hold period
        for i in range(ema_period, len(ohlc)):
            if close.iloc[i] > upper.iloc[i]:
                signal.iloc[i:min(i+hold_bars, len(ohlc))] = 1
            elif close.iloc[i] < lower.iloc[i]:
                signal.iloc[i:min(i+hold_bars, len(ohlc))] = -1
        
        return signal.shift(1).fillna(0)
    
    @staticmethod
    def donchian_channel(
        ohlc: pd.DataFrame,
        period: int = 20,
        exit_period: int = 10
    ) -> pd.Series:
        """
        Donchian Channel breakout (Turtle Trading style)
        """
        high = ohlc['High']
        low = ohlc['Low']
        close = ohlc['Close']
        
        # Entry channels
        upper = high.rolling(period).max()
        lower = low.rolling(period).min()
        
        # Exit channels
        exit_upper = high.rolling(exit_period).max()
        exit_lower = low.rolling(exit_period).min()
        
        signal = pd.Series(0, index=ohlc.index, dtype=float)
        position = 0
        
        for i in range(period, len(ohlc)):
            # Entry logic
            if close.iloc[i] >= upper.iloc[i-1] and position <= 0:
                position = 1
            elif close.iloc[i] <= lower.iloc[i-1] and position >= 0:
                position = -1
            
            # Exit logic
            if position == 1 and close.iloc[i] <= exit_lower.iloc[i-1]:
                position = 0
            elif position == -1 and close.iloc[i] >= exit_upper.iloc[i-1]:
                position = 0
            
            signal.iloc[i] = position
        
        return signal.shift(1).fillna(0)
    
    @staticmethod
    def rsi_divergence(
        ohlc: pd.DataFrame,
        rsi_period: int = 14,
        divergence_lookback: int = 5,
        rsi_oversold: float = 30,
        rsi_overbought: float = 70
    ) -> pd.Series:
        """
        RSI divergence strategy
        """
        ti = TechnicalIndicators
        close = ohlc['Close']
        rsi = ti.rsi(ohlc, rsi_period)
        
        signal = pd.Series(0, index=ohlc.index, dtype=float)
        
        for i in range(divergence_lookback * 2, len(ohlc)):
            # Bullish divergence: price makes lower low, RSI makes higher low
            price_window = close.iloc[i-divergence_lookback:i+1]
            rsi_window = rsi.iloc[i-divergence_lookback:i+1]
            
            if (rsi.iloc[i] < rsi_oversold and
                price_window.iloc[-1] <= price_window.min() and
                rsi_window.iloc[-1] > rsi_window.min()):
                signal.iloc[i] = 1
            
            # Bearish divergence: price makes higher high, RSI makes lower high
            elif (rsi.iloc[i] > rsi_overbought and
                  price_window.iloc[-1] >= price_window.max() and
                  rsi_window.iloc[-1] < rsi_window.max()):
                signal.iloc[i] = -1
        
        return signal.shift(1).fillna(0)


def calculate_strategy_metrics(ohlc: pd.DataFrame, signal: pd.Series) -> Dict:
    """Calculate comprehensive strategy metrics"""
    returns = np.log(ohlc['Close']).diff().shift(-1)
    strategy_returns = signal * returns
    strategy_returns = strategy_returns.dropna()
    
    if len(strategy_returns) == 0 or len(strategy_returns[strategy_returns < 0]) == 0:
        return None
    
    # Basic metrics
    total_return = np.exp(strategy_returns.sum()) - 1
    
    # Annualize (assuming 4H bars, ~6 per day, ~252 trading days)
    years = len(ohlc) / (6 * 252)
    annual_return = (1 + total_return) ** (1/years) - 1 if years > 0 else 0
    
    # Profit factor
    winning = strategy_returns[strategy_returns > 0].sum()
    losing = strategy_returns[strategy_returns < 0].abs().sum()
    profit_factor = winning / losing if losing > 0 else 0
    
    # Sharpe (annualized)
    sharpe = strategy_returns.mean() / strategy_returns.std() * np.sqrt(252 * 6) if strategy_returns.std() > 0 else 0
    
    # Drawdown
    cum_returns = strategy_returns.cumsum()
    running_max = cum_returns.cummax()
    drawdown = cum_returns - running_max
    max_dd = drawdown.min()
    
    # Trade stats
    trades = (signal.diff() != 0).sum()
    win_rate = len(strategy_returns[strategy_returns > 0]) / len(strategy_returns) * 100
    
    return {
        'total_return': float(total_return),
        'annual_return': float(annual_return),
        'annual_return_pct': float(annual_return * 100),
        'profit_factor': float(profit_factor),
        'sharpe_ratio': float(sharpe),
        'max_drawdown': float(max_dd),
        'max_drawdown_pct': float(max_dd * 100),
        'win_rate': float(win_rate),
        'trades': int(trades),
        'years': float(years)
    }


def run_mcpt_test(
    ohlc: pd.DataFrame,
    strategy_func,
    strategy_params: Dict,
    n_permutations: int = 100
) -> Dict:
    """Run MCPT on a strategy"""
    
    # Generate signal
    signal = strategy_func(ohlc, **strategy_params)
    real_metrics = calculate_strategy_metrics(ohlc, signal)
    
    if real_metrics is None:
        return {'passed': False, 'error': 'No losing trades'}
    
    real_pf = real_metrics['profit_factor']
    
    # Run permutations
    perm_better_count = 1
    permuted_pfs = []
    
    for perm_i in range(1, n_permutations):
        try:
            # Convert to lowercase for permutation
            ohlc_lower = ohlc.copy()
            ohlc_lower.columns = [c.lower() for c in ohlc_lower.columns]
            
            perm_data = get_permutation(ohlc_lower, seed=perm_i * 100)
            
            # Convert back
            perm_data.columns = [c.capitalize() for c in perm_data.columns]
            
            perm_signal = strategy_func(perm_data, **strategy_params)
            perm_metrics = calculate_strategy_metrics(perm_data, perm_signal)
            
            if perm_metrics is None:
                perm_pf = 1.0
            else:
                perm_pf = perm_metrics['profit_factor']
            
            if perm_pf >= real_pf:
                perm_better_count += 1
            
            permuted_pfs.append(perm_pf)
        except:
            permuted_pfs.append(1.0)
    
    p_value = perm_better_count / n_permutations
    passed = p_value < 0.01
    
    return {
        'real_metrics': real_metrics,
        'mcpt': {
            'real_pf': float(real_pf),
            'p_value': float(p_value),
            'permuted_pfs_mean': float(np.mean(permuted_pfs)),
            'permuted_pfs_std': float(np.std(permuted_pfs)),
            'passed': passed
        }
    }


def optimize_strategy(
    ohlc: pd.DataFrame,
    strategy_func,
    param_grid: Dict[str, List],
    target_annual_return: float = 0.06
) -> Tuple[Dict, Dict]:
    """
    Optimize strategy parameters on training data
    Returns best params and their metrics
    """
    print(f"\n  Optimizing {strategy_func.__name__}...")
    print(f"  Testing {np.prod([len(v) for v in param_grid.values()])} combinations...")
    
    best_params = None
    best_metrics = None
    best_score = -np.inf
    
    # Generate all parameter combinations
    from itertools import product
    param_names = list(param_grid.keys())
    param_values = list(param_grid.values())
    
    for values in product(*param_values):
        params = dict(zip(param_names, values))
        
        try:
            signal = strategy_func(ohlc, **params)
            metrics = calculate_strategy_metrics(ohlc, signal)
            
            if metrics is None:
                continue
            
            # Score: prioritize profit factor and annual return, penalize drawdown
            score = (
                metrics['profit_factor'] * 2 +
                metrics['annual_return'] * 10 -
                abs(metrics['max_drawdown']) * 5
            )
            
            # Must meet minimum requirements (relaxed)
            if (metrics['annual_return'] >= target_annual_return * 0.3 and  # At least 30% of target in training
                metrics['profit_factor'] > 1.05 and
                metrics['trades'] > 30):
                
                if score > best_score:
                    best_score = score
                    best_params = params
                    best_metrics = metrics
        except:
            continue
    
    return best_params, best_metrics


def test_strategy_builder(pair: str = "EURUSD", target_annual: float = 0.06):
    """
    Main strategy building loop
    """
    print("="*80)
    print(f"SYSTEMATIC STRATEGY BUILDER")
    print(f"Target: {target_annual*100:.0f}% annual return with MCPT p < 0.01")
    print("="*80)
    
    # Load data
    cache_file = Path(__file__).parent.parent / 'data' / 'forex_cache' / f'{pair}_2016_2024_4h.parquet'
    
    if not cache_file.exists():
        print(f"Error: Data file not found: {cache_file}")
        return None
    
    ohlc = pd.read_parquet(cache_file)
    if 'open' in ohlc.columns:
        ohlc.columns = [c.capitalize() for c in ohlc.columns]
    
    print(f"\nData: {pair}, {len(ohlc)} bars ({ohlc.index[0]} to {ohlc.index[-1]})")
    
    # Split data: 70% train, 30% test
    split_idx = int(len(ohlc) * 0.7)
    train_data = ohlc[:split_idx]
    test_data = ohlc[split_idx:]
    
    print(f"Train: {len(train_data)} bars, Test: {len(test_data)} bars")
    
    # Define strategies to test
    strategies = [
        {
            'name': 'Donchian Channel',
            'func': StrategyGenerator.donchian_channel,
            'params': {
                'period': [15, 20, 25, 30],
                'exit_period': [5, 10, 15]
            }
        },
        {
            'name': 'MACD Crossover',
            'func': StrategyGenerator.macd_crossover,
            'params': {
                'fast': [8, 12, 16],
                'slow': [21, 26, 30],
                'signal_period': [7, 9, 11],
                'min_hist': [0.00001, 0.00005, 0.0001]
            }
        },
        {
            'name': 'Keltner Channel',
            'func': StrategyGenerator.keltner_channel,
            'params': {
                'ema_period': [15, 20, 25],
                'atr_period': [8, 10, 14],
                'atr_mult': [1.5, 2.0, 2.5],
                'hold_bars': [3, 5, 8]
            }
        },
        {
            'name': 'RSI Divergence',
            'func': StrategyGenerator.rsi_divergence,
            'params': {
                'rsi_period': [10, 14, 18],
                'divergence_lookback': [5, 7, 10],
                'rsi_oversold': [25, 30, 35],
                'rsi_overbought': [65, 70, 75]
            }
        },
        {
            'name': 'RSI Mean Reversion (Aggressive)',
            'func': StrategyGenerator.rsi_mean_reversion,
            'params': {
                'rsi_period': [10, 14, 18],
                'rsi_oversold': [15, 20, 25],
                'rsi_overbought': [75, 80, 85],
                'hold_bars': [2, 3, 5, 8]
            }
        },
        {
            'name': 'Momentum + Filters (Relaxed)',
            'func': StrategyGenerator.momentum_with_filters,
            'params': {
                'fast_ma': [6, 8, 10],
                'slow_ma': [20, 25, 30],
                'rsi_min': [35, 40, 45],
                'rsi_max': [55, 60, 65],
                'adx_min': [10, 15, 20]
            }
        }
    ]
    
    results = []
    
    for strategy in strategies:
        print(f"\n{'='*80}")
        print(f"Testing: {strategy['name']}")
        print(f"{'='*80}")
        
        # Optimize on training data
        best_params, train_metrics = optimize_strategy(
            train_data,
            strategy['func'],
            strategy['params'],
            target_annual
        )
        
        if best_params is None:
            print(f"  ❌ No viable parameters found")
            continue
        
        print(f"\n  ✓ Best params: {best_params}")
        print(f"  Train metrics:")
        print(f"    Annual Return: {train_metrics['annual_return_pct']:.2f}%")
        print(f"    Profit Factor: {train_metrics['profit_factor']:.3f}")
        print(f"    Sharpe: {train_metrics['sharpe_ratio']:.2f}")
        print(f"    Max DD: {train_metrics['max_drawdown_pct']:.2f}%")
        print(f"    Trades: {train_metrics['trades']}")
        
        # Test on out-of-sample with MCPT
        print(f"\n  Running MCPT on test data...")
        mcpt_result = run_mcpt_test(
            test_data,
            strategy['func'],
            best_params,
            n_permutations=100
        )
        
        test_metrics = mcpt_result['real_metrics']
        mcpt = mcpt_result['mcpt']
        
        print(f"\n  Test Performance:")
        print(f"    Annual Return: {test_metrics['annual_return_pct']:.2f}%")
        print(f"    Profit Factor: {test_metrics['profit_factor']:.3f}")
        print(f"    Sharpe: {test_metrics['sharpe_ratio']:.2f}")
        print(f"    Max DD: {test_metrics['max_drawdown_pct']:.2f}%")
        print(f"    Trades: {test_metrics['trades']}")
        
        print(f"\n  MCPT Results:")
        print(f"    Real PF: {mcpt['real_pf']:.3f}")
        print(f"    P-Value: {mcpt['p_value']:.4f}")
        print(f"    Status: {'✓ PASS' if mcpt['passed'] else '✗ FAIL'}")
        
        # Check if meets all criteria
        meets_return = test_metrics['annual_return_pct'] >= target_annual * 100
        meets_mcpt = mcpt['passed']
        
        result = {
            'strategy': strategy['name'],
            'params': best_params,
            'train_metrics': train_metrics,
            'test_metrics': test_metrics,
            'mcpt': mcpt,
            'meets_return_target': meets_return,
            'meets_mcpt': meets_mcpt,
            'success': meets_return and meets_mcpt
        }
        
        results.append(result)
        
        if result['success']:
            print(f"\n  🎉 SUCCESS! Strategy meets all criteria!")
            print(f"     ✓ Annual return: {test_metrics['annual_return_pct']:.2f}% (target: {target_annual*100:.0f}%)")
            print(f"     ✓ MCPT: p={mcpt['p_value']:.4f} < 0.01")
    
    # Summary
    print(f"\n{'='*80}")
    print(f"SUMMARY")
    print(f"{'='*80}")
    
    successful = [r for r in results if r['success']]
    
    if successful:
        print(f"\n🎉 Found {len(successful)} successful strategy(ies)!")
        for r in successful:
            print(f"\n  {r['strategy']}")
            print(f"    Params: {r['params']}")
            print(f"    Test Annual Return: {r['test_metrics']['annual_return_pct']:.2f}%")
            print(f"    Test PF: {r['test_metrics']['profit_factor']:.3f}")
            print(f"    MCPT p-value: {r['mcpt']['p_value']:.4f}")
    else:
        print(f"\n❌ No strategy passed all criteria")
        print(f"\nBest performers:")
        
        # Sort by combination of metrics
        results.sort(key=lambda x: (
            x['mcpt']['passed'],
            x['test_metrics']['annual_return_pct'],
            -x['mcpt']['p_value']
        ), reverse=True)
        
        for r in results[:3]:
            print(f"\n  {r['strategy']}")
            print(f"    Test Return: {r['test_metrics']['annual_return_pct']:.2f}% (target: {target_annual*100:.0f}%)")
            print(f"    MCPT: p={r['mcpt']['p_value']:.4f} ({'PASS' if r['mcpt']['passed'] else 'FAIL'})")
    
    # Save results
    results_dir = Path(__file__).parent.parent / 'results'
    results_dir.mkdir(parents=True, exist_ok=True)
    
    with open(results_dir / 'systematic_strategy_search.json', 'w') as f:
        json.dump({
            'pair': pair,
            'target_annual_return': target_annual,
            'successful_count': len(successful),
            'total_tested': len(results),
            'results': results
        }, f, indent=2)
    
    print(f"\n💾 Results saved to {results_dir}/systematic_strategy_search.json")
    
    return results


if __name__ == '__main__':
    results = test_strategy_builder(pair="EURUSD", target_annual=0.06)
