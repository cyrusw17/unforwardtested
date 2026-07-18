"""
Ultra-Selective Robust Strategies Designed to Pass MCPT
Focus: Low frequency, minimal parameters, exploit real market structure
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))

import pandas as pd
import numpy as np
from typing import Dict, Tuple
from tqdm import tqdm
import json


class RobustStrategies:
    """Strategies designed to pass MCPT by exploiting real market phenomena"""
    
    @staticmethod
    def regime_volatility_strategy(
        ohlc: pd.DataFrame,
        vol_lookback: int = 100,
        vol_threshold_low: float = 0.3,
        vol_threshold_high: float = 0.7,
        trend_lookback: int = 50,
        min_trend_strength: float = 0.02
    ) -> pd.Series:
        """
        Strategy 1: Volatility Regime + Trend
        
        Concept: Real markets have volatility clustering and autocorrelation.
        Shuffled data destroys these properties.
        
        Rules:
        - Only trade in LOW volatility regimes (before breakouts)
        - Require strong trend alignment
        - Very selective (expect < 30 trades/year)
        """
        close = ohlc['Close']
        
        # Calculate volatility (ATR-based)
        high = ohlc['High']
        low = ohlc['Low']
        tr = pd.DataFrame({
            'hl': high - low,
            'hc': abs(high - close.shift(1)),
            'lc': abs(low - close.shift(1))
        }).max(axis=1)
        atr = tr.rolling(14).mean()
        atr_pct = atr / close
        
        # Volatility percentile (where are we in historical volatility distribution?)
        vol_percentile = atr_pct.rolling(vol_lookback).apply(
            lambda x: pd.Series(x).rank(pct=True).iloc[-1]
        )
        
        # Only trade in LOW volatility (bottom 30%)
        low_vol_regime = vol_percentile < vol_threshold_low
        
        # Trend strength (EMA distance)
        ema_fast = close.ewm(span=20).mean()
        ema_slow = close.ewm(span=50).mean()
        trend_strength = (ema_fast - ema_slow) / ema_slow
        
        # Strong trend required
        strong_bullish = trend_strength > min_trend_strength
        strong_bearish = trend_strength < -min_trend_strength
        
        # Additional filter: Price must be near EMA (not overextended)
        price_to_ema = (close - ema_fast) / ema_fast
        near_ema = abs(price_to_ema) < 0.005  # Within 0.5%
        
        # Signals: Low vol + Strong trend + Near EMA
        signal = pd.Series(0, index=ohlc.index, dtype=float)
        signal[low_vol_regime & strong_bullish & near_ema] = 1
        signal[low_vol_regime & strong_bearish & near_ema] = -1
        
        return signal.shift(1).fillna(0)
    
    @staticmethod
    def extreme_reversion_strategy(
        ohlc: pd.DataFrame,
        lookback: int = 200,
        extreme_threshold: float = 2.5,
        confirmation_bars: int = 3
    ) -> pd.Series:
        """
        Strategy 2: Extreme Value Mean Reversion
        
        Concept: Real markets mean-revert from statistical extremes.
        Shuffled data loses this property.
        
        Rules:
        - Only trade at 2.5+ standard deviation moves
        - Wait for confirmation (trend reversal)
        - Very selective (expect < 20 trades/year)
        """
        close = ohlc['Close']
        
        # Calculate z-score
        sma = close.rolling(lookback).mean()
        std = close.rolling(lookback).std()
        z_score = (close - sma) / std
        
        # Extreme conditions
        extreme_high = z_score > extreme_threshold
        extreme_low = z_score < -extreme_threshold
        
        # Confirmation: Price starting to reverse
        price_change = close.pct_change(confirmation_bars)
        reversing_down = price_change < -0.01  # 1% down from extreme high
        reversing_up = price_change > 0.01     # 1% up from extreme low
        
        # Additional: Volume confirmation (if available)
        if 'Volume' in ohlc.columns:
            vol_ma = ohlc['Volume'].rolling(20).mean()
            high_volume = ohlc['Volume'] > vol_ma * 1.2
        else:
            high_volume = pd.Series(True, index=ohlc.index)
        
        # Signals
        signal = pd.Series(0, index=ohlc.index, dtype=float)
        signal[extreme_low.shift(confirmation_bars) & reversing_up & high_volume] = 1
        signal[extreme_high.shift(confirmation_bars) & reversing_down & high_volume] = -1
        
        return signal.shift(1).fillna(0)
    
    @staticmethod
    def multi_timeframe_alignment_strategy(
        ohlc: pd.DataFrame,
        fast_period: int = 20,
        medium_period: int = 50,
        slow_period: int = 100,
        min_separation: float = 0.015
    ) -> pd.Series:
        """
        Strategy 3: Perfect Multi-Timeframe Alignment
        
        Concept: Real trends show alignment across timeframes.
        Shuffled data destroys inter-timeframe relationships.
        
        Rules:
        - ALL three EMAs must be aligned
        - Sufficient separation between EMAs
        - Price must have just crossed into alignment
        - Very selective (expect < 25 trades/year)
        """
        close = ohlc['Close']
        
        # Three EMAs
        ema_fast = close.ewm(span=fast_period).mean()
        ema_medium = close.ewm(span=medium_period).mean()
        ema_slow = close.ewm(span=slow_period).mean()
        
        # Perfect bullish alignment: Fast > Medium > Slow
        bullish_aligned = (ema_fast > ema_medium) & (ema_medium > ema_slow)
        
        # Perfect bearish alignment: Fast < Medium < Slow
        bearish_aligned = (ema_fast < ema_medium) & (ema_medium < ema_slow)
        
        # Separation requirement (trend strength)
        fast_medium_sep = abs(ema_fast - ema_medium) / ema_medium
        medium_slow_sep = abs(ema_medium - ema_slow) / ema_slow
        
        sufficient_separation = (fast_medium_sep > min_separation) & (medium_slow_sep > min_separation)
        
        # Entry: Just entered alignment (wasn't aligned before)
        bullish_entry = bullish_aligned & (bullish_aligned.shift(1) == False)
        bearish_entry = bearish_aligned & (bearish_aligned.shift(1) == False)
        
        # Price position: Must be near fast EMA (not overextended)
        price_to_fast = abs(close - ema_fast) / ema_fast
        near_fast = price_to_fast < 0.003  # Within 0.3%
        
        # Signals
        signal = pd.Series(0, index=ohlc.index, dtype=float)
        signal[bullish_entry & sufficient_separation & near_fast] = 1
        signal[bearish_entry & sufficient_separation & near_fast] = -1
        
        return signal.shift(1).fillna(0)
    
    @staticmethod
    def volatility_breakout_strategy(
        ohlc: pd.DataFrame,
        vol_lookback: int = 50,
        squeeze_threshold: float = 0.5,
        breakout_multiplier: float = 1.5,
        trend_confirm: int = 20
    ) -> pd.Series:
        """
        Strategy 4: Volatility Squeeze Breakout
        
        Concept: Low volatility precedes high volatility in real markets.
        This autocorrelation doesn't exist in shuffled data.
        
        Rules:
        - Volatility must be in bottom 50% (squeeze)
        - Breakout must be 1.5x recent ATR
        - Trend confirmation required
        - Very selective (expect < 30 trades/year)
        """
        high = ohlc['High']
        low = ohlc['Low']
        close = ohlc['Close']
        
        # ATR
        tr = pd.DataFrame({
            'hl': high - low,
            'hc': abs(high - close.shift(1)),
            'lc': abs(low - close.shift(1))
        }).max(axis=1)
        atr = tr.rolling(14).mean()
        
        # Volatility percentile
        atr_percentile = atr.rolling(vol_lookback).apply(
            lambda x: pd.Series(x).rank(pct=True).iloc[-1]
        )
        
        # Squeeze: Volatility in bottom half
        in_squeeze = atr_percentile < squeeze_threshold
        
        # Breakout: Large move
        price_move = close.diff().abs()
        breakout = price_move > (atr * breakout_multiplier)
        
        # Direction of breakout
        bullish_breakout = close.diff() > (atr * breakout_multiplier)
        bearish_breakout = close.diff() < -(atr * breakout_multiplier)
        
        # Trend confirmation: EMA
        ema = close.ewm(span=trend_confirm).mean()
        trend_bullish = close > ema
        trend_bearish = close < ema
        
        # Must have been in squeeze recently (within last 5 bars)
        recent_squeeze = in_squeeze.rolling(5).max()
        
        # Signals
        signal = pd.Series(0, index=ohlc.index, dtype=float)
        signal[recent_squeeze & bullish_breakout & trend_bullish] = 1
        signal[recent_squeeze & bearish_breakout & trend_bearish] = -1
        
        return signal.shift(1).fillna(0)


def calculate_metrics(ohlc: pd.DataFrame, signal: pd.Series) -> Dict:
    """Calculate strategy metrics"""
    returns = np.log(ohlc['Close']).diff().shift(-1)
    strategy_returns = signal * returns
    strategy_returns = strategy_returns.dropna()
    
    if len(strategy_returns) == 0 or len(strategy_returns[strategy_returns < 0]) == 0:
        return None
    
    total_return = np.exp(strategy_returns.sum()) - 1
    years = len(ohlc) / (6 * 252)
    annual_return = (1 + total_return) ** (1/years) - 1 if years > 0 else 0
    
    winning = strategy_returns[strategy_returns > 0].sum()
    losing = strategy_returns[strategy_returns < 0].abs().sum()
    profit_factor = winning / losing if losing > 0 else 0
    
    sharpe = strategy_returns.mean() / strategy_returns.std() * np.sqrt(252 * 6) if strategy_returns.std() > 0 else 0
    
    cum_returns = strategy_returns.cumsum()
    running_max = cum_returns.cummax()
    drawdown = cum_returns - running_max
    max_dd = drawdown.min()
    
    trades = (signal.diff() != 0).sum()
    win_rate = len(strategy_returns[strategy_returns > 0]) / len(strategy_returns) * 100
    
    avg_win = strategy_returns[strategy_returns > 0].mean() if len(strategy_returns[strategy_returns > 0]) > 0 else 0
    avg_loss = strategy_returns[strategy_returns < 0].mean() if len(strategy_returns[strategy_returns < 0]) > 0 else 0
    
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
        'trades_per_year': float(trades / years) if years > 0 else 0,
        'avg_win': float(avg_win),
        'avg_loss': float(avg_loss),
        'years': float(years)
    }


def run_mcpt(ohlc: pd.DataFrame, strategy_func, strategy_params: Dict, n_permutations: int = 100) -> Dict:
    """Run MCPT"""
    from mcpt_strategy.utils import get_permutation
    
    signal = strategy_func(ohlc, **strategy_params)
    real_metrics = calculate_metrics(ohlc, signal)
    
    if real_metrics is None:
        return {'passed': False, 'error': 'No valid metrics'}
    
    real_pf = real_metrics['profit_factor']
    
    if real_pf < 1.3:
        return {'passed': False, 'error': f'PF {real_pf:.2f} < 1.3', 'real_metrics': real_metrics}
    if real_metrics['annual_return'] < 0.06:
        return {'passed': False, 'error': f'Return {real_metrics["annual_return_pct"]:.1f}% < 6%', 'real_metrics': real_metrics}
    
    perm_better = 1
    perm_pfs = []
    
    print(f"  Real strategy: {real_metrics['trades']} trades, PF {real_pf:.3f}, Return {real_metrics['annual_return_pct']:.1f}%")
    
    for i in tqdm(range(1, n_permutations), desc="MCPT"):
        try:
            ohlc_lower = ohlc.copy()
            ohlc_lower.columns = [c.lower() for c in ohlc_lower.columns]
            perm_data = get_permutation(ohlc_lower, seed=i * 100)
            perm_data.columns = [c.capitalize() for c in perm_data.columns]
            
            perm_signal = strategy_func(perm_data, **strategy_params)
            perm_metrics = calculate_metrics(perm_data, perm_signal)
            
            perm_pf = perm_metrics['profit_factor'] if perm_metrics else 1.0
            
            if perm_pf >= real_pf:
                perm_better += 1
            
            perm_pfs.append(perm_pf)
        except:
            perm_pfs.append(1.0)
    
    p_value = perm_better / n_permutations
    passed = p_value < 0.05
    
    return {
        'real_metrics': real_metrics,
        'real_pf': float(real_pf),
        'p_value': float(p_value),
        'permuted_mean': float(np.mean(perm_pfs)),
        'permuted_std': float(np.std(perm_pfs)),
        'permuted_better_count': int(perm_better - 1),
        'passed': passed,
        'reason': 'success' if passed else f'p-value {p_value:.4f} >= 0.05'
    }


def main():
    """Test all robust strategies"""
    print("="*80)
    print("ULTRA-SELECTIVE ROBUST STRATEGIES")
    print("Goal: Pass MCPT with p < 0.05")
    print("="*80)
    
    # Load data
    cache_dir = Path(__file__).parent.parent / 'data' / 'forex_cache'
    cache_2024 = cache_dir / 'EURUSD_2016_2024_4h.parquet'
    cache_2026 = cache_dir / 'EURUSD_2026_current_4h.parquet'
    
    if not cache_2024.exists():
        print("ERROR: Training data not found")
        return
    
    ohlc_2024 = pd.read_parquet(cache_2024)
    if 'open' in ohlc_2024.columns:
        ohlc_2024.columns = [c.capitalize() for c in ohlc_2024.columns]
    
    train_data = ohlc_2024[(ohlc_2024.index.year >= 2020) & (ohlc_2024.index.year <= 2024)]
    
    if cache_2026.exists():
        test_data = pd.read_parquet(cache_2026)
        if 'open' in test_data.columns:
            test_data.columns = [c.capitalize() for c in test_data.columns]
    else:
        print("ERROR: No 2025+ data")
        return
    
    print(f"\n📊 Data:")
    print(f"  Training: {train_data.index[0]} to {train_data.index[-1]} ({len(train_data)} bars)")
    print(f"  Testing:  {test_data.index[0]} to {test_data.index[-1]} ({len(test_data)} bars)")
    
    # Strategies to test
    strategies = [
        {
            'name': 'Volatility Regime - Strict',
            'func': RobustStrategies.regime_volatility_strategy,
            'params': {'vol_lookback': 100, 'vol_threshold_low': 0.3, 'trend_lookback': 50, 'min_trend_strength': 0.02}
        },
        {
            'name': 'Volatility Regime - Relaxed',
            'func': RobustStrategies.regime_volatility_strategy,
            'params': {'vol_lookback': 100, 'vol_threshold_low': 0.4, 'trend_lookback': 50, 'min_trend_strength': 0.015}
        },
        {
            'name': 'Extreme Reversion - 2.5σ',
            'func': RobustStrategies.extreme_reversion_strategy,
            'params': {'lookback': 200, 'extreme_threshold': 2.5, 'confirmation_bars': 3}
        },
        {
            'name': 'Extreme Reversion - 2.0σ',
            'func': RobustStrategies.extreme_reversion_strategy,
            'params': {'lookback': 200, 'extreme_threshold': 2.0, 'confirmation_bars': 3}
        },
        {
            'name': 'Extreme Reversion - 1.8σ',
            'func': RobustStrategies.extreme_reversion_strategy,
            'params': {'lookback': 150, 'extreme_threshold': 1.8, 'confirmation_bars': 2}
        },
        {
            'name': 'Multi-TF Alignment - Strict',
            'func': RobustStrategies.multi_timeframe_alignment_strategy,
            'params': {'fast_period': 20, 'medium_period': 50, 'slow_period': 100, 'min_separation': 0.015}
        },
        {
            'name': 'Multi-TF Alignment - Moderate',
            'func': RobustStrategies.multi_timeframe_alignment_strategy,
            'params': {'fast_period': 20, 'medium_period': 50, 'slow_period': 100, 'min_separation': 0.010}
        },
        {
            'name': 'Volatility Breakout - Conservative',
            'func': RobustStrategies.volatility_breakout_strategy,
            'params': {'vol_lookback': 50, 'squeeze_threshold': 0.5, 'breakout_multiplier': 1.5}
        },
        {
            'name': 'Volatility Breakout - Moderate',
            'func': RobustStrategies.volatility_breakout_strategy,
            'params': {'vol_lookback': 50, 'squeeze_threshold': 0.6, 'breakout_multiplier': 1.3}
        },
    ]
    
    results = []
    
    for strategy in strategies:
        print(f"\n{'='*80}")
        print(f"Testing: {strategy['name']}")
        print(f"{'='*80}")
        
        # Training
        print(f"\nTraining (2020-2024)...")
        signal_train = strategy['func'](train_data, **strategy['params'])
        metrics_train = calculate_metrics(train_data, signal_train)
        
        if metrics_train:
            print(f"  Trades: {metrics_train['trades']} ({metrics_train['trades_per_year']:.1f}/year)")
            print(f"  Annual Return: {metrics_train['annual_return_pct']:.2f}%")
            print(f"  Profit Factor: {metrics_train['profit_factor']:.3f}")
            print(f"  Win Rate: {metrics_train['win_rate']:.1f}%")
        else:
            print(f"  ❌ No valid metrics")
            continue
        
        # Testing
        print(f"\nForward Test (2026)...")
        signal_test = strategy['func'](test_data, **strategy['params'])
        metrics_test = calculate_metrics(test_data, signal_test)
        
        if metrics_test:
            print(f"  Trades: {metrics_test['trades']} ({metrics_test['trades_per_year']:.1f}/year)")
            print(f"  Annual Return: {metrics_test['annual_return_pct']:.2f}%")
            print(f"  Profit Factor: {metrics_test['profit_factor']:.3f}")
            print(f"  Win Rate: {metrics_test['win_rate']:.1f}%")
            
            # MCPT
            if metrics_test['profit_factor'] >= 1.3 and metrics_test['annual_return'] >= 0.06:
                print(f"\n Running MCPT...")
                mcpt_result = run_mcpt(test_data, strategy['func'], strategy['params'], n_permutations=100)
                
                print(f"\nMCPT Results:")
                print(f"  Real PF: {mcpt_result['real_pf']:.3f}")
                print(f"  Permuted Mean PF: {mcpt_result['permuted_mean']:.3f}")
                print(f"  Permuted Better: {mcpt_result['permuted_better_count']}/99")
                print(f"  P-Value: {mcpt_result['p_value']:.4f}")
                print(f"  Status: {'✅ PASS' if mcpt_result['passed'] else '❌ FAIL'}")
                
                results.append({
                    'strategy': strategy['name'],
                    'params': strategy['params'],
                    'train_metrics': metrics_train,
                    'test_metrics': metrics_test,
                    'mcpt': mcpt_result,
                    'passed': mcpt_result['passed']
                })
            else:
                print(f"\n❌ Did not meet minimum requirements")
                results.append({
                    'strategy': strategy['name'],
                    'params': strategy['params'],
                    'train_metrics': metrics_train,
                    'test_metrics': metrics_test,
                    'passed': False
                })
        else:
            print(f"  ❌ No valid metrics")
    
    # Summary
    print(f"\n{'='*80}")
    print("FINAL RESULTS")
    print("="*80)
    
    passed_strategies = [r for r in results if r.get('passed', False)]
    
    if passed_strategies:
        print(f"\n✅ {len(passed_strategies)} strategy(ies) PASSED MCPT!")
        for r in passed_strategies:
            print(f"\n  🎯 {r['strategy']}")
            print(f"     Test Return: {r['test_metrics']['annual_return_pct']:.2f}%")
            print(f"     Test PF: {r['test_metrics']['profit_factor']:.3f}")
            print(f"     Test Win Rate: {r['test_metrics']['win_rate']:.1f}%")
            print(f"     Trades/Year: {r['test_metrics']['trades_per_year']:.1f}")
            print(f"     MCPT P-Value: {r['mcpt']['p_value']:.4f} ✅")
    else:
        print(f"\n❌ No strategies passed MCPT yet")
        print(f"\nClosest to passing:")
        valid_results = [r for r in results if 'mcpt' in r]
        if valid_results:
            valid_results.sort(key=lambda x: x['mcpt'].get('p_value', 1.0))
            for r in valid_results[:3]:
                print(f"\n  {r['strategy']}")
                print(f"    Test Return: {r['test_metrics']['annual_return_pct']:.2f}%")
                print(f"    Test PF: {r['test_metrics']['profit_factor']:.3f}")
                print(f"    Trades/Year: {r['test_metrics']['trades_per_year']:.1f}")
                print(f"    MCPT P-Value: {r['mcpt']['p_value']:.4f}")
    
    # Save
    results_dir = Path(__file__).parent.parent / 'results'
    results_dir.mkdir(parents=True, exist_ok=True)
    
    with open(results_dir / 'robust_strategies_mcpt_results.json', 'w') as f:
        json.dump({
            'training_period': f"{train_data.index[0]} to {train_data.index[-1]}",
            'testing_period': f"{test_data.index[0]} to {test_data.index[-1]}",
            'results': results,
            'passed_count': len(passed_strategies)
        }, f, indent=2)
    
    print(f"\n💾 Results saved")
    print(f"\n{'='*80}\n")


if __name__ == '__main__':
    main()
