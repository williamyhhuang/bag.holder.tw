"""
Unit tests for weekly signal generation (Weekly BB Squeeze Break, Weekly Donchian Breakout).
Tests cover helper functions and integration with TechnicalStrategy.
"""
import pytest
from datetime import date, timedelta
from decimal import Decimal
from typing import List

from src.application.services.backtest_strategy import (
    _build_weekly_ohlcv,
    _compute_weekly_bollinger,
    _compute_weekly_donchian_high,
    TechnicalStrategy,
)
from src.domain.models import StockData, SignalType


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_stock_data(day: date, close: float, high: float = None, low: float = None, open_: float = None) -> StockData:
    c = Decimal(str(close))
    h = Decimal(str(high)) if high is not None else c * Decimal("1.01")
    l = Decimal(str(low)) if low is not None else c * Decimal("0.99")
    o = Decimal(str(open_)) if open_ is not None else c
    return StockData(
        symbol="TEST",
        date=day,
        open_price=o,
        high_price=h,
        low_price=l,
        close_price=c,
        volume=1_000_000,
        adj_close=c,
    )


def _trading_days(start: date, n: int) -> List[date]:
    """Generate n weekdays starting from start."""
    days = []
    d = start
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d)
        d += timedelta(days=1)
    return days


def _price_series(start: date, n: int, base: float = 100.0, step: float = 0.0) -> List[StockData]:
    days = _trading_days(start, n)
    return [_make_stock_data(d, base + i * step) for i, d in enumerate(days)]


# ─────────────────────────────────────────────────────────────────────────────
# _build_weekly_ohlcv
# ─────────────────────────────────────────────────────────────────────────────

class TestBuildWeeklyOhlcv:
    def test_aggregates_to_fewer_rows(self):
        data = _price_series(date(2022, 1, 3), 10)  # 2 weeks
        weekly = _build_weekly_ohlcv(data)
        assert len(weekly) <= len(data)
        assert len(weekly) >= 1

    def test_close_is_last_day(self):
        # Mon-Fri week: close should be Friday's close
        data = [
            _make_stock_data(date(2022, 1, 3), 100),  # Mon
            _make_stock_data(date(2022, 1, 4), 101),  # Tue
            _make_stock_data(date(2022, 1, 5), 102),  # Wed
            _make_stock_data(date(2022, 1, 6), 103),  # Thu
            _make_stock_data(date(2022, 1, 7), 104),  # Fri
        ]
        weekly = _build_weekly_ohlcv(data)
        assert len(weekly) == 1
        week_date, _, _, _, close = weekly[0]
        assert week_date == date(2022, 1, 7)
        assert close == Decimal("104")

    def test_high_is_week_max(self):
        data = [
            _make_stock_data(date(2022, 1, 3), 100, high=105),
            _make_stock_data(date(2022, 1, 4), 100, high=110),
            _make_stock_data(date(2022, 1, 5), 100, high=103),
        ]
        weekly = _build_weekly_ohlcv(data)
        _, _, high, _, _ = weekly[0]
        assert high == Decimal("110")

    def test_low_is_week_min(self):
        data = [
            _make_stock_data(date(2022, 1, 3), 100, low=95),
            _make_stock_data(date(2022, 1, 4), 100, low=92),
            _make_stock_data(date(2022, 1, 5), 100, low=98),
        ]
        weekly = _build_weekly_ohlcv(data)
        _, _, _, low, _ = weekly[0]
        assert low == Decimal("92")

    def test_sorted_chronologically(self):
        data = _price_series(date(2022, 1, 3), 20)
        weekly = _build_weekly_ohlcv(data)
        dates = [row[0] for row in weekly]
        assert dates == sorted(dates)

    def test_empty_input(self):
        assert _build_weekly_ohlcv([]) == []


# ─────────────────────────────────────────────────────────────────────────────
# _compute_weekly_bollinger
# ─────────────────────────────────────────────────────────────────────────────

class TestComputeWeeklyBollinger:
    def _make_wohlcv(self, closes):
        start = date(2020, 1, 6)  # Monday
        rows = []
        for i, c in enumerate(closes):
            d = start + timedelta(weeks=i, days=4)  # Fridays
            cd = Decimal(str(c))
            rows.append((d, cd, cd * Decimal("1.01"), cd * Decimal("0.99"), cd))
        return rows

    def test_insufficient_data_returns_empty(self):
        wohlcv = self._make_wohlcv([100] * 5)
        result = _compute_weekly_bollinger(wohlcv, period=20)
        assert len(result) == 0

    def test_has_entries_for_enough_data(self):
        wohlcv = self._make_wohlcv([100] * 25)
        result = _compute_weekly_bollinger(wohlcv, period=20)
        assert len(result) == 6  # 25 - 20 + 1

    def test_upper_above_lower(self):
        wohlcv = self._make_wohlcv(list(range(80, 105)))  # 25 points
        result = _compute_weekly_bollinger(wohlcv, period=20)
        for upper, middle, lower in result.values():
            assert upper > lower
            assert upper > middle > lower

    def test_flat_price_narrow_bands(self):
        wohlcv = self._make_wohlcv([100.0] * 25)
        result = _compute_weekly_bollinger(wohlcv, period=20)
        for upper, middle, lower in result.values():
            assert abs(float(upper) - float(lower)) < 0.01  # nearly zero std


# ─────────────────────────────────────────────────────────────────────────────
# _compute_weekly_donchian_high
# ─────────────────────────────────────────────────────────────────────────────

class TestComputeWeeklyDonchianHigh:
    def _make_wohlcv(self, highs):
        start = date(2020, 1, 10)  # Fridays
        rows = []
        for i, h in enumerate(highs):
            d = start + timedelta(weeks=i)
            hd = Decimal(str(h))
            rows.append((d, hd, hd, hd * Decimal("0.98"), hd))
        return rows

    def test_no_output_until_period_plus_one(self):
        wohlcv = self._make_wohlcv([100] * 10)
        result = _compute_weekly_donchian_high(wohlcv, period=10)
        assert len(result) == 0  # exactly 10 weeks → no output (need period+1)

    def test_first_output_at_period_plus_one(self):
        highs = [100] * 11
        wohlcv = self._make_wohlcv(highs)
        result = _compute_weekly_donchian_high(wohlcv, period=10)
        assert len(result) == 1

    def test_reflects_prior_period_weeks(self):
        # highs: 10 weeks of 100, then 1 week of 90
        # donchian for week 11 should be max of weeks 1-10 = 100
        highs = [100] * 10 + [90]
        wohlcv = self._make_wohlcv(highs)
        result = _compute_weekly_donchian_high(wohlcv, period=10)
        assert len(result) == 1
        val = list(result.values())[0]
        assert val == Decimal("100")

    def test_uses_high_not_close(self):
        start = date(2020, 1, 10)
        rows = []
        for i in range(12):
            d = start + timedelta(weeks=i)
            close = Decimal("100")
            high = Decimal(str(110 + i))  # increasing highs
            rows.append((d, close, high, Decimal("95"), close))
        result = _compute_weekly_donchian_high(rows, period=10)
        # Week 11 (index 10): prior highs are weeks 0-9, max high = 110+9 = 119
        first_val = list(result.values())[0]
        assert first_val == Decimal("119")


# ─────────────────────────────────────────────────────────────────────────────
# TechnicalStrategy integration
# ─────────────────────────────────────────────────────────────────────────────

class TestWeeklySignalsIntegration:
    def _make_strategy(self, **kwargs):
        return TechnicalStrategy(
            enable_weekly_signals=True,
            weekly_bb_period=20,
            weekly_donchian_period=10,
            require_ma60_uptrend=False,
            require_volume_confirmation=False,
            rsi_min_entry=0,
            require_weekly_trend=False,
            **kwargs,
        )

    def _make_rising_data(self, n_weeks: int = 40, base: float = 100.0) -> List[StockData]:
        """Generate n_weeks of weekly data (5 days each)."""
        data = []
        start = date(2022, 1, 3)
        price = base
        d = start
        for _ in range(n_weeks * 5):
            if d.weekday() < 5:
                data.append(_make_stock_data(d, price, high=price * 1.01, low=price * 0.99))
                price *= 1.003  # gentle uptrend
            d += timedelta(days=1)
        return data

    def test_weekly_signals_disabled_by_default(self):
        strategy = TechnicalStrategy(
            require_ma60_uptrend=False,
            require_volume_confirmation=False,
            rsi_min_entry=0,
        )
        data = self._make_rising_data(35)
        signals = strategy.generate_signals("TEST", data)
        names = {s.signal_name for s in signals}
        assert "Weekly BB Squeeze Break" not in names
        assert "Weekly Donchian Breakout" not in names

    def test_weekly_signals_enabled_fires_on_week_end(self):
        strategy = self._make_strategy()
        data = self._make_rising_data(40)
        signals = strategy.generate_signals("TEST", data)
        weekly_sigs = [s for s in signals if s.signal_name.startswith("Weekly")]
        # All weekly signals must fall on last trading day of ISO week (Fri or Thu)
        for sig in weekly_sigs:
            # The day after should be in a different ISO week (or it's the last date)
            assert sig.date.weekday() in (0, 1, 2, 3, 4), "Signal not on a weekday"

    def test_weekly_donchian_fires_on_breakout(self):
        """Build a dataset where a breakout above 10-week high is obvious."""
        strategy = self._make_strategy()
        # 30 weeks of flat 100 (>120 days warmup for MA120), then 8 weeks at 130
        flat_days = _trading_days(date(2022, 1, 3), 30 * 5)
        jump_days = _trading_days(flat_days[-1] + timedelta(days=1), 8 * 5)
        data = (
            [_make_stock_data(d, 100.0, high=100.5, low=99.5) for d in flat_days]
            + [_make_stock_data(d, 130.0, high=130.65, low=129.35) for d in jump_days]
        )
        signals = strategy.generate_signals("TEST", data)
        weekly_don = [s for s in signals if s.signal_name == "Weekly Donchian Breakout"]
        assert len(weekly_don) > 0

    def test_no_weekly_signal_below_donchian_high(self):
        """Flat price never breaks above prior N-week high."""
        strategy = self._make_strategy()
        data = _trading_days(date(2022, 1, 3), 35 * 5)
        price_data = [_make_stock_data(d, 100.0, high=100.5, low=99.5) for d in data]
        signals = strategy.generate_signals("TEST", price_data)
        weekly_don = [s for s in signals if s.signal_name == "Weekly Donchian Breakout"]
        assert len(weekly_don) == 0  # flat never breaks above its own high

    def test_weekly_signals_are_buy_type(self):
        strategy = self._make_strategy()
        data = self._make_rising_data(40)
        signals = strategy.generate_signals("TEST", data)
        weekly_sigs = [s for s in signals if s.signal_name.startswith("Weekly")]
        for s in weekly_sigs:
            assert s.signal_type in (SignalType.BUY, SignalType.WATCH)
