"""Market data loading with a hard cutoff at 2025-12-31 (no 2026 look-ahead)."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, List, Optional

import pandas as pd
import yfinance as yf

# Hard constraint: never load bars after this date for strategy development.
MAX_ALLOWED_DATE = pd.Timestamp("2025-12-31 23:59:59", tz="UTC")

PAIR_TICKERS = {
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "USDJPY": "USDJPY=X",
    "AUDUSD": "AUDUSD=X",
}

# Approximate OANDA retail spreads in price units (mid-market).
DEFAULT_SPREADS = {
    "EURUSD": 0.00013,
    "GBPUSD": 0.00015,
    "USDJPY": 0.015,
    "AUDUSD": 0.00014,
}

PIP_SIZES = {
    "EURUSD": 0.0001,
    "GBPUSD": 0.0001,
    "USDJPY": 0.01,
    "AUDUSD": 0.0001,
}


class DataHandler:
    """Fetch and cache OHLC data for major forex pairs."""

    def __init__(self, cache_dir: str | Path = "data/cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_path(self, symbol: str, interval: str, start: str, end: str) -> Path:
        safe = f"{symbol}_{interval}_{start}_{end}".replace("=", "").replace(":", "")
        return self.cache_dir / f"{safe}.parquet"

    @staticmethod
    def _normalize_ohlc(df: pd.DataFrame) -> pd.DataFrame:
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        rename = {c: c.title() for c in df.columns}
        df = df.rename(columns=rename)
        needed = ["Open", "High", "Low", "Close"]
        missing = [c for c in needed if c not in df.columns]
        if missing:
            raise ValueError(f"Missing OHLC columns: {missing}")
        out = df[needed].copy()
        if "Volume" in df.columns:
            out["Volume"] = df["Volume"]
        else:
            out["Volume"] = 0.0
        out = out.dropna(subset=needed)
        if out.index.tz is None:
            out.index = out.index.tz_localize("UTC")
        else:
            out.index = out.index.tz_convert("UTC")
        return out.sort_index()

    @staticmethod
    def _enforce_date_cap(df: pd.DataFrame, end: Optional[str] = None) -> pd.DataFrame:
        """Strip any accidental 2026+ bars and honor requested end date."""
        if df.empty:
            return df
        idx = df.index
        if idx.tz is None:
            idx = idx.tz_localize("UTC")
            df = df.copy()
            df.index = idx
        cap = MAX_ALLOWED_DATE
        if end is not None:
            end_ts = pd.Timestamp(end)
            if end_ts.tzinfo is None:
                end_ts = end_ts.tz_localize("UTC")
            else:
                end_ts = end_ts.tz_convert("UTC")
            # Make end inclusive through end-of-day UTC
            if end_ts.hour == 0 and end_ts.minute == 0 and end_ts.second == 0:
                end_ts = end_ts + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
            cap = min(cap, end_ts)
        return df[df.index <= cap].copy()

    def fetch_data(
        self,
        symbol: str,
        start: str,
        end: str,
        interval: str = "1d",
        use_cache: bool = True,
    ) -> pd.DataFrame:
        """
        Fetch OHLCV data for a Yahoo Finance symbol.

        Notes
        -----
        - Yahoo Finance forex history is most reliable on daily bars.
        - For intraday, yfinance only provides ~60 days of 1h/4h history.
          This project therefore uses daily bars for the 2020-2025 study window,
          optionally synthesizing a 4H-like series via forward-fill resampling
          only when explicitly requested with interval='4h_synth'.
        """
        def _naive(ts) -> pd.Timestamp:
            t = pd.Timestamp(ts)
            return t.tz_localize(None) if t.tzinfo is not None else t

        end_cap = min(_naive(end), _naive("2025-12-31"))
        end_str = end_cap.strftime("%Y-%m-%d")
        start_str = _naive(start).strftime("%Y-%m-%d")

        # Reject any request that tries to pull 2026 development data.
        if _naive(start) > _naive(MAX_ALLOWED_DATE):
            raise ValueError("Start date is after 2025-12-31; 2026 data is forbidden.")

        yf_interval = interval
        synth_4h = False
        if interval in {"4h", "4H"}:
            # Long-history 4H is unavailable from yfinance; use daily and note it.
            # Callers that need denser signals should use interval='1d'.
            yf_interval = "1d"
            synth_4h = False
        elif interval == "4h_synth":
            yf_interval = "1d"
            synth_4h = True

        cache_file = self._cache_path(symbol, interval, start_str, end_str)
        if use_cache and cache_file.exists():
            df = pd.read_parquet(cache_file)
            if df.index.tz is None:
                df.index = df.index.tz_localize("UTC")
            return self._enforce_date_cap(df, end_str)

        # yfinance `end` is exclusive for daily; add one day for inclusive end.
        yf_end = (end_cap + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        raw = yf.download(
            symbol,
            start=start_str,
            end=yf_end,
            interval=yf_interval,
            auto_adjust=True,
            progress=False,
            threads=False,
        )
        if raw is None or raw.empty:
            raise RuntimeError(f"No data returned for {symbol} ({start_str}..{end_str})")

        df = self._normalize_ohlc(raw)
        df = self._enforce_date_cap(df, end_str)

        if synth_4h and not df.empty:
            # Expand daily bars into 6x 4H placeholders (same OHLC) for session filters.
            df = df.resample("4h").ffill()
            df = self._enforce_date_cap(df, end_str)

        if use_cache and not df.empty:
            df.to_parquet(cache_file)

        return df

    def fetch_pair(
        self,
        pair: str,
        start: str = "2020-01-01",
        end: str = "2025-12-31",
        interval: str = "1d",
    ) -> pd.DataFrame:
        ticker = PAIR_TICKERS.get(pair.upper(), pair)
        df = self.fetch_data(ticker, start, end, interval=interval)
        df.attrs["pair"] = pair.upper().replace("=X", "")
        df.attrs["ticker"] = ticker
        return df

    def fetch_all_pairs(
        self,
        pairs: Optional[Iterable[str]] = None,
        start: str = "2020-01-01",
        end: str = "2025-12-31",
        interval: str = "1d",
    ) -> Dict[str, pd.DataFrame]:
        pairs = list(pairs or PAIR_TICKERS.keys())
        out: Dict[str, pd.DataFrame] = {}
        for pair in pairs:
            out[pair] = self.fetch_pair(pair, start=start, end=end, interval=interval)
        return out

    @staticmethod
    def assert_no_2026(df: pd.DataFrame, label: str = "dataset") -> None:
        if df.empty:
            return
        if (df.index > MAX_ALLOWED_DATE).any():
            raise AssertionError(f"{label} contains bars after 2025-12-31")
