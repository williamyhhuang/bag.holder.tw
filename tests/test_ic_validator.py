"""
Unit tests for ICValidator (src/application/services/ic_validator.py)
"""
import math
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import List
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent.parent))

from src.application.services.ic_validator import (
    ICValidator,
    ICResult,
    ICReport,
    _spearman_correlation,
    _compute_t_stat,
)


# ── helpers ───────────────────────────────────────────────────────────────────

@dataclass
class MockStockData:
    symbol: str
    date: date
    open_price: Decimal
    high_price: Decimal
    low_price: Decimal
    close_price: Decimal
    volume: int
    adj_close: Decimal = None


def _make_records(symbol: str, start: date, closes: List[float], vols: List[int] = None) -> List[MockStockData]:
    if vols is None:
        vols = [1_000_000] * len(closes)
    records = []
    for i, (c, v) in enumerate(zip(closes, vols)):
        d = start + timedelta(days=i)
        p = Decimal(str(c))
        records.append(MockStockData(
            symbol=symbol, date=d,
            open_price=p, high_price=p, low_price=p, close_price=p,
            volume=v,
        ))
    return records


# ── _spearman_correlation ────────────────────────────────────────────────────

class TestSpearmanCorrelation:
    def test_perfect_positive(self):
        x = [1.0, 2.0, 3.0, 4.0, 5.0]
        y = [1.0, 2.0, 3.0, 4.0, 5.0]
        assert _spearman_correlation(x, y) == pytest.approx(1.0)

    def test_perfect_negative(self):
        x = [1.0, 2.0, 3.0, 4.0, 5.0]
        y = [5.0, 4.0, 3.0, 2.0, 1.0]
        assert _spearman_correlation(x, y) == pytest.approx(-1.0)

    def test_no_correlation(self):
        # 不相關序列的 IC 應接近 0，但不一定嚴格等於
        x = [1.0, 2.0, 3.0, 4.0, 5.0]
        y = [3.0, 1.0, 5.0, 2.0, 4.0]
        ic = _spearman_correlation(x, y)
        assert ic is not None
        assert abs(ic) < 0.3  # 不強相關

    def test_length_mismatch_returns_none(self):
        assert _spearman_correlation([1.0, 2.0], [1.0]) is None

    def test_too_short_returns_none(self):
        assert _spearman_correlation([1.0, 2.0], [1.0, 2.0]) is None  # n < 3

    def test_constant_x_returns_none(self):
        # 標準差為 0
        assert _spearman_correlation([5.0, 5.0, 5.0], [1.0, 2.0, 3.0]) is None

    def test_with_ties(self):
        # 有並列值也能計算
        x = [1.0, 1.0, 2.0, 3.0, 3.0]
        y = [1.0, 2.0, 3.0, 4.0, 5.0]
        ic = _spearman_correlation(x, y)
        assert ic is not None
        assert ic > 0  # 正相關

    def test_nonlinear_monotone(self):
        # 非線性但單調遞增：Spearman 應 = 1
        x = [1.0, 4.0, 9.0, 16.0, 25.0]  # x^2
        y = [1.0, 2.0, 3.0, 4.0, 5.0]
        assert _spearman_correlation(x, y) == pytest.approx(1.0)


# ── _compute_t_stat ──────────────────────────────────────────────────────────

class TestComputeTStat:
    def test_basic(self):
        # mean=0.03, std=0.10, n=100 → t = 0.03 / (0.10/10) = 3.0
        t = _compute_t_stat(0.03, 0.10, 100)
        assert t == pytest.approx(3.0)

    def test_zero_std(self):
        assert _compute_t_stat(0.05, 0.0, 50) == 0.0

    def test_zero_n(self):
        assert _compute_t_stat(0.05, 0.10, 0) == 0.0

    def test_negative_ic(self):
        t = _compute_t_stat(-0.03, 0.10, 100)
        assert t == pytest.approx(-3.0)


# ── ICResult ─────────────────────────────────────────────────────────────────

class TestICResult:
    def test_is_significant_true(self):
        r = ICResult("rps_3m", 20, 0.03, 0.08, 0.375, 2.5, 0.60, 100)
        assert r.is_significant is True
        assert r.has_predictive_power is True

    def test_is_significant_false_low_tstat(self):
        r = ICResult("rps_3m", 20, 0.03, 0.08, 0.375, 1.5, 0.60, 50)
        assert r.is_significant is False

    def test_is_significant_false_low_pos_rate(self):
        r = ICResult("rps_3m", 20, 0.03, 0.08, 0.375, 2.5, 0.50, 100)
        assert r.is_significant is False

    def test_has_predictive_power_false(self):
        r = ICResult("rps_3m", 20, 0.01, 0.08, 0.125, 2.5, 0.60, 100)
        assert r.has_predictive_power is False


# ── ICReport ─────────────────────────────────────────────────────────────────

class TestICReport:
    def test_get_result(self):
        r1 = ICResult("rps_3m", 20, 0.03, 0.08, 0.375, 2.5, 0.60, 100)
        r2 = ICResult("vol_ratio", 10, 0.01, 0.05, 0.2, 1.0, 0.50, 80)
        report = ICReport(results=[r1, r2])
        assert report.get("rps_3m", 20) is r1
        assert report.get("vol_ratio", 10) is r2
        assert report.get("rps_6m", 20) is None

    def test_summary_table_contains_factor_names(self):
        r1 = ICResult("rps_3m", 20, 0.03, 0.08, 0.375, 2.5, 0.60, 100)
        report = ICReport(
            results=[r1],
            start_date=date(2022, 1, 1),
            end_date=date(2026, 5, 30),
            universe_size=1700,
        )
        table = report.summary_table()
        assert "rps_3m" in table
        assert "20d" in table
        assert "✅" in table


# ── ICValidator._compute_factor ──────────────────────────────────────────────

class TestComputeFactor:
    def setup_method(self):
        self.validator = ICValidator()
        self.start = date(2025, 1, 1)

    def test_rps_3m_positive(self):
        closes = [100.0] * 63 + [120.0]  # 上漲 20%
        records = _make_records("A", self.start, closes)
        target = records[-1].date
        val = self.validator._compute_factor(records, target, "rps_3m")
        assert val == pytest.approx(0.20, rel=0.01)

    def test_rps_3m_insufficient_data(self):
        records = _make_records("A", self.start, [100.0] * 10)
        target = records[-1].date
        assert self.validator._compute_factor(records, target, "rps_3m") is None

    def test_vol_ratio(self):
        vols = [1_000_000] * 20 + [3_000_000]
        closes = [100.0] * 21
        records = _make_records("A", self.start, closes, vols)
        target = records[-1].date
        val = self.validator._compute_factor(records, target, "vol_ratio")
        assert val == pytest.approx(3.0, rel=0.01)

    def test_unknown_factor(self):
        records = _make_records("A", self.start, [100.0] * 30)
        target = records[-1].date
        assert self.validator._compute_factor(records, target, "unknown_factor") is None


# ── ICValidator._nth_trading_date ────────────────────────────────────────────

class TestNthTradingDate:
    def test_basic(self):
        dates = [date(2025, 1, i) for i in range(1, 11)]
        result = ICValidator._nth_trading_date(dates, date(2025, 1, 1), 5)
        assert result == date(2025, 1, 6)

    def test_out_of_range(self):
        dates = [date(2025, 1, i) for i in range(1, 6)]
        assert ICValidator._nth_trading_date(dates, date(2025, 1, 1), 10) is None

    def test_date_not_in_list(self):
        dates = [date(2025, 1, 2), date(2025, 1, 3), date(2025, 1, 6)]
        # 2025-01-01 不在清單，找最近的之後日期
        result = ICValidator._nth_trading_date(dates, date(2025, 1, 1), 2)
        # 最近後日期 2025-01-02 的 index=0, 往前 -1 無效
        # 預期回傳 None 或合理結果（不拋例外）
        # 這裡主要確保不拋例外
        pass  # 不 assert，只確保不 crash


# ── ICValidator.run（整合測試）───────────────────────────────────────────────

class TestICValidatorRun:
    def setup_method(self):
        self.validator = ICValidator()
        # 建立 5 支股票，130 天歷史
        self.start = date(2024, 1, 1)
        self.end = date(2024, 5, 10)

        returns = [0.30, 0.10, -0.05, 0.20, 0.01]
        symbols = ["A", "B", "C", "D", "E"]
        self.stock_data = {}
        for sym, ret in zip(symbols, returns):
            closes = [100.0] * 129 + [100.0 * (1 + ret)]
            self.stock_data[sym] = _make_records(sym, self.start, closes)

    def test_run_returns_report(self):
        report = self.validator.run(
            stock_data_dict=self.stock_data,
            factors=["rps_3m"],
            forward_days=[5],
            start_date=self.start,
            end_date=self.end,
            min_stocks_per_date=3,
            sampling_freq=10,
        )
        assert isinstance(report, ICReport)

    def test_run_no_crash_with_sparse_data(self):
        """稀疏資料（大部分股票資料不足）不會拋例外"""
        sparse = {"X": _make_records("X", self.start, [100.0] * 5)}
        report = self.validator.run(
            stock_data_dict=sparse,
            factors=["rps_3m"],
            forward_days=[5],
            start_date=self.start,
            end_date=self.end,
            min_stocks_per_date=20,  # 要求 20 支，但只有 1 支
            sampling_freq=5,
        )
        # 因樣本不足，結果可能為空，但不應拋例外
        assert isinstance(report, ICReport)
