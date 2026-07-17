"""
Generate more realistic cryptocurrency price data with stronger trends
Uses regime-switching model to create distinct trending and ranging periods
"""
import pandas as pd
import numpy as np
from pathlib import Path


def generate_realistic_crypto(
    start_date: str = '2016-01-01',
    end_date: str = '2026-07-17',
    timeframe_hours: int = 1,
    initial_price: float = 500.0,
    seed: int = 42
) -> pd.DataFrame:
    """
    Generate synthetic crypto data with realistic trend/range regimes
    """
    np.random.seed(seed)
    
    start = pd.to_datetime(start_date)
    end = pd.to_datetime(end_date)
    
    n_bars = int((end - start).total_seconds() / (3600 * timeframe_hours))
    
    print(f"Generating {n_bars} bars of realistic crypto data...")
    
    timestamp_index = pd.date_range(start=start, periods=n_bars, freq=pd.Timedelta(hours=timeframe_hours))
    
    dt = timeframe_hours / (365.25 * 24)
    
    regimes = [
        ('2016-01-01', '2016-12-31', 'range', 0.0, 0.6),
        ('2017-01-01', '2017-12-17', 'bull', 2.5, 0.7),
        ('2017-12-18', '2018-12-31', 'bear', -1.5, 0.8),
        ('2019-01-01', '2019-12-31', 'range', 0.0, 0.5),
        ('2020-01-01', '2020-10-01', 'range', 0.0, 0.6),
        ('2020-10-01', '2021-04-01', 'bull', 2.0, 0.65),
        ('2021-04-01', '2021-11-01', 'bull', 1.5, 0.60),
        ('2021-11-01', '2022-12-31', 'bear', -1.0, 0.75),
        ('2023-01-01', '2023-12-31', 'range', 0.1, 0.55),
        ('2024-01-01', '2024-12-31', 'bull', 1.2, 0.65),
        ('2025-01-01', '2025-12-31', 'bull', 1.5, 0.70),
        ('2026-01-01', '2026-07-17', 'range', 0.2, 0.60),
    ]
    
    log_returns = np.zeros(n_bars)
    
    for start_regime, end_regime, regime_type, annual_drift, annual_vol in regimes:
        mask = (timestamp_index >= start_regime) & (timestamp_index <= end_regime)
        regime_indices = np.where(mask)[0]
        
        if len(regime_indices) == 0:
            continue
        
        start_idx = regime_indices[0]
        end_idx = regime_indices[-1]
        regime_len = end_idx - start_idx + 1
        
        drift = annual_drift * dt
        vol = annual_vol * np.sqrt(dt)
        
        if regime_type == 'bull':
            trend_strength = 0.7
            noise_strength = 0.3
        elif regime_type == 'bear':
            trend_strength = 0.7
            noise_strength = 0.3
        else:
            trend_strength = 0.2
            noise_strength = 0.8
        
        regime_returns = np.random.normal(drift, vol, regime_len)
        
        if regime_type in ['bull', 'bear']:
            trend = np.linspace(0, drift * regime_len / 2, regime_len)
            regime_returns = trend_strength * trend + noise_strength * regime_returns
        
        log_returns[start_idx:end_idx+1] = regime_returns
    
    log_prices = np.log(initial_price) + np.cumsum(log_returns)
    close_prices = np.exp(log_prices)
    
    intrabar_vol = 0.005
    
    high_prices = close_prices * (1 + np.abs(np.random.normal(0, intrabar_vol, n_bars)))
    low_prices = close_prices * (1 - np.abs(np.random.normal(0, intrabar_vol, n_bars)))
    
    open_prices = np.zeros(n_bars)
    open_prices[0] = initial_price
    open_prices[1:] = close_prices[:-1] * np.exp(np.random.normal(0, intrabar_vol * 0.5, n_bars-1))
    
    high_prices = np.maximum.reduce([open_prices, high_prices, close_prices])
    low_prices = np.minimum.reduce([open_prices, low_prices, close_prices])
    
    volume = np.random.lognormal(mean=10, sigma=0.5, size=n_bars)
    
    df = pd.DataFrame({
        'open': open_prices,
        'high': high_prices,
        'low': low_prices,
        'close': close_prices,
        'volume': volume
    }, index=timestamp_index)
    
    return df


if __name__ == '__main__':
    data_dir = Path(__file__).parent
    
    df = generate_realistic_crypto(
        start_date='2016-01-01',
        end_date='2026-07-17',
        timeframe_hours=1,
        initial_price=500.0,
        seed=42
    )
    
    save_path = data_dir / 'BTCUSDT_1h.parquet'
    df.to_parquet(save_path)
    
    print(f"\nGenerated {len(df)} bars")
    print(f"Date range: {df.index[0]} to {df.index[-1]}")
    print(f"Price range: ${df['close'].min():.2f} to ${df['close'].max():.2f}")
    print(f"Saved to {save_path}")
    
    print("\nFirst few rows:")
    print(df.head())
    
    print("\nLast few rows:")
    print(df.tail())
    
    print("\nAnnual returns by year:")
    for year in range(2016, 2027):
        year_data = df[df.index.year == year]
        if len(year_data) > 0:
            start_price = year_data['close'].iloc[0]
            end_price = year_data['close'].iloc[-1]
            ret = (end_price / start_price - 1) * 100
            regime_info = ""
            if year in [2017, 2020, 2021, 2024, 2025]:
                regime_info = " (Bull)"
            elif year in [2018, 2022]:
                regime_info = " (Bear)"
            else:
                regime_info = " (Range)"
            print(f"  {year}: {ret:+7.1f}%{regime_info}")
