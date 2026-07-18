"""
MCPT Validation on 2014-2016 Data
Tests if the SMC strategy passes MCPT on this historical period
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))

import pandas as pd
import numpy as np
from typing import Dict
from tqdm import tqdm

from core.indicators import TechnicalIndicators
from mcpt_strategy.utils import get_permutation


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


def calculate_returns(ohlc: pd.DataFrame, signals: pd.Series) -> pd.Series:
    """Calculate strategy returns"""
    returns = ohlc['Close'].pct_change()
    strategy_returns = returns * signals.shift(1)
    return strategy_returns


def calculate_metrics(ohlc: pd.DataFrame, signals: pd.Series) -> Dict:
    """Calculate performance metrics"""
    returns = calculate_returns(ohlc, signals)
    
    # Filter to only trades
    trades = returns[signals.shift(1) != 0]
    
    if len(trades) == 0:
        return {
            'total_return': 0,
            'annual_return': 0,
            'profit_factor': 1.0,
            'sharpe_ratio': 0,
            'max_drawdown': 0,
            'win_rate': 0,
            'trades': 0
        }
    
    # Calculate metrics
    total_return = (1 + returns).prod() - 1
    
    years = (ohlc.index[-1] - ohlc.index[0]).days / 365.25
    annual_return = (1 + total_return) ** (1 / years) - 1
    
    winners = trades[trades > 0].sum()
    losers = abs(trades[trades < 0].sum())
    profit_factor = winners / losers if losers > 0 else float('inf')
    
    sharpe = returns.mean() / returns.std() * np.sqrt(252 * 6) if returns.std() > 0 else 0
    
    cumulative = (1 + returns).cumprod()
    running_max = cumulative.expanding().max()
    drawdown = (cumulative - running_max) / running_max
    max_drawdown = drawdown.min()
    
    win_rate = (trades > 0).sum() / len(trades) * 100
    
    return {
        'total_return': total_return,
        'annual_return': annual_return,
        'annual_return_pct': annual_return * 100,
        'profit_factor': profit_factor,
        'sharpe_ratio': sharpe,
        'max_drawdown': max_drawdown,
        'max_drawdown_pct': max_drawdown * 100,
        'win_rate': win_rate,
        'trades': len(trades),
        'years': years
    }


def run_mcpt(ohlc: pd.DataFrame, strategy_func, strategy_params: Dict,
             n_permutations: int = 100, min_pf: float = 1.3, 
             min_return: float = 0.06, p_threshold: float = 0.05) -> Dict:
    """Run Monte Carlo Permutation Test"""
    
    print("\n" + "="*80)
    print("MONTE CARLO PERMUTATION TEST (MCPT)")
    print("="*80)
    
    # Generate real signals
    print("\nGenerating signals for real data...")
    real_signals = strategy_func(ohlc, **strategy_params)
    real_metrics = calculate_metrics(ohlc, real_signals)
    
    print(f"\n📊 Real Strategy Performance:")
    print(f"  Total Return: {real_metrics['total_return']*100:.2f}%")
    print(f"  Annual Return: {real_metrics['annual_return_pct']:.2f}%")
    print(f"  Profit Factor: {real_metrics['profit_factor']:.3f}")
    print(f"  Sharpe Ratio: {real_metrics['sharpe_ratio']:.2f}")
    print(f"  Max Drawdown: {real_metrics['max_drawdown_pct']:.2f}%")
    print(f"  Win Rate: {real_metrics['win_rate']:.1f}%")
    print(f"  Trades: {real_metrics['trades']}")
    
    # Check minimum requirements
    if real_metrics['profit_factor'] < min_pf:
        return {
            'real_metrics': real_metrics,
            'real_pf': real_metrics['profit_factor'],
            'p_value': 1.0,
            'passed': False,
            'reason': f"Profit Factor {real_metrics['profit_factor']:.3f} < {min_pf}"
        }
    
    if real_metrics['annual_return'] < min_return:
        return {
            'real_metrics': real_metrics,
            'real_pf': real_metrics['profit_factor'],
            'p_value': 1.0,
            'passed': False,
            'reason': f"Annual Return {real_metrics['annual_return']*100:.2f}% < {min_return*100}%"
        }
    
    # Run permutations
    print(f"\nRunning {n_permutations} permutations...")
    permuted_pfs = []
    
    for i in tqdm(range(n_permutations), desc="MCPT Progress"):
        # Permute OHLC data (convert to lowercase for get_permutation)
        ohlc_lowercase = ohlc.copy()
        ohlc_lowercase.columns = [c.lower() for c in ohlc_lowercase.columns]
        perm_ohlc = get_permutation(ohlc_lowercase)
        # Convert back to capitalized for strategy
        perm_ohlc.columns = [c.capitalize() for c in perm_ohlc.columns]
        
        # Generate signals on permuted data
        perm_signals = strategy_func(perm_ohlc, **strategy_params)
        perm_metrics = calculate_metrics(perm_ohlc, perm_signals)
        permuted_pfs.append(perm_metrics['profit_factor'])
    
    # Calculate p-value
    real_pf = real_metrics['profit_factor']
    better_or_equal = sum(1 for pf in permuted_pfs if pf >= real_pf)
    p_value = better_or_equal / n_permutations
    
    permuted_mean = np.mean(permuted_pfs)
    permuted_std = np.std(permuted_pfs)
    
    print(f"\n📈 MCPT Results:")
    print(f"  Real Profit Factor: {real_pf:.3f}")
    print(f"  Permuted Mean PF: {permuted_mean:.3f}")
    print(f"  Permuted Std PF: {permuted_std:.3f}")
    print(f"  P-Value: {p_value:.4f}")
    print(f"  Threshold: {p_threshold}")
    
    passed = p_value < p_threshold
    
    if passed:
        print(f"\n✅ MCPT PASSED!")
        print(f"  Only {p_value*100:.1f}% of random permutations performed as well")
        print(f"  Strategy has statistical significance")
    else:
        print(f"\n❌ MCPT FAILED")
        print(f"  {p_value*100:.1f}% of random permutations performed as well")
        print(f"  Strategy may not have edge over random")
    
    return {
        'real_metrics': real_metrics,
        'real_pf': real_pf,
        'p_value': p_value,
        'permuted_mean': permuted_mean,
        'permuted_std': permuted_std,
        'passed': passed,
        'reason': 'success' if passed else f'p-value {p_value:.4f} >= {p_threshold}'
    }


def main():
    """Run MCPT on 2014-2016 data"""
    print("="*80)
    print("MCPT VALIDATION - 2014-2016 DATA")
    print("="*80)
    
    # Load 2010-2016 data and filter to 2014-2016
    cache_dir = Path(__file__).parent.parent / 'data' / 'forex_cache'
    cache_file = cache_dir / 'EURUSD_2010_2016_4h.parquet'
    
    if not cache_file.exists():
        print("ERROR: 2010-2016 data not found. Run fetch_historical_data.py first.")
        return
    
    print(f"\nLoading data from {cache_file}")
    ohlc = pd.read_parquet(cache_file)
    
    # Filter to 2014-2016
    ohlc = ohlc[(ohlc.index.year >= 2014) & (ohlc.index.year <= 2016)]
    
    if 'open' in ohlc.columns:
        ohlc.columns = [c.capitalize() for c in ohlc.columns]
    
    print(f"\nData: EUR/USD 4H")
    print(f"Period: {ohlc.index[0]} to {ohlc.index[-1]}")
    print(f"Bars: {len(ohlc)}")
    print(f"Years: {(ohlc.index[-1] - ohlc.index[0]).days / 365.25:.2f}")
    
    print(f"\nForex-adapted MCPT Criteria:")
    print(f"  P-Value: < 0.05")
    print(f"  Min Profit Factor: > 1.3")
    print(f"  Min Annual Return: > 6%")
    
    # Run MCPT
    strategy_params = {
        'ob_lookback': 5,
        'use_structure': True
    }
    
    result = run_mcpt(
        ohlc,
        smc_order_block_strategy,
        strategy_params,
        n_permutations=100,
        min_pf=1.3,
        min_return=0.06,
        p_threshold=0.05
    )
    
    # Save results
    import json
    results_file = Path(__file__).parent.parent / 'results' / 'mcpt_2014_2016_results.json'
    
    # Convert numpy types to native Python for JSON serialization
    json_result = {
        'period': f"{ohlc.index[0]} to {ohlc.index[-1]}",
        'bars': len(ohlc),
        'years': float(result['real_metrics']['years']),
        'real_metrics': {
            k: float(v) if isinstance(v, (np.float64, np.float32, np.int64, np.int32)) else v
            for k, v in result['real_metrics'].items()
        },
        'real_pf': float(result['real_pf']),
        'p_value': float(result['p_value']),
        'permuted_mean': float(result.get('permuted_mean', 0)),
        'permuted_std': float(result.get('permuted_std', 0)),
        'passed': bool(result['passed']),
        'reason': result['reason']
    }
    
    with open(results_file, 'w') as f:
        json.dump(json_result, f, indent=2)
    
    print(f"\n✅ Results saved to {results_file}")
    
    # Summary
    print("\n" + "="*80)
    print("FINAL VERDICT")
    print("="*80)
    
    if result['passed']:
        print(f"\n✅ STRATEGY PASSES MCPT ON 2014-2016 DATA")
        print(f"  P-Value: {result['p_value']:.4f} < 0.05")
        print(f"  Profit Factor: {result['real_pf']:.3f}")
        print(f"  Annual Return: {result['real_metrics']['annual_return_pct']:.2f}%")
        print(f"\n  This validates the strategy on a different historical period!")
    else:
        print(f"\n❌ STRATEGY FAILS MCPT ON 2014-2016 DATA")
        print(f"  Reason: {result['reason']}")
        print(f"  P-Value: {result['p_value']:.4f}")
        print(f"  This suggests the strategy may not generalize to all periods")
    
    print(f"\n{'='*80}\n")


if __name__ == '__main__':
    main()
