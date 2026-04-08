"""
Unit tests for scripts/analyze_scan_attribution.py
"""
import sys
import os
from datetime import date, timedelta
from decimal import Decimal
from typing import List

import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from scripts.analyze_scan_attribution import (
    classify_trades,
    compute_stats,
    SCAN_TYPES,
)
from src.backtest.models import Position, PositionStatus


def _make_position(
    symbol: str,
    entry_date: date,
    pnl: float = 100.0,
    pnl_pct: float = 5.0,
    holding: int = 3,
    signal: str = "BB Squeeze Break",
) -> Position:
    return Position(
        symbol=symbol,
        quantity=1000,
        entry_price=Decimal("100"),
        entry_date=entry_date,
        current_price=Decimal("105"),
        current_date=entry_date + timedelta(days=holding),
        status=PositionStatus.CLOSED,
        exit_price=Decimal("105"),
        exit_date=entry_date + timedelta(days=holding),
        pnl=Decimal(str(pnl)),
        pnl_percent=Decimal(str(pnl_pct)),
        holding_days=holding,
        entry_signal_name=signal,
    )


class TestClassifyTrades:
    def _make_whitelists(self):
        d = date(2025, 3, 1)
        return {
            "momentum": {d: {"AAPL", "TSLA"}},
            "oversold": {d: {"NVDA"}},
            "breakout":  {d: {"AAPL", "MSFT"}},
        }

    def test_trade_in_single_category(self):
        wls = self._make_whitelists()
        d = date(2025, 3, 1)
        pos = _make_position("NVDA", d)  # only in oversold
        groups = classify_trades([pos], wls)
        assert pos in groups["oversold"]
        assert pos not in groups["momentum"]
        assert pos not in groups["breakout"]
        assert pos not in groups["none"]

    def test_trade_in_multiple_categories(self):
        wls = self._make_whitelists()
        d = date(2025, 3, 1)
        pos = _make_position("AAPL", d)  # in both momentum + breakout
        groups = classify_trades([pos], wls)
        assert pos in groups["momentum"]
        assert pos in groups["breakout"]
        assert pos not in groups["oversold"]
        assert pos not in groups["none"]

    def test_trade_in_no_category(self):
        wls = self._make_whitelists()
        d = date(2025, 3, 1)
        pos = _make_position("UNKNOWN", d)
        groups = classify_trades([pos], wls)
        assert pos in groups["none"]
        for t in SCAN_TYPES:
            assert pos not in groups[t]

    def test_uses_most_recent_whitelist_date(self):
        """Entry date T+1 should use whitelist from T (most recent available)"""
        d = date(2025, 3, 1)
        wls = {
            "momentum": {d: {"AAPL"}},  # whitelist on day d
            "oversold": {},
            "breakout": {},
        }
        pos = _make_position("AAPL", d + timedelta(days=1))  # entry day after whitelist
        groups = classify_trades([pos], wls)
        assert pos in groups["momentum"]  # uses d's whitelist

    def test_no_available_whitelist_date(self):
        """If whitelist only has future dates, trade goes to none"""
        future = date(2025, 4, 1)
        wls = {
            "momentum": {future: {"AAPL"}},
            "oversold": {},
            "breakout": {},
        }
        pos = _make_position("AAPL", date(2025, 3, 1))  # entry before whitelist
        groups = classify_trades([pos], wls)
        assert pos in groups["none"]

    def test_empty_positions(self):
        wls = self._make_whitelists()
        groups = classify_trades([], wls)
        for t in list(SCAN_TYPES) + ["none"]:
            assert groups[t] == []


class TestComputeStats:
    def test_empty_positions(self):
        s = compute_stats("test", [])
        assert s.trades == 0
        assert s.win_rate == 0.0
        assert s.total_pnl_pct == 0.0

    def test_all_winning_trades(self):
        positions = [
            _make_position("A", date(2025, 1, 1), pnl=100, pnl_pct=5.0),
            _make_position("B", date(2025, 1, 2), pnl=200, pnl_pct=10.0),
        ]
        s = compute_stats("test", positions)
        assert s.trades == 2
        assert s.wins == 2
        assert s.win_rate == 100.0
        assert abs(s.avg_pnl_pct - 7.5) < 1e-9
        assert abs(s.total_pnl_pct - 15.0) < 1e-9

    def test_mixed_win_loss(self):
        positions = [
            _make_position("A", date(2025, 1, 1), pnl=100,  pnl_pct=5.0),
            _make_position("B", date(2025, 1, 2), pnl=-50,  pnl_pct=-2.5),
        ]
        s = compute_stats("test", positions)
        assert s.wins == 1
        assert abs(s.win_rate - 50.0) < 1e-9
        assert abs(s.avg_pnl_pct - 1.25) < 1e-9

    def test_signal_breakdown(self):
        positions = [
            _make_position("A", date(2025, 1, 1), pnl=100, signal="Donchian Breakout"),
            _make_position("B", date(2025, 1, 2), pnl=-50, signal="Donchian Breakout"),
            _make_position("C", date(2025, 1, 3), pnl=80,  signal="BB Squeeze Break"),
        ]
        s = compute_stats("test", positions)
        assert s.signal_breakdown["Donchian Breakout"]["trades"] == 2
        assert s.signal_breakdown["Donchian Breakout"]["wins"] == 1
        assert s.signal_breakdown["BB Squeeze Break"]["trades"] == 1
        assert s.signal_breakdown["BB Squeeze Break"]["wins"] == 1

    def test_holding_days_average(self):
        positions = [
            _make_position("A", date(2025, 1, 1), holding=2),
            _make_position("B", date(2025, 1, 2), holding=4),
        ]
        s = compute_stats("test", positions)
        assert abs(s.avg_holding - 3.0) < 1e-9
