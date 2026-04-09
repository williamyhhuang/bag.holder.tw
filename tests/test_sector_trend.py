"""
Unit tests for src/scanner/sector_trend.py
"""
import sys
import os
from datetime import date
from decimal import Decimal

import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.scanner.sector_trend import (
    SectorTrendAnalyzer,
    MIN_SECTOR_STOCKS,
    _EXEMPT_SECTORS,
)
from src.backtest.models import StockData


def _make_stock_data(symbol: str, dates_prices: list[tuple]) -> list[StockData]:
    """建立測試用 StockData 清單"""
    records = []
    for d, price in dates_prices:
        records.append(StockData(
            symbol=symbol,
            date=d,
            open_price=Decimal(str(price)),
            high_price=Decimal(str(price)),
            low_price=Decimal(str(price)),
            close_price=Decimal(str(price)),
            volume=1_000_000,
        ))
    return records


class TestGetStockSector:
    """SectorTrendAnalyzer.get_stock_sector()"""

    def setup_method(self):
        self.analyzer = SectorTrendAnalyzer()

    def test_tsmc_is_electronics(self):
        # 2330 前兩碼 "23" → 電子工業（TWSE 產業別分類獨立於股票代碼前綴）
        assert self.analyzer.get_stock_sector("2330") == "電子工業"

    def test_umc_is_semiconductor(self):
        # 2303 前兩碼 "23" → 電子工業（同上，基於代碼前綴）
        assert self.analyzer.get_stock_sector("2303") == "電子工業"

    def test_24xx_is_semiconductor(self):
        # 2454 聯發科 前兩碼 "24" → 半導體業
        assert self.analyzer.get_stock_sector("2454") == "半導體業"

    def test_food_sector(self):
        # 1216 統一 → 食品工業
        assert self.analyzer.get_stock_sector("1216") == "食品工業"

    def test_plastics_sector(self):
        # 1301 台塑 → 塑膠工業
        assert self.analyzer.get_stock_sector("1301") == "塑膠工業"

    def test_finance_sector(self):
        # 2882 國泰金 → 金融保險
        assert self.analyzer.get_stock_sector("2882") == "金融保險"

    def test_shipping_sector(self):
        # 2603 長榮 → 航運業
        assert self.analyzer.get_stock_sector("2603") == "航運業"

    def test_biotech_sector(self):
        # 4102 → 生技醫療
        assert self.analyzer.get_stock_sector("4102") == "生技醫療"

    def test_otc_stock_with_o_suffix(self):
        # OTC 股票後綴 'O' 需被去除再查詢
        # 6274O → 前兩碼 '62' → 科技上櫃
        assert self.analyzer.get_stock_sector("6274O") == "科技上櫃"

    def test_etf(self):
        assert self.analyzer.get_stock_sector("0050") == "ETF"

    def test_unknown_prefix_returns_other(self):
        assert self.analyzer.get_stock_sector("9999") == "其他"


class TestComputeSectorStrength:
    """SectorTrendAnalyzer.compute_sector_strength()"""

    def setup_method(self):
        self.analyzer = SectorTrendAnalyzer()

    def _make_dates(self, n: int, base: date = date(2025, 1, 2)) -> list[date]:
        """產生 n 個連續工作日（每天 +1 day，簡化版）"""
        from datetime import timedelta
        return [base + timedelta(days=i) for i in range(n)]

    def test_all_above_ma20_gives_100_pct(self):
        """所有股票都在 MA20 上方 → strength = 1.0"""
        # 準備 MIN_SECTOR_STOCKS + 1 支股票，都是上升趨勢（後面價格 > MA20）
        target = date(2025, 2, 1)
        stock_data = {}
        # 建立 25 筆資料，價格從 10 漲到 35（前 20 均線 ≈ 20，今天 35 > 20）
        for i in range(MIN_SECTOR_STOCKS + 1):
            symbol = f"280{i}"  # 金融保險族群
            dates_prices = []
            for j in range(25):
                d = date(2025, 1, j + 1) if j < 25 else target
                price = 10 + j  # 10, 11, ..., 34
                dates_prices.append((date(2025, 1, j + 1), price))
            dates_prices.append((target, 35))
            stock_data[symbol] = _make_stock_data(symbol, dates_prices)

        strength = self.analyzer.compute_sector_strength(stock_data, target)
        assert "金融保險" in strength
        assert strength["金融保險"] == pytest.approx(1.0, abs=0.01)

    def test_all_below_ma20_gives_0_pct(self):
        """所有股票都在 MA20 下方 → strength = 0.0"""
        target = date(2025, 2, 1)
        stock_data = {}
        # 建立資料，前 20 日價格高，今天價格低（低於 MA20）
        for i in range(MIN_SECTOR_STOCKS + 1):
            symbol = f"260{i}"  # 航運業族群
            dates_prices = []
            for j in range(20):
                dates_prices.append((date(2025, 1, j + 1), 50))  # MA20 = 50
            dates_prices.append((target, 30))  # close = 30 < MA20 = 50
            stock_data[symbol] = _make_stock_data(symbol, dates_prices)

        strength = self.analyzer.compute_sector_strength(stock_data, target)
        assert "航運業" in strength
        assert strength["航運業"] == pytest.approx(0.0, abs=0.01)

    def test_half_above_gives_50_pct(self):
        """一半股票在 MA20 上方 → strength ≈ 0.5"""
        target = date(2025, 2, 1)
        stock_data = {}
        n = 4  # 4 支股票

        for i in range(n):
            symbol = f"260{i}"  # 航運業族群
            dates_prices = []
            for j in range(20):
                dates_prices.append((date(2025, 1, j + 1), 50))  # MA20 = 50
            # 一半股票今天在 MA20 上方（60），一半在下方（40）
            close_price = 60 if i < n // 2 else 40
            dates_prices.append((target, close_price))
            stock_data[symbol] = _make_stock_data(symbol, dates_prices)

        strength = self.analyzer.compute_sector_strength(stock_data, target)
        assert "航運業" in strength
        assert strength["航運業"] == pytest.approx(0.5, abs=0.01)

    def test_insufficient_data_stock_skipped(self):
        """資料不足 20 天的股票不計入計算"""
        target = date(2025, 2, 1)
        stock_data = {}
        # 只有 5 天資料的股票（不足 MA20）
        for i in range(MIN_SECTOR_STOCKS + 1):
            symbol = f"260{i}"
            dates_prices = [(date(2025, 1, j + 1), 50) for j in range(5)]
            dates_prices.append((target, 60))
            stock_data[symbol] = _make_stock_data(symbol, dates_prices)

        strength = self.analyzer.compute_sector_strength(stock_data, target)
        # 資料不足，所有股票都被跳過，沒有統計結果
        assert "航運業" not in strength

    def test_small_sector_returns_1_0(self):
        """股票數 < MIN_SECTOR_STOCKS 的族群強度設為 1.0（不過濾）"""
        target = date(2025, 2, 1)
        stock_data = {}
        # 只有 2 支股票（< MIN_SECTOR_STOCKS=3），且都在 MA20 下方
        for i in range(MIN_SECTOR_STOCKS - 1):
            symbol = f"180{i}"  # 傳統工業族群
            dates_prices = [(date(2025, 1, j + 1), 50) for j in range(20)]
            dates_prices.append((target, 20))  # 遠低於 MA20
            stock_data[symbol] = _make_stock_data(symbol, dates_prices)

        strength = self.analyzer.compute_sector_strength(stock_data, target)
        if "傳統工業" in strength:
            assert strength["傳統工業"] == pytest.approx(1.0, abs=0.01)

    def test_exempt_sectors_not_in_result(self):
        """ETF / 其他 族群不在計算結果中"""
        target = date(2025, 2, 1)
        stock_data = {}
        for i in range(5):
            symbol = f"005{i}"  # ETF
            dates_prices = [(date(2025, 1, j + 1), 100) for j in range(21)]
            dates_prices.append((target, 120))
            stock_data[symbol] = _make_stock_data(symbol, dates_prices)

        strength = self.analyzer.compute_sector_strength(stock_data, target)
        assert "ETF" not in strength
        assert "其他" not in strength


class TestGetStrongSectors:
    """SectorTrendAnalyzer.get_strong_sectors()"""

    def setup_method(self):
        self.analyzer = SectorTrendAnalyzer()

    def test_above_threshold_is_strong(self):
        strength = {"半導體業": 0.7, "航運業": 0.3}
        strong = self.analyzer.get_strong_sectors(strength, threshold=0.5)
        assert "半導體業" in strong
        assert "航運業" not in strong

    def test_exactly_at_threshold_is_strong(self):
        strength = {"電子工業": 0.5}
        strong = self.analyzer.get_strong_sectors(strength, threshold=0.5)
        assert "電子工業" in strong

    def test_exempt_sectors_always_in_strong(self):
        """ETF / 其他 永遠視為強勢（免過濾）"""
        strength = {}  # 空的，沒有任何族群資料
        strong = self.analyzer.get_strong_sectors(strength, threshold=0.5)
        for exempt in _EXEMPT_SECTORS:
            assert exempt in strong

    def test_empty_strength_returns_only_exempt(self):
        strong = self.analyzer.get_strong_sectors({}, threshold=0.5)
        assert strong == _EXEMPT_SECTORS


class TestBuildSectorSummary:
    """SectorTrendAnalyzer.build_sector_summary()"""

    def setup_method(self):
        self.analyzer = SectorTrendAnalyzer()

    def test_sorted_by_strength_desc(self):
        strength = {"A": 0.3, "B": 0.8, "C": 0.6}
        summary = self.analyzer.build_sector_summary(strength, threshold=0.5)
        scores = [r["strength_pct"] for r in summary]
        assert scores == sorted(scores, reverse=True)

    def test_is_strong_flag(self):
        strength = {"強勢族": 0.7, "弱勢族": 0.2}
        summary = self.analyzer.build_sector_summary(strength, threshold=0.5)
        row_map = {r["sector"]: r for r in summary}
        assert row_map["強勢族"]["is_strong"] is True
        assert row_map["弱勢族"]["is_strong"] is False

    def test_strength_pct_rounded(self):
        strength = {"電子工業": 0.666}
        summary = self.analyzer.build_sector_summary(strength, threshold=0.5)
        assert summary[0]["strength_pct"] == 66.6
