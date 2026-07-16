#!/usr/bin/env python3
"""Market / indicator research for 2020-2025 forex majors."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.data_handler import DataHandler
from core.indicators import TechnicalIndicators

OUT = Path(__file__).resolve().parent


def analyze_pair(pair: str, df: pd.DataFrame) -> dict:
    ti = TechnicalIndicators
    close = df["Close"]
    ret = close.pct_change()
    atr = ti.atr(df)
    adx, plus_di, minus_di = ti.adx(df)
    rsi = ti.rsi(df)
    ema3 = ti.ema(df, 3)
    ema9 = ti.ema(df, 9)
    ema21 = ti.ema(df, 21)

    # Next-day return for correlation (shift target backward relative to features)
    fwd = ret.shift(-1)
    feats = pd.DataFrame(
        {
            "atr_pct": atr / close,
            "adx": adx,
            "rsi": rsi,
            "ema3_9_spread": (ema3 - ema9) / close,
            "ema9_21_spread": (ema9 - ema21) / close,
            "plus_minus_di": plus_di - minus_di,
            "fwd_ret": fwd,
        }
    ).dropna()

    corr = feats.corr()["fwd_ret"].drop("fwd_ret")
    yearly = close.resample("YE").last().pct_change().dropna()
    # include 2020 from first
    first = close.iloc[0]
    y_end = close.groupby(close.index.year).last()
    yrets = {}
    prev = first
    for y, v in y_end.items():
        if y == close.index[0].year:
            yrets[y] = v / prev - 1
        else:
            # use prior year end if available
            pass
    # cleaner yearly returns
    yrets = {}
    years = sorted(close.index.year.unique())
    for y in years:
        c = close[close.index.year == y]
        yrets[y] = c.iloc[-1] / c.iloc[0] - 1

    vol = ret.std() * np.sqrt(252)
    trend_share = float((adx > 20).mean())
    return {
        "pair": pair,
        "bars": len(df),
        "start": str(df.index[0].date()),
        "end": str(df.index[-1].date()),
        "ann_vol": round(float(vol), 4),
        "total_return": round(float(close.iloc[-1] / close.iloc[0] - 1), 4),
        "pct_adx_gt_20": round(trend_share, 4),
        "avg_atr_pct": round(float((atr / close).mean()), 5),
        "yearly_returns": yrets,
        "feature_corr_fwd": corr.to_dict(),
        "corr_series": corr,
    }


def main():
    handler = DataHandler(cache_dir=ROOT / "data" / "cache")
    data = handler.fetch_all_pairs(start="2020-01-01", end="2025-12-31", interval="1d")

    corr_rows = []
    summary_rows = []
    year_rows = []
    narratives = []

    for pair, df in data.items():
        handler.assert_no_2026(df, pair)
        a = analyze_pair(pair, df)
        summary_rows.append(
            {
                "pair": pair,
                "bars": a["bars"],
                "start": a["start"],
                "end": a["end"],
                "ann_vol": a["ann_vol"],
                "buy_hold_return": a["total_return"],
                "pct_adx_gt_20": a["pct_adx_gt_20"],
                "avg_atr_pct": a["avg_atr_pct"],
            }
        )
        for feat, val in a["feature_corr_fwd"].items():
            corr_rows.append({"pair": pair, "feature": feat, "corr_with_next_day_return": val})
        for y, r in a["yearly_returns"].items():
            year_rows.append({"pair": pair, "year": y, "buy_hold_return": r})
        narratives.append(
            f"- **{pair}**: buy&hold {a['total_return']*100:.1f}%, ann vol {a['ann_vol']*100:.1f}%, "
            f"ADX>20 on {a['pct_adx_gt_20']*100:.0f}% of days, avg ATR% {a['avg_atr_pct']*100:.3f}%."
        )

    summary = pd.DataFrame(summary_rows)
    corr_df = pd.DataFrame(corr_rows)
    years = pd.DataFrame(year_rows)
    summary.to_csv(OUT / "pair_summary.csv", index=False)
    corr_df.to_csv(OUT / "indicator_correlations.csv", index=False)
    years.to_csv(OUT / "yearly_buyhold.csv", index=False)

    # Cross-pair correlation
    rets = pd.DataFrame({p: d["Close"].pct_change() for p, d in data.items()}).dropna()
    rets.corr().to_csv(OUT / "cross_pair_correlation.csv")

    md = f"""# Market Analysis 2020-2025

## Scope
- Pairs: EURUSD, GBPUSD, USDJPY, AUDUSD
- Timeframe: **daily** (Yahoo Finance long-history forex; 4H long history unavailable)
- Window: 2020-01-01 to 2025-12-31 (**no 2026 data**)

## Regime Context
Major episodes in-sample:
1. **2020 COVID shock** — extreme volatility spike, risk-off USD bid, then V-shaped recovery.
2. **2021 reflation / risk-on** — relatively orderly trends, lower crisis vol.
3. **2022 Fed hiking / USD strength** — strong USDJPY / DXY trends; mean-reversion traps frequent.
4. **2023 disinflation pivot hopes** — choppier FX, intermittent trend bursts.
5. **2024-2025** — policy divergence themes; mixed trending/ranging months.

A robust strategy must survive crisis vol (2020), strong trend years (2022), and chop (2023+).

## Pair Snapshot
{chr(10).join(narratives)}

## Indicator Notes
Correlations of classic features vs **next-day returns** are weak (as expected in FX), so edges must come from **filtered event signals** (crossovers + ADX + volatility targeting), not raw predictive R².

See `indicator_correlations.csv` for pair-level feature correlations.

## Implications for Strategy Design
1. Use **ADX** to avoid low-trend chop.
2. Use **ATR-based stops/targets** so risk scales with regime.
3. Prefer **dual frequency** (rare high-R:R + steadier background) to diversify trade timing.
4. Trade a **basket** — EURUSD/GBPUSD are correlated; USDJPY diversifies somewhat.
5. Keep costs realistic; daily FX edges are small after spreads.
"""
    (OUT / "market_analysis_2020_2025.md").write_text(md)

    concepts = """# Strategy Concepts (2020-2025 Research)

## Concept A — Dual EMA Sniper + Background (Primary)
- Sniper: EMA 3/9 cross, ADX filter, 1–5 ATR R:R, capped frequency, 2% risk
- Background: EMA 9/21 cross, stricter ADX, 2–3 ATR R:R, 1% risk
- Why: Balances lottery-ticket trend capture with steadier participation
- Risk: Overtrading if ADX too low; correlated entries across EUR/GBP

## Concept B — Volatility-Regime Adaptive Targets
- ATR z-score classifies high/normal/low vol
- Tighten targets in high vol; widen in low vol
- Why: 2020-style spikes stop out fixed wide targets; quiet markets need room
- Risk: Misclassified regimes around transitions

## Concept C — DI-Confirmed Trend Following
- EMA cross only when +DI/-DI agrees
- Optional RSI ceiling/floor to avoid late chase
- Why: Improves directional alignment vs raw cross
- Risk: Fewer trades; missed early moves

## Concept D — Session / Event Avoidance (Secondary)
- On daily data, session filters are limited
- Practical proxy: skip entries when ATR z-score extreme AND ADX collapsing
- Why: Avoid exhausting climax bars
- Risk: Hard to validate without intraday history

## Concept E — Momentum Breakout + ATR Channel
- Enter on close beyond N-day high/low with ADX rising
- Exit on opposite channel or ATR stop
- Why: Captures 2022-style trend legs
- Risk: Whipsaw in 2023 chop; may fail WR target without filters

## Selected Path
Prioritize **A + B + C** (dual system with vol-adaptive targets and DI/RSI filters),
then validate with walk-forward / OOS / Monte Carlo on 2020-2025 only.
"""
    (OUT / "strategy_concepts.md").write_text(concepts)
    print("Research artifacts written to", OUT)


if __name__ == "__main__":
    main()
