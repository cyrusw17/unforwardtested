"""
Export EUR/USD 4H data to CSV format for TradingView import
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))

import pandas as pd

def export_to_csv():
    """Export all EUR/USD data to CSV"""
    
    cache_dir = Path(__file__).parent / 'forex_cache'
    
    # Load 2016-2024 data
    file_2016_2024 = cache_dir / 'EURUSD_2016_2024_4h.parquet'
    
    if not file_2016_2024.exists():
        print(f"Error: Data not found at {file_2016_2024}")
        return
    
    print("Loading EUR/USD data...")
    df = pd.read_parquet(file_2016_2024)
    
    # Normalize column names to lowercase
    df.columns = [c.lower() for c in df.columns]
    
    # Add volume column if not present (TradingView requires it)
    if 'volume' not in df.columns:
        df['volume'] = 0
    
    # Reset index to make timestamp a column
    df = df.reset_index()
    df = df.rename(columns={'timestamp': 'date'})
    
    # Format date as YYYY-MM-DD HH:MM:SS
    df['date'] = df['date'].dt.strftime('%Y-%m-%d %H:%M:%S')
    
    # Select and order columns
    df = df[['date', 'open', 'high', 'low', 'close', 'volume']]
    
    # Save to CSV
    output_file = cache_dir / 'EURUSD_4H.csv'
    df.to_csv(output_file, index=False)
    
    print(f"\n✅ Exported {len(df)} bars to: {output_file}")
    print(f"   Period: {df['date'].iloc[0]} to {df['date'].iloc[-1]}")
    print(f"   Size: {output_file.stat().st_size / 1024 / 1024:.2f} MB")
    
    # Also create a smaller sample for quick testing (last 2 years)
    df_sample = df.tail(4000)  # ~2 years of 4H data
    sample_file = cache_dir / 'EURUSD_4H_sample.csv'
    df_sample.to_csv(sample_file, index=False)
    
    print(f"\n✅ Sample (last 2 years): {sample_file}")
    print(f"   Period: {df_sample['date'].iloc[0]} to {df_sample['date'].iloc[-1]}")
    print(f"   Bars: {len(df_sample)}")
    
    # Print first few rows as example
    print(f"\n📋 First 5 rows (example):")
    print(df.head(5).to_string(index=False))
    
    return output_file, sample_file


if __name__ == '__main__':
    export_to_csv()
