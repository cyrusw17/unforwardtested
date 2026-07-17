"""
MCPT Test on REAL FOREX DATA - The Proper Test

This tests the forex strategy on actual forex market data from Dukascopy,
which is what the strategy was originally designed for.
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))

import pandas as pd
import numpy as np
from tqdm import tqdm
import json
import matplotlib.pyplot as plt
import requests
import time
import random
import string

# Import from existing forex strategy
from core.indicators import TechnicalIndicators
from mcpt_strategy.utils import get_permutation


# Modified Dukascopy fetcher to support 2016+ data
def _jsonp_name() -> str:
    return "_callbacks____" + "".join(random.choices(string.ascii_letters + string.digits, k=9))


def fetch_forex_data(
    pair: str = "EURUSD",
    start_year: int = 2016,
    end_year: int = 2025,
    interval: str = "4HOUR"
) -> pd.DataFrame:
    """
    Fetch real forex data from Dukascopy free service
    """
    print(f"\n📡 Fetching {pair} data from Dukascopy ({start_year}-{end_year})...")
    
    pair_map = {
        "EURUSD": "EUR/USD",
        "GBPUSD": "GBP/USD",
        "USDJPY": "USD/JPY",
        "AUDUSD": "AUD/USD",
    }
    
    instrument = pair_map.get(pair.upper(), pair)
    
    # Start from beginning of period
    start_ts = pd.Timestamp(f"{start_year}-01-01", tz="UTC")
    start_ms = int(start_ts.timestamp() * 1000)
    
    all_bars = []
    last_update = start_ms
    max_iterations = 100  # Safety limit
    
    for iteration in range(max_iterations):
        try:
            jsonp = _jsonp_name()
            params = {
                "path": "chart/json3",
                "splits": "true",
                "stocks": "true",
                "time_direction": "N",
                "jsonp": jsonp,
                "last_update": str(int(last_update)),
                "offer_side": "B",
                "instrument": instrument,
                "interval": interval,
                "limit": "5000",
            }
            headers = {
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
                "Referer": "https://freeserv.dukascopy.com/2.0/?path=chart/index",
                "Host": "freeserv.dukascopy.com",
            }
            
            r = requests.get(
                "https://freeserv.dukascopy.com/2.0/index.php",
                headers=headers,
                params=params,
                timeout=60,
            )
            r.raise_for_status()
            
            text = r.text
            if text.startswith(jsonp + "(") and text.endswith(");"):
                text = text[len(jsonp) + 1 : -2]
            
            data = json.loads(text)
            
            if not data or not isinstance(data, list):
                break
            
            all_bars.extend(data)
            
            # Get timestamp of last bar
            last_bar_ts = data[-1][0]  # First element is timestamp
            last_update = last_bar_ts
            
            # Check if we've reached the end year
            bar_date = pd.Timestamp(last_bar_ts, unit='ms', tz='UTC')
            if bar_date.year > end_year:
                break
            
            print(f"  Fetched {len(all_bars)} bars (latest: {bar_date.strftime('%Y-%m-%d')})")
            
            time.sleep(0.5)  # Rate limiting
            
        except Exception as e:
            print(f"  Warning: {e}")
            break
    
    if not all_bars:
        raise ValueError(f"No data fetched for {pair}")
    
    # Convert to DataFrame
    df = pd.DataFrame(all_bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True)
    df = df.set_index('timestamp').sort_index()
    
    # Filter to requested period
    df = df[
        (df.index.year >= start_year) & 
        (df.index.year <= end_year)
    ]
    
    # Normalize column names
    df.columns = ['Open', 'High', 'Low', 'Close', 'Volume']
    
    print(f"✓ Fetched {len(df)} bars from {df.index[0]} to {df.index[-1]}")
    
    return df


def forex_signal_generator(
    ohlc: pd.DataFrame,
    sniper_fast: int = 3,
    sniper_slow: int = 9,
    sniper_adx: float = 15.0,
    use_di_filter: bool = True
) -> pd.Series:
    """
    Forex strategy signal generator (EMA 3/9 + ADX + DI filter)
    """
    ti = TechnicalIndicators
    
    # Calculate indicators
    ema_fast = ti.ema(ohlc, sniper_fast)
    ema_slow = ti.ema(ohlc, sniper_slow)
    adx, plus_di, minus_di = ti.adx(ohlc, 14)
    
    # Generate crossover signals
    cross_up = (ema_fast > ema_slow) & (ema_fast.shift(1) <= ema_slow.shift(1))
    cross_down = (ema_fast < ema_slow) & (ema_fast.shift(1) >= ema_slow.shift(1))
    
    # Long and short conditions
    long = cross_up & (adx > sniper_adx)
    short = cross_down & (adx > sniper_adx)
    
    # DI filter
    if use_di_filter:
        long = long & (plus_di > minus_di)
        short = short & (minus_di > plus_di)
    
    # Create signal series
    signal = pd.Series(0, index=ohlc.index, dtype=float)
    signal[long] = 1
    signal[short] = -1
    
    # Shift for next-bar execution
    signal = signal.shift(1).fillna(0)
    
    return signal


def calculate_metrics(ohlc: pd.DataFrame, signal: pd.Series) -> dict:
    """Calculate strategy performance metrics"""
    returns = np.log(ohlc['Close']).diff().shift(-1)
    strategy_returns = signal * returns
    strategy_returns = strategy_returns.dropna()
    
    if len(strategy_returns) == 0:
        return None
    
    # Profit factor
    winning = strategy_returns[strategy_returns > 0].sum()
    losing = strategy_returns[strategy_returns < 0].abs().sum()
    
    if losing == 0:
        profit_factor = winning if winning > 0 else 0
    else:
        profit_factor = winning / losing
    
    # Other metrics
    total_return = np.exp(strategy_returns.sum()) - 1
    sharpe = strategy_returns.mean() / strategy_returns.std() * np.sqrt(252/4) if strategy_returns.std() > 0 else 0
    
    # Drawdown
    cum_returns = strategy_returns.cumsum()
    running_max = cum_returns.cummax()
    drawdown = cum_returns - running_max
    max_dd = drawdown.min()
    
    # Trade count
    trades = (signal.diff() != 0).sum()
    
    # Win rate
    win_rate = len(strategy_returns[strategy_returns > 0]) / len(strategy_returns) * 100 if len(strategy_returns) > 0 else 0
    
    return {
        'total_return': float(total_return),
        'total_return_pct': float(total_return * 100),
        'profit_factor': float(profit_factor),
        'sharpe_ratio': float(sharpe),
        'max_drawdown': float(max_dd),
        'max_drawdown_pct': float(max_dd * 100),
        'win_rate': float(win_rate),
        'trades': int(trades),
        'bars': len(ohlc)
    }


def run_mcpt_on_real_forex(
    pair: str = "EURUSD",
    train_start: int = 2016,
    train_end: int = 2024,
    n_permutations: int = 100,
    cache_file: str = None
) -> dict:
    """
    Run MCPT on real forex data
    """
    print(f"\n{'='*80}")
    print(f"MCPT ON REAL FOREX DATA: {pair}")
    print(f"Training Period: {train_start}-{train_end}")
    print('='*80)
    
    # Try to load from cache first
    if cache_file and Path(cache_file).exists():
        print(f"\n📂 Loading cached data from {cache_file}")
        ohlc = pd.read_parquet(cache_file)
        if 'open' in ohlc.columns:
            ohlc.columns = [c.capitalize() for c in ohlc.columns]
    else:
        # Fetch fresh data
        ohlc = fetch_forex_data(pair, train_start, train_end)
        
        # Cache it
        if cache_file:
            cache_path = Path(cache_file)
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            ohlc.to_parquet(cache_file)
            print(f"💾 Cached data to {cache_file}")
    
    # Strategy parameters
    strategy_params = {
        'sniper_fast': 3,
        'sniper_slow': 9,
        'sniper_adx': 15.0,
        'use_di_filter': True
    }
    
    print(f"\n[1/2] Testing on real {pair} data ({len(ohlc)} bars)...")
    
    # Generate signals and calculate metrics
    signal = forex_signal_generator(ohlc, **strategy_params)
    real_metrics = calculate_metrics(ohlc, signal)
    
    if real_metrics is None:
        return {
            'error': 'No trades generated',
            'real_pf': 0.0,
            'p_value': 1.0,
            'passed': False
        }
    
    real_pf = real_metrics['profit_factor']
    
    print(f"\n📊 Real Performance:")
    print(f"  Profit Factor: {real_pf:.4f}")
    print(f"  Total Return: {real_metrics['total_return_pct']:.2f}%")
    print(f"  Sharpe Ratio: {real_metrics['sharpe_ratio']:.2f}")
    print(f"  Max Drawdown: {real_metrics['max_drawdown_pct']:.2f}%")
    print(f"  Win Rate: {real_metrics['win_rate']:.1f}%")
    print(f"  Trades: {real_metrics['trades']}")
    
    # Run permutations
    print(f"\n[2/2] Running {n_permutations} permutations...")
    perm_better_count = 1  # Start at 1 to include real result
    permuted_pfs = []
    
    # Debug first permutation
    debug_first = True
    
    for perm_i in tqdm(range(1, n_permutations), desc="MCPT"):
        try:
            # Need to convert to lowercase for permutation function
            ohlc_lower = ohlc.copy()
            ohlc_lower.columns = [c.lower() for c in ohlc_lower.columns]
            
            perm_data = get_permutation(ohlc_lower, seed=perm_i * 100)
            
            # Convert back to capitalized for indicator calculation
            perm_data.columns = [c.capitalize() for c in perm_data.columns]
            
            perm_signal = forex_signal_generator(perm_data, **strategy_params)
            perm_metrics = calculate_metrics(perm_data, perm_signal)
            
            if debug_first and perm_i == 1:
                print(f"\n  DEBUG perm 1:")
                print(f"    Perm data shape: {perm_data.shape}")
                print(f"    Perm signal unique: {perm_signal.unique()}")
                print(f"    Perm trades: {(perm_signal.diff() != 0).sum()}")
                print(f"    Perm metrics: {perm_metrics}")
                debug_first = False
            
            if perm_metrics is None:
                perm_pf = 1.0
            else:
                perm_pf = perm_metrics['profit_factor']
            
            if perm_pf >= real_pf:
                perm_better_count += 1
            
            permuted_pfs.append(perm_pf)
        except Exception as e:
            if perm_i <= 3:
                print(f"\n  Warning: Permutation {perm_i} failed: {e}")
                import traceback
                traceback.print_exc()
            permuted_pfs.append(1.0)
    
    p_value = perm_better_count / n_permutations
    passed = p_value < 0.01
    
    print(f"\n{'='*80}")
    print(f"MCPT RESULTS")
    print(f"{'='*80}")
    print(f"  Real Profit Factor:      {real_pf:.4f}")
    print(f"  Mean Permuted PF:        {np.mean(permuted_pfs):.4f}")
    print(f"  Std Permuted PF:         {np.std(permuted_pfs):.4f}")
    print(f"  P-Value:                 {p_value:.4f}")
    print(f"  Permutations Better:     {perm_better_count-1}/{n_permutations-1}")
    print(f"  Status:                  {'✓ PASS' if passed else '✗ FAIL'} (threshold < 0.01)")
    print(f"{'='*80}")
    
    return {
        'pair': pair,
        'period': f'{train_start}-{train_end}',
        'real_metrics': real_metrics,
        'mcpt': {
            'real_pf': float(real_pf),
            'p_value': float(p_value),
            'perm_better_count': int(perm_better_count),
            'permuted_pfs_mean': float(np.mean(permuted_pfs)),
            'permuted_pfs_std': float(np.std(permuted_pfs)),
            'permuted_pfs': [float(x) for x in permuted_pfs],
            'passed': passed
        }
    }


def test_multiple_pairs():
    """
    Test on multiple forex pairs
    """
    print("\n" + "="*80)
    print("FOREX STRATEGY MCPT - MULTI-PAIR TEST")
    print("Testing on REAL forex data from Dukascopy")
    print("="*80)
    
    pairs = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD"]
    results = {}
    
    cache_dir = Path(__file__).parent.parent / 'data' / 'forex_cache'
    cache_dir.mkdir(parents=True, exist_ok=True)
    
    for pair in pairs:
        cache_file = cache_dir / f"{pair}_2016_2024_4h.parquet"
        
        try:
            result = run_mcpt_on_real_forex(
                pair=pair,
                train_start=2016,
                train_end=2024,
                n_permutations=100,
                cache_file=str(cache_file)
            )
            results[pair] = result
        except Exception as e:
            print(f"\n⚠️  Error testing {pair}: {e}")
            results[pair] = {'error': str(e)}
    
    # Summary
    print("\n" + "="*80)
    print("MULTI-PAIR SUMMARY")
    print("="*80)
    
    passed_count = 0
    total_tested = 0
    
    for pair, result in results.items():
        if 'error' in result:
            print(f"\n{pair}: ❌ ERROR - {result['error']}")
        else:
            total_tested += 1
            mcpt = result['mcpt']
            status = "✓ PASS" if mcpt['passed'] else "✗ FAIL"
            
            if mcpt['passed']:
                passed_count += 1
            
            print(f"\n{pair}: {status}")
            print(f"  Real PF:    {mcpt['real_pf']:.4f}")
            print(f"  P-Value:    {mcpt['p_value']:.4f}")
            print(f"  Return:     {result['real_metrics']['total_return_pct']:.2f}%")
            print(f"  Sharpe:     {result['real_metrics']['sharpe_ratio']:.2f}")
            print(f"  Max DD:     {result['real_metrics']['max_drawdown_pct']:.2f}%")
    
    print(f"\n{'='*80}")
    print(f"FINAL RESULT: {passed_count}/{total_tested} pairs passed MCPT")
    print(f"{'='*80}")
    
    # Save results
    results_dir = Path(__file__).parent.parent / 'results'
    results_dir.mkdir(parents=True, exist_ok=True)
    
    with open(results_dir / 'forex_mcpt_real_data.json', 'w') as f:
        json.dump({
            'summary': {
                'pairs_tested': total_tested,
                'pairs_passed': passed_count,
                'pass_rate': passed_count / total_tested if total_tested > 0 else 0
            },
            'results': results
        }, f, indent=2)
    
    # Plot comparison
    if total_tested > 0:
        fig, axes = plt.subplots(2, 2, figsize=(16, 12))
        fig.patch.set_facecolor('#0d1117')
        
        for idx, (pair, result) in enumerate(results.items()):
            if 'error' in result:
                continue
            
            ax = axes[idx // 2, idx % 2]
            ax.set_facecolor('#0d1117')
            
            mcpt = result['mcpt']
            
            # Histogram
            ax.hist(mcpt['permuted_pfs'], bins=50, color='#58a6ff', alpha=0.7, 
                   edgecolor='white', label='Permutations')
            ax.axvline(mcpt['real_pf'], color='#f85149', linewidth=2.5, 
                      label=f'Real (PF={mcpt["real_pf"]:.3f})')
            
            status_color = '#3fb950' if mcpt['passed'] else '#f85149'
            status_text = 'PASS' if mcpt['passed'] else 'FAIL'
            
            ax.set_xlabel('Profit Factor', fontsize=11, color='white')
            ax.set_ylabel('Frequency', fontsize=11, color='white')
            ax.set_title(f'{pair} - P-Value: {mcpt["p_value"]:.4f} - {status_text}', 
                        fontsize=13, fontweight='bold', color=status_color)
            ax.legend(fontsize=10)
            ax.tick_params(colors='white')
            ax.grid(False)
            
            for spine in ax.spines.values():
                spine.set_color('white')
        
        plt.tight_layout()
        plt.savefig(results_dir / 'forex_mcpt_real_multipair.png', 
                   dpi=150, bbox_inches='tight', facecolor='#0d1117')
        
        print(f"\n📊 Visualization saved to {results_dir}/forex_mcpt_real_multipair.png")
    
    return results


if __name__ == '__main__':
    results = test_multiple_pairs()
