"""
Data fetching module for cryptocurrency OHLC data
Uses ccxt library to fetch historical data from various exchanges
"""
import pandas as pd
import numpy as np
from pathlib import Path
import ccxt
from datetime import datetime, timedelta


def fetch_binance_data(
    symbol: str = 'BTC/USDT',
    timeframe: str = '1h',
    start_date: str = '2016-01-01',
    end_date: str = '2026-07-17',
    save_path: str = None
) -> pd.DataFrame:
    """
    Fetch OHLC data from Binance
    
    Args:
        symbol: Trading pair (e.g., 'BTC/USDT')
        timeframe: Candle timeframe ('1h', '4h', '1d', etc.)
        start_date: Start date in 'YYYY-MM-DD' format
        end_date: End date in 'YYYY-MM-DD' format
        save_path: Optional path to save the data
        
    Returns:
        DataFrame with columns ['open', 'high', 'low', 'close', 'volume']
    """
    exchange = ccxt.binance({
        'enableRateLimit': True,
        'options': {'defaultType': 'spot'}
    })
    
    since = exchange.parse8601(f'{start_date}T00:00:00Z')
    end_ts = exchange.parse8601(f'{end_date}T23:59:59Z')
    
    timeframe_ms = exchange.parse_timeframe(timeframe) * 1000
    
    all_ohlcv = []
    
    print(f"Fetching {symbol} {timeframe} data from {start_date} to {end_date}...")
    
    while since < end_ts:
        try:
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe, since, limit=1000)
            
            if not ohlcv:
                break
            
            all_ohlcv.extend(ohlcv)
            since = ohlcv[-1][0] + timeframe_ms
            
            print(f"Fetched up to {datetime.fromtimestamp(since/1000).strftime('%Y-%m-%d')}", end='\r')
            
        except Exception as e:
            print(f"\nError fetching data: {e}")
            break
    
    print(f"\nTotal candles fetched: {len(all_ohlcv)}")
    
    df = pd.DataFrame(
        all_ohlcv, 
        columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
    )
    
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df.set_index('timestamp', inplace=True)
    
    df = df[(df.index >= start_date) & (df.index <= end_date)]
    
    if save_path:
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(save_path)
        print(f"Saved to {save_path}")
    
    return df


def load_data(path: str) -> pd.DataFrame:
    """Load OHLC data from parquet file"""
    df = pd.read_parquet(path)
    return df


def split_data_by_year(
    df: pd.DataFrame,
    train_start: int = 2016,
    train_end: int = 2024,
    test_start: int = 2025,
    test_end: int = 2026
):
    """
    Split data into training and testing periods
    
    Args:
        df: DataFrame with datetime index
        train_start: Start year for training (inclusive)
        train_end: End year for training (inclusive)
        test_start: Start year for testing (inclusive)
        test_end: End year for testing (inclusive)
        
    Returns:
        Tuple of (train_df, test_df)
    """
    train_df = df[
        (df.index.year >= train_start) & 
        (df.index.year <= train_end)
    ].copy()
    
    test_df = df[
        (df.index.year >= test_start) & 
        (df.index.year <= test_end)
    ].copy()
    
    print(f"Training data: {train_df.index[0]} to {train_df.index[-1]} ({len(train_df)} bars)")
    print(f"Testing data: {test_df.index[0]} to {test_df.index[-1]} ({len(test_df)} bars)")
    
    return train_df, test_df


if __name__ == '__main__':
    data_dir = Path(__file__).parent
    
    df = fetch_binance_data(
        symbol='BTC/USDT',
        timeframe='1h',
        start_date='2016-01-01',
        end_date='2026-07-17',
        save_path=str(data_dir / 'BTCUSDT_1h.parquet')
    )
    
    print("\nData shape:", df.shape)
    print(df.head())
    print(df.tail())
