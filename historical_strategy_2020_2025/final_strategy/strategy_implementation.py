"""
All-era locked strategy: residual momentum × liquidity sweep (sniper-only).

Selected by hard multi-era gates on Dukascopy 4H 2018-2025 (no 2026):
  2018-2019 >= -2%, 2020 >= -5%, 2021-2023 >= 0, 2024-2025 >= 0,
  full return > 0, max DD < 20%, trades >= 25.

This replaces train-window-only locks that failed on 2018-2020.
"""

from __future__ import annotations

from typing import Dict, Optional

from core.all_era_signals import AllEraConfig as StrategyConfig
from core.all_era_signals import allocation_map, build_signal_frames

__all__ = ["StrategyConfig", "allocation_map", "build_signal_frames", "prepare_pair_signals"]


def prepare_pair_signals(df, cfg: Optional[StrategyConfig] = None):
    """Not used directly — residual factor needs the full basket via build_signal_frames()."""
    raise RuntimeError("Use build_signal_frames(pair_data, cfg) for cross-pair residual signals")
