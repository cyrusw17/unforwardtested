"""
Enhanced ICT Scoring Strategy
Weighted scoring system using multiple ICT concepts across 1H and 4H
Train on 2020-2024, test on 2025+
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))

import pandas as pd
import numpy as np
from typing import Tuple, Dict
from tqdm import tqdm
import json


class ICTScoring:
    """ICT indicators with scoring weights"""
    
    @staticmethod
    def order_blocks_with_strength(ohlc: pd.DataFrame, lookback: int = 5) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """Order blocks with strength score"""
        bullish_ob = pd.Series(0.0, index=ohlc.index)
        bearish_ob = pd.Series(0.0, index=ohlc.index)
        
        close = ohlc['Close']
        open_price = ohlc['Open']
        body = abs(close - open_price)
        avg_body = body.rolling(20).mean()
        
        # Strength based on body size relative to average
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
        
        return bullish_ob, bearish_ob, strength
    
    @staticmethod
    def fvg_with_size(ohlc: pd.DataFrame) -> Tuple[pd.Series, pd.Series]:
        """Fair Value Gaps with size measurement"""
        high = ohlc['High']
        low = ohlc['Low']
        close = ohlc['Close']
        
        bullish_fvg_size = (low - high.shift(2)).clip(lower=0) / close * 100
        bearish_fvg_size = (low.shift(2) - high).clip(lower=0) / close * 100
        
        return bullish_fvg_size, bearish_fvg_size
    
    @staticmethod
    def liquidity_sweep_strength(ohlc: pd.DataFrame, lookback: int = 10) -> Tuple[pd.Series, pd.Series]:
        """Liquidity sweeps with strength"""
        high = ohlc['High']
        low = ohlc['Low']
        close = ohlc['Close']
        open_price = ohlc['Open']
        
        bullish_sweep = pd.Series(0.0, index=ohlc.index)
        bearish_sweep = pd.Series(0.0, index=ohlc.index)
        
        for i in range(lookback, len(ohlc)):
            recent_low = low.iloc[i-lookback:i].min()
            if low.iloc[i] <= recent_low * 1.0001:  # Sweep low
                wick_size = (close.iloc[i] - low.iloc[i]) / (high.iloc[i] - low.iloc[i] + 0.0001)
                if wick_size > 0.3:  # Rejection wick
                    bullish_sweep.iloc[i] = wick_size * 2
            
            recent_high = high.iloc[i-lookback:i].max()
            if high.iloc[i] >= recent_high * 0.9999:  # Sweep high
                wick_size = (high.iloc[i] - close.iloc[i]) / (high.iloc[i] - low.iloc[i] + 0.0001)
                if wick_size > 0.3:
                    bearish_sweep.iloc[i] = wick_size * 2
        
        return bullish_sweep, bearish_sweep
    
    @staticmethod
    def market_structure_score(ohlc: pd.DataFrame, swing_length: int = 5) -> pd.Series:
        """Market structure with strength"""
        high = ohlc['High']
        low = ohlc['Low']
        close = ohlc['Close']
        
        recent_high = high.rolling(swing_length).max()
        recent_low = low.rolling(swing_length).min()
        
        # Calculate how far above/below structure
        above_high = ((close - recent_high.shift(1)) / recent_high.shift(1) * 100).clip(-5, 5)
        below_low = ((close - recent_low.shift(1)) / recent_low.shift(1) * 100).clip(-5, 5)
        
        structure = pd.Series(0.0, index=ohlc.index)
        structure[close > recent_high.shift(1)] = above_high[close > recent_high.shift(1)]
        structure[close < recent_low.shift(1)] = below_low[close < recent_low.shift(1)]
        
        return structure.ffill().fillna(0)
    
    @staticmethod
    def trend_strength(ohlc: pd.DataFrame, fast: int = 10, slow: int = 30) -> pd.Series:
        """Trend strength using EMA distance"""
        fast_ema = ohlc['Close'].ewm(span=fast).mean()
        slow_ema = ohlc['Close'].ewm(span=slow).mean()
        
        # Percentage distance between EMAs
        trend_strength = ((fast_ema - slow_ema) / slow_ema * 100).clip(-5, 5)
        
        return trend_strength


def scoring_strategy(
    ohlc_4h: pd.DataFrame,
    ohlc_1h: pd.DataFrame = None,
    entry_threshold: float = 3.0,
    ob_lookback: int = 5,
    structure_length: int = 5
) -> pd.Series:
    """
    Scoring-based strategy
    Takes trade when score exceeds threshold
    """
    ict = ICTScoring()
    
    # === 4H SCORING ===
    bullish_ob_4h, bearish_ob_4h, strength_4h = ict.order_blocks_with_strength(ohlc_4h, ob_lookback)
    bullish_fvg_4h, bearish_fvg_4h = ict.fvg_with_size(ohlc_4h)
    bullish_sweep_4h, bearish_sweep_4h = ict.liquidity_sweep_strength(ohlc_4h)
    structure_4h = ict.market_structure_score(ohlc_4h, structure_length)
    trend_4h = ict.trend_strength(ohlc_4h)
    
    # Calculate bullish and bearish scores
    bullish_score_4h = (
        bullish_ob_4h * 2.0 +           # OB worth 2x
        bullish_fvg_4h * 1.5 +          # FVG worth 1.5x
        bullish_sweep_4h * 1.5 +        # Sweep worth 1.5x
        structure_4h.clip(lower=0) +    # Positive structure
        trend_4h.clip(lower=0)          # Positive trend
    )
    
    bearish_score_4h = (
        bearish_ob_4h * 2.0 +
        bearish_fvg_4h * 1.5 +
        bearish_sweep_4h * 1.5 +
        abs(structure_4h.clip(upper=0)) +
        abs(trend_4h.clip(upper=0))
    )
    
    # === 1H CONFIRMATION (if provided) ===
    if ohlc_1h is not None:
        bullish_ob_1h, bearish_ob_1h, strength_1h = ict.order_blocks_with_strength(ohlc_1h, ob_lookback)
        bullish_fvg_1h, bearish_fvg_1h = ict.fvg_with_size(ohlc_1h)
        bullish_sweep_1h, bearish_sweep_1h = ict.liquidity_sweep_strength(ohlc_1h)
        structure_1h = ict.market_structure_score(ohlc_1h, structure_length)
        trend_1h = ict.trend_strength(ohlc_1h)
        
        bullish_score_1h = (
            bullish_ob_1h * 1.0 +
            bullish_fvg_1h * 0.75 +
            bullish_sweep_1h * 0.75 +
            structure_1h.clip(lower=0) * 0.5 +
            trend_1h.clip(lower=0) * 0.5
        )
        
        bearish_score_1h = (
            bearish_ob_1h * 1.0 +
            bearish_fvg_1h * 0.75 +
            bearish_sweep_1h * 0.75 +
            abs(structure_1h.clip(upper=0)) * 0.5 +
            abs(trend_1h.clip(upper=0)) * 0.5
        )
        
        # Aggregate 1H scores to 4H (sum of last 4 hours)
        bullish_agg_1h = bullish_score_1h.rolling(4).sum().reindex(ohlc_4h.index, method='ffill').fillna(0)
        bearish_agg_1h = bearish_score_1h.rolling(4).sum().reindex(ohlc_4h.index, method='ffill').fillna(0)
        
        # Combine 4H and 1H scores
        bullish_total = bullish_score_4h + bullish_agg_1h * 0.5
        bearish_total = bearish_score_4h + bearish_agg_1h * 0.5
    else:
        bullish_total = bullish_score_4h
        bearish_total = bearish_score_4h
    
    # Generate signals
    signal = pd.Series(0, index=ohlc_4h.index, dtype=float)
    signal[bullish_total >= entry_threshold] = 1
    signal[bearish_total >= entry_threshold] = -1
    
    # If both exceed threshold, take the stronger one
    both_exceed = (bullish_total >= entry_threshold) & (bearish_total >= entry_threshold)
    signal[both_exceed & (bullish_total > bearish_total)] = 1
    signal[both_exceed & (bearish_total > bullish_total)] = -1
    
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
        'years': float(years)
    }


def run_mcpt(ohlc_4h: pd.DataFrame, ohlc_1h: pd.DataFrame, strategy_params: Dict, n_permutations: int = 100) -> Dict:
    """Run MCPT"""
    from mcpt_strategy.utils import get_permutation
    
    signal = scoring_strategy(ohlc_4h, ohlc_1h, **strategy_params)
    real_metrics = calculate_metrics(ohlc_4h, signal)
    
    if real_metrics is None:
        return {'passed': False, 'error': 'No valid metrics'}
    
    real_pf = real_metrics['profit_factor']
    
    if real_pf < 1.3:
        return {'passed': False, 'error': f'PF {real_pf:.2f} < 1.3', 'real_metrics': real_metrics}
    if real_metrics['annual_return'] < 0.06:
        return {'passed': False, 'error': f'Return {real_metrics["annual_return_pct"]:.1f}% < 6%', 'real_metrics': real_metrics}
    
    perm_better = 1
    perm_pfs = []
    
    for i in tqdm(range(1, n_permutations), desc="MCPT Progress"):
        try:
            ohlc_4h_lower = ohlc_4h.copy()
            ohlc_4h_lower.columns = [c.lower() for c in ohlc_4h_lower.columns]
            perm_4h = get_permutation(ohlc_4h_lower, seed=i * 100)
            perm_4h.columns = [c.capitalize() for c in perm_4h.columns]
            
            perm_1h = None
            if ohlc_1h is not None:
                ohlc_1h_lower = ohlc_1h.copy()
                ohlc_1h_lower.columns = [c.lower() for c in ohlc_1h_lower.columns]
                perm_1h = get_permutation(ohlc_1h_lower, seed=i * 200)
                perm_1h.columns = [c.capitalize() for c in perm_1h.columns]
            
            perm_signal = scoring_strategy(perm_4h, perm_1h, **strategy_params)
            perm_metrics = calculate_metrics(perm_4h, perm_signal)
            
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
        'passed': passed,
        'reason': 'success' if passed else f'p-value {p_value:.4f} >= 0.05'
    }


def main():
    """Main execution"""
    print("="*80)
    print("ENHANCED ICT SCORING STRATEGY")
    print("Multi-timeframe weighted scoring system")
    print("Training: 2020-2024 | Testing: 2025+")
    print("="*80)
    
    # Load 4H data
    cache_dir = Path(__file__).parent.parent / 'data' / 'forex_cache'
    cache_2024 = cache_dir / 'EURUSD_2016_2024_4h.parquet'
    cache_2026 = cache_dir / 'EURUSD_2026_current_4h.parquet'
    
    if not cache_2024.exists():
        print("ERROR: Training data not found")
        return
    
    ohlc_4h_all = pd.read_parquet(cache_2024)
    if 'open' in ohlc_4h_all.columns:
        ohlc_4h_all.columns = [c.capitalize() for c in ohlc_4h_all.columns]
    
    train_4h = ohlc_4h_all[(ohlc_4h_all.index.year >= 2020) & (ohlc_4h_all.index.year <= 2024)]
    
    if cache_2026.exists():
        test_4h = pd.read_parquet(cache_2026)
        if 'open' in test_4h.columns:
            test_4h.columns = [c.capitalize() for c in test_4h.columns]
    else:
        print("ERROR: No 2025+ data")
        return
    
    print(f"\n📊 4H Data:")
    print(f"  Training: {train_4h.index[0]} to {train_4h.index[-1]} ({len(train_4h)} bars)")
    print(f"  Testing:  {test_4h.index[0]} to {test_4h.index[-1]} ({len(test_4h)} bars)")
    
    # Fetch 1H data
    print(f"\nFetching 1H data...")
    try:
        from smc_1h_4h_confluence import fetch_1h_data
        train_1h = fetch_1h_data('2020-01-01', '2024-12-31')
        test_1h = fetch_1h_data('2026-01-01', '2026-07-17')
        print(f"  ✅ 1H data available ({len(train_1h)} train, {len(test_1h)} test bars)")
    except Exception as e:
        print(f"  ⚠️  1H data not available: {e}")
        train_1h = None
        test_1h = None
    
    # Test configurations
    configurations = [
        {'name': '4H Only - Very High Threshold', 'use_1h': False, 'params': {'entry_threshold': 5.0, 'ob_lookback': 5, 'structure_length': 5}},
        {'name': '4H Only - Ultra High Threshold', 'use_1h': False, 'params': {'entry_threshold': 6.0, 'ob_lookback': 7, 'structure_length': 7}},
        {'name': '1H+4H - Med Threshold', 'use_1h': True, 'params': {'entry_threshold': 3.0, 'ob_lookback': 5, 'structure_length': 5}},
        {'name': '1H+4H - High Threshold', 'use_1h': True, 'params': {'entry_threshold': 4.0, 'ob_lookback': 5, 'structure_length': 5}},
    ]
    
    results = []
    
    for config in configurations:
        print(f"\n{'='*80}")
        print(f"Testing: {config['name']}")
        print(f"{'='*80}")
        
        # Determine which 1H data to use
        use_1h_train = train_1h if config.get('use_1h', False) else None
        use_1h_test = test_1h if config.get('use_1h', False) else None
        
        if config.get('use_1h', False) and (train_1h is None or test_1h is None):
            print(f"  ⚠️  Skipping - 1H data not available")
            continue
        
        # Training
        print(f"\nTraining (2020-2024)...")
        signal_train = scoring_strategy(train_4h, use_1h_train, **config['params'])
        metrics_train = calculate_metrics(train_4h, signal_train)
        
        if metrics_train:
            print(f"  Annual Return: {metrics_train['annual_return_pct']:.2f}%")
            print(f"  Profit Factor: {metrics_train['profit_factor']:.3f}")
            print(f"  Win Rate: {metrics_train['win_rate']:.1f}%")
            print(f"  Trades: {metrics_train['trades']}")
        
        # Testing
        print(f"\nForward test (2025+)...")
        signal_test = scoring_strategy(test_4h, use_1h_test, **config['params'])
        metrics_test = calculate_metrics(test_4h, signal_test)
        
        if metrics_test:
            print(f"  Annual Return: {metrics_test['annual_return_pct']:.2f}%")
            print(f"  Profit Factor: {metrics_test['profit_factor']:.3f}")
            print(f"  Win Rate: {metrics_test['win_rate']:.1f}%")
            print(f"  Trades: {metrics_test['trades']}")
            
            # MCPT
            if metrics_test['profit_factor'] >= 1.3 and metrics_test['annual_return'] >= 0.06:
                print(f"\nRunning MCPT...")
                mcpt_result = run_mcpt(test_4h, use_1h_test, config['params'], n_permutations=100)
                
                print(f"\nMCPT Results:")
                print(f"  Real PF: {mcpt_result['real_pf']:.3f}")
                print(f"  P-Value: {mcpt_result['p_value']:.4f}")
                print(f"  Status: {'✅ PASS' if mcpt_result['passed'] else '❌ FAIL'}")
                
                results.append({
                    'config': config['name'],
                    'params': config['params'],
                    'train_metrics': metrics_train,
                    'test_metrics': metrics_test,
                    'mcpt': mcpt_result,
                    'passed': mcpt_result['passed']
                })
            else:
                print(f"\n❌ Did not meet requirements")
                results.append({
                    'config': config['name'],
                    'params': config['params'],
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
    
    passed_configs = [r for r in results if r.get('passed', False)]
    
    if passed_configs:
        print(f"\n✅ {len(passed_configs)} configuration(s) passed MCPT!")
        for r in passed_configs:
            print(f"\n  {r['config']}")
            print(f"    Test Return: {r['test_metrics']['annual_return_pct']:.2f}%")
            print(f"    Test PF: {r['test_metrics']['profit_factor']:.3f}")
            print(f"    Test Win Rate: {r['test_metrics']['win_rate']:.1f}%")
            print(f"    MCPT P-Value: {r['mcpt']['p_value']:.4f}")
    else:
        print(f"\n❌ No configurations passed MCPT")
        valid_results = [r for r in results if 'test_metrics' in r and r['test_metrics']]
        if valid_results:
            valid_results.sort(key=lambda x: x['test_metrics'].get('annual_return_pct', 0), reverse=True)
            print(f"\nBest performers:")
            for r in valid_results[:3]:
                print(f"\n  {r['config']}")
                print(f"    Test Return: {r['test_metrics']['annual_return_pct']:.2f}%")
                print(f"    Test PF: {r['test_metrics']['profit_factor']:.3f}")
                print(f"    Test Win Rate: {r['test_metrics']['win_rate']:.1f}%")
    
    # Save
    results_dir = Path(__file__).parent.parent / 'results'
    results_dir.mkdir(parents=True, exist_ok=True)
    
    with open(results_dir / 'enhanced_ict_scoring_results.json', 'w') as f:
        json.dump({
            'training_period': f"{train_4h.index[0]} to {train_4h.index[-1]}",
            'testing_period': f"{test_4h.index[0]} to {test_4h.index[-1]}",
            'results': results,
            'passed_count': len(passed_configs)
        }, f, indent=2)
    
    print(f"\n💾 Results saved to {results_dir}/enhanced_ict_scoring_results.json")
    print(f"\n{'='*80}\n")


if __name__ == '__main__':
    main()
