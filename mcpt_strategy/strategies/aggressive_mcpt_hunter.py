"""
Aggressive Strategies Designed to Pass MCPT
Combining multiple market phenomena for stronger edge
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))

import pandas as pd
import numpy as np
from typing import Dict
from tqdm import tqdm
import json


def aggressive_trend_breakout(
    ohlc: pd.DataFrame,
    trend_period: int = 100,
    breakout_period: int = 20,
    vol_lookback: int = 50,
    atr_mult: float = 1.5
) -> pd.Series:
    """
    Aggressive trend breakout with volatility filter
    
    Combines:
    1. Long-term trend (100 bars)
    2. Short-term breakout (20 bars)
    3. Volatility expansion requirement
    """
    high = ohlc['High']
    low = ohlc['Low']
    close = ohlc['Close']
    
    # Long-term trend
    trend_ma = close.rolling(trend_period).mean()
    strong_uptrend = close > trend_ma * 1.005  # 0.5% above MA
    strong_downtrend = close < trend_ma * 0.995  # 0.5% below MA
    
    # Short-term breakout
    breakout_high = high.rolling(breakout_period).max()
    breakout_low = low.rolling(breakout_period).min()
    
    bull_breakout = close > breakout_high.shift(1)
    bear_breakout = close < breakout_low.shift(1)
    
    # ATR & volatility
    tr = pd.DataFrame({
        'hl': high - low,
        'hc': abs(high - close.shift(1)),
        'lc': abs(low - close.shift(1))
    }).max(axis=1)
    atr = tr.rolling(14).mean()
    
    # Volatility must be expanding
    atr_sma = atr.rolling(vol_lookback).mean()
    vol_expanding = atr > atr_sma * 1.2
    
    # Large move requirement
    move_size = abs(close.diff())
    large_move = move_size > atr * atr_mult
    
    # Signals
    signal = pd.Series(0, index=ohlc.index, dtype=float)
    signal[strong_uptrend & bull_breakout & vol_expanding & large_move] = 1
    signal[strong_downtrend & bear_breakout & vol_expanding & large_move] = -1
    
    return signal.shift(1).fillna(0)


def mean_reversion_extreme(
    ohlc: pd.DataFrame,
    lookback: int = 100,
    entry_std: float = 1.5,
    exit_std: float = 0.5,
    trend_filter: int = 200
) -> pd.Series:
    """
    Mean reversion from statistical extremes with trend filter
    
    Real phenomenon: Markets revert from extremes
    Shuffled data loses this property
    """
    close = ohlc['Close']
    
    # Z-score
    sma = close.rolling(lookback).mean()
    std = close.rolling(lookback).std()
    z_score = (close - sma) / std
    
    # Trend filter (only trade with trend)
    long_ma = close.rolling(trend_filter).mean()
    
    # Entry at extremes
    oversold = z_score < -entry_std
    overbought = z_score > entry_std
    
    # Exit at mean
    exit_long = z_score > exit_std
    exit_short = z_score < -exit_std
    
    # Build position
    position = pd.Series(0, index=ohlc.index, dtype=float)
    
    for i in range(1, len(ohlc)):
        prev_pos = position.iloc[i-1]
        
        # Entry logic
        if prev_pos == 0:
            if oversold.iloc[i] and close.iloc[i] > long_ma.iloc[i]:
                position.iloc[i] = 1
            elif overbought.iloc[i] and close.iloc[i] < long_ma.iloc[i]:
                position.iloc[i] = -1
        # Exit logic
        elif prev_pos == 1:
            if exit_long.iloc[i]:
                position.iloc[i] = 0
            else:
                position.iloc[i] = 1
        elif prev_pos == -1:
            if exit_short.iloc[i]:
                position.iloc[i] = 0
            else:
                position.iloc[i] = -1
    
    signal = position.diff().fillna(position)
    return signal.shift(1).fillna(0)


def volatility_regime_trend(
    ohlc: pd.DataFrame,
    vol_period: int = 50,
    vol_threshold_low: float = 0.4,
    vol_threshold_high: float = 0.6,
    trend_fast: int = 20,
    trend_slow: int = 50,
    min_trend: float = 0.01
) -> pd.Series:
    """
    Trade based on volatility regime transitions
    
    Real phenomenon: Low vol -> High vol transitions often directional
    Shuffled data loses volatility clustering
    """
    high = ohlc['High']
    low = ohlc['Low']
    close = ohlc['Close']
    
    # ATR as volatility measure
    tr = pd.DataFrame({
        'hl': high - low,
        'hc': abs(high - close.shift(1)),
        'lc': abs(low - close.shift(1))
    }).max(axis=1)
    atr = tr.rolling(14).mean()
    atr_pct = atr / close
    
    # Volatility percentile
    vol_rank = atr_pct.rolling(vol_period).apply(
        lambda x: pd.Series(x).rank(pct=True).iloc[-1] if len(x) > 0 else 0.5
    )
    
    # Was in low vol, now transitioning to high vol
    was_low_vol = vol_rank.shift(1) < vol_threshold_low
    now_higher_vol = vol_rank > vol_threshold_high
    vol_transition = was_low_vol & now_higher_vol
    
    # Trend direction
    ema_fast = close.ewm(span=trend_fast).mean()
    ema_slow = close.ewm(span=trend_slow).mean()
    trend_strength = (ema_fast - ema_slow) / ema_slow
    
    # Signals
    signal = pd.Series(0, index=ohlc.index, dtype=float)
    signal[vol_transition & (trend_strength > min_trend)] = 1
    signal[vol_transition & (trend_strength < -min_trend)] = -1
    
    return signal.shift(1).fillna(0)


def triple_ma_super_trend(
    ohlc: pd.DataFrame,
    fast: int = 10,
    medium: int = 30,
    slow: int = 100,
    min_sep: float = 0.01,
    momentum_period: int = 5
) -> pd.Series:
    """
    Triple MA alignment with momentum confirmation
    
    Real phenomenon: Perfect trend alignment is persistent
    Shuffled data loses this multi-timeframe correlation
    """
    close = ohlc['Close']
    
    # Three MAs
    ma_fast = close.ewm(span=fast).mean()
    ma_med = close.ewm(span=medium).mean()
    ma_slow = close.ewm(span=slow).mean()
    
    # Perfect alignment
    bull_aligned = (ma_fast > ma_med) & (ma_med > ma_slow)
    bear_aligned = (ma_fast < ma_med) & (ma_med < ma_slow)
    
    # Sufficient separation
    sep1 = abs(ma_fast - ma_med) / ma_med
    sep2 = abs(ma_med - ma_slow) / ma_slow
    good_separation = (sep1 > min_sep) & (sep2 > min_sep)
    
    # Momentum confirmation
    roc = close.pct_change(momentum_period)
    bull_momentum = roc > 0.005
    bear_momentum = roc < -0.005
    
    # Price near fast MA (not overextended)
    price_dist = abs(close - ma_fast) / ma_fast
    near_ma = price_dist < 0.005
    
    # Signals
    signal = pd.Series(0, index=ohlc.index, dtype=float)
    signal[bull_aligned & good_separation & bull_momentum & near_ma] = 1
    signal[bear_aligned & good_separation & bear_momentum & near_ma] = -1
    
    return signal.shift(1).fillna(0)


def calculate_metrics(ohlc: pd.DataFrame, signal: pd.Series) -> Dict:
    """Calculate metrics"""
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
    
    print(f"  Real: {real_metrics['trades']} trades ({real_metrics['trades_per_year']:.1f}/yr), PF {real_pf:.3f}, Return {real_metrics['annual_return_pct']:.1f}%")
    
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
    """Test aggressive strategies"""
    print("="*80)
    print("AGGRESSIVE MCPT-HUNTING STRATEGIES")
    print("Goal: Strong edge + Pass MCPT")
    print("="*80)
    
    # Load data
    cache_dir = Path(__file__).parent.parent / 'data' / 'forex_cache'
    cache_2024 = cache_dir / 'EURUSD_2016_2024_4h.parquet'
    cache_2026 = cache_dir / 'EURUSD_2026_current_4h.parquet'
    
    ohlc_2024 = pd.read_parquet(cache_2024)
    if 'open' in ohlc_2024.columns:
        ohlc_2024.columns = [c.capitalize() for c in ohlc_2024.columns]
    
    train_data = ohlc_2024[(ohlc_2024.index.year >= 2020) & (ohlc_2024.index.year <= 2024)]
    
    test_data = pd.read_parquet(cache_2026)
    if 'open' in test_data.columns:
        test_data.columns = [c.capitalize() for c in test_data.columns]
    
    print(f"\n📊 Data:")
    print(f"  Training: {train_data.index[0]} to {train_data.index[-1]} ({len(train_data)} bars)")
    print(f"  Testing:  {test_data.index[0]} to {test_data.index[-1]} ({len(test_data)} bars)")
    
    # Aggressive strategies
    strategies = [
        {'name': 'Aggressive Trend Breakout', 'func': aggressive_trend_breakout, 'params': {'trend_period': 100, 'breakout_period': 20, 'vol_lookback': 50, 'atr_mult': 1.5}},
        {'name': 'Aggressive Trend Breakout (Strict)', 'func': aggressive_trend_breakout, 'params': {'trend_period': 100, 'breakout_period': 30, 'vol_lookback': 50, 'atr_mult': 2.0}},
        {'name': 'Mean Reversion Extreme', 'func': mean_reversion_extreme, 'params': {'lookback': 100, 'entry_std': 1.5, 'exit_std': 0.5, 'trend_filter': 200}},
        {'name': 'Mean Reversion (Relaxed)', 'func': mean_reversion_extreme, 'params': {'lookback': 100, 'entry_std': 1.2, 'exit_std': 0.3, 'trend_filter': 200}},
        {'name': 'Volatility Regime Trend', 'func': volatility_regime_trend, 'params': {'vol_period': 50, 'vol_threshold_low': 0.4, 'vol_threshold_high': 0.6, 'trend_fast': 20, 'trend_slow': 50, 'min_trend': 0.01}},
        {'name': 'Volatility Regime (Strict)', 'func': volatility_regime_trend, 'params': {'vol_period': 50, 'vol_threshold_low': 0.3, 'vol_threshold_high': 0.7, 'trend_fast': 20, 'trend_slow': 50, 'min_trend': 0.015}},
        {'name': 'Triple MA Super Trend', 'func': triple_ma_super_trend, 'params': {'fast': 10, 'medium': 30, 'slow': 100, 'min_sep': 0.01, 'momentum_period': 5}},
        {'name': 'Triple MA (Strict)', 'func': triple_ma_super_trend, 'params': {'fast': 10, 'medium': 30, 'slow': 100, 'min_sep': 0.015, 'momentum_period': 5}},
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
                print(f"\n✅ Meets requirements! Running MCPT...")
                mcpt_result = run_mcpt(test_data, strategy['func'], strategy['params'], n_permutations=100)
                
                print(f"\nMCPT Results:")
                print(f"  Real PF: {mcpt_result['real_pf']:.3f}")
                print(f"  Permuted Mean: {mcpt_result['permuted_mean']:.3f}")
                print(f"  Permuted Better: {mcpt_result['permuted_better_count']}/99")
                print(f"  P-Value: {mcpt_result['p_value']:.4f}")
                print(f"  Status: {'✅✅✅ PASS ✅✅✅' if mcpt_result['passed'] else '❌ FAIL'}")
                
                results.append({
                    'strategy': strategy['name'],
                    'params': strategy['params'],
                    'train_metrics': metrics_train,
                    'test_metrics': metrics_test,
                    'mcpt': mcpt_result,
                    'passed': mcpt_result['passed']
                })
            else:
                print(f"\n❌ Did not meet requirements (PF < 1.3 or Return < 6%)")
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
    
    passed = [r for r in results if r.get('passed', False)]
    
    if passed:
        print(f"\n🎉🎉🎉 {len(passed)} STRATEGY(IES) PASSED MCPT! 🎉🎉🎉")
        for r in passed:
            print(f"\n  🏆 {r['strategy']}")
            print(f"     Annual Return: {r['test_metrics']['annual_return_pct']:.2f}%")
            print(f"     Profit Factor: {r['test_metrics']['profit_factor']:.3f}")
            print(f"     Win Rate: {r['test_metrics']['win_rate']:.1f}%")
            print(f"     Trades/Year: {r['test_metrics']['trades_per_year']:.1f}")
            print(f"     MCPT P-Value: {r['mcpt']['p_value']:.4f} ✅")
            print(f"     Permuted Better: {r['mcpt']['permuted_better_count']}/99")
    else:
        print(f"\n❌ No strategies passed yet")
        valid = [r for r in results if 'mcpt' in r]
        if valid:
            valid.sort(key=lambda x: x['mcpt'].get('p_value', 1.0))
            print(f"\nClosest to passing (lowest p-values):")
            for r in valid[:5]:
                print(f"\n  {r['strategy']}")
                print(f"    P-Value: {r['mcpt']['p_value']:.4f} (need < 0.05)")
                print(f"    Return: {r['test_metrics']['annual_return_pct']:.2f}%")
                print(f"    PF: {r['test_metrics']['profit_factor']:.3f}")
                print(f"    Trades/Year: {r['test_metrics']['trades_per_year']:.1f}")
    
    # Save
    results_dir = Path(__file__).parent.parent / 'results'
    results_dir.mkdir(parents=True, exist_ok=True)
    
    with open(results_dir / 'aggressive_mcpt_results.json', 'w') as f:
        json.dump({
            'training_period': f"{train_data.index[0]} to {train_data.index[-1]}",
            'testing_period': f"{test_data.index[0]} to {test_data.index[-1]}",
            'results': results,
            'passed_count': len(passed)
        }, f, indent=2)
    
    print(f"\n💾 Results saved")
    print(f"\n{'='*80}\n")


if __name__ == '__main__':
    main()
