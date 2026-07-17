"""
Generate synthetic cryptocurrency price data for testing
Uses a geometric Brownian motion with realistic parameters
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path


def generate_crypto_ohlc(
    start_date: str = '2016-01-01',
    end_date: str = '2026-07-17',
    timeframe_hours: int = 1,
    initial_price: float = 500.0,
    annual_drift: float = 0.8,
    annual_vol: float = 0.80,
    seed: int = 42
) -> pd.DataFrame:
    """
    Generate synthetic OHLC data using geometric Brownian motion
    
    Args:
        start_date: Start date for data
        end_date: End date for data
        timeframe_hours: Hours per candle
        initial_price: Starting price
        annual_drift: Annual drift rate (0.8 = 80% per year)
        annual_vol: Annual volatility (0.8 = 80% annualized)
        seed: Random seed for reproducibility
        
    Returns:
        DataFrame with OHLC data
    """
    np.random.seed(seed)
    
    start = pd.to_datetime(start_date)
    end = pd.to_datetime(end_date)
    
    n_bars = int((end - start).total_seconds() / (3600 * timeframe_hours))
    
    print(f"Generating {n_bars} bars of synthetic data...")
    
    dt = timeframe_hours / (365.25 * 24)
    
    drift = annual_drift * dt
    vol = annual_vol * np.sqrt(dt)
    
    log_returns = np.random.normal(drift, vol, n_bars)
    
    log_returns[0] = 0
    
    log_prices = np.log(initial_price) + np.cumsum(log_returns)
    close_prices = np.exp(log_prices)
    
    intrabar_vol = vol * 0.3
    
    high_prices = close_prices * np.exp(np.abs(np.random.normal(0, intrabar_vol, n_bars)))
    low_prices = close_prices * np.exp(-np.abs(np.random.normal(0, intrabar_vol, n_bars)))
    
    open_prices = np.zeros(n_bars)
    open_prices[0] = initial_price
    open_prices[1:] = close_prices[:-1] * np.exp(np.random.normal(0, vol * 0.1, n_bars-1))
    
    high_prices = np.maximum.reduce([open_prices, high_prices, close_prices])
    low_prices = np.minimum.reduce([open_prices, low_prices, close_prices])
    
    timestamp_index = pd.date_range(start=start, periods=n_bars, freq=pd.Timedelta(hours=timeframe_hours))
    
    volume = np.random.lognormal(mean=10, sigma=0.5, size=n_bars)
    
    df = pd.DataFrame({
        'open': open_prices,
        'high': high_prices,
        'low': low_prices,
        'close': close_prices,
        'volume': volume
    }, index=timestamp_index)
    
    # Apply stronger trend multipliers
    bull_periods = [
        ('2017-01-01', '2017-11-30', 2.0),  # Strong 2017 bull
        ('2020-10-01', '2021-04-01', 1.8),  # 2020-2021 bull
        ('2024-01-01', '2024-12-31', 1.2),  # 2024 bull
        ('2025-01-01', '2025-12-31', 1.5),  # 2025 bull (forward test period)
    ]
    
    for start_bull, end_bull, strength in bull_periods:
        mask = (df.index >= start_bull) & (df.index <= end_bull)
        n_bull_bars = mask.sum()
        if n_bull_bars > 0:
            # Create a smoother trend
            bull_multiplier = np.exp(np.linspace(0, strength, n_bull_bars))
            # Apply only to the cumulative close prices to maintain trend
            df.loc[mask, 'close'] = df.loc[mask, 'close'].iloc[0] * bull_multiplier * (df.loc[mask, 'close'] / df.loc[mask, 'close'].iloc[0])
            df.loc[mask, 'open'] = df.loc[mask, 'close'].shift(1).fillna(df.loc[mask, 'close'].iloc[0])
            df.loc[mask, 'high'] = df.loc[mask, ['close', 'open']].max(axis=1) * 1.005
            df.loc[mask, 'low'] = df.loc[mask, ['close', 'open']].min(axis=1) * 0.995
    
    bear_periods = [
        ('2018-01-01', '2018-12-31', 0.7),  # 2018 bear
        ('2022-01-01', '2022-11-30', 0.8),  # 2022 bear
    ]
    
    for start_bear, end_bear, strength in bear_periods:
        mask = (df.index >= start_bear) & (df.index <= end_bear)
        n_bear_bars = mask.sum()
        if n_bear_bars > 0:
            bear_multiplier = np.exp(np.linspace(0, -strength, n_bear_bars))
            df.loc[mask, 'close'] = df.loc[mask, 'close'].iloc[0] * bear_multiplier * (df.loc[mask, 'close'] / df.loc[mask, 'close'].iloc[0])
            df.loc[mask, 'open'] = df.loc[mask, 'close'].shift(1).fillna(df.loc[mask, 'close'].iloc[0])
            df.loc[mask, 'high'] = df.loc[mask, ['close', 'open']].max(axis=1) * 1.005
            df.loc[mask, 'low'] = df.loc[mask, ['close', 'open']].min(axis=1) * 0.995
    
    return df


if __name__ == '__main__':
    data_dir = Path(__file__).parent
    
    df = generate_crypto_ohlc(
        start_date='2016-01-01',
        end_date='2026-07-17',
        timeframe_hours=1,
        initial_price=500.0,
        annual_drift=0.5,
        annual_vol=0.75,
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
            print(f"  {year}: {ret:+.1f}%")
