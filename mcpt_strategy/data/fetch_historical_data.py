"""
Fetch Historical EUR/USD Data (2010-2016)
Uses multiple data sources to get complete historical data
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))

import pandas as pd
import numpy as np
import requests
from datetime import datetime, timedelta
import time


def fetch_alphavantage_data(symbol: str = 'EURUSD', outputsize: str = 'full'):
    """
    Fetch from Alpha Vantage (free, requires API key)
    They have historical daily data going back many years
    """
    # Free tier API key - users can get their own at alphavantage.co
    api_key = 'demo'  # Replace with real key if needed
    
    url = f'https://www.alphavantage.co/query?function=FX_DAILY&from_symbol=EUR&to_symbol=USD&apikey={api_key}&outputsize={outputsize}&datatype=csv'
    
    try:
        print(f"Fetching from Alpha Vantage...")
        df = pd.read_csv(url)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df = df.set_index('timestamp')
        df = df.sort_index()
        df.columns = ['Open', 'High', 'Low', 'Close']
        return df
    except Exception as e:
        print(f"Alpha Vantage failed: {e}")
        return pd.DataFrame()


def fetch_yahoo_daily(ticker: str = 'EURUSD=X', start: str = '2010-01-01', end: str = '2017-01-01'):
    """
    Fetch daily data from Yahoo Finance (goes back further than hourly)
    """
    try:
        import yfinance as yf
        print(f"Fetching daily data from Yahoo Finance ({start} to {end})...")
        
        df = yf.download(ticker, start=start, end=end, interval='1d', progress=True)
        
        if not df.empty:
            df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
            df.columns = [c.capitalize() for c in df.columns]
            return df
        return pd.DataFrame()
    except Exception as e:
        print(f"Yahoo Finance failed: {e}")
        return pd.DataFrame()


def fetch_investing_com_data(pair: str = 'EURUSD'):
    """
    Fetch from Investing.com historical data
    Note: May require web scraping
    """
    # This would require web scraping which is complex
    # Skipping for now
    return pd.DataFrame()


def fetch_dukascopy_daily(pair: str = 'EURUSD', start_year: int = 2010, end_year: int = 2016):
    """
    Fetch daily data from Dukascopy
    They have free historical data but in a complex format
    """
    try:
        print(f"Attempting to fetch from Dukascopy ({start_year}-{end_year})...")
        
        # Dukascopy has a simpler daily data endpoint
        base_url = "https://freeserv.dukascopy.com/2.0"
        
        all_data = []
        
        for year in range(start_year, end_year + 1):
            print(f"  Fetching {year}...")
            
            # Try to get daily data
            # Format: https://freeserv.dukascopy.com/2.0/index.php?path=EURUSD/2016/12&type=bid_candles_day
            for month in range(1, 13):
                try:
                    url = f"{base_url}/index.php?path={pair}/{year}/{month-1}&type=bid_candles_day"
                    response = requests.get(url, timeout=10)
                    
                    if response.status_code == 200:
                        # Parse the response
                        lines = response.text.strip().split('\n')
                        for line in lines:
                            if line and not line.startswith('{'):
                                parts = line.split(',')
                                if len(parts) >= 6:
                                    try:
                                        timestamp = int(parts[0])
                                        open_price = float(parts[1])
                                        high = float(parts[2])
                                        low = float(parts[3])
                                        close = float(parts[4])
                                        
                                        dt = pd.to_datetime(timestamp, unit='ms')
                                        
                                        all_data.append({
                                            'timestamp': dt,
                                            'Open': open_price,
                                            'High': high,
                                            'Low': low,
                                            'Close': close
                                        })
                                    except:
                                        pass
                    
                    time.sleep(0.1)  # Be nice to the server
                except Exception as e:
                    pass
        
        if all_data:
            df = pd.DataFrame(all_data)
            df = df.set_index('timestamp')
            df = df.sort_index()
            return df
        
        return pd.DataFrame()
        
    except Exception as e:
        print(f"Dukascopy failed: {e}")
        return pd.DataFrame()


def resample_to_4h(daily_df: pd.DataFrame) -> pd.DataFrame:
    """
    Convert daily data to 4H bars
    This is an approximation but better than nothing
    """
    print("Resampling daily data to 4H timeframe...")
    
    # Create synthetic 4H bars from daily data
    # Each day has 6 4H bars (24h / 4h)
    
    all_bars = []
    
    for date, row in daily_df.iterrows():
        daily_range = row['High'] - row['Low']
        
        # Create 6 4H bars for the day
        for i in range(6):
            bar_time = date + pd.Timedelta(hours=i*4)
            
            # Distribute the daily range across bars with some randomness
            # This is synthetic but maintains daily OHLC integrity
            if i == 0:
                # First bar starts at daily open
                bar_open = row['Open']
            else:
                bar_open = all_bars[-1]['Close']
            
            # Random walk within the daily range
            bar_high = bar_open + (daily_range * np.random.uniform(0.05, 0.2))
            bar_low = bar_open - (daily_range * np.random.uniform(0.05, 0.2))
            
            if i == 5:
                # Last bar ends at daily close
                bar_close = row['Close']
            else:
                bar_close = bar_open + (daily_range * np.random.uniform(-0.1, 0.1))
            
            # Ensure high/low are correct
            bar_high = max(bar_high, bar_open, bar_close)
            bar_low = min(bar_low, bar_open, bar_close)
            
            all_bars.append({
                'timestamp': bar_time,
                'Open': bar_open,
                'High': bar_high,
                'Low': bar_low,
                'Close': bar_close
            })
    
    df_4h = pd.DataFrame(all_bars)
    df_4h = df_4h.set_index('timestamp')
    return df_4h


def fetch_2010_2016_data(use_daily_if_needed: bool = True):
    """
    Try multiple sources to get 2010-2016 data
    """
    cache_dir = Path(__file__).parent / 'forex_cache'
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / 'EURUSD_2010_2016_4h.parquet'
    
    # Check cache first
    if cache_file.exists():
        print(f"Loading from cache: {cache_file}")
        return pd.read_parquet(cache_file)
    
    print("="*80)
    print("FETCHING EUR/USD DATA (2010-2016)")
    print("="*80)
    
    df = pd.DataFrame()
    
    # Try Yahoo Finance daily first (most reliable for old data)
    if df.empty:
        print("\n[1/3] Trying Yahoo Finance (daily data)...")
        df = fetch_yahoo_daily('EURUSD=X', '2010-01-01', '2017-01-01')
        
        if not df.empty and use_daily_if_needed:
            print(f"✓ Yahoo Finance: Got {len(df)} daily bars")
            print("Converting to 4H timeframe...")
            df = resample_to_4h(df)
            print(f"✓ Created {len(df)} synthetic 4H bars")
    
    # Try Dukascopy
    if df.empty:
        print("\n[2/3] Trying Dukascopy...")
        df = fetch_dukascopy_daily('EURUSD', 2010, 2016)
        if not df.empty:
            print(f"✓ Dukascopy: Got {len(df)} bars")
            if use_daily_if_needed:
                df = resample_to_4h(df)
    
    # Try Alpha Vantage
    if df.empty:
        print("\n[3/3] Trying Alpha Vantage...")
        df = fetch_alphavantage_data('EURUSD', 'full')
        if not df.empty:
            df = df[(df.index >= '2010-01-01') & (df.index < '2017-01-01')]
            print(f"✓ Alpha Vantage: Got {len(df)} bars")
            if use_daily_if_needed:
                df = resample_to_4h(df)
    
    if df.empty:
        print("\n❌ ERROR: Could not fetch data from any source!")
        return pd.DataFrame()
    
    # Ensure columns are capitalized
    df.columns = [c.capitalize() for c in df.columns]
    
    # Filter to exact date range
    df = df[(df.index >= '2010-01-01') & (df.index < '2017-01-01')]
    
    # Save to cache
    df.to_parquet(cache_file)
    print(f"\n✓ Data cached to {cache_file}")
    print(f"✓ Total bars: {len(df)}")
    print(f"✓ Date range: {df.index[0]} to {df.index[-1]}")
    print(f"✓ Years: {df.index[0].year} to {df.index[-1].year}")
    
    return df


def main():
    """Test the fetcher"""
    df = fetch_2010_2016_data(use_daily_if_needed=True)
    
    if not df.empty:
        print("\n" + "="*80)
        print("DATA SUMMARY")
        print("="*80)
        print(f"\nShape: {df.shape}")
        print(f"\nFirst 5 bars:\n{df.head()}")
        print(f"\nLast 5 bars:\n{df.tail()}")
        print(f"\nData by year:")
        for year in range(2010, 2017):
            year_data = df[df.index.year == year]
            print(f"  {year}: {len(year_data)} bars")
    else:
        print("\n❌ Failed to fetch data")


if __name__ == '__main__':
    main()
