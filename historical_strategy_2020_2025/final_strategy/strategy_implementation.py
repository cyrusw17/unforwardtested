"""
Dual forex strategy (Sniper + Background) — 2020-2025 locked implementation.

Classic EMA-crossover dual system inspired by the reference design, re-tuned
exclusively on 2020-01-01 .. 2025-12-31 data (no 2026 look-ahead).

Sniper  : EMA 5/13 cross, ADX>12, DI confirm, RSI bound, 1.0/5.0 ATR SL/TP
Background: EMA 8/21 cross, ADX>18, DI confirm, RSI bound, 2.0/3.0 ATR SL/TP
Dynamic ATR targets by volatility regime (ATR z-score).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict, Optional

import pandas as pd

from core.indicators import TechnicalIndicators


@dataclass
class StrategyConfig:
    name: str = "dual_ema_vol_regime_final"

    # Sniper
    sniper_fast: int = 5
    sniper_slow: int = 13
    sniper_adx: float = 12.0
    sniper_sl_atr: float = 1.0
    sniper_tp_atr: float = 5.0
    sniper_risk_pct: float = 2.0
    sniper_max_per_month: int = 3

    # Background
    bg_fast: int = 8
    bg_slow: int = 21
    bg_adx: float = 18.0
    bg_sl_atr: float = 2.0
    bg_tp_atr: float = 3.0
    bg_risk_pct: float = 1.0
    bg_max_per_month: int = 0  # 0 = unlimited

    # Shared filters / regime
    atr_period: int = 14
    adx_period: int = 14
    atr_z_lookback: int = 50
    rsi_period: int = 14
    use_rsi_filter: bool = True
    rsi_long_max: float = 70.0
    rsi_short_min: float = 30.0
    use_dynamic_targets: bool = True
    high_vol_mult: float = 0.75
    low_vol_mult: float = 1.35
    normal_vol_mult: float = 1.0
    high_z: float = 1.0
    low_z: float = -1.0

    # Capital allocation
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
    """Add indicator and causal (next-bar) signal columns for one pair."""
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
    out["rsi"] = ti.rsi(out, cfg.rsi_period)
    out["atr_z"] = ti.atr_zscore(out["atr"], cfg.atr_z_lookback)
    out["regime"] = ti.volatility_regime(out["atr_z"], cfg.high_z, cfg.low_z)

    s_cross_up = (out["ema_s_fast"] > out["ema_s_slow"]) & (
        out["ema_s_fast"].shift(1) <= out["ema_s_slow"].shift(1)
    )
    s_cross_dn = (out["ema_s_fast"] < out["ema_s_slow"]) & (
        out["ema_s_fast"].shift(1) >= out["ema_s_slow"].shift(1)
    )
    b_cross_up = (out["ema_b_fast"] > out["ema_b_slow"]) & (
        out["ema_b_fast"].shift(1) <= out["ema_b_slow"].shift(1)
    )
    b_cross_dn = (out["ema_b_fast"] < out["ema_b_slow"]) & (
        out["ema_b_fast"].shift(1) >= out["ema_b_slow"].shift(1)
    )

    long_ok = out["plus_di"] > out["minus_di"]
    short_ok = out["minus_di"] > out["plus_di"]
    rsi_long_ok = (~cfg.use_rsi_filter) | (out["rsi"] < cfg.rsi_long_max)
    rsi_short_ok = (~cfg.use_rsi_filter) | (out["rsi"] > cfg.rsi_short_min)

    sniper_long = s_cross_up & (out["adx"] > cfg.sniper_adx) & long_ok & rsi_long_ok
    sniper_short = s_cross_dn & (out["adx"] > cfg.sniper_adx) & short_ok & rsi_short_ok
    bg_long = b_cross_up & (out["adx"] > cfg.bg_adx) & long_ok & rsi_long_ok
    bg_short = b_cross_dn & (out["adx"] > cfg.bg_adx) & short_ok & rsi_short_ok

    sniper_sig = pd.Series(0, index=out.index, dtype=int)
    sniper_sig = sniper_sig.mask(sniper_long, 1).mask(sniper_short, -1)
    bg_sig = pd.Series(0, index=out.index, dtype=int)
    bg_sig = bg_sig.mask(bg_long, 1).mask(bg_short, -1)

    # Fill next open — no look-ahead
    out["sniper_signal"] = sniper_sig.shift(1).fillna(0).astype(int)
    out["background_signal"] = bg_sig.shift(1).fillna(0).astype(int)

    reg_mult = out["regime"].map(
        lambda r: _regime_multiplier(str(r), cfg) if cfg.use_dynamic_targets else 1.0
    )
    out["sniper_sl_atr_mult"] = cfg.sniper_sl_atr * reg_mult
    out["sniper_tp_atr_mult"] = cfg.sniper_tp_atr * reg_mult
    out["background_sl_atr_mult"] = cfg.bg_sl_atr * reg_mult
    out["background_tp_atr_mult"] = cfg.bg_tp_atr * reg_mult
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
