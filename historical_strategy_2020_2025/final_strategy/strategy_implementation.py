"""
2% Very Conservative Dual Strategy — future-proofed implementation.

Base idea from the recommended dual system (Sniper + Background), re-validated
on Dukascopy 4H data for 2020-01-01 .. 2025-12-31 only (no 2026).

Critical future-proofing changes vs the marketing brief (required for edge):
1. DI direction filter (+DI/-DI must agree with trade direction) — applied before signal shift
2. Higher ADX gates: sniper 15 / background 25 (brief used 10 / 20)
3. Sniper take-profit 3.0 ATR (brief used 5.0 ATR)
4. Risk 1%/1% of sleeve capital (brief 2%/1% failed OOS / hit 20% halt)
5. Soft DD cut at 15% (halve risk) + hard halt at 20%

Kept from the brief:
- EMA 3/9 sniper, EMA 9/21 background
- 60/40 allocation, $1,000 start, 50:1 leverage
- Vol regime z>1.5 / z<-1.0 with 0.75x / 1.25x target scaling
- Trend boost ADX>30 → TP × 1.5
- Sniper max 2 trades/pair/month
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict, Optional

import pandas as pd

from core.indicators import TechnicalIndicators


@dataclass
class StrategyConfig:
    name: str = "very_conservative_2pct_dual_futureproof"

    # Sniper
    sniper_fast: int = 3
    sniper_slow: int = 9
    sniper_adx: float = 15.0
    sniper_sl_atr: float = 1.0
    sniper_tp_atr: float = 3.0
    sniper_risk_pct: float = 1.0
    sniper_max_per_month: int = 2

    # Background
    bg_fast: int = 9
    bg_slow: int = 21
    bg_adx: float = 25.0
    bg_sl_atr: float = 2.0
    bg_tp_atr: float = 3.0
    bg_risk_pct: float = 1.0
    bg_max_per_month: int = 0

    # Shared / regime
    atr_period: int = 14
    adx_period: int = 14
    atr_z_lookback: int = 50
    use_rsi_filter: bool = False
    use_di_filter: bool = True
    use_dynamic_targets: bool = True
    high_vol_mult: float = 0.75
    low_vol_mult: float = 1.25
    normal_vol_mult: float = 1.0
    high_z: float = 1.5
    low_z: float = -1.0
    trend_boost_adx: float = 30.0
    trend_boost_mult: float = 1.5
    use_trend_boost: bool = True

    # Capital
    sniper_alloc: float = 0.60
    background_alloc: float = 0.40

    def to_dict(self) -> dict:
        return asdict(self)


def _regime_multiplier(regime: str, cfg: StrategyConfig) -> float:
    if regime == "high":
        return cfg.high_vol_mult
    if regime == "low":
        return cfg.low_vol_mult
    return cfg.normal_vol_mult


def prepare_pair_signals(df: pd.DataFrame, cfg: StrategyConfig) -> pd.DataFrame:
    out = df.copy()
    ti = TechnicalIndicators

    out["ema_s_fast"] = ti.ema(out, cfg.sniper_fast)
    out["ema_s_slow"] = ti.ema(out, cfg.sniper_slow)
    out["ema_b_fast"] = ti.ema(out, cfg.bg_fast)
    out["ema_b_slow"] = ti.ema(out, cfg.bg_slow)
    out["atr"] = ti.atr(out, cfg.atr_period)
    adx, plus_di, minus_di = ti.adx(out, cfg.adx_period)
    out["adx"] = adx
    out["plus_di"] = plus_di
    out["minus_di"] = minus_di
    out["atr_z"] = ti.atr_zscore(out["atr"], cfg.atr_z_lookback)
    out["regime"] = ti.volatility_regime(out["atr_z"], cfg.high_z, cfg.low_z)

    s_up = (out["ema_s_fast"] > out["ema_s_slow"]) & (
        out["ema_s_fast"].shift(1) <= out["ema_s_slow"].shift(1)
    )
    s_dn = (out["ema_s_fast"] < out["ema_s_slow"]) & (
        out["ema_s_fast"].shift(1) >= out["ema_s_slow"].shift(1)
    )
    b_up = (out["ema_b_fast"] > out["ema_b_slow"]) & (
        out["ema_b_fast"].shift(1) <= out["ema_b_slow"].shift(1)
    )
    b_dn = (out["ema_b_fast"] < out["ema_b_slow"]) & (
        out["ema_b_fast"].shift(1) >= out["ema_b_slow"].shift(1)
    )

    sniper_long = s_up & (out["adx"] > cfg.sniper_adx)
    sniper_short = s_dn & (out["adx"] > cfg.sniper_adx)
    bg_long = b_up & (out["adx"] > cfg.bg_adx)
    bg_short = b_dn & (out["adx"] > cfg.bg_adx)

    if cfg.use_di_filter:
        sniper_long &= out["plus_di"] > out["minus_di"]
        sniper_short &= out["minus_di"] > out["plus_di"]
        bg_long &= out["plus_di"] > out["minus_di"]
        bg_short &= out["minus_di"] > out["plus_di"]

    sniper_sig = pd.Series(0, index=out.index, dtype=int)
    sniper_sig = sniper_sig.mask(sniper_long, 1).mask(sniper_short, -1)
    bg_sig = pd.Series(0, index=out.index, dtype=int)
    bg_sig = bg_sig.mask(bg_long, 1).mask(bg_short, -1)

    out["sniper_signal"] = sniper_sig.shift(1).fillna(0).astype(int)
    out["background_signal"] = bg_sig.shift(1).fillna(0).astype(int)

    reg_mult = out["regime"].map(
        lambda r: _regime_multiplier(str(r), cfg) if cfg.use_dynamic_targets else 1.0
    )
    trend_mult = pd.Series(1.0, index=out.index)
    if cfg.use_trend_boost:
        trend_mult = trend_mult.mask(out["adx"] > cfg.trend_boost_adx, cfg.trend_boost_mult)

    out["sniper_sl_atr_mult"] = cfg.sniper_sl_atr * reg_mult
    out["sniper_tp_atr_mult"] = cfg.sniper_tp_atr * reg_mult * trend_mult
    out["background_sl_atr_mult"] = cfg.bg_sl_atr * reg_mult
    out["background_tp_atr_mult"] = cfg.bg_tp_atr * reg_mult * trend_mult
    out["sniper_risk_pct"] = cfg.sniper_risk_pct
    out["background_risk_pct"] = cfg.bg_risk_pct
    out["sniper_max_per_month"] = cfg.sniper_max_per_month
    out["background_max_per_month"] = cfg.bg_max_per_month
    out["sniper_allow"] = True
    out["background_allow"] = True
    return out


def build_signal_frames(
    pair_data: Dict[str, pd.DataFrame],
    cfg: Optional[StrategyConfig] = None,
) -> Dict[str, pd.DataFrame]:
    cfg = cfg or StrategyConfig()
    return {pair: prepare_pair_signals(df, cfg) for pair, df in pair_data.items()}


def allocation_map(cfg: StrategyConfig) -> Dict[str, float]:
    return {"sniper": cfg.sniper_alloc, "background": cfg.background_alloc}
