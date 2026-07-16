"""Event-driven multi-pair forex backtester with realistic costs and leverage."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .data_handler import DEFAULT_SPREADS, PIP_SIZES


@dataclass
class Trade:
    pair: str
    strategy: str
    side: str  # long / short
    entry_time: pd.Timestamp
    entry_price: float
    stop_loss: float
    take_profit: float
    size_units: float
    risk_pct: float
    exit_time: Optional[pd.Timestamp] = None
    exit_price: Optional[float] = None
    pnl: float = 0.0
    pnl_pct: float = 0.0
    exit_reason: str = ""
    bars_held: int = 0
    regime: str = "normal"
    initial_stop: float = 0.0
    initial_tp: float = 0.0
    initial_units: float = 0.0
    realized_partial: float = 0.0
    moved_be: bool = False
    partial_taken: bool = False

    def to_dict(self) -> dict:
        d = asdict(self)
        d["entry_time"] = str(self.entry_time)
        d["exit_time"] = str(self.exit_time) if self.exit_time is not None else None
        return d


@dataclass
class BacktestResult:
    equity_curve: pd.Series
    trades: List[Trade]
    metrics: dict
    monthly_returns: pd.Series = field(default_factory=pd.Series)
    yearly_returns: pd.Series = field(default_factory=pd.Series)

    def trades_df(self) -> pd.DataFrame:
        if not self.trades:
            return pd.DataFrame()
        return pd.DataFrame([t.to_dict() for t in self.trades])


class Backtester:
    """
    Multi-pair portfolio backtester.

    Assumptions
    -----------
    - Signals are generated on bar close and filled on next bar open.
    - Stops / targets are checked on High/Low of subsequent bars.
    - Costs = spread + slippage (half on entry, half on exit via worse fill).
    - Position size constrained by 50:1 leverage and per-trade risk %.
    - Hard portfolio max drawdown kill-switch (default 20%).
    - Optional: move stop to breakeven at 1R; take partial profits at partial_r.
    """

    def __init__(
        self,
        initial_capital: float = 10_000.0,
        leverage: float = 50.0,
        max_drawdown_pct: float = 20.0,
        slippage_pips: float = 0.75,
        spreads: Optional[Dict[str, float]] = None,
        use_breakeven: bool = True,
        breakeven_r: float = 1.0,
        use_partial_tp: bool = True,
        partial_r: float = 1.2,
        partial_fraction: float = 0.5,
        max_bars_held: int = 30,
        allow_dual_positions: bool = True,
    ):
        self.initial_capital = initial_capital
        self.leverage = leverage
        self.max_drawdown_pct = max_drawdown_pct
        self.slippage_pips = slippage_pips
        self.spreads = spreads or DEFAULT_SPREADS
        self.use_breakeven = use_breakeven
        self.breakeven_r = breakeven_r
        self.use_partial_tp = use_partial_tp
        self.partial_r = partial_r
        self.partial_fraction = partial_fraction
        self.max_bars_held = max_bars_held
        self.allow_dual_positions = allow_dual_positions

    def _cost_price(self, pair: str) -> float:
        spread = self.spreads.get(pair, 0.00015)
        pip = PIP_SIZES.get(pair, 0.0001)
        return spread + self.slippage_pips * pip

    def _position_size(
        self,
        equity: float,
        risk_pct: float,
        entry: float,
        stop: float,
        pair: str,
        allocation_frac: float,
    ) -> float:
        risk_dollars = equity * allocation_frac * (risk_pct / 100.0)
        stop_dist = abs(entry - stop)
        if stop_dist <= 0 or entry <= 0:
            return 0.0
        if pair.endswith("JPY"):
            risk_per_unit = stop_dist / entry
        else:
            risk_per_unit = stop_dist
        units = risk_dollars / risk_per_unit
        max_notional = equity * self.leverage * allocation_frac
        max_units = max_notional / entry
        return float(max(0.0, min(units, max_units)))

    def _pnl(self, pair: str, side: str, entry: float, exit_: float, units: float) -> float:
        direction = 1.0 if side == "long" else -1.0
        move = (exit_ - entry) * direction
        if pair.endswith("JPY"):
            return units * (move / entry)
        return units * move

    def _r_distance(self, trade: Trade) -> float:
        return abs(trade.entry_price - trade.initial_stop)

    def _favorable_extreme(self, trade: Trade, high: float, low: float) -> float:
        if trade.side == "long":
            return high
        return low

    def _adverse_extreme(self, trade: Trade, high: float, low: float) -> float:
        if trade.side == "long":
            return low
        return high

    def _price_at_r(self, trade: Trade, r_mult: float) -> float:
        dist = self._r_distance(trade)
        if trade.side == "long":
            return trade.entry_price + r_mult * dist
        return trade.entry_price - r_mult * dist

    def run(
        self,
        signal_frames: Dict[str, pd.DataFrame],
        capital_alloc: Optional[Dict[str, float]] = None,
    ) -> BacktestResult:
        capital_alloc = capital_alloc or {"sniper": 0.60, "background": 0.40}
        strategies = list(capital_alloc.keys())

        all_idx = sorted(set().union(*[set(df.index) for df in signal_frames.values()]))
        idx = pd.DatetimeIndex(all_idx)

        equity = self.initial_capital
        peak = equity
        halted = False
        open_trades: List[Trade] = []
        closed: List[Trade] = []
        equity_points = []
        monthly_counts: Dict[Tuple[str, str, str], int] = {}

        for ts in idx:
            if halted:
                equity_points.append((ts, equity))
                continue

            still_open: List[Trade] = []
            for trade in open_trades:
                df = signal_frames.get(trade.pair)
                if df is None or ts not in df.index:
                    still_open.append(trade)
                    continue
                bar = df.loc[ts]
                high = float(bar["High"])
                low = float(bar["Low"])
                close_px = float(bar["Close"])
                trade.bars_held += 1
                r_dist = self._r_distance(trade)
                exited = False

                # Manage partial TP / breakeven using favorable excursion.
                fav = self._favorable_extreme(trade, high, low)
                if r_dist > 0:
                    if trade.side == "long":
                        fav_r = (fav - trade.entry_price) / r_dist
                    else:
                        fav_r = (trade.entry_price - fav) / r_dist
                else:
                    fav_r = 0.0

                if (
                    self.use_partial_tp
                    and not trade.partial_taken
                    and fav_r >= self.partial_r
                    and trade.size_units > 0
                ):
                    part_units = trade.size_units * self.partial_fraction
                    part_price = self._price_at_r(trade, self.partial_r)
                    cost = self._cost_price(trade.pair) / 2.0
                    fill = part_price - cost if trade.side == "long" else part_price + cost
                    pnl_part = self._pnl(trade.pair, trade.side, trade.entry_price, fill, part_units)
                    equity += pnl_part
                    trade.realized_partial += pnl_part
                    trade.size_units -= part_units
                    trade.partial_taken = True
                    # After partial, tighten stop to breakeven
                    trade.stop_loss = trade.entry_price
                    trade.moved_be = True

                if (
                    self.use_breakeven
                    and not trade.moved_be
                    and fav_r >= self.breakeven_r
                ):
                    trade.stop_loss = trade.entry_price
                    trade.moved_be = True

                # Stop / target / time exit
                hit_sl = hit_tp = hit_time = False
                exit_price = None
                reason = ""

                if trade.side == "long":
                    if low <= trade.stop_loss:
                        hit_sl = True
                        exit_price = trade.stop_loss
                        reason = "stop_loss" if not trade.moved_be else "breakeven_stop"
                    elif high >= trade.take_profit:
                        hit_tp = True
                        exit_price = trade.take_profit
                        reason = "take_profit"
                else:
                    if high >= trade.stop_loss:
                        hit_sl = True
                        exit_price = trade.stop_loss
                        reason = "stop_loss" if not trade.moved_be else "breakeven_stop"
                    elif low <= trade.take_profit:
                        hit_tp = True
                        exit_price = trade.take_profit
                        reason = "take_profit"

                if not (hit_sl or hit_tp) and trade.bars_held >= self.max_bars_held:
                    hit_time = True
                    exit_price = close_px
                    reason = "time_exit"

                if hit_sl or hit_tp or hit_time:
                    cost = self._cost_price(trade.pair) / 2.0
                    if trade.side == "long":
                        fill = exit_price - cost
                    else:
                        fill = exit_price + cost
                    pnl = self._pnl(
                        trade.pair, trade.side, trade.entry_price, fill, trade.size_units
                    )
                    equity += pnl
                    trade.exit_time = ts
                    trade.exit_price = fill
                    trade.pnl = pnl + trade.realized_partial
                    trade.pnl_pct = trade.pnl / self.initial_capital * 100.0
                    trade.exit_reason = reason + ("_partial" if trade.partial_taken else "")
                    closed.append(trade)
                    exited = True

                if not exited:
                    still_open.append(trade)

            open_trades = still_open

            peak = max(peak, equity)
            dd_pct = (peak - equity) / peak * 100.0 if peak > 0 else 0.0
            if dd_pct >= self.max_drawdown_pct:
                for trade in open_trades:
                    df = signal_frames.get(trade.pair)
                    if df is None or ts not in df.index:
                        continue
                    close_px = float(df.loc[ts, "Close"])
                    cost = self._cost_price(trade.pair) / 2.0
                    fill = close_px - cost if trade.side == "long" else close_px + cost
                    pnl = self._pnl(
                        trade.pair, trade.side, trade.entry_price, fill, trade.size_units
                    )
                    equity += pnl
                    trade.exit_time = ts
                    trade.exit_price = fill
                    trade.pnl = pnl + trade.realized_partial
                    trade.pnl_pct = trade.pnl / self.initial_capital * 100.0
                    trade.exit_reason = "max_drawdown_halt"
                    closed.append(trade)
                open_trades = []
                halted = True
                equity_points.append((ts, equity))
                continue

            for pair, df in signal_frames.items():
                if ts not in df.index:
                    continue
                bar = df.loc[ts]
                for strat in strategies:
                    sig_col = f"{strat}_signal"
                    if sig_col not in df.columns:
                        continue
                    signal = int(bar[sig_col]) if not pd.isna(bar[sig_col]) else 0
                    if signal == 0:
                        continue

                    if self.allow_dual_positions:
                        if any(t.pair == pair and t.strategy == strat for t in open_trades):
                            continue
                    else:
                        if any(t.pair == pair for t in open_trades):
                            continue

                    allow_col = f"{strat}_allow"
                    if allow_col in df.columns and not bool(bar[allow_col]):
                        continue

                    max_month = bar.get(f"{strat}_max_per_month", np.nan)
                    ym = f"{ts.year}-{ts.month:02d}"
                    key = (pair, strat, ym)
                    if not pd.isna(max_month) and int(max_month) > 0:
                        if monthly_counts.get(key, 0) >= int(max_month):
                            continue

                    atr = float(bar.get("atr", np.nan))
                    if not np.isfinite(atr) or atr <= 0:
                        continue

                    sl_mult = float(bar.get(f"{strat}_sl_atr_mult", 1.0))
                    tp_mult = float(bar.get(f"{strat}_tp_atr_mult", 2.0))
                    risk_pct = float(bar.get(f"{strat}_risk_pct", 1.0))
                    regime = str(bar.get("regime", "normal"))

                    open_px = float(bar["Open"])
                    cost = self._cost_price(pair) / 2.0
                    if signal > 0:
                        entry = open_px + cost
                        sl = entry - sl_mult * atr
                        tp = entry + tp_mult * atr
                        side = "long"
                    else:
                        entry = open_px - cost
                        sl = entry + sl_mult * atr
                        tp = entry - tp_mult * atr
                        side = "short"

                    units = self._position_size(
                        equity=equity,
                        risk_pct=risk_pct,
                        entry=entry,
                        stop=sl,
                        pair=pair,
                        allocation_frac=capital_alloc[strat],
                    )
                    if units <= 0:
                        continue

                    trade = Trade(
                        pair=pair,
                        strategy=strat,
                        side=side,
                        entry_time=ts,
                        entry_price=entry,
                        stop_loss=sl,
                        take_profit=tp,
                        size_units=units,
                        risk_pct=risk_pct,
                        regime=regime,
                        initial_stop=sl,
                        initial_tp=tp,
                        initial_units=units,
                    )
                    open_trades.append(trade)
                    monthly_counts[key] = monthly_counts.get(key, 0) + 1

            equity_points.append((ts, equity))

        if open_trades:
            for trade in open_trades:
                df = signal_frames[trade.pair]
                close_px = float(df.iloc[-1]["Close"])
                cost = self._cost_price(trade.pair) / 2.0
                fill = close_px - cost if trade.side == "long" else close_px + cost
                pnl = self._pnl(
                    trade.pair, trade.side, trade.entry_price, fill, trade.size_units
                )
                equity += pnl
                trade.exit_time = df.index[-1]
                trade.exit_price = fill
                trade.pnl = pnl + trade.realized_partial
                trade.pnl_pct = trade.pnl / self.initial_capital * 100.0
                trade.exit_reason = "end_of_data"
                closed.append(trade)
            equity_points.append((idx[-1], equity))

        eq = pd.Series(
            [e for _, e in equity_points],
            index=pd.DatetimeIndex([t for t, _ in equity_points]),
            name="equity",
        ).sort_index()
        eq = eq[~eq.index.duplicated(keep="last")]

        metrics = self.compute_metrics(eq, closed)
        monthly = eq.resample("ME").last().pct_change().dropna()
        by_year = eq.groupby(eq.index.year).last()
        yearly_rets = {}
        prev = self.initial_capital
        for year, val in by_year.items():
            yearly_rets[year] = (val / prev) - 1.0
            prev = val
        yearly = pd.Series(yearly_rets)

        return BacktestResult(
            equity_curve=eq,
            trades=closed,
            metrics=metrics,
            monthly_returns=monthly,
            yearly_returns=yearly,
        )

    def compute_metrics(self, equity: pd.Series, trades: List[Trade]) -> dict:
        if equity.empty:
            return {
                "total_return_pct": 0.0,
                "annualized_return_pct": 0.0,
                "max_drawdown_pct": 0.0,
                "sharpe": 0.0,
                "win_rate": 0.0,
                "total_trades": 0,
                "trades_per_month": 0.0,
                "profit_factor": 0.0,
                "final_equity": self.initial_capital,
            }

        total_return = equity.iloc[-1] / self.initial_capital - 1.0
        days = max((equity.index[-1] - equity.index[0]).days, 1)
        years = days / 365.25
        ann = (1 + total_return) ** (1 / years) - 1 if years > 0 and (1 + total_return) > 0 else -1.0

        roll_max = equity.cummax()
        dd = (equity - roll_max) / roll_max
        max_dd = float(dd.min() * 100.0)

        daily = equity.resample("1D").last().ffill().pct_change().dropna()
        if len(daily) > 2 and daily.std() > 0:
            sharpe = float(np.sqrt(252) * daily.mean() / daily.std())
        else:
            sharpe = 0.0

        wins = [t for t in trades if t.pnl > 0]
        losses = [t for t in trades if t.pnl <= 0]
        win_rate = len(wins) / len(trades) * 100.0 if trades else 0.0
        gross_win = sum(t.pnl for t in wins)
        gross_loss = abs(sum(t.pnl for t in losses))
        pf = gross_win / gross_loss if gross_loss > 0 else float("inf") if gross_win > 0 else 0.0
        months = max(days / 30.437, 1e-9)
        tpm = len(trades) / months

        return {
            "total_return_pct": round(total_return * 100.0, 2),
            "annualized_return_pct": round(ann * 100.0, 2),
            "max_drawdown_pct": round(abs(max_dd), 2),
            "sharpe": round(sharpe, 3),
            "win_rate": round(win_rate, 2),
            "total_trades": len(trades),
            "trades_per_month": round(tpm, 2),
            "profit_factor": round(pf, 3) if np.isfinite(pf) else 999.0,
            "final_equity": round(float(equity.iloc[-1]), 2),
            "years": round(years, 2),
            "avg_trade_pnl": round(float(np.mean([t.pnl for t in trades])), 2) if trades else 0.0,
        }
