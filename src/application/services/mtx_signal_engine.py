"""
MTX Signal Engine — 微台指 (MTX) 多重時間框架技術分析
實作 SKILL.md 進出場策略：日K定方向、5分K確認、1分K找進場
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from datetime import datetime, time
from enum import Enum
from typing import Dict, List, Optional, Tuple

import numpy as np

try:
    import talib as _talib  # type: ignore

    _TALIB = True
except ImportError:  # pragma: no cover
    _TALIB = False


# ---------------------------------------------------------------------------
# Domain types
# ---------------------------------------------------------------------------

class SignalDirection(Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    CLOSE_LONG = "CLOSE_LONG"
    CLOSE_SHORT = "CLOSE_SHORT"
    HOLD = "HOLD"


@dataclass
class TradeSignal:
    direction: SignalDirection
    price: float
    timestamp: datetime
    reason: str
    confidence: float  # 0.0–1.0


# ---------------------------------------------------------------------------
# Bar management
# ---------------------------------------------------------------------------

@dataclass
class OHLCVBar:
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int

    @classmethod
    def from_tick(cls, ts: datetime, price: float, volume: int) -> "OHLCVBar":
        return cls(ts, price, price, price, price, volume)

    def update(self, price: float, volume: int) -> None:
        self.high = max(self.high, price)
        self.low = min(self.low, price)
        self.close = price
        self.volume += volume


def _floor_to_tf(ts: datetime, minutes: int) -> datetime:
    """Floor *ts* down to the nearest *minutes* boundary."""
    total = ts.hour * 60 + ts.minute
    floored = (total // minutes) * minutes
    return ts.replace(hour=floored // 60, minute=floored % 60, second=0, microsecond=0)


class BarManager:
    """
    Builds OHLCV bars on a fixed timeframe from streaming tick data.

    Historical bars can be pre-loaded via :py:meth:`seed`.
    """

    def __init__(self, timeframe_minutes: int, max_bars: int = 300) -> None:
        self.tf = timeframe_minutes
        self.bars: deque[OHLCVBar] = deque(maxlen=max_bars)
        self.current: Optional[OHLCVBar] = None

    # ------------------------------------------------------------------
    # Seeding

    def seed(self, candles: List[Dict]) -> None:
        """
        Pre-load closed bars from REST API response.

        Each *candle* dict is expected to contain keys:
        ``time`` (or ``ts``), ``open``, ``high``, ``low``, ``close``, ``volume``.
        """
        for c in candles:
            raw_ts = c.get("time") or c.get("ts")
            if isinstance(raw_ts, str):
                # e.g. "2024-05-19T09:00:00"
                try:
                    raw_ts = datetime.fromisoformat(raw_ts[:19])
                except ValueError:
                    raw_ts = datetime.now()
            elif not isinstance(raw_ts, datetime):
                raw_ts = datetime.now()

            bar = OHLCVBar(
                ts=raw_ts,
                open=float(c.get("open", 0) or 0),
                high=float(c.get("high", 0) or 0),
                low=float(c.get("low", 0) or 0),
                close=float(c.get("close", 0) or 0),
                volume=int(c.get("volume", 0) or 0),
            )
            if bar.close > 0:
                self.bars.append(bar)

    # ------------------------------------------------------------------
    # Tick ingestion

    def add_tick(self, price: float, volume: int, ts: datetime) -> bool:
        """
        Process an incoming tick.

        Returns ``True`` if a bar was *closed* (i.e. a new bar started).
        """
        bar_ts = _floor_to_tf(ts, self.tf)
        if self.current is None:
            self.current = OHLCVBar.from_tick(bar_ts, price, volume)
            return False

        if bar_ts > self.current.ts:
            self.bars.append(self.current)
            self.current = OHLCVBar.from_tick(bar_ts, price, volume)
            return True

        self.current.update(price, volume)
        return False

    # ------------------------------------------------------------------
    # Data access

    def get_arrays(self) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """
        Return ``(open, high, low, close, volume)`` float64 arrays,
        including the currently forming bar.
        """
        bars = list(self.bars)
        if self.current is not None:
            bars.append(self.current)

        if not bars:
            empty = np.array([], dtype=float)
            return empty, empty, empty, empty, empty

        return (
            np.array([b.open for b in bars], dtype=float),
            np.array([b.high for b in bars], dtype=float),
            np.array([b.low for b in bars], dtype=float),
            np.array([b.close for b in bars], dtype=float),
            np.array([b.volume for b in bars], dtype=float),
        )

    def __len__(self) -> int:
        return len(self.bars) + (1 if self.current else 0)


# ---------------------------------------------------------------------------
# Technical indicators
# ---------------------------------------------------------------------------

def compute_stoch(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    fastk: int = 9,
    slowk: int = 3,
    slowd: int = 3,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Stochastic Oscillator (K, D).

    Uses TA-Lib when available; falls back to a pure-numpy implementation.
    """
    if _TALIB and len(close) >= fastk + slowk + slowd:
        k, d = _talib.STOCH(
            high, low, close,
            fastk_period=fastk,
            slowk_period=slowk,
            slowk_matype=0,
            slowd_period=slowd,
            slowd_matype=0,
        )
        return k, d

    return _stoch_numpy(high, low, close, fastk, slowk, slowd)


def _stoch_numpy(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    fastk: int,
    slowk: int,
    slowd: int,
) -> Tuple[np.ndarray, np.ndarray]:
    n = len(close)
    raw_k = np.full(n, np.nan)
    for i in range(fastk - 1, n):
        h = high[i - fastk + 1 : i + 1].max()
        lo = low[i - fastk + 1 : i + 1].min()
        raw_k[i] = (close[i] - lo) / (h - lo) * 100 if (h - lo) != 0 else 50.0

    # Slow %K = SMA(raw_k, slowk)
    k = np.full(n, np.nan)
    for i in range(fastk - 1 + slowk - 1, n):
        w = raw_k[i - slowk + 1 : i + 1]
        if not np.any(np.isnan(w)):
            k[i] = w.mean()

    # Slow %D = SMA(k, slowd)
    d = np.full(n, np.nan)
    for i in range(fastk - 1 + slowk - 1 + slowd - 1, n):
        w = k[i - slowd + 1 : i + 1]
        if not np.any(np.isnan(w)):
            d[i] = w.mean()

    return k, d


def compute_ma(close: np.ndarray, period: int) -> np.ndarray:
    """Simple Moving Average."""
    if _TALIB and len(close) >= period:
        return _talib.SMA(close, timeperiod=period)

    n = len(close)
    ma = np.full(n, np.nan)
    for i in range(period - 1, n):
        ma[i] = close[i - period + 1 : i + 1].mean()
    return ma


def golden_cross(k: np.ndarray, d: np.ndarray) -> bool:
    """True if K crossed **above** D on the most recent bar."""
    if len(k) < 2:
        return False
    if np.isnan(k[-2]) or np.isnan(d[-2]) or np.isnan(k[-1]) or np.isnan(d[-1]):
        return False
    return (k[-2] < d[-2]) and (k[-1] >= d[-1])


def death_cross(k: np.ndarray, d: np.ndarray) -> bool:
    """True if K crossed **below** D on the most recent bar."""
    if len(k) < 2:
        return False
    if np.isnan(k[-2]) or np.isnan(d[-2]) or np.isnan(k[-1]) or np.isnan(d[-1]):
        return False
    return (k[-2] > d[-2]) and (k[-1] <= d[-1])


# ---------------------------------------------------------------------------
# Main signal engine
# ---------------------------------------------------------------------------

class MTXSignalEngine:
    """
    Multi-timeframe signal engine for MTX (微台指).

    Timeframes used:
    * **Daily** — establish trend direction
    * **5-min**  — confirm short-term momentum
    * **1-min**  — precise entry trigger

    Parameters
    ----------
    stop_loss_pts:   Close position if loss exceeds this (default 30 pts)
    take_profit_pts: Close position if profit exceeds this (default 50 pts)
    """

    def __init__(
        self,
        stop_loss_pts: float = 30.0,
        take_profit_pts: float = 50.0,
    ) -> None:
        self.stop_loss_pts = stop_loss_pts
        self.take_profit_pts = take_profit_pts

        self.bar_1m = BarManager(1)
        self.bar_5m = BarManager(5)
        self.bar_d = BarManager(1440)  # daily bars seeded from REST API

        self.last_price: Optional[float] = None

    # ------------------------------------------------------------------
    # Seeding

    def seed_1m(self, candles: List[Dict]) -> None:
        self.bar_1m.seed(candles)

    def seed_5m(self, candles: List[Dict]) -> None:
        self.bar_5m.seed(candles)

    def seed_daily(self, candles: List[Dict]) -> None:
        self.bar_d.seed(candles)

    # ------------------------------------------------------------------
    # Tick ingestion

    def add_tick(self, price: float, volume: int, ts: Optional[datetime] = None) -> None:
        ts = ts or datetime.now()
        self.last_price = price
        self.bar_1m.add_tick(price, volume, ts)
        self.bar_5m.add_tick(price, volume, ts)

    # ------------------------------------------------------------------
    # Signal evaluation

    def evaluate(
        self,
        current_position: Optional[str] = None,
        entry_price: Optional[float] = None,
    ) -> TradeSignal:
        """
        Evaluate all timeframes and return the appropriate :class:`TradeSignal`.

        Parameters
        ----------
        current_position: ``'LONG'``, ``'SHORT'``, or ``None``
        entry_price:      Entry price of the current position (if any)
        """
        price = self.last_price or 0.0
        now = datetime.now()

        # 1. Check exit conditions first (stop-loss / take-profit / reversal)
        if current_position and entry_price is not None and price > 0:
            exit_sig = self._check_exit(current_position, entry_price, price, now)
            if exit_sig is not None:
                return exit_sig

        # 2. Entry conditions
        daily_bias = self._daily_bias()    # +1 bullish  / -1 bearish / 0 neutral
        signal_5m = self._signal_5m()      # +1          / -1         / 0
        signal_1m = self._entry_1m()       # +1 long trig/ -1 short   / 0

        # Long: daily not bearish, 5m bullish, 1m long trigger
        if daily_bias >= 0 and signal_5m == 1 and signal_1m == 1:
            if current_position != "LONG":
                conf = 0.6 + 0.15 * min(daily_bias + 1, 2)
                return TradeSignal(
                    SignalDirection.LONG, price, now,
                    f"Day={daily_bias:+d} 5m=+1 1m=+1", round(conf, 2),
                )

        # Short: daily not bullish, 5m bearish, 1m short trigger
        if daily_bias <= 0 and signal_5m == -1 and signal_1m == -1:
            if current_position != "SHORT":
                conf = 0.6 + 0.15 * min(abs(daily_bias) + 1, 2)
                return TradeSignal(
                    SignalDirection.SHORT, price, now,
                    f"Day={daily_bias:+d} 5m=-1 1m=-1", round(conf, 2),
                )

        return TradeSignal(SignalDirection.HOLD, price, now, "No signal", 0.0)

    # ------------------------------------------------------------------
    # Internal helpers

    def _check_exit(
        self,
        position: str,
        entry_price: float,
        current_price: float,
        now: datetime,
    ) -> Optional[TradeSignal]:
        pnl = (
            current_price - entry_price
            if position == "LONG"
            else entry_price - current_price
        )

        if pnl <= -self.stop_loss_pts:
            direction = (
                SignalDirection.CLOSE_LONG
                if position == "LONG"
                else SignalDirection.CLOSE_SHORT
            )
            return TradeSignal(
                direction, current_price, now,
                f"停損 {pnl:.0f}pts", 1.0,
            )

        if pnl >= self.take_profit_pts:
            direction = (
                SignalDirection.CLOSE_LONG
                if position == "LONG"
                else SignalDirection.CLOSE_SHORT
            )
            return TradeSignal(
                direction, current_price, now,
                f"獲利 {pnl:.0f}pts", 1.0,
            )

        # 1-min KD reverse cross
        _, h, l, c, _ = self.bar_1m.get_arrays()
        if len(c) >= 15:
            k_arr, d_arr = compute_stoch(h, l, c)
            if position == "LONG" and death_cross(k_arr, d_arr):
                return TradeSignal(
                    SignalDirection.CLOSE_LONG, current_price, now,
                    "1mK死叉出場", 0.8,
                )
            if position == "SHORT" and golden_cross(k_arr, d_arr):
                return TradeSignal(
                    SignalDirection.CLOSE_SHORT, current_price, now,
                    "1mK黃金交叉出場", 0.8,
                )

        return None

    def _daily_bias(self) -> int:
        """
        Daily trend bias.

        Returns +1 (bullish), -1 (bearish), or 0 (neutral / insufficient data).
        """
        _, h, l, c, _ = self.bar_d.get_arrays()
        if len(c) < 12:
            return 0

        ma5 = compute_ma(c, 5)
        ma10 = compute_ma(c, 10)
        k_arr, d_arr = compute_stoch(h, l, c)

        if any(np.isnan(x[-1]) for x in (ma5, ma10, k_arr, d_arr)):
            return 0

        kd_val = k_arr[-1]

        # Overbought / oversold override
        if kd_val > 80:
            return -1
        if kd_val < 20:
            return 1

        # Trend alignment
        if c[-1] > ma5[-1] > ma10[-1] and k_arr[-1] > d_arr[-1]:
            return 1
        if c[-1] < ma5[-1] < ma10[-1] and k_arr[-1] < d_arr[-1]:
            return -1
        return 0

    def _signal_5m(self) -> int:
        """
        5-min signal: +1 bullish, -1 bearish, 0 neutral.
        """
        _, h, l, c, v = self.bar_5m.get_arrays()
        if len(c) < 15:
            return 0

        k_arr, d_arr = compute_stoch(h, l, c)
        ma5 = compute_ma(c, 5)
        ma10 = compute_ma(c, 10)

        if np.isnan(k_arr[-1]) or np.isnan(d_arr[-1]):
            return 0

        score = 0

        # KD golden / death cross
        if golden_cross(k_arr, d_arr) and k_arr[-1] < 60:
            score += 1
        elif death_cross(k_arr, d_arr) and k_arr[-1] > 40:
            score -= 1

        # MA5 / MA10 cross (need at least 2 valid values)
        if not any(np.isnan(x) for x in (ma5[-1], ma10[-1], ma5[-2], ma10[-2])):
            if ma5[-2] < ma10[-2] and ma5[-1] >= ma10[-1]:
                score += 1
            elif ma5[-2] > ma10[-2] and ma5[-1] <= ma10[-1]:
                score -= 1

        # Volume confirmation — amplify score if volume is elevated
        if len(v) >= 5 and v[-1] > np.nanmean(v[-5:]) * 1.2 and score != 0:
            score = int(math.copysign(abs(score) + 1, score))

        return max(-1, min(1, score))

    def _entry_1m(self) -> int:
        """
        1-min entry trigger: +1 long, -1 short, 0 none.
        """
        _, h, l, c, _ = self.bar_1m.get_arrays()
        if len(c) < 15:
            return 0

        k_arr, d_arr = compute_stoch(h, l, c)
        ma5 = compute_ma(c, 5)

        if any(np.isnan(x[-1]) for x in (k_arr, d_arr, ma5)):
            return 0

        if golden_cross(k_arr, d_arr) and c[-1] > ma5[-1]:
            return 1
        if death_cross(k_arr, d_arr) and c[-1] < ma5[-1]:
            return -1
        return 0
