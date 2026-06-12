"""
Unit tests for scripts/analyze_signal_attribution.py
"""
import sys
import os
from datetime import date, timedelta
from decimal import Decimal

import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from scripts.analyze_signal_attribution import (
    compute_signal_stats,
    classify_loo,
    build_p1_strategy,
    LooResult,
)
from src.domain.models import Position, PositionStatus
from config.settings import settings


def _make_position(
    symbol: str = "2330",
    pnl: float = 100.0,
    pnl_pct: float = 5.0,
    holding: int = 3,
    signal: str = "Donchian Breakout",
) -> Position:
    entry = date(2025, 3, 1)
    return Position(
        symbol=symbol,
        quantity=1000,
        entry_price=Decimal("100"),
        entry_date=entry,
        current_price=Decimal("105"),
        current_date=entry + timedelta(days=holding),
        status=PositionStatus.CLOSED,
        exit_price=Decimal("105"),
        exit_date=entry + timedelta(days=holding),
        pnl=Decimal(str(pnl)),
        pnl_percent=Decimal(str(pnl_pct)),
        holding_days=holding,
        entry_signal_name=signal,
    )


class TestComputeSignalStats:
    def test_empty_positions(self):
        assert compute_signal_stats([]) == {}

    def test_single_signal_basic_stats(self):
        positions = [
            _make_position(pnl=100, pnl_pct=10.0, signal="Golden Cross"),
            _make_position(pnl=-50, pnl_pct=-5.0, signal="Golden Cross"),
        ]
        stats = compute_signal_stats(positions)
        assert set(stats.keys()) == {"Golden Cross"}
        s = stats["Golden Cross"]
        assert s.trades == 2
        assert s.wins == 1
        assert s.win_rate == pytest.approx(50.0)
        assert s.avg_pnl_pct == pytest.approx(2.5)
        assert s.avg_win_pct == pytest.approx(10.0)
        assert s.avg_loss_pct == pytest.approx(-5.0)
        # 期望值 = 0.5*10 + 0.5*(-5) = 2.5
        assert s.expectancy_pct == pytest.approx(2.5)
        assert s.profit_factor == pytest.approx(100 / 50)
        assert s.total_pnl == pytest.approx(50.0)

    def test_multiple_signals_grouped(self):
        positions = [
            _make_position(signal="Golden Cross"),
            _make_position(signal="Donchian Breakout"),
            _make_position(signal="Donchian Breakout"),
        ]
        stats = compute_signal_stats(positions)
        assert stats["Golden Cross"].trades == 1
        assert stats["Donchian Breakout"].trades == 2

    def test_all_wins_profit_factor_inf(self):
        positions = [_make_position(pnl=100, pnl_pct=5.0)]
        s = compute_signal_stats(positions)["Donchian Breakout"]
        assert s.profit_factor == float('inf')
        assert s.win_rate == pytest.approx(100.0)

    def test_zero_pnl_counts_as_loss(self):
        positions = [_make_position(pnl=0, pnl_pct=0.0)]
        s = compute_signal_stats(positions)["Donchian Breakout"]
        assert s.wins == 0
        assert s.win_rate == pytest.approx(0.0)

    def test_unknown_signal_name(self):
        pos = _make_position()
        pos.entry_signal_name = None
        stats = compute_signal_stats([pos])
        assert "Unknown" in stats

    def test_avg_holding(self):
        positions = [
            _make_position(holding=2),
            _make_position(holding=4),
        ]
        s = compute_signal_stats(positions)["Donchian Breakout"]
        assert s.avg_holding == pytest.approx(3.0)


class TestClassifyLoo:
    def _loo(self, d_return, d_sharpe=0.0):
        return LooResult(
            disabled_signal="X", total_trades=10, win_rate=50.0,
            total_return_pct=10.0, sharpe=1.0, max_drawdown=5.0,
            d_return=d_return, d_sharpe=d_sharpe,
        )

    def test_negative_contribution(self):
        # 停用後報酬大幅上升 → 訊號是負貢獻
        assert "停用" in classify_loo(self._loo(d_return=3.0, d_sharpe=0.1))

    def test_positive_contribution(self):
        # 停用後報酬大幅下降 → 訊號是正貢獻
        assert "保留" in classify_loo(self._loo(d_return=-3.0))

    def test_neutral(self):
        assert "中性" in classify_loo(self._loo(d_return=0.5))

    def test_return_up_but_sharpe_down_is_neutral(self):
        # 報酬上升但 Sharpe 惡化 → 不建議停用
        assert "中性" in classify_loo(self._loo(d_return=3.0, d_sharpe=-0.2))


class TestBuildP1Strategy:
    def test_mirrors_production_settings(self):
        cfg = settings.backtest
        strategy = build_p1_strategy()
        expected_disabled = [
            s.strip() for s in cfg.disabled_signals.split(",") if s.strip()
        ]
        assert strategy.disabled_signals == expected_disabled
        assert strategy.require_ma60_uptrend == cfg.require_ma60_uptrend
        assert strategy.min_volume_lots == cfg.min_volume_lots
        assert strategy.min_confirming_signals == cfg.min_confirming_signals
        assert strategy.donchian_period == cfg.donchian_period

    def test_extra_disabled_appended(self):
        strategy = build_p1_strategy(extra_disabled=["Golden Cross"])
        assert "Golden Cross" in strategy.disabled_signals
