"""
Unit tests for FactorEngine and InstitutionalHistoryLoader
"""
import json
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import List
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.application.services.factor_engine import FactorEngine, FactorScores, _percentile_rank
from src.infrastructure.market_data.institutional_history import InstitutionalHistoryLoader


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


def _make_stock_data(symbol: str, start_date: date, closes: List[float], volumes: List[int] = None) -> List[MockStockData]:
    """建立模擬股票歷史資料"""
    result = []
    if volumes is None:
        volumes = [1_000_000] * len(closes)
    for i, (close, vol) in enumerate(zip(closes, volumes)):
        d = start_date + timedelta(days=i)
        p = Decimal(str(close))
        result.append(MockStockData(
            symbol=symbol,
            date=d,
            open_price=p,
            high_price=p * Decimal("1.02"),
            low_price=p * Decimal("0.98"),
            close_price=p,
            volume=vol,
        ))
    return result


# ── _percentile_rank ─────────────────────────────────────────────────────────

class TestPercentileRank:
    def test_empty_dict(self):
        assert _percentile_rank({}) == {}

    def test_single_item(self):
        result = _percentile_rank({"A": 10.0})
        assert result == {"A": 0.5}

    def test_two_items(self):
        result = _percentile_rank({"A": 5.0, "B": 10.0})
        assert result["A"] == pytest.approx(0.0)
        assert result["B"] == pytest.approx(1.0)

    def test_three_items_evenly_spaced(self):
        result = _percentile_rank({"A": 1.0, "B": 2.0, "C": 3.0})
        assert result["A"] == pytest.approx(0.0)
        assert result["B"] == pytest.approx(0.5)
        assert result["C"] == pytest.approx(1.0)

    def test_negative_values(self):
        result = _percentile_rank({"A": -10.0, "B": 0.0, "C": 10.0})
        assert result["A"] < result["B"] < result["C"]

    def test_all_same_values(self):
        result = _percentile_rank({"A": 5.0, "B": 5.0})
        # 相同值按字母排序，A 排前（0.0），B 排後（1.0）
        assert set(result.values()) == {0.0, 1.0}


# ── FactorEngine._compute_rps ────────────────────────────────────────────────

class TestComputeRps:
    def setup_method(self):
        self.engine = FactorEngine()
        self.target_date = date(2025, 1, 30)

    def test_rps_positive_return(self):
        """股票上漲時 RPS 原始值為正"""
        # 63 天前 100，今天 120 → 報酬率 +20%
        closes = [100.0] * 63 + [120.0]
        start = self.target_date - timedelta(days=63)
        data = {"A": _make_stock_data("A", start, closes)}
        result = self.engine._compute_rps(data, self.target_date, 63)
        assert "A" in result
        assert result["A"] == pytest.approx(0.20, rel=0.01)

    def test_rps_insufficient_data(self):
        """資料不足時不計入結果"""
        closes = [100.0] * 10  # 只有 10 天資料
        start = self.target_date - timedelta(days=9)
        data = {"A": _make_stock_data("A", start, closes)}
        result = self.engine._compute_rps(data, self.target_date, 63)
        assert "A" not in result

    def test_rps_ranking_order(self):
        """上漲多的股票 RPS 百分位應高於上漲少的"""
        start = self.target_date - timedelta(days=64)
        # A 漲 30%，B 漲 5%
        closes_a = [100.0] * 63 + [130.0]
        closes_b = [100.0] * 63 + [105.0]
        candidate_data = {
            "A": _make_stock_data("A", start, closes_a),
            "B": _make_stock_data("B", start, closes_b),
        }
        raw = self.engine._compute_rps(candidate_data, self.target_date, 63)
        pct = _percentile_rank(raw)
        assert pct["A"] > pct["B"]


# ── FactorEngine._compute_vol_ratio ─────────────────────────────────────────

class TestComputeVolRatio:
    def setup_method(self):
        self.engine = FactorEngine()
        self.target_date = date(2025, 1, 30)

    def test_vol_ratio_calculation(self):
        """今日量是均量 2 倍時，比率應為 2.0"""
        start = self.target_date - timedelta(days=21)
        vols = [1_000_000] * 20 + [2_000_000]  # 前 20 天均量 100萬，今天 200萬
        closes = [100.0] * 21
        data = {"A": _make_stock_data("A", start, closes, vols)}
        result = self.engine._compute_vol_ratio(data, self.target_date)
        assert "A" in result
        assert result["A"] == pytest.approx(2.0, rel=0.01)

    def test_vol_ratio_insufficient_data(self):
        """不足 21 天資料不計入"""
        start = self.target_date - timedelta(days=10)
        data = {"A": _make_stock_data("A", start, [100.0] * 11)}
        result = self.engine._compute_vol_ratio(data, self.target_date)
        assert "A" not in result

    def test_vol_ratio_ranking(self):
        """量能爆量的股票排名應高於縮量的"""
        start = self.target_date - timedelta(days=21)
        closes = [100.0] * 21
        # A 今日量是均量 3 倍，B 是 0.5 倍
        vols_a = [1_000_000] * 20 + [3_000_000]
        vols_b = [1_000_000] * 20 + [500_000]
        data = {
            "A": _make_stock_data("A", start, closes, vols_a),
            "B": _make_stock_data("B", start, closes, vols_b),
        }
        raw = self.engine._compute_vol_ratio(data, self.target_date)
        pct = _percentile_rank(raw)
        assert pct["A"] > pct["B"]


# ── FactorEngine._compute_inst_score ────────────────────────────────────────

class TestComputeInstScore:
    def setup_method(self):
        self.engine = FactorEngine()

    def test_both_buying(self):
        """外資 3 天 + 投信 2 天 → 3*0.6 + 2*0.4 = 2.6"""
        inst = {"A": {"foreign_consecutive": 3, "trust_consecutive": 2}}
        result = self.engine._compute_inst_score(inst, {"A"})
        assert result["A"] == pytest.approx(3 * 0.6 + 2 * 0.4)

    def test_no_inst_data(self):
        """無法人資料的股票不出現在結果中（上櫃等）"""
        result = self.engine._compute_inst_score({}, {"B"})
        assert "B" not in result

    def test_inst_score_ranking(self):
        """連續買超天數多的分數應高"""
        inst = {
            "A": {"foreign_consecutive": 5, "trust_consecutive": 5},
            "B": {"foreign_consecutive": 1, "trust_consecutive": 0},
        }
        raw = self.engine._compute_inst_score(inst, {"A", "B"})
        assert raw["A"] > raw["B"]


# ── FactorEngine.compute_factor_scores ──────────────────────────────────────

class TestComputeFactorScores:
    def setup_method(self):
        self.engine = FactorEngine()
        self.target_date = date(2025, 1, 30)

    def _make_full_data(self, symbol: str, return_63d: float, vol_ratio: float) -> List[MockStockData]:
        """建立含 130 天歷史的完整股票資料"""
        start = self.target_date - timedelta(days=130)
        base_vol = 1_000_000
        today_vol = int(base_vol * vol_ratio)
        vols = [base_vol] * 129 + [today_vol]
        # 63 天前的收盤價推算
        close_63d_ago = 100.0
        close_today = close_63d_ago * (1 + return_63d)
        closes = [close_63d_ago] * 129 + [close_today]
        return _make_stock_data(symbol, start, closes, vols)

    def test_empty_candidates(self):
        assert self.engine.compute_factor_scores({}, [], self.target_date) == {}

    def test_composite_range(self):
        """合成分數應在 0~1 之間"""
        data = {
            "A": self._make_full_data("A", 0.30, 2.5),
            "B": self._make_full_data("B", 0.05, 0.8),
        }
        scores = self.engine.compute_factor_scores(
            stock_data_dict=data,
            candidate_symbols=["A", "B"],
            target_date=self.target_date,
        )
        for sym, s in scores.items():
            assert 0.0 <= s.composite <= 1.0, f"{sym}: composite={s.composite} 超出範圍"

    def test_stronger_stock_higher_score(self):
        """綜合指標更強的股票應有更高的 composite 分數"""
        data = {
            "STRONG": self._make_full_data("STRONG", 0.40, 3.0),
            "WEAK": self._make_full_data("WEAK", 0.02, 0.5),
        }
        inst = {
            "STRONG": {"foreign_consecutive": 5, "trust_consecutive": 3},
            "WEAK": {"foreign_consecutive": 0, "trust_consecutive": 0},
        }
        scores = self.engine.compute_factor_scores(
            stock_data_dict=data,
            candidate_symbols=["STRONG", "WEAK"],
            target_date=self.target_date,
            inst_consecutive=inst,
        )
        assert scores["STRONG"].composite > scores["WEAK"].composite

    def test_symbol_not_in_data_still_returns_entry(self):
        """候選清單中的股票若無歷史資料，也不會造成錯誤"""
        data = {"A": self._make_full_data("A", 0.10, 1.5)}
        scores = self.engine.compute_factor_scores(
            stock_data_dict=data,
            candidate_symbols=["A", "B"],  # B 沒有資料
            target_date=self.target_date,
        )
        assert "A" in scores
        # B 沒有足夠資料計算 RPS/Vol，仍可能有分數（預設 0.5）或不在結果中
        # 只確保不拋例外


# ── InstitutionalHistoryLoader ───────────────────────────────────────────────

class TestInstitutionalHistoryLoader:
    def test_cache_save_and_load(self, tmp_path):
        """儲存後可從快取讀取"""
        loader = InstitutionalHistoryLoader(history_dir=tmp_path)
        target = date(2025, 1, 15)
        test_data = {
            "2330": {"foreign_net": 500000, "trust_net": 100000, "dealer_net": 10000},
            "2454": {"foreign_net": -200000, "trust_net": 50000, "dealer_net": 5000},
        }
        loader._save_to_cache(target, test_data)
        loaded = loader._load_from_cache(target)
        assert loaded == test_data

    def test_cache_miss_returns_none(self, tmp_path):
        loader = InstitutionalHistoryLoader(history_dir=tmp_path)
        result = loader._load_from_cache(date(2025, 1, 1))
        assert result is None

    def test_build_consecutive_days(self, tmp_path):
        """連續買超計算正確"""
        loader = InstitutionalHistoryLoader(history_dir=tmp_path)

        # 預先快取 3 天資料
        days = [date(2025, 1, 13), date(2025, 1, 14), date(2025, 1, 15)]
        loader._save_to_cache(days[0], {
            "2330": {"foreign_net": 100000, "trust_net": 50000, "dealer_net": 0},
        })
        loader._save_to_cache(days[1], {
            "2330": {"foreign_net": 200000, "trust_net": -10000, "dealer_net": 0},
        })
        loader._save_to_cache(days[2], {
            "2330": {"foreign_net": 150000, "trust_net": 30000, "dealer_net": 0},
        })

        result = loader.build_consecutive_days(end_date=days[2], n_days=5)
        assert "2330" in result
        # 外資連續買超 3 天
        assert result["2330"]["foreign_consecutive"] == 3
        # 投信：第2天賣出，重置；第3天買進 → 連續1天
        assert result["2330"]["trust_consecutive"] == 1

    def test_fetch_from_api_on_cache_miss(self, tmp_path):
        """快取未命中時呼叫 API（mock）"""
        loader = InstitutionalHistoryLoader(history_dir=tmp_path)
        target = date(2025, 1, 15)

        mock_response = {
            "2330": {"foreign_net": 300000, "trust_net": 150000, "dealer_net": 20000}
        }
        with patch(
            "src.infrastructure.market_data.institutional_history._fetch_t86_for_date",
            return_value=mock_response,
        ):
            result = loader.load_date(target)

        assert result == mock_response
        # 應已快取
        cached = loader._load_from_cache(target)
        assert cached == mock_response

    def test_non_trading_day_not_cached(self, tmp_path):
        """非交易日（API 回傳 None）不會快取空資料"""
        loader = InstitutionalHistoryLoader(history_dir=tmp_path)
        target = date(2025, 1, 1)  # 元旦

        with patch(
            "src.infrastructure.market_data.institutional_history._fetch_t86_for_date",
            return_value=None,
        ):
            result = loader.load_date(target)

        assert result == {}
        # 非交易日不應快取
        assert not (tmp_path / f"{target.strftime('%Y%m%d')}.json").exists()
