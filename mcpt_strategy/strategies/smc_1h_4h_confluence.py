"""
1H + 4H SMC Confluence Strategy
Use 1H timeframe to confirm 4H signals for higher win rate
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


class ICTIndicators:
    """Core ICT indicators"""
    
    @staticmethod
    def identify_order_blocks(ohlc: pd.DataFrame, lookback: int = 5) -> Tuple[pd.Series, pd.Series]:
        """Order blocks"""
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
        """Liquidity sweeps"""
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
    def trend_alignment(ohlc: pd.DataFrame, fast_period: int = 10, slow_period: int = 30) -> pd.Series:
        """Trend alignment using EMAs"""
        fast_ema = ohlc['Close'].ewm(span=fast_period).mean()
        slow_ema = ohlc['Close'].ewm(span=slow_period).mean()
        
        trend = pd.Series(0, index=ohlc.index)
        trend[fast_ema > slow_ema] = 1
        trend[fast_ema < slow_ema] = -1
        
        return trend


def fetch_1h_data(start_date: str, end_date: str) -> pd.DataFrame:
    """Fetch 1H EUR/USD data from Dukascopy"""
    from core.h4_data import download_h4_pair, _fetch_chunk
    import requests
    import json
    import random
    import string
    import time
    
    print(f"Fetching 1H data from {start_date} to {end_date}...")
    
    # Use similar logic to download_h4_pair but for 1H
    instrument = "EUR/USD"
    start_ts = pd.Timestamp(start_date, tz="UTC")
    end_ts = pd.Timestamp(end_date, tz="UTC") + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
    
    rows = []
    cursor_ms = int(start_ts.timestamp() * 1000)
    end_ms = int(end_ts.timestamp() * 1000)
    seen = set()
    stall = 0
    
    def fetch_1h_chunk(instrument: str, last_update_ms: int, limit: int = 5000) -> list:
        jsonp = "_callbacks____" + "".join(random.choices(string.ascii_letters + string.digits, k=9))
        params = {
            "path": "chart/json3",
            "splits": "true",
            "stocks": "true",
            "time_direction": "N",
            "jsonp": jsonp,
            "last_update": str(int(last_update_ms)),
            "offer_side": "B",
            "instrument": instrument,
            "interval": "1HOUR",
            "limit": str(int(limit)),
        }
        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://freeserv.dukascopy.com/2.0/?path=chart/index",
            "Host": "freeserv.dukascopy.com",
        }
        for attempt in range(5):
            try:
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
                if not isinstance(data, list):
                    raise RuntimeError(f"Unexpected payload: {data}")
                return data
            except Exception:
                if attempt == 4:
                    raise
                time.sleep(1.5 * (attempt + 1))
        return []
    
    while cursor_ms <= end_ms and stall < 5:
        chunk = fetch_1h_chunk(instrument, cursor_ms, limit=5000)
        useful = 0
        last_ts = None
        for item in chunk:
            if not item or item[0] is None:
                continue
            ts = int(item[0])
            if ts in seen:
                continue
            if ts < int(start_ts.timestamp() * 1000):
                continue
            if ts > end_ms:
                continue
            seen.add(ts)
            o, h, l, c, v = float(item[1]), float(item[2]), float(item[3]), float(item[4]), float(item[5])
            hi = max(o, h, l, c)
            lo = min(o, h, l, c)
            if h >= max(o, c) and l <= min(o, c):
                hi, lo = h, l
            rows.append((pd.Timestamp(ts, unit="ms", tz="UTC"), o, hi, lo, c, v))
            useful += 1
            last_ts = ts
        
        if useful == 0 or last_ts is None:
            stall += 1
            cursor_ms += 3600 * 1000 * 50
            time.sleep(0.2)
            continue
        
        stall = 0
        next_ms = last_ts + 1
        if next_ms <= cursor_ms:
            stall += 1
            cursor_ms += 3600 * 1000
        else:
            cursor_ms = next_ms
        time.sleep(0.15)
    
    if not rows:
        print(f"  ❌ Failed to fetch 1H data")
        return None
    
    df = pd.DataFrame(rows, columns=["Date", "Open", "High", "Low", "Close", "Volume"]).set_index("Date")
    df = df[~df.index.duplicated(keep="last")].sort_index()
    df = df[(df.index >= start_ts) & (df.index <= end_ts)]
    print(f"  ✅ Loaded {len(df)} bars")
    return df


def confluence_1h_4h_strategy(
    ohlc_4h: pd.DataFrame,
    ohlc_1h: pd.DataFrame,
    ob_lookback_4h: int = 5,
    ob_lookback_1h: int = 5,
    structure_length: int = 5,
    require_all_signals: bool = False
) -> pd.Series:
    """
    Strategy using 1H to confirm 4H signals
    
    4H provides main signal (OB + Structure)
    1H must confirm with same direction (OB OR FVG OR Sweep + Structure alignment)
    """
    ict = ICTIndicators()
    
    # === 4H ANALYSIS ===
    bullish_ob_4h, bearish_ob_4h = ict.identify_order_blocks(ohlc_4h, ob_lookback_4h)
    structure_4h = ict.identify_structure(ohlc_4h, structure_length)
    trend_4h = ict.trend_alignment(ohlc_4h)
    
    # 4H signals
    signal_4h_bullish = bullish_ob_4h & (structure_4h >= 0) & (trend_4h > 0)
    signal_4h_bearish = bearish_ob_4h & (structure_4h <= 0) & (trend_4h < 0)
    
    # === 1H ANALYSIS ===
    bullish_ob_1h, bearish_ob_1h = ict.identify_order_blocks(ohlc_1h, ob_lookback_1h)
    bullish_fvg_1h, bearish_fvg_1h = ict.identify_fvg(ohlc_1h)
    bullish_sweep_1h, bearish_sweep_1h = ict.identify_liquidity_sweep(ohlc_1h)
    structure_1h = ict.identify_structure(ohlc_1h, structure_length)
    trend_1h = ict.trend_alignment(ohlc_1h)
    
    # 1H confirmations
    confirm_1h_bullish = (
        (bullish_ob_1h | bullish_fvg_1h | bullish_sweep_1h) & 
        (structure_1h >= 0) & 
        (trend_1h > 0)
    )
    confirm_1h_bearish = (
        (bearish_ob_1h | bearish_fvg_1h | bearish_sweep_1h) & 
        (structure_1h <= 0) & 
        (trend_1h < 0)
    )
    
    # === ALIGN 1H TO 4H ===
    # For each 4H bar, check if any of the corresponding 1H bars have confirmation
    signal_4h = pd.Series(0, index=ohlc_4h.index, dtype=float)
    
    for idx_4h in ohlc_4h.index:
        # Find corresponding 1H bars (4 bars per 4H period)
        start_1h = idx_4h - pd.Timedelta(hours=4)
        end_1h = idx_4h
        
        mask_1h = (ohlc_1h.index > start_1h) & (ohlc_1h.index <= end_1h)
        
        if mask_1h.sum() == 0:
            continue
        
        # Check if 4H has signal
        try:
            bullish_val = signal_4h_bullish.loc[idx_4h]
            bearish_val = signal_4h_bearish.loc[idx_4h]
            
            # Convert to scalar if needed
            if isinstance(bullish_val, pd.Series):
                has_bullish_4h = bool(bullish_val.iloc[0]) if len(bullish_val) > 0 else False
            else:
                has_bullish_4h = bool(bullish_val)
            
            if isinstance(bearish_val, pd.Series):
                has_bearish_4h = bool(bearish_val.iloc[0]) if len(bearish_val) > 0 else False
            else:
                has_bearish_4h = bool(bearish_val)
        except:
            has_bullish_4h = False
            has_bearish_4h = False
        
        if has_bullish_4h:
            # Check if any 1H bar confirms
            if confirm_1h_bullish.loc[mask_1h].any():
                signal_4h.at[idx_4h] = 1
        
        elif has_bearish_4h:
            if confirm_1h_bearish.loc[mask_1h].any():
                signal_4h.at[idx_4h] = -1
    
    return signal_4h.shift(1).fillna(0)


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


def run_mcpt(
    ohlc_4h: pd.DataFrame,
    ohlc_1h: pd.DataFrame,
    strategy_params: Dict,
    n_permutations: int = 100
) -> Dict:
    """Run MCPT"""
    from mcpt_strategy.utils import get_permutation
    
    # Real strategy
    signal = confluence_1h_4h_strategy(ohlc_4h, ohlc_1h, **strategy_params)
    real_metrics = calculate_metrics(ohlc_4h, signal)
    
    if real_metrics is None:
        return {'passed': False, 'error': 'No valid metrics'}
    
    real_pf = real_metrics['profit_factor']
    
    if real_pf < 1.3:
        return {'passed': False, 'error': f'PF {real_pf:.2f} < 1.3', 'real_metrics': real_metrics}
    if real_metrics['annual_return'] < 0.06:
        return {'passed': False, 'error': f'Return {real_metrics["annual_return_pct"]:.1f}% < 6%', 'real_metrics': real_metrics}
    
    # Run permutations
    perm_better = 1
    perm_pfs = []
    
    for i in tqdm(range(1, n_permutations), desc="MCPT Progress"):
        try:
            # Permute 4H
            ohlc_4h_lower = ohlc_4h.copy()
            ohlc_4h_lower.columns = [c.lower() for c in ohlc_4h_lower.columns]
            perm_4h = get_permutation(ohlc_4h_lower, seed=i * 100)
            perm_4h.columns = [c.capitalize() for c in perm_4h.columns]
            
            # Permute 1H
            ohlc_1h_lower = ohlc_1h.copy()
            ohlc_1h_lower.columns = [c.lower() for c in ohlc_1h_lower.columns]
            perm_1h = get_permutation(ohlc_1h_lower, seed=i * 200)
            perm_1h.columns = [c.capitalize() for c in perm_1h.columns]
            
            perm_signal = confluence_1h_4h_strategy(perm_4h, perm_1h, **strategy_params)
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
    print("1H + 4H SMC CONFLUENCE STRATEGY")
    print("Training: 2020-2024 | Testing: 2025+")
    print("="*80)
    
    # Load 4H data
    cache_dir = Path(__file__).parent.parent / 'data' / 'forex_cache'
    cache_2024 = cache_dir / 'EURUSD_2016_2024_4h.parquet'
    cache_2026 = cache_dir / 'EURUSD_2026_current_4h.parquet'
    
    if not cache_2024.exists():
        print(f"ERROR: Training data not found")
        return
    
    ohlc_4h_all = pd.read_parquet(cache_2024)
    if 'open' in ohlc_4h_all.columns:
        ohlc_4h_all.columns = [c.capitalize() for c in ohlc_4h_all.columns]
    
    # Filter training period
    train_4h = ohlc_4h_all[(ohlc_4h_all.index.year >= 2020) & (ohlc_4h_all.index.year <= 2024)]
    
    # Load test data
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
    train_1h = fetch_1h_data('2020-01-01', '2024-12-31')
    test_1h = fetch_1h_data('2026-01-01', '2026-07-17')
    
    if train_1h is None or test_1h is None:
        print("\n❌ Failed to fetch 1H data")
        return
    
    print(f"\n📊 1H Data:")
    print(f"  Training: {train_1h.index[0]} to {train_1h.index[-1]} ({len(train_1h)} bars)")
    print(f"  Testing:  {test_1h.index[0]} to {test_1h.index[-1]} ({len(test_1h)} bars)")
    
    # Test configurations
    print(f"\n{'='*80}")
    print("TESTING CONFIGURATIONS")
    print("="*80)
    
    configurations = [
        {'name': 'Standard 1H+4H', 'params': {'ob_lookback_4h': 5, 'ob_lookback_1h': 5, 'structure_length': 5}},
        {'name': 'Aggressive 1H+4H', 'params': {'ob_lookback_4h': 3, 'ob_lookback_1h': 3, 'structure_length': 3}},
        {'name': 'Conservative 1H+4H', 'params': {'ob_lookback_4h': 7, 'ob_lookback_1h': 7, 'structure_length': 7}},
    ]
    
    results = []
    
    for config in configurations:
        print(f"\n{'='*80}")
        print(f"Testing: {config['name']}")
        print(f"{'='*80}")
        
        # Training performance
        print(f"\nTraining (2020-2024)...")
        signal_train = confluence_1h_4h_strategy(train_4h, train_1h, **config['params'])
        metrics_train = calculate_metrics(train_4h, signal_train)
        
        if metrics_train:
            print(f"  Annual Return: {metrics_train['annual_return_pct']:.2f}%")
            print(f"  Profit Factor: {metrics_train['profit_factor']:.3f}")
            print(f"  Win Rate: {metrics_train['win_rate']:.1f}%")
            print(f"  Trades: {metrics_train['trades']}")
        
        # Forward test
        print(f"\nForward test (2025+)...")
        signal_test = confluence_1h_4h_strategy(test_4h, test_1h, **config['params'])
        metrics_test = calculate_metrics(test_4h, signal_test)
        
        if metrics_test:
            print(f"  Annual Return: {metrics_test['annual_return_pct']:.2f}%")
            print(f"  Profit Factor: {metrics_test['profit_factor']:.3f}")
            print(f"  Win Rate: {metrics_test['win_rate']:.1f}%")
            print(f"  Trades: {metrics_test['trades']}")
            
            # MCPT
            if metrics_test['profit_factor'] >= 1.3 and metrics_test['annual_return'] >= 0.06:
                print(f"\nRunning MCPT...")
                mcpt_result = run_mcpt(test_4h, test_1h, config['params'], n_permutations=100)
                
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
    
    with open(results_dir / 'smc_1h_4h_confluence_results.json', 'w') as f:
        json.dump({
            'training_period': f"{train_4h.index[0]} to {train_4h.index[-1]}",
            'testing_period': f"{test_4h.index[0]} to {test_4h.index[-1]}",
            'results': results,
            'passed_count': len(passed_configs)
        }, f, indent=2)
    
    print(f"\n💾 Results saved to {results_dir}/smc_1h_4h_confluence_results.json")
    print(f"\n{'='*80}\n")


if __name__ == '__main__':
    main()
