#!/usr/bin/env python3
"""Full-period backtest for the all-era locked strategy (2018-2025 H4)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.all_era_signals import AllEraConfig, allocation_map, build_signal_frames
from core.backtest import Backtester

HERE = Path(__file__).resolve().parent
CACHE = ROOT / "data" / "cache" / "h4_2018_2025"


def load_config() -> AllEraConfig:
    data = json.loads((HERE / "config.json").read_text())
    known = AllEraConfig().__dict__.keys()
    return AllEraConfig(**{k: v for k, v in data.items() if k in known})


def load_pairs() -> dict:
    out = {}
    for p in ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD"]:
        path = CACHE / f"{p}_h4_2018_2025.parquet"
        if not path.exists():
            # fallback: download via h4 helper into extended cache
            import core.h4_data as h4
            import time

            CACHE.mkdir(parents=True, exist_ok=True)
            instrument = h4.PAIR_TO_INSTRUMENT[p]
            start_ts = pd.Timestamp("2018-01-01", tz="UTC")
            end_ts = pd.Timestamp("2025-12-31 23:59:59", tz="UTC")
            rows = []
            cursor_ms = int(start_ts.timestamp() * 1000)
            end_ms = int(end_ts.timestamp() * 1000)
            seen = set()
            stall = 0
            while cursor_ms <= end_ms and stall < 3:
                chunk = h4._fetch_chunk(instrument, cursor_ms, limit=5000)
                useful = 0
                last_ts = None
                for item in chunk:
                    if not item or item[0] is None:
                        continue
                    ts = int(item[0])
                    if ts in seen or ts < int(start_ts.timestamp() * 1000) or ts > end_ms:
                        continue
                    seen.add(ts)
                    o, a, b, c, v = map(float, item[1:6])
                    hi, lo = max(o, a, b, c), min(o, a, b, c)
                    if a >= max(o, c) and b <= min(o, c):
                        hi, lo = a, b
                    rows.append((pd.Timestamp(ts, unit="ms", tz="UTC"), o, hi, lo, c, v))
                    useful += 1
                    last_ts = ts
                if useful == 0 or last_ts is None:
                    stall += 1
                    cursor_ms += 4 * 3600 * 1000 * 50
                    time.sleep(0.2)
                    continue
                stall = 0
                cursor_ms = last_ts + 1 if last_ts + 1 > cursor_ms else cursor_ms + 4 * 3600 * 1000
                time.sleep(0.12)
            df = pd.DataFrame(rows, columns=["Date", "Open", "High", "Low", "Close", "Volume"]).set_index("Date")
            df = df[~df.index.duplicated(keep="last")].sort_index()
            df.to_parquet(path)
        else:
            df = pd.read_parquet(path)
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC")
        assert df.index.max().year <= 2025
        out[p] = df
    return out


def main():
    cfg = load_config()
    pairs = load_pairs()
    meta = json.loads((HERE / "config.json").read_text()).get("backtest", {})
    bt = Backtester(
        initial_capital=float(meta.get("initial_capital", 1000)),
        leverage=float(meta.get("leverage", 50)),
        max_drawdown_pct=float(meta.get("max_drawdown_pct", 20)),
        soft_drawdown_pct=float(meta.get("soft_drawdown_pct", 15)),
        soft_risk_mult=float(meta.get("soft_risk_mult", 0.5)),
        slippage_pips=float(meta.get("slippage_pips", 0.5)),
        use_breakeven=False,
        use_partial_tp=False,
        max_bars_held=10**9,
        allow_dual_positions=True,
    )
    result = bt.run(build_signal_frames(pairs, cfg), capital_alloc=allocation_map(cfg))
    result.trades_df().to_csv(HERE / "full_period_trades.csv", index=False)
    result.equity_curve.to_csv(HERE / "full_period_equity.csv", header=True)
    (HERE / "full_period_metrics.json").write_text(json.dumps(result.metrics, indent=2))
    print(json.dumps(result.metrics, indent=2))
    return result


if __name__ == "__main__":
    main()
