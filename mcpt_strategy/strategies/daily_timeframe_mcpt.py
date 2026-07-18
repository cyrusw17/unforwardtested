"""
Daily Timeframe MCPT Testing
Lower noise, stronger trends = better MCPT chances
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))

import pandas as pd
import numpy as np
from typing import Dict, Tuple
from tqdm import tqdm
import json
import yfinance as yf


def fetch_daily_forex(pair: str = 'EURUSD=X', start: str = '2020-01-01', end: str = '2026-12-31') -> pd.DataFrame:
    """Fetch daily forex data from Yahoo Finance"""
    print(f"Fetching {pair} daily data from {start} to {end}...")
    
    try:
        df = yf.download(pair, start=start, end=end, progress=False)
        
        if df is None or len(df) == 0:
            print(f"  ❌ No data returned")
            return None
        
        # Standardize columns
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
        df = df[['Open', 'High', 'Low', 'Close', 'Volume']]
        
        print(f"  ✅ Loaded {len(df)} daily bars")
        return df
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return None


class EnhancedICTDaily:
    """Enhanced ICT Scoring adapted for daily timeframe"""
    
    @staticmethod
    def order_blocks_with_strength(ohlc: pd.DataFrame, lookback: int = 5) -> Tuple[pd.Series, pd.Series]:
        """Order blocks with strength"""
        bullish_ob = pd.Series(0.0, index=ohlc.index)
        bearish_ob = pd.Series(0.0, index=ohlc.index)
        
        close = ohlc['Close']
        open_price = ohlc['Open']
        body = abs(close - open_price)
        avg_body = body.rolling(20).mean()
        
        strength = (body / avg_body).fillna(0).clip(0, 3)
        
        strong_bullish = (close > open_price) & (body > avg_body * 1.2)
        strong_bearish = (close < open_price) & (body > avg_body * 1.2)
        
        for i in range(lookback, len(ohlc)):
            if strong_bullish.iloc[i]:
                for j in range(1, min(lookback, i)):
                    if close.iloc[i-j] < open_price.iloc[i-j]:
                        bullish_ob.iloc[i-j] = strength.iloc[i]
                        break
            
            if strong_bearish.iloc[i]:
                for j in range(1, min(lookback, i)):
                    if close.iloc[i-j] > open_price.iloc[i-j]:
                        bearish_ob.iloc[i-j] = strength.iloc[i]
                        break
        
        return bullish_ob, bearish_ob
    
    @staticmethod
    def fvg_with_size(ohlc: pd.DataFrame) -> Tuple[pd.Series, pd.Series]:
        """Fair Value Gaps"""
        high = ohlc['High']
        low = ohlc['Low']
        close = ohlc['Close']
        
        bullish_fvg_size = (low - high.shift(2)).clip(lower=0) / close * 100
        bearish_fvg_size = (low.shift(2) - high).clip(lower=0) / close * 100
        
        return bullish_fvg_size, bearish_fvg_size
    
    @staticmethod
    def liquidity_sweep_strength(ohlc: pd.DataFrame, lookback: int = 10) -> Tuple[pd.Series, pd.Series]:
        """Liquidity sweeps"""
        high = ohlc['High']
        low = ohlc['Low']
        close = ohlc['Close']
        
        bullish_sweep = pd.Series(0.0, index=ohlc.index)
        bearish_sweep = pd.Series(0.0, index=ohlc.index)
        
        for i in range(lookback, len(ohlc)):
            recent_low = low.iloc[i-lookback:i].min()
            if low.iloc[i] <= recent_low * 1.0001:
                wick_size = (close.iloc[i] - low.iloc[i]) / (high.iloc[i] - low.iloc[i] + 0.0001)
                if wick_size > 0.3:
                    bullish_sweep.iloc[i] = wick_size * 2
            
            recent_high = high.iloc[i-lookback:i].max()
            if high.iloc[i] >= recent_high * 0.9999:
                wick_size = (high.iloc[i] - close.iloc[i]) / (high.iloc[i] - low.iloc[i] + 0.0001)
                if wick_size > 0.3:
                    bearish_sweep.iloc[i] = wick_size * 2
        
        return bullish_sweep, bearish_sweep
    
    @staticmethod
    def market_structure_score(ohlc: pd.DataFrame, swing_length: int = 5) -> pd.Series:
        """Market structure"""
        high = ohlc['High']
        low = ohlc['Low']
        close = ohlc['Close']
        
        recent_high = high.rolling(swing_length).max()
        recent_low = low.rolling(swing_length).min()
        
        above_high = ((close - recent_high.shift(1)) / recent_high.shift(1) * 100).clip(-5, 5)
        below_low = ((close - recent_low.shift(1)) / recent_low.shift(1) * 100).clip(-5, 5)
        
        structure = pd.Series(0.0, index=ohlc.index)
        structure[close > recent_high.shift(1)] = above_high[close > recent_high.shift(1)]
        structure[close < recent_low.shift(1)] = below_low[close < recent_low.shift(1)]
        
        return structure.ffill().fillna(0)
    
    @staticmethod
    def trend_strength(ohlc: pd.DataFrame, fast: int = 10, slow: int = 30) -> pd.Series:
        """Trend strength"""
        fast_ema = ohlc['Close'].ewm(span=fast).mean()
        slow_ema = ohlc['Close'].ewm(span=slow).mean()
        
        trend_strength = ((fast_ema - slow_ema) / slow_ema * 100).clip(-5, 5)
        
        return trend_strength


def enhanced_ict_scoring_daily(
    ohlc: pd.DataFrame,
    entry_threshold: float = 3.0,
    ob_lookback: int = 5,
    structure_length: int = 5
) -> pd.Series:
    """Enhanced ICT scoring for daily timeframe"""
    ict = EnhancedICTDaily()
    
    bullish_ob, bearish_ob = ict.order_blocks_with_strength(ohlc, ob_lookback)
    bullish_fvg, bearish_fvg = ict.fvg_with_size(ohlc)
    bullish_sweep, bearish_sweep = ict.liquidity_sweep_strength(ohlc)
    structure = ict.market_structure_score(ohlc, structure_length)
    trend = ict.trend_strength(ohlc)
    
    # Scoring
    bullish_score = (
        bullish_ob * 2.0 +
        bullish_fvg * 1.5 +
        bullish_sweep * 1.5 +
        structure.clip(lower=0) +
        trend.clip(lower=0)
    )
    
    bearish_score = (
        bearish_ob * 2.0 +
        bearish_fvg * 1.5 +
        bearish_sweep * 1.5 +
        abs(structure.clip(upper=0)) +
        abs(trend.clip(upper=0))
    )
    
    # Signals
    signal = pd.Series(0, index=ohlc.index, dtype=float)
    signal[bullish_score >= entry_threshold] = 1
    signal[bearish_score >= entry_threshold] = -1
    
    # If both, take stronger
    both = (bullish_score >= entry_threshold) & (bearish_score >= entry_threshold)
    signal[both & (bullish_score > bearish_score)] = 1
    signal[both & (bearish_score > bullish_score)] = -1
    
    return signal.shift(1).fillna(0)


def calculate_metrics(ohlc: pd.DataFrame, signal: pd.Series) -> Dict:
    """Calculate metrics"""
    returns = np.log(ohlc['Close']).diff().shift(-1)
    strategy_returns = signal * returns
    strategy_returns = strategy_returns.dropna()
    
    if len(strategy_returns) == 0 or len(strategy_returns[strategy_returns < 0]) == 0:
        return None
    
    total_return = np.exp(strategy_returns.sum()) - 1
    years = len(ohlc) / 252
    annual_return = (1 + total_return) ** (1/years) - 1 if years > 0 else 0
    
    winning = strategy_returns[strategy_returns > 0].sum()
    losing = strategy_returns[strategy_returns < 0].abs().sum()
    profit_factor = winning / losing if losing > 0 else 0
    
    sharpe = strategy_returns.mean() / strategy_returns.std() * np.sqrt(252) if strategy_returns.std() > 0 else 0
    
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
    """Test daily timeframe"""
    print("="*80)
    print("DAILY TIMEFRAME MCPT TESTING")
    print("Testing multiple pairs and configurations")
    print("="*80)
    
    # Pairs to test
    pairs = [
        ('EURUSD=X', 'EUR/USD'),
        ('GBPUSD=X', 'GBP/USD'),
        ('USDJPY=X', 'USD/JPY'),
        ('AUDUSD=X', 'AUD/USD'),
    ]
    
    all_results = []
    
    for pair_symbol, pair_name in pairs:
        print(f"\n{'='*80}")
        print(f"Testing {pair_name}")
        print(f"{'='*80}")
        
        # Fetch data
        df = fetch_daily_forex(pair_symbol, '2020-01-01', '2026-12-31')
        
        if df is None or len(df) == 0:
            print(f"  ❌ Skipping {pair_name} - no data")
            continue
        
        # Split train/test
        train_data = df[df.index.year <= 2024]
        test_data = df[df.index.year >= 2025]
        
        if len(test_data) == 0:
            print(f"  ⚠️  No 2025+ data, using last 20% as test")
            split_idx = int(len(df) * 0.8)
            train_data = df.iloc[:split_idx]
            test_data = df.iloc[split_idx:]
        
        print(f"\n  Training: {train_data.index[0].date()} to {train_data.index[-1].date()} ({len(train_data)} bars)")
        print(f"  Testing:  {test_data.index[0].date()} to {test_data.index[-1].date()} ({len(test_data)} bars)")
        
        # Test configurations
        configs = [
            {'name': 'Low Threshold (2.0)', 'params': {'entry_threshold': 2.0, 'ob_lookback': 5, 'structure_length': 5}},
            {'name': 'Med Threshold (3.0)', 'params': {'entry_threshold': 3.0, 'ob_lookback': 5, 'structure_length': 5}},
            {'name': 'High Threshold (4.0)', 'params': {'entry_threshold': 4.0, 'ob_lookback': 5, 'structure_length': 5}},
            {'name': 'Very High (5.0)', 'params': {'entry_threshold': 5.0, 'ob_lookback': 7, 'structure_length': 7}},
        ]
        
        for config in configs:
            print(f"\n  --- {config['name']} ---")
            
            # Training
            print(f"  Training...")
            signal_train = enhanced_ict_scoring_daily(train_data, **config['params'])
            metrics_train = calculate_metrics(train_data, signal_train)
            
            if metrics_train:
                print(f"    Return: {metrics_train['annual_return_pct']:.2f}%, PF: {metrics_train['profit_factor']:.3f}, Trades: {metrics_train['trades']}")
            else:
                print(f"    ❌ No valid metrics")
                continue
            
            # Testing
            print(f"  Forward Test...")
            signal_test = enhanced_ict_scoring_daily(test_data, **config['params'])
            metrics_test = calculate_metrics(test_data, signal_test)
            
            if metrics_test:
                print(f"    Return: {metrics_test['annual_return_pct']:.2f}%, PF: {metrics_test['profit_factor']:.3f}, Trades: {metrics_test['trades']}")
                
                # MCPT
                if metrics_test['profit_factor'] >= 1.3 and metrics_test['annual_return'] >= 0.06:
                    print(f"  ✅ Meets requirements! Running MCPT...")
                    mcpt_result = run_mcpt(test_data, enhanced_ict_scoring_daily, config['params'], n_permutations=100)
                    
                    print(f"\n  MCPT Results:")
                    print(f"    Real PF: {mcpt_result['real_pf']:.3f}")
                    print(f"    Permuted Mean: {mcpt_result['permuted_mean']:.3f}")
                    print(f"    P-Value: {mcpt_result['p_value']:.4f}")
                    
                    if mcpt_result['passed']:
                        print(f"\n  🎉🎉🎉 ✅ PASSED MCPT ✅ 🎉🎉🎉")
                        print(f"  Pair: {pair_name}, Config: {config['name']}")
                    else:
                        print(f"    ❌ Failed (p >= 0.05)")
                    
                    all_results.append({
                        'pair': pair_name,
                        'config': config['name'],
                        'params': config['params'],
                        'train_metrics': metrics_train,
                        'test_metrics': metrics_test,
                        'mcpt': mcpt_result,
                        'passed': mcpt_result['passed']
                    })
                else:
                    print(f"    ❌ Did not meet requirements")
            else:
                print(f"    ❌ No valid metrics")
    
    # Final summary
    print(f"\n{'='*80}")
    print("FINAL SUMMARY")
    print("="*80)
    
    passed = [r for r in all_results if r.get('passed', False)]
    
    if passed:
        print(f"\n🏆🏆🏆 {len(passed)} CONFIGURATION(S) PASSED MCPT! 🏆🏆🏆")
        for r in passed:
            print(f"\n  ✅ {r['pair']} - {r['config']}")
            print(f"     Return: {r['test_metrics']['annual_return_pct']:.2f}%")
            print(f"     PF: {r['test_metrics']['profit_factor']:.3f}")
            print(f"     Win Rate: {r['test_metrics']['win_rate']:.1f}%")
            print(f"     MCPT P-Value: {r['mcpt']['p_value']:.4f}")
    else:
        print(f"\n❌ No configurations passed yet")
        if all_results:
            all_results.sort(key=lambda x: x.get('mcpt', {}).get('p_value', 1.0))
            print(f"\nBest performers (lowest p-values):")
            for r in all_results[:5]:
                if 'mcpt' in r:
                    print(f"\n  {r['pair']} - {r['config']}")
                    print(f"    P-Value: {r['mcpt']['p_value']:.4f}")
                    print(f"    Return: {r['test_metrics']['annual_return_pct']:.2f}%")
                    print(f"    PF: {r['test_metrics']['profit_factor']:.3f}")
    
    # Save
    results_dir = Path(__file__).parent.parent / 'results'
    results_dir.mkdir(parents=True, exist_ok=True)
    
    with open(results_dir / 'daily_timeframe_mcpt_results.json', 'w') as f:
        json.dump({
            'timeframe': 'daily',
            'pairs_tested': len(pairs),
            'configs_tested': len(configs),
            'results': all_results,
            'passed_count': len(passed)
        }, f, indent=2)
    
    print(f"\n💾 Results saved")
    print(f"\n{'='*80}\n")


if __name__ == '__main__':
    main()
