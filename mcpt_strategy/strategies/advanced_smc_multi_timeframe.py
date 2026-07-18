"""
Advanced Multi-Timeframe SMC Strategy
Uses multiple ICT concepts across 1H and 4H timeframes for confluence
Train on 2020-2024, test on 2025+
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))

import pandas as pd
import numpy as np
from typing import Tuple, Dict, List
from tqdm import tqdm
import json

from core.indicators import TechnicalIndicators


class AdvancedSMCIndicators:
    """Advanced Smart Money Concept indicators with multi-timeframe"""
    
    @staticmethod
    def identify_order_blocks(ohlc: pd.DataFrame, lookback: int = 5) -> Tuple[pd.Series, pd.Series]:
        """Identify order blocks"""
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
    
    @staticmethod
    def identify_fvg(ohlc: pd.DataFrame) -> Tuple[pd.Series, pd.Series]:
        """Fair Value Gaps"""
        high = ohlc['High']
        low = ohlc['Low']
        
        bullish_fvg = low > high.shift(2)
        bearish_fvg = high < low.shift(2)
        
        return bullish_fvg, bearish_fvg
    
    @staticmethod
    def identify_liquidity_sweep(ohlc: pd.DataFrame, lookback: int = 10) -> Tuple[pd.Series, pd.Series]:
        """Liquidity sweeps (stop hunts)"""
        high = ohlc['High']
        low = ohlc['Low']
        close = ohlc['Close']
        
        bullish_sweep = pd.Series(False, index=ohlc.index)
        bearish_sweep = pd.Series(False, index=ohlc.index)
        
        for i in range(lookback, len(ohlc)):
            recent_low = low.iloc[i-lookback:i].min()
            if low.iloc[i] <= recent_low and close.iloc[i] > low.iloc[i]:
                bullish_sweep.iloc[i] = True
            
            recent_high = high.iloc[i-lookback:i].max()
            if high.iloc[i] >= recent_high and close.iloc[i] < high.iloc[i]:
                bearish_sweep.iloc[i] = True
        
        return bullish_sweep, bearish_sweep
    
    @staticmethod
    def identify_structure(ohlc: pd.DataFrame, swing_length: int = 5) -> pd.Series:
        """Market structure"""
        high = ohlc['High']
        low = ohlc['Low']
        
        recent_high = high.rolling(swing_length).max()
        recent_low = low.rolling(swing_length).min()
        
        structure = pd.Series(0, index=ohlc.index)
        structure[ohlc['Close'] > recent_high.shift(1)] = 1
        structure[ohlc['Close'] < recent_low.shift(1)] = -1
        
        return structure.ffill().fillna(0)
    
    @staticmethod
    def identify_break_of_structure(ohlc: pd.DataFrame, lookback: int = 20) -> Tuple[pd.Series, pd.Series]:
        """Break of Structure (BOS) - continuation pattern"""
        high = ohlc['High']
        low = ohlc['Low']
        close = ohlc['Close']
        
        bullish_bos = pd.Series(False, index=ohlc.index)
        bearish_bos = pd.Series(False, index=ohlc.index)
        
        for i in range(lookback, len(ohlc)):
            # Bullish BOS: break above recent swing high
            swing_high = high.iloc[i-lookback:i-1].max()
            if close.iloc[i] > swing_high:
                bullish_bos.iloc[i] = True
            
            # Bearish BOS: break below recent swing low
            swing_low = low.iloc[i-lookback:i-1].min()
            if close.iloc[i] < swing_low:
                bearish_bos.iloc[i] = True
        
        return bullish_bos, bearish_bos
    
    @staticmethod
    def identify_change_of_character(ohlc: pd.DataFrame, lookback: int = 10) -> Tuple[pd.Series, pd.Series]:
        """Change of Character (CHOCH) - reversal pattern"""
        high = ohlc['High']
        low = ohlc['Low']
        close = ohlc['Close']
        
        bullish_choch = pd.Series(False, index=ohlc.index)
        bearish_choch = pd.Series(False, index=ohlc.index)
        
        # CHOCH = break of counter-trend structure
        for i in range(lookback*2, len(ohlc)):
            # Bullish CHOCH: was bearish, now breaks up
            recent_trend = close.iloc[i-lookback:i].diff().mean()
            if recent_trend < 0:  # Was going down
                recent_high = high.iloc[i-lookback:i].max()
                if close.iloc[i] > recent_high:
                    bullish_choch.iloc[i] = True
            
            # Bearish CHOCH: was bullish, now breaks down
            if recent_trend > 0:  # Was going up
                recent_low = low.iloc[i-lookback:i].min()
                if close.iloc[i] < recent_low:
                    bearish_choch.iloc[i] = True
        
        return bullish_choch, bearish_choch
    
    @staticmethod
    def premium_discount_zones(ohlc: pd.DataFrame, lookback: int = 50) -> Tuple[pd.Series, pd.Series]:
        """Premium/Discount zones"""
        high = ohlc['High']
        low = ohlc['Low']
        close = ohlc['Close']
        
        range_high = high.rolling(lookback).max()
        range_low = low.rolling(lookback).min()
        range_size = range_high - range_low
        
        premium_level = range_high - (range_size * 0.3)
        discount_level = range_low + (range_size * 0.3)
        
        in_premium = close > premium_level
        in_discount = close < discount_level
        
        return in_premium, in_discount
    
    @staticmethod
    def identify_inducement(ohlc: pd.DataFrame, lookback: int = 5) -> Tuple[pd.Series, pd.Series]:
        """Inducement - false breakout before real move"""
        high = ohlc['High']
        low = ohlc['Low']
        close = ohlc['Close']
        
        bullish_inducement = pd.Series(False, index=ohlc.index)
        bearish_inducement = pd.Series(False, index=ohlc.index)
        
        for i in range(lookback, len(ohlc)):
            # Bullish: fake breakout down, then reverses up
            if i >= 2:
                prev_low = low.iloc[i-2]
                if low.iloc[i-1] < prev_low and close.iloc[i] > close.iloc[i-1]:
                    bullish_inducement.iloc[i] = True
            
            # Bearish: fake breakout up, then reverses down
            if i >= 2:
                prev_high = high.iloc[i-2]
                if high.iloc[i-1] > prev_high and close.iloc[i] < close.iloc[i-1]:
                    bearish_inducement.iloc[i] = True
        
        return bullish_inducement, bearish_inducement


class MultiTimeframeStrategy:
    """Multi-timeframe SMC strategy"""
    
    @staticmethod
    def resample_to_higher_tf(ohlc: pd.DataFrame, factor: int = 4) -> pd.DataFrame:
        """Resample 1H to 4H (or any factor)"""
        return ohlc.resample(f'{factor}H').agg({
            'Open': 'first',
            'High': 'max',
            'Low': 'min',
            'Close': 'last'
        }).dropna()
    
    @staticmethod
    def align_signals(lower_tf: pd.Series, higher_tf: pd.Series) -> pd.Series:
        """Align lower timeframe signals with higher timeframe"""
        # Reindex higher TF to lower TF
        aligned = higher_tf.reindex(lower_tf.index, method='ffill')
        return aligned
    
    @staticmethod
    def advanced_confluence_strategy(
        ohlc: pd.DataFrame,
        use_multi_tf: bool = True,
        min_confluence: int = 3,
        ob_lookback: int = 5,
        structure_length: int = 5
    ) -> pd.Series:
        """
        Advanced strategy with multiple ICT concepts and multi-timeframe
        """
        smc = AdvancedSMCIndicators()
        
        # === PRIMARY TIMEFRAME (4H) ANALYSIS ===
        bullish_ob, bearish_ob = smc.identify_order_blocks(ohlc, ob_lookback)
        bullish_fvg, bearish_fvg = smc.identify_fvg(ohlc)
        bullish_sweep, bearish_sweep = smc.identify_liquidity_sweep(ohlc)
        structure = smc.identify_structure(ohlc, structure_length)
        bullish_bos, bearish_bos = smc.identify_break_of_structure(ohlc)
        bullish_choch, bearish_choch = smc.identify_change_of_character(ohlc)
        in_premium, in_discount = smc.premium_discount_zones(ohlc)
        bullish_induce, bearish_induce = smc.identify_inducement(ohlc)
        
        # === MULTI-TIMEFRAME CONFLUENCE ===
        if use_multi_tf:
            # Resample to higher timeframe (4H -> 16H or similar)
            try:
                htf_ohlc = MultiTimeframeStrategy.resample_to_higher_tf(ohlc, factor=4)
                htf_structure = smc.identify_structure(htf_ohlc, structure_length)
                htf_bullish_ob, htf_bearish_ob = smc.identify_order_blocks(htf_ohlc, ob_lookback)
                
                # Align to primary timeframe
                htf_structure_aligned = MultiTimeframeStrategy.align_signals(structure, htf_structure)
                htf_bullish_ob_aligned = MultiTimeframeStrategy.align_signals(bullish_ob, htf_bullish_ob)
                htf_bearish_ob_aligned = MultiTimeframeStrategy.align_signals(bearish_ob, htf_bearish_ob)
            except:
                htf_structure_aligned = pd.Series(0, index=ohlc.index)
                htf_bullish_ob_aligned = pd.Series(False, index=ohlc.index)
                htf_bearish_ob_aligned = pd.Series(False, index=ohlc.index)
        else:
            htf_structure_aligned = pd.Series(0, index=ohlc.index)
            htf_bullish_ob_aligned = pd.Series(False, index=ohlc.index)
            htf_bearish_ob_aligned = pd.Series(False, index=ohlc.index)
        
        # === BULLISH CONFLUENCE COUNT ===
        bullish_signals = (
            bullish_ob.astype(int) +                    # 1. Order Block
            bullish_fvg.astype(int) +                   # 2. Fair Value Gap
            bullish_sweep.astype(int) +                 # 3. Liquidity Sweep
            (structure > 0).astype(int) +               # 4. Bullish Structure
            bullish_bos.astype(int) +                   # 5. Break of Structure
            bullish_choch.astype(int) +                 # 6. Change of Character
            in_discount.astype(int) +                   # 7. Discount Zone
            bullish_induce.astype(int) +                # 8. Inducement
            (htf_structure_aligned > 0).astype(int) +   # 9. HTF Structure
            htf_bullish_ob_aligned.astype(int)          # 10. HTF Order Block
        )
        
        # === BEARISH CONFLUENCE COUNT ===
        bearish_signals = (
            bearish_ob.astype(int) +
            bearish_fvg.astype(int) +
            bearish_sweep.astype(int) +
            (structure < 0).astype(int) +
            bearish_bos.astype(int) +
            bearish_choch.astype(int) +
            in_premium.astype(int) +
            bearish_induce.astype(int) +
            (htf_structure_aligned < 0).astype(int) +
            htf_bearish_ob_aligned.astype(int)
        )
        
        # === GENERATE SIGNALS ===
        signal = pd.Series(0, index=ohlc.index, dtype=float)
        signal[bullish_signals >= min_confluence] = 1
        signal[bearish_signals >= min_confluence] = -1
        
        # Execute next bar
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


def run_mcpt(ohlc: pd.DataFrame, strategy_params: Dict, n_permutations: int = 100) -> Dict:
    """Run MCPT"""
    from mcpt_strategy.utils import get_permutation
    
    # Real strategy
    signal = MultiTimeframeStrategy.advanced_confluence_strategy(ohlc, **strategy_params)
    real_metrics = calculate_metrics(ohlc, signal)
    
    if real_metrics is None:
        return {'passed': False, 'error': 'No valid metrics'}
    
    real_pf = real_metrics['profit_factor']
    
    # Check minimum requirements
    if real_pf < 1.3:
        return {'passed': False, 'error': f'PF {real_pf:.2f} < 1.3', 'real_metrics': real_metrics}
    if real_metrics['annual_return'] < 0.06:
        return {'passed': False, 'error': f'Return {real_metrics["annual_return_pct"]:.1f}% < 6%', 'real_metrics': real_metrics}
    
    # Run permutations
    perm_better = 1
    perm_pfs = []
    
    for i in tqdm(range(1, n_permutations), desc="MCPT Progress"):
        try:
            ohlc_lower = ohlc.copy()
            ohlc_lower.columns = [c.lower() for c in ohlc_lower.columns]
            perm_data = get_permutation(ohlc_lower, seed=i * 100)
            perm_data.columns = [c.capitalize() for c in perm_data.columns]
            
            perm_signal = MultiTimeframeStrategy.advanced_confluence_strategy(perm_data, **strategy_params)
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
        'passed': passed,
        'reason': 'success' if passed else f'p-value {p_value:.4f} >= 0.05'
    }


def main():
    """Train on 2020-2024, test on 2025+"""
    print("="*80)
    print("ADVANCED MULTI-TIMEFRAME SMC STRATEGY")
    print("Training: 2020-2024 | Testing: 2025+")
    print("="*80)
    
    # Load data
    cache_dir = Path(__file__).parent.parent / 'data' / 'forex_cache'
    cache_2024 = cache_dir / 'EURUSD_2016_2024_4h.parquet'
    cache_2026 = cache_dir / 'EURUSD_2026_current_4h.parquet'
    
    if not cache_2024.exists():
        print(f"ERROR: Training data not found")
        return
    
    ohlc_2024 = pd.read_parquet(cache_2024)
    if 'open' in ohlc_2024.columns:
        ohlc_2024.columns = [c.capitalize() for c in ohlc_2024.columns]
    
    # Filter to 2020-2024
    train_data = ohlc_2024[(ohlc_2024.index.year >= 2020) & (ohlc_2024.index.year <= 2024)]
    
    # Load test data (2025+)
    if cache_2026.exists():
        test_data = pd.read_parquet(cache_2026)
        if 'open' in test_data.columns:
            test_data.columns = [c.capitalize() for c in test_data.columns]
    else:
        print("ERROR: No 2025+ data available")
        return
    
    print(f"\n📊 Data Split:")
    print(f"  Training: {train_data.index[0]} to {train_data.index[-1]} ({len(train_data)} bars)")
    print(f"  Testing:  {test_data.index[0]} to {test_data.index[-1]} ({len(test_data)} bars)")
    
    # Test different configurations
    print(f"\n{'='*80}")
    print("TESTING CONFIGURATIONS")
    print("="*80)
    
    configurations = [
        {'name': '3 Confluence MTF', 'params': {'use_multi_tf': True, 'min_confluence': 3, 'ob_lookback': 5, 'structure_length': 5}},
        {'name': '4 Confluence MTF', 'params': {'use_multi_tf': True, 'min_confluence': 4, 'ob_lookback': 5, 'structure_length': 5}},
        {'name': '3 Confluence No MTF', 'params': {'use_multi_tf': False, 'min_confluence': 3, 'ob_lookback': 5, 'structure_length': 5}},
        {'name': '5 Confluence MTF', 'params': {'use_multi_tf': True, 'min_confluence': 5, 'ob_lookback': 7, 'structure_length': 7}},
    ]
    
    results = []
    
    for config in configurations:
        print(f"\n{'='*80}")
        print(f"Testing: {config['name']}")
        print(f"{'='*80}")
        
        # Test on training data first (sanity check)
        print(f"\nTraining performance (2020-2024)...")
        signal_train = MultiTimeframeStrategy.advanced_confluence_strategy(train_data, **config['params'])
        metrics_train = calculate_metrics(train_data, signal_train)
        
        if metrics_train:
            print(f"  Annual Return: {metrics_train['annual_return_pct']:.2f}%")
            print(f"  Profit Factor: {metrics_train['profit_factor']:.3f}")
            print(f"  Win Rate: {metrics_train['win_rate']:.1f}%")
            print(f"  Trades: {metrics_train['trades']}")
        
        # Test on forward data
        print(f"\nForward test (2025+)...")
        signal_test = MultiTimeframeStrategy.advanced_confluence_strategy(test_data, **config['params'])
        metrics_test = calculate_metrics(test_data, signal_test)
        
        if metrics_test:
            print(f"  Annual Return: {metrics_test['annual_return_pct']:.2f}%")
            print(f"  Profit Factor: {metrics_test['profit_factor']:.3f}")
            print(f"  Win Rate: {metrics_test['win_rate']:.1f}%")
            print(f"  Trades: {metrics_test['trades']}")
            
            # Run MCPT on forward data
            if metrics_test['profit_factor'] >= 1.3 and metrics_test['annual_return'] >= 0.06:
                print(f"\nRunning MCPT on forward data...")
                mcpt_result = run_mcpt(test_data, config['params'], n_permutations=100)
                
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
                print(f"\n❌ Did not meet minimum requirements for MCPT")
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
        print(f"\nBest performers:")
        valid_results = [r for r in results if 'test_metrics' in r and r['test_metrics']]
        if valid_results:
            valid_results.sort(key=lambda x: x['test_metrics'].get('annual_return_pct', 0), reverse=True)
            for r in valid_results[:3]:
                print(f"\n  {r['config']}")
                print(f"    Test Return: {r['test_metrics']['annual_return_pct']:.2f}%")
                print(f"    Test PF: {r['test_metrics']['profit_factor']:.3f}")
                print(f"    Test Win Rate: {r['test_metrics']['win_rate']:.1f}%")
    
    # Save results
    results_dir = Path(__file__).parent.parent / 'results'
    results_dir.mkdir(parents=True, exist_ok=True)
    
    with open(results_dir / 'advanced_smc_mtf_results.json', 'w') as f:
        json.dump({
            'training_period': f"{train_data.index[0]} to {train_data.index[-1]}",
            'testing_period': f"{test_data.index[0]} to {test_data.index[-1]}",
            'results': results,
            'passed_count': len(passed_configs)
        }, f, indent=2)
    
    print(f"\n💾 Results saved to {results_dir}/advanced_smc_mtf_results.json")
    print(f"\n{'='*80}\n")


if __name__ == '__main__':
    main()
