"""
Residual Momentum × Liquidity Sweep dual strategy.

Entry confluence (not EMA cross):
1. Residual momentum — pair log-return residualized vs equal-weight majors basket
2. Liquidity sweep — pierce prior swing extreme, reclaim with rejection wick
3. DI / mild ADX — directional agreement, avoid dead ranges

Dual sleeves:
- Sniper: stricter residual-z, same-bar sweep, monthly cap, wider target
- Background: milder residual-z, short persistence window, steadier frequency

Stops prefer the sweep extreme (liquidity invalidation). ATR targets + vol regime.
Data: Dukascopy 4H 2020-01-01 .. 2025-12-31 only (no 2026).
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
class StrategyConfig:
    name: str = "residual_momentum_liquidity_sweep"

    # Residual momentum (asymmetric mom lookbacks from edge study)
    beta_lookback: int = 60
    mom_lookback: int = 8  # primary (long-friendly); short uses mom_lookback_short
    mom_lookback_short: int = 4
    resid_z_lookback: int = 60
    sniper_resid_z: float = 1.25
    bg_resid_z: float = 0.75
    require_resid_accel: bool = False

    # Liquidity sweep
    swing_lookback: int = 18
    swing_lookback_short: int = 24
    min_wick_atr: float = 0.10
    sniper_persist: int = 1
    bg_persist: int = 2

    # Exits / risk
    sniper_sl_atr: float = 1.25
    sniper_tp_atr: float = 4.0
    sniper_risk_pct: float = 1.5
    sniper_max_per_month: int = 3
    bg_sl_atr: float = 1.5
    bg_tp_atr: float = 2.5
    bg_risk_pct: float = 1.0
    bg_max_per_month: int = 0
    use_sweep_stop: bool = True
    sweep_stop_buffer_atr: float = 0.1
    max_sl_atr: float = 2.25

    # Shared / regime
    atr_period: int = 14
    atr_z_lookback: int = 50
    use_dynamic_targets: bool = True
    high_vol_mult: float = 0.75
    low_vol_mult: float = 1.25
    normal_vol_mult: float = 1.0
    high_z: float = 1.5
    low_z: float = -1.0
    trend_boost_adx: float = 28.0
    trend_boost_mult: float = 1.25
    use_trend_boost: bool = True
    adx_period: int = 14
    min_adx: float = 10.0

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


def _sl_tp_multiples(
    out: pd.DataFrame,
    cfg: StrategyConfig,
    sniper_side: pd.Series,
    bg_side: pd.Series,
) -> pd.DataFrame:
    ti = TechnicalIndicators
    adx, _, _ = ti.adx(out, cfg.adx_period)
    out["adx"] = adx
    out["atr_z"] = ti.atr_zscore(out["atr"], cfg.atr_z_lookback)
    out["regime"] = ti.volatility_regime(out["atr_z"], cfg.high_z, cfg.low_z)

    reg_mult = out["regime"].map(
        lambda r: _regime_multiplier(str(r), cfg) if cfg.use_dynamic_targets else 1.0
    )
    trend_mult = pd.Series(1.0, index=out.index)
    if cfg.use_trend_boost:
        trend_mult = trend_mult.mask(out["adx"] > cfg.trend_boost_adx, cfg.trend_boost_mult)

    sniper_sl = pd.Series(float(cfg.sniper_sl_atr), index=out.index) * reg_mult
    bg_sl = pd.Series(float(cfg.bg_sl_atr), index=out.index) * reg_mult
    sniper_tp = pd.Series(float(cfg.sniper_tp_atr), index=out.index) * reg_mult * trend_mult
    bg_tp = pd.Series(float(cfg.bg_tp_atr), index=out.index) * reg_mult * trend_mult

    if cfg.use_sweep_stop:
        atr = out["atr"].replace(0, np.nan)
        approx = out["Close"]
        buf = cfg.sweep_stop_buffer_atr * atr
        long_dist = ((approx - (out["Low"] - buf)) / atr).clip(lower=0.4, upper=cfg.max_sl_atr)
        short_dist = (((out["High"] + buf) - approx) / atr).clip(lower=0.4, upper=cfg.max_sl_atr)
        sniper_sl = sniper_sl.mask(sniper_side > 0, long_dist).mask(sniper_side < 0, short_dist)
        bg_sl = bg_sl.mask(bg_side > 0, long_dist).mask(bg_side < 0, short_dist)

    out["sniper_sl_atr_mult"] = sniper_sl.astype(float)
    out["sniper_tp_atr_mult"] = sniper_tp.astype(float)
    out["background_sl_atr_mult"] = bg_sl.astype(float)
    out["background_tp_atr_mult"] = bg_tp.astype(float)
    return out


def prepare_pair_signals(df: pd.DataFrame, cfg: StrategyConfig) -> pd.DataFrame:
    out = df.copy()
    ti = TechnicalIndicators
    if "atr" not in out.columns:
        out["atr"] = ti.atr(out, cfg.atr_period)
    if "resid_z" not in out.columns or "resid_z_short" not in out.columns:
        raise ValueError("residual columns missing — use build_signal_frames()")

    # Long sweeps use swing_lookback; short sweeps use swing_lookback_short
    long_sw = liquidity_sweep_flags(out, cfg.swing_lookback, cfg.min_wick_atr)
    short_sw = liquidity_sweep_flags(out, cfg.swing_lookback_short, cfg.min_wick_atr)
    out["bull_sweep"] = long_sw["bull_sweep"]
    out["bear_sweep"] = short_sw["bear_sweep"]
    out["swing_low"] = long_sw["swing_low"]
    out["swing_high"] = short_sw["swing_high"]

    bull_s = recent_event(out["bull_sweep"], cfg.sniper_persist)
    bear_s = recent_event(out["bear_sweep"], cfg.sniper_persist)
    bull_b = recent_event(out["bull_sweep"], cfg.bg_persist)
    bear_b = recent_event(out["bear_sweep"], cfg.bg_persist)

    rz_long = out["resid_z"]
    rz_short = out["resid_z_short"]
    rm_long = out["resid_mom"]
    rm_short = out["resid_mom_short"]

    accel = rm_long > rm_long.shift(1) if cfg.require_resid_accel else pd.Series(True, index=out.index)
    decel = rm_short < rm_short.shift(1) if cfg.require_resid_accel else pd.Series(True, index=out.index)

    adx, plus_di, minus_di = ti.adx(out, cfg.adx_period)
    trend_ok = adx > cfg.min_adx

    sniper_long = (
        bull_s & (rz_long >= cfg.sniper_resid_z) & accel & trend_ok & (plus_di > minus_di)
    )
    sniper_short = (
        bear_s & (rz_short <= -cfg.sniper_resid_z) & decel & trend_ok & (minus_di > plus_di)
    )
    bg_long = bull_b & (rz_long >= cfg.bg_resid_z) & trend_ok & (plus_di > minus_di)
    bg_short = bear_b & (rz_short <= -cfg.bg_resid_z) & trend_ok & (minus_di > plus_di)

    sniper_sig = pd.Series(0, index=out.index, dtype=int)
    sniper_sig = sniper_sig.mask(sniper_long, 1).mask(sniper_short, -1)
    bg_sig = pd.Series(0, index=out.index, dtype=int)
    bg_sig = bg_sig.mask(bg_long, 1).mask(bg_short, -1)

    # Avoid double-counting: if sniper fires, suppress background on that bar
    bg_sig = bg_sig.mask(sniper_sig != 0, 0)

    out = _sl_tp_multiples(out, cfg, sniper_sig, bg_sig)

    out["sniper_signal"] = sniper_sig.shift(1).fillna(0).astype(int)
    out["background_signal"] = bg_sig.shift(1).fillna(0).astype(int)
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
    out["background_allow"] = True
    return out


def build_signal_frames(
    pair_data: Dict[str, pd.DataFrame],
    cfg: Optional[StrategyConfig] = None,
) -> Dict[str, pd.DataFrame]:
    cfg = cfg or StrategyConfig()
    ti = TechnicalIndicators

    base: Dict[str, pd.DataFrame] = {}
    for pair, df in pair_data.items():
        d = df.copy()
        d["atr"] = ti.atr(d, cfg.atr_period)
        base[pair] = d

    long_res = compute_cross_pair_residuals(
        base,
        beta_lookback=cfg.beta_lookback,
        mom_lookback=cfg.mom_lookback,
        z_lookback=cfg.resid_z_lookback,
    )
    short_res = compute_cross_pair_residuals(
        base,
        beta_lookback=cfg.beta_lookback,
        mom_lookback=cfg.mom_lookback_short,
        z_lookback=cfg.resid_z_lookback,
    )

    merged: Dict[str, pd.DataFrame] = {}
    for pair in base:
        frame = long_res[pair].copy()
        frame["resid_mom_short"] = short_res[pair]["resid_mom"]
        frame["resid_z_short"] = short_res[pair]["resid_z"]
        merged[pair] = prepare_pair_signals(frame, cfg)
    return merged


def allocation_map(cfg: StrategyConfig) -> Dict[str, float]:
    return {"sniper": cfg.sniper_alloc, "background": cfg.background_alloc}
