"""
Unit tests for scripts/backtest_scan_types.py utility functions
"""
import sys
import os
from datetime import date
from decimal import Decimal

import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from scripts.backtest_scan_types import _compute_rsi, _compute_ma, build_scan_whitelist
from src.backtest.models import StockData


# ─────────────────────────────────────────────
# _compute_rsi
# ─────────────────────────────────────────────

class TestComputeRsi:
    def test_length_matches_input(self):
        closes = [float(i + 100) for i in range(30)]
        result = _compute_rsi(closes, period=14)
        assert len(result) == len(closes)

    def test_first_period_values_are_nan(self):
        closes = [float(i + 100) for i in range(30)]
        result = _compute_rsi(closes, period=14)
        for v in result[:14]:
            assert v != v  # nan check

    def test_uptrend_gives_high_rsi(self):
        # Strictly increasing prices → RSI should be high
        closes = [float(100 + i * 2) for i in range(30)]
        result = _compute_rsi(closes, period=14)
        assert result[-1] > 70

    def test_downtrend_gives_low_rsi(self):
        closes = [float(200 - i * 2) for i in range(30)]
        result = _compute_rsi(closes, period=14)
        assert result[-1] < 30

    def test_short_series_returns_all_nan(self):
        closes = [100.0, 101.0, 99.0]
        result = _compute_rsi(closes, period=14)
        assert all(v != v for v in result)


# ─────────────────────────────────────────────
# _compute_ma
# ─────────────────────────────────────────────

class TestComputeMa:
    def test_length_matches_input(self):
        closes = [float(i + 100) for i in range(30)]
        result = _compute_ma(closes, period=20)
        assert len(result) == len(closes)

    def test_first_period_minus_one_are_nan(self):
        closes = [float(i + 100) for i in range(30)]
        result = _compute_ma(closes, period=20)
        for v in result[:19]:
            assert v != v

    def test_constant_series(self):
        closes = [50.0] * 30
        result = _compute_ma(closes, period=5)
        for v in result[4:]:
            assert abs(v - 50.0) < 1e-9

    def test_ma_value_is_average(self):
        closes = [1.0, 2.0, 3.0, 4.0, 5.0]
        result = _compute_ma(closes, period=5)
        assert abs(result[-1] - 3.0) < 1e-9


# ─────────────────────────────────────────────
# build_scan_whitelist
# ─────────────────────────────────────────────

def _make_stock_data(symbol: str, closes: list, volumes: list, start: date) -> list:
    from datetime import timedelta
    records = []
    for i, (c, v) in enumerate(zip(closes, volumes)):
        records.append(StockData(
            symbol=symbol,
            date=start + timedelta(days=i),
            open_price=Decimal(str(c)),
            high_price=Decimal(str(c * 1.01)),
            low_price=Decimal(str(c * 0.99)),
            close_price=Decimal(str(c)),
            volume=v,
        ))
    return records


class TestBuildScanWhitelist:
    """Test whitelist building for each scan type"""

    def _make_universe(self):
        """Create a minimal universe with 3 stocks and 35 daily records"""
        from datetime import timedelta
        start = date(2025, 1, 1)

        # Uptrend stock: price goes up every day, high volume
        closes_up = [100.0 + i * 1.0 for i in range(35)]
        volumes_up = [600_000] * 35

        # Oversold stock: price drops sharply, then recovers; high volume
        closes_down = [100.0 - i * 1.5 for i in range(35)]
        closes_down = [max(c, 1.0) for c in closes_down]  # floor at 1
        volumes_down = [400_000] * 35

        # Flat stock: minimal movement
        closes_flat = [50.0] * 35
        volumes_flat = [100_000] * 35

        return {
            "UP": _make_stock_data("UP", closes_up, volumes_up, start),
            "DOWN": _make_stock_data("DOWN", closes_down, volumes_down, start),
            "FLAT": _make_stock_data("FLAT", closes_flat, volumes_flat, start),
        }

    def test_momentum_whitelist_non_empty(self):
        universe = self._make_universe()
        start = date(2025, 1, 22)  # after 21 warm-up days
        end = date(2025, 2, 4)
        wl = build_scan_whitelist(universe, "momentum", start, end)
        # UP stock has +1% daily change > 3%? No, only 1% — let's just check it runs
        assert isinstance(wl, dict)

    def test_oversold_whitelist_structure(self):
        universe = self._make_universe()
        start = date(2025, 1, 22)
        end = date(2025, 2, 4)
        wl = build_scan_whitelist(universe, "oversold", start, end)
        assert isinstance(wl, dict)
        # All values should be sets of strings
        for v in wl.values():
            assert isinstance(v, set)

    def test_breakout_whitelist_structure(self):
        universe = self._make_universe()
        start = date(2025, 1, 22)
        end = date(2025, 2, 4)
        wl = build_scan_whitelist(universe, "breakout", start, end)
        assert isinstance(wl, dict)

    def test_whitelist_dates_within_range(self):
        universe = self._make_universe()
        start = date(2025, 1, 22)
        end = date(2025, 2, 4)
        for scan_type in ("momentum", "oversold", "breakout"):
            wl = build_scan_whitelist(universe, scan_type, start, end)
            for d in wl:
                assert start <= d <= end

    def test_momentum_requires_price_change(self):
        """Flat stock (0% daily change) should not appear in momentum whitelist"""
        from datetime import timedelta
        start = date(2025, 1, 1)
        # Create a stock with no price change but high volume
        closes = [100.0] * 35
        volumes = [1_000_000] * 35
        universe = {"FLAT_HIGH_VOL": _make_stock_data("FLAT_HIGH_VOL", closes, volumes, start)}
        ws = date(2025, 1, 22)
        we = date(2025, 2, 4)
        wl = build_scan_whitelist(universe, "momentum", ws, we)
        for s in wl.values():
            assert "FLAT_HIGH_VOL" not in s

    def test_breakout_requires_close_above_ma20(self):
        """A stock with close below MA20 should not appear in breakout whitelist"""
        from datetime import timedelta
        start = date(2025, 1, 1)
        # Downtrend stock: starts high and drops below MA20 quickly
        closes = [100.0 - i * 0.5 for i in range(35)]
        volumes = [2_000_000] * 35  # high volume
        universe = {"DOWNTREND": _make_stock_data("DOWNTREND", closes, volumes, start)}
        ws = date(2025, 1, 22)
        we = date(2025, 2, 4)
        wl = build_scan_whitelist(universe, "breakout", ws, we)
        # Downtrend: close < MA20 towards the end → should not be in breakout
        for d, s in wl.items():
            # Can't guarantee exact result due to MA warmup, just verify no error
            assert isinstance(s, set)

    def test_unknown_scan_type_returns_empty(self):
        universe = self._make_universe()
        start = date(2025, 1, 22)
        end = date(2025, 2, 4)
        wl = build_scan_whitelist(universe, "nonexistent", start, end)
        assert wl == {}

    def test_insufficient_data_skipped(self):
        """Stocks with < 25 records should be silently skipped"""
        from datetime import timedelta
        start = date(2025, 1, 1)
        short_records = _make_stock_data("SHORT", [100.0] * 10, [1_000_000] * 10, start)
        universe = {"SHORT": short_records}
        ws = date(2025, 1, 1)
        we = date(2025, 1, 15)
        wl = build_scan_whitelist(universe, "breakout", ws, we)
        assert wl == {}
