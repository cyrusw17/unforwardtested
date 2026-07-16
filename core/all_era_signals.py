"""
Multi-era signal families for robustness selection across 2018-2025.

Families
--------
1. residual_sweep — residual momentum × liquidity sweep (sniper and/or background)
2. donchian — classic channel breakout + ADX
3. xs_residual — cross-sectional residual rank (long strongest / short weakest)
4. residual_ts — pure residual time-series momentum (no sweep), ADX gated
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict, Optional

import numpy as np
import pandas as pd

from core.indicators import TechnicalIndicators
from core.residual_momentum import (
    compute_cross_pair_residuals,
    liquidity_sweep_flags,
    recent_event,
)


@dataclass
class AllEraConfig:
    name: str = "all_era"
    family: str = "residual_sweep"  # residual_sweep | donchian | xs_residual | residual_ts

    # Residual
    beta_lookback: int = 60
    mom_lookback: int = 8
    mom_lookback_short: int = 4
    resid_z_lookback: int = 60
    sniper_resid_z: float = 1.25
    bg_resid_z: float = 0.75

    # Sweep
    swing_lookback: int = 18
    swing_lookback_short: int = 24
    min_wick_atr: float = 0.10
    sniper_persist: int = 1
    bg_persist: int = 2
    use_sweep: bool = True

    # Donchian
    donchian_n: int = 20
    donchian_exit_n: int = 10

    # XS residual
    xs_z_edge: float = 0.75  # require top-bottom z gap

    # Shared filters / risk
    atr_period: int = 14
    adx_period: int = 14
    min_adx: float = 12.0
    use_di: bool = True
    sniper_only: bool = True
    sniper_sl_atr: float = 1.5
    sniper_tp_atr: float = 3.0
    bg_sl_atr: float = 1.75
    bg_tp_atr: float = 2.5
    sniper_risk_pct: float = 1.0
    bg_risk_pct: float = 1.0
    sniper_max_per_month: int = 3
    bg_max_per_month: int = 0
    use_sweep_stop: bool = True
    sweep_stop_buffer_atr: float = 0.1
    max_sl_atr: float = 2.5
    atr_z_lookback: int = 50
    use_dynamic_targets: bool = True
    high_vol_mult: float = 0.75
    low_vol_mult: float = 1.25
    high_z: float = 1.5
    low_z: float = -1.0
    # Optional: skip high-vol chaos
    max_atr_z: float = 3.0
    sniper_alloc: float = 1.0
    background_alloc: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


def _regime_mult(regime: str, cfg: AllEraConfig) -> float:
    if regime == "high":
        return cfg.high_vol_mult
    if regime == "low":
        return cfg.low_vol_mult
    return 1.0


def _attach_risk(out: pd.DataFrame, cfg: AllEraConfig, side: pd.Series, prefix: str) -> None:
    ti = TechnicalIndicators
    if "atr_z" not in out.columns:
        out["atr_z"] = ti.atr_zscore(out["atr"], cfg.atr_z_lookback)
        out["regime"] = ti.volatility_regime(out["atr_z"], cfg.high_z, cfg.low_z)
    reg = out["regime"].map(lambda r: _regime_mult(str(r), cfg) if cfg.use_dynamic_targets else 1.0)
    sl0 = cfg.sniper_sl_atr if prefix == "sniper" else cfg.bg_sl_atr
    tp0 = cfg.sniper_tp_atr if prefix == "sniper" else cfg.bg_tp_atr
    sl = pd.Series(float(sl0), index=out.index) * reg
    tp = pd.Series(float(tp0), index=out.index) * reg
    if cfg.use_sweep_stop and "Low" in out.columns:
        atr = out["atr"].replace(0, np.nan)
        buf = cfg.sweep_stop_buffer_atr * atr
        long_d = ((out["Close"] - (out["Low"] - buf)) / atr).clip(0.4, cfg.max_sl_atr)
        short_d = (((out["High"] + buf) - out["Close"]) / atr).clip(0.4, cfg.max_sl_atr)
        sl = sl.mask(side > 0, long_d).mask(side < 0, short_d)
    out[f"{prefix}_sl_atr_mult"] = sl.astype(float)
    out[f"{prefix}_tp_atr_mult"] = tp.astype(float)
    out[f"{prefix}_risk_pct"] = cfg.sniper_risk_pct if prefix == "sniper" else cfg.bg_risk_pct
    out[f"{prefix}_max_per_month"] = (
        cfg.sniper_max_per_month if prefix == "sniper" else cfg.bg_max_per_month
    )
    out[f"{prefix}_allow"] = True


def _finalize(out: pd.DataFrame, sniper: pd.Series, bg: pd.Series, cfg: AllEraConfig) -> pd.DataFrame:
    if cfg.sniper_only:
        bg = pd.Series(0, index=out.index, dtype=int)
    # atr-z chaos filter
    if "atr_z" not in out.columns:
        out["atr_z"] = TechnicalIndicators.atr_zscore(out["atr"], cfg.atr_z_lookback)
        out["regime"] = TechnicalIndicators.volatility_regime(out["atr_z"], cfg.high_z, cfg.low_z)
    chaos = out["atr_z"].abs() > cfg.max_atr_z
    sniper = sniper.mask(chaos, 0)
    bg = bg.mask(chaos, 0)
    bg = bg.mask(sniper != 0, 0)

    _attach_risk(out, cfg, sniper, "sniper")
    _attach_risk(out, cfg, bg, "background")

    out["sniper_signal"] = sniper.shift(1).fillna(0).astype(int)
    out["background_signal"] = bg.shift(1).fillna(0).astype(int)
    for col in (
        "sniper_sl_atr_mult",
        "sniper_tp_atr_mult",
        "background_sl_atr_mult",
        "background_tp_atr_mult",
    ):
        out[col] = out[col].shift(1)
    out["sniper_risk_pct"] = cfg.sniper_risk_pct
    out["background_risk_pct"] = cfg.bg_risk_pct
    out["sniper_max_per_month"] = cfg.sniper_max_per_month
    out["background_max_per_month"] = cfg.bg_max_per_month
    out["sniper_allow"] = True
    out["background_allow"] = not cfg.sniper_only
    return out


def _di_ok(out: pd.DataFrame, cfg: AllEraConfig):
    adx, plus_di, minus_di = TechnicalIndicators.adx(out, cfg.adx_period)
    out["adx"] = adx
    out["plus_di"] = plus_di
    out["minus_di"] = minus_di
    trend = adx > cfg.min_adx
    if cfg.use_di:
        return trend, plus_di > minus_di, minus_di > plus_di
    return trend, pd.Series(True, index=out.index), pd.Series(True, index=out.index)


def build_residual_base(pair_data: Dict[str, pd.DataFrame], cfg: AllEraConfig) -> Dict[str, pd.DataFrame]:
    base = {}
    for p, df in pair_data.items():
        d = df.copy()
        d["atr"] = TechnicalIndicators.atr(d, cfg.atr_period)
        base[p] = d
    long_res = compute_cross_pair_residuals(base, cfg.beta_lookback, cfg.mom_lookback, cfg.resid_z_lookback)
    short_res = compute_cross_pair_residuals(
        base, cfg.beta_lookback, cfg.mom_lookback_short, cfg.resid_z_lookback
    )
    out = {}
    for p in base:
        frame = long_res[p].copy()
        frame["resid_z_short"] = short_res[p]["resid_z"]
        frame["resid_mom_short"] = short_res[p]["resid_mom"]
        out[p] = frame
    return out


def signals_residual_sweep(pair_data: Dict[str, pd.DataFrame], cfg: AllEraConfig) -> Dict[str, pd.DataFrame]:
    residualized = build_residual_base(pair_data, cfg)
    out = {}
    for p, df in residualized.items():
        frame = df.copy()
        long_sw = liquidity_sweep_flags(frame, cfg.swing_lookback, cfg.min_wick_atr)
        short_sw = liquidity_sweep_flags(frame, cfg.swing_lookback_short, cfg.min_wick_atr)
        bull = recent_event(long_sw["bull_sweep"], cfg.sniper_persist) if cfg.use_sweep else pd.Series(True, index=frame.index)
        bear = recent_event(short_sw["bear_sweep"], cfg.sniper_persist) if cfg.use_sweep else pd.Series(True, index=frame.index)
        bull_b = recent_event(long_sw["bull_sweep"], cfg.bg_persist) if cfg.use_sweep else pd.Series(True, index=frame.index)
        bear_b = recent_event(short_sw["bear_sweep"], cfg.bg_persist) if cfg.use_sweep else pd.Series(True, index=frame.index)
        trend, long_di, short_di = _di_ok(frame, cfg)
        rz, rzs = frame["resid_z"], frame["resid_z_short"]
        sniper = pd.Series(0, index=frame.index, dtype=int)
        sniper = sniper.mask(bull & (rz >= cfg.sniper_resid_z) & trend & long_di, 1)
        sniper = sniper.mask(bear & (rzs <= -cfg.sniper_resid_z) & trend & short_di, -1)
        bg = pd.Series(0, index=frame.index, dtype=int)
        bg = bg.mask(bull_b & (rz >= cfg.bg_resid_z) & trend & long_di, 1)
        bg = bg.mask(bear_b & (rzs <= -cfg.bg_resid_z) & trend & short_di, -1)
        out[p] = _finalize(frame, sniper, bg, cfg)
    return out


def signals_residual_ts(pair_data: Dict[str, pd.DataFrame], cfg: AllEraConfig) -> Dict[str, pd.DataFrame]:
    """Residual momentum without sweep — enter on z cross above threshold."""
    residualized = build_residual_base(pair_data, cfg)
    out = {}
    for p, df in residualized.items():
        frame = df.copy()
        trend, long_di, short_di = _di_ok(frame, cfg)
        rz, rzs = frame["resid_z"], frame["resid_z_short"]
        # Trigger on crossing into threshold (event), not hold
        long_x = (rz >= cfg.sniper_resid_z) & (rz.shift(1) < cfg.sniper_resid_z)
        short_x = (rzs <= -cfg.sniper_resid_z) & (rzs.shift(1) > -cfg.sniper_resid_z)
        sniper = pd.Series(0, index=frame.index, dtype=int)
        sniper = sniper.mask(long_x & trend & long_di, 1)
        sniper = sniper.mask(short_x & trend & short_di, -1)
        bg = pd.Series(0, index=frame.index, dtype=int)
        out[p] = _finalize(frame, sniper, bg, cfg)
    return out


def signals_donchian(pair_data: Dict[str, pd.DataFrame], cfg: AllEraConfig) -> Dict[str, pd.DataFrame]:
    out = {}
    for p, df in pair_data.items():
        frame = df.copy()
        frame["atr"] = TechnicalIndicators.atr(frame, cfg.atr_period)
        n = cfg.donchian_n
        hh = frame["High"].rolling(n).max().shift(1)
        ll = frame["Low"].rolling(n).min().shift(1)
        trend, long_di, short_di = _di_ok(frame, cfg)
        long_e = (frame["Close"] > hh) & trend & long_di
        short_e = (frame["Close"] < ll) & trend & short_di
        # event: first break only
        long_x = long_e & ~long_e.shift(1).fillna(False)
        short_x = short_e & ~short_e.shift(1).fillna(False)
        sniper = pd.Series(0, index=frame.index, dtype=int)
        sniper = sniper.mask(long_x, 1).mask(short_x, -1)
        bg = pd.Series(0, index=frame.index, dtype=int)
        # Donchian uses ATR stops, not sweep stops
        cfg2 = AllEraConfig(**{**cfg.to_dict(), "use_sweep_stop": False})
        out[p] = _finalize(frame, sniper, bg, cfg2)
    return out


def signals_xs_residual(pair_data: Dict[str, pd.DataFrame], cfg: AllEraConfig) -> Dict[str, pd.DataFrame]:
    """Each bar: long max resid_z pair, short min resid_z pair if gap >= xs_z_edge."""
    residualized = build_residual_base(pair_data, cfg)
    # Align z
    z = pd.DataFrame({p: df["resid_z"] for p, df in residualized.items()})
    zmax = z.max(axis=1)
    zmin = z.min(axis=1)
    gap = zmax - zmin
    long_pair = z.idxmax(axis=1)
    short_pair = z.idxmin(axis=1)
    out = {}
    for p, df in residualized.items():
        frame = df.copy()
        trend, long_di, short_di = _di_ok(frame, cfg)
        is_long = (long_pair == p) & (gap >= cfg.xs_z_edge) & trend & long_di
        is_short = (short_pair == p) & (gap >= cfg.xs_z_edge) & trend & short_di
        # events: become the extreme this bar
        long_x = is_long & ~is_long.shift(1).fillna(False)
        short_x = is_short & ~is_short.shift(1).fillna(False)
        sniper = pd.Series(0, index=frame.index, dtype=int)
        sniper = sniper.mask(long_x, 1).mask(short_x, -1)
        bg = pd.Series(0, index=frame.index, dtype=int)
        cfg2 = AllEraConfig(**{**cfg.to_dict(), "use_sweep_stop": False})
        out[p] = _finalize(frame, sniper, bg, cfg2)
    return out


def build_signal_frames(pair_data: Dict[str, pd.DataFrame], cfg: AllEraConfig) -> Dict[str, pd.DataFrame]:
    if cfg.family == "residual_sweep":
        return signals_residual_sweep(pair_data, cfg)
    if cfg.family == "residual_ts":
        return signals_residual_ts(pair_data, cfg)
    if cfg.family == "donchian":
        return signals_donchian(pair_data, cfg)
    if cfg.family == "xs_residual":
        return signals_xs_residual(pair_data, cfg)
    raise ValueError(f"Unknown family: {cfg.family}")


def allocation_map(cfg: AllEraConfig) -> Dict[str, float]:
    if cfg.sniper_only:
        return {"sniper": 1.0}
    return {"sniper": cfg.sniper_alloc, "background": cfg.background_alloc}
