"""Download and cache Dukascopy 4H forex bars (hard-capped at 2025-12-31, no 2026)."""

from __future__ import annotations

import json
import random
import string
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, Optional

import pandas as pd
import requests

MAX_ALLOWED = pd.Timestamp("2025-12-31 23:59:59", tz="UTC")
MIN_ALLOWED = pd.Timestamp("2018-01-01 00:00:00", tz="UTC")

PAIR_TO_INSTRUMENT = {
    "EURUSD": "EUR/USD",
    "GBPUSD": "GBP/USD",
    "USDJPY": "USD/JPY",
    "AUDUSD": "AUD/USD",
}


def _jsonp_name() -> str:
    return "_callbacks____" + "".join(random.choices(string.ascii_letters + string.digits, k=9))


def _fetch_chunk(
    instrument: str,
    last_update_ms: int,
    limit: int = 5000,
    offer_side: str = "B",
    interval: str = "4HOUR",
) -> list:
    jsonp = _jsonp_name()
    params = {
        "path": "chart/json3",
        "splits": "true",
        "stocks": "true",
        "time_direction": "N",
        "jsonp": jsonp,
        "last_update": str(int(last_update_ms)),
        "offer_side": offer_side,
        "instrument": instrument,
        "interval": interval,
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


def download_h4_pair(
    pair: str,
    start: str = "2020-01-01",
    end: str = "2025-12-31",
    cache_dir: str | Path = "data/cache/h4",
    force: bool = False,
) -> pd.DataFrame:
    """Download 4H OHLC for one pair, cached as parquet, capped at 2025-12-31."""
    pair = pair.upper()
    instrument = PAIR_TO_INSTRUMENT[pair]
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"{pair}_h4_2020_2025.parquet"

    start_ts = max(pd.Timestamp(start, tz="UTC"), MIN_ALLOWED)
    end_ts = min(pd.Timestamp(end, tz="UTC") + pd.Timedelta(days=1) - pd.Timedelta(seconds=1), MAX_ALLOWED)

    if cache_file.exists() and not force:
        df = pd.read_parquet(cache_file)
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC")
        else:
            df.index = df.index.tz_convert("UTC")
        df = df[(df.index >= start_ts) & (df.index <= end_ts)]
        if (df.index > MAX_ALLOWED).any():
            raise AssertionError(f"{pair} cache contains 2026+ bars")
        return df

    rows = []
    cursor_ms = int(start_ts.timestamp() * 1000)
    end_ms = int(end_ts.timestamp() * 1000)
    seen = set()
    stall = 0

    while cursor_ms <= end_ms and stall < 3:
        chunk = _fetch_chunk(instrument, cursor_ms, limit=5000)
        # API returns [ts, open, high? wait - from sample: [ts, open, close?, low?, high?, vol?]
        # Sample: [1577908800000, 1.1212, 1.12218, 1.12106, 1.12188, 2621.32]
        # Dukascopy json3 typically: [timestamp, open, close, low, high, volume] OR [ts,o,h,l,c,v]
        # Check: open=1.1212, next 1.12218 > open, next 1.12106 < open, next 1.12188 near open
        # That pattern is O,H,L,C (high>open, low<open, close near)
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
            # Detect OHLCV vs OCLHV: if item[2] < item[3] often, might be O,C,L,H
            # For safety: use high=max(o,h,l,c), low=min(...)
            hi = max(o, h, l, c)
            lo = min(o, h, l, c)
            # Prefer native if already ordered as OHLC
            if h >= max(o, c) and l <= min(o, c):
                hi, lo = h, l
            rows.append((pd.Timestamp(ts, unit="ms", tz="UTC"), o, hi, lo, c, v))
            useful += 1
            last_ts = ts

        if useful == 0 or last_ts is None:
            stall += 1
            cursor_ms += 4 * 3600 * 1000 * 50  # jump ahead ~50 bars
            time.sleep(0.2)
            continue

        stall = 0
        # Advance past last timestamp
        next_ms = last_ts + 1
        if next_ms <= cursor_ms:
            stall += 1
            cursor_ms += 4 * 3600 * 1000
        else:
            cursor_ms = next_ms
        time.sleep(0.15)

    if not rows:
        raise RuntimeError(f"No H4 data downloaded for {pair}")

    df = pd.DataFrame(rows, columns=["Date", "Open", "High", "Low", "Close", "Volume"]).set_index("Date")
    df = df[~df.index.duplicated(keep="last")].sort_index()
    df = df[(df.index >= start_ts) & (df.index <= end_ts)]
    if (df.index > MAX_ALLOWED).any():
        raise AssertionError("Downloaded bars after 2025-12-31")
    df.to_parquet(cache_file)
    return df


def download_all_h4(
    pairs: Optional[Iterable[str]] = None,
    start: str = "2020-01-01",
    end: str = "2025-12-31",
    cache_dir: str | Path = "data/cache/h4",
    force: bool = False,
) -> Dict[str, pd.DataFrame]:
    pairs = list(pairs or PAIR_TO_INSTRUMENT.keys())
    out = {}
    for pair in pairs:
        print(f"Downloading {pair} H4 {start}..{end} ...")
        df = download_h4_pair(pair, start=start, end=end, cache_dir=cache_dir, force=force)
        print(f"  {pair}: {len(df)} bars {df.index[0]} -> {df.index[-1]}")
        out[pair] = df
    return out


if __name__ == "__main__":
    download_all_h4()
