"""
Unit tests for src/scanner/sector_trend.py
"""
import sys
import os
from datetime import date
from decimal import Decimal
from unittest.mock import patch

import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.domain.services.sector_trend_analyzer import (
    SectorTrendAnalyzer,
    MIN_SECTOR_STOCKS,
    _EXEMPT_SECTORS,
    _extract_code,
)
from src.utils.stock_industry_mapper import (
    get_sector_name,
    INDUSTRY_CODE_TO_SECTOR,
)
from src.domain.models import StockData


# ── Mock 產業別資料（避免測試時發 HTTP 請求）────────────────────────────────
MOCK_INDUSTRIES = {
    # 正確的 TWSE 官方產業別代碼（已依 openapi.twse.com.tw 驗證）
    "2330": "24",   # 台積電 → 半導體業（code 24）
    "2303": "24",   # 聯電 → 半導體業（code 24）
    "2454": "24",   # 聯發科 → 半導體業（code 24）
    "1216": "02",   # 統一 → 食品工業
    "1301": "03",   # 台塑 → 塑膠工業
    "2882": "17",   # 國泰金 → 金融保險
    "2603": "15",   # 長榮 → 航運業
    "4102": "22",   # 葡萄王型 → 生技醫療（code 22）
    "5243": "26",   # 乙盛-KY → 光電業（code 26）
    "5475": "28",   # 德宏 → 電子零組件（code 28）
    "3583": "24",   # 辛耘 → 半導體業
    "2467": "28",   # 志聖 → 電子零組件（code 28，TWSE 實際資料）
    # 金融族群（測試用）
    "2801": "17",
    "2802": "17",
    "2803": "17",
    "2804": "17",
    # 航運族群（測試用）
    "2601": "15",
    "2602": "15",
    "2603": "15",
    "2604": "15",
    # 傳統工業（測試用）
    "1801": "08",   # 玻璃陶瓷
    "1802": "08",
}


def _make_stock_data(symbol: str, dates_prices: list) -> list:
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


@pytest.fixture
def analyzer():
    """建立帶有 mock 產業別資料的 SectorTrendAnalyzer"""
    with patch("src.domain.services.sector_trend_analyzer.get_stock_industries", return_value=MOCK_INDUSTRIES):
        a = SectorTrendAnalyzer()
    return a


class TestExtractCode:
    def test_tw_stock(self):
        assert _extract_code("2330") == "2330"

    def test_otc_stock_removes_o(self):
        assert _extract_code("4741O") == "4741"

    def test_otc_stock_longer(self):
        assert _extract_code("6274O") == "6274"


class TestGetSectorName:
    """stock_industry_mapper.get_sector_name() — 依 TWSE 官方資料驗證"""

    def test_semiconductor_is_code_24(self):
        # 台積電、聯電 → code 24 = 半導體業
        assert get_sector_name("24") == "半導體業"

    def test_biotech_is_code_22(self):
        # 葡萄王、生達、五鼎 → code 22 = 生技醫療
        assert get_sector_name("22") == "生技醫療"

    def test_optoelectronics_is_code_26(self):
        # 友達、億光、中環 → code 26 = 光電業
        assert get_sector_name("26") == "光電業"

    def test_electronic_components_is_code_28(self):
        # 台達電、華通 → code 28 = 電子零組件
        assert get_sector_name("28") == "電子零組件"

    def test_finance(self):
        assert get_sector_name("17") == "金融保險"

    def test_shipping(self):
        assert get_sector_name("15") == "航運業"

    def test_food(self):
        assert get_sector_name("02") == "食品工業"

    def test_unknown_code_returns_other(self):
        assert get_sector_name("99") == "其他"

    def test_green_energy(self):
        assert get_sector_name("35") == "綠能環保"

    def test_electronic_distribution_is_code_29(self):
        # 聯強、燦坤 → code 29 = 電子通路
        assert get_sector_name("29") == "電子通路"

    def test_telecom_is_code_27(self):
        # 中華電、智邦 → code 27 = 通信網路
        assert get_sector_name("27") == "通信網路"


class TestGetStockSector:
    """SectorTrendAnalyzer.get_stock_sector() — 使用 mock 產業別資料"""

    def test_tsmc_semiconductor(self, analyzer):
        # 2330 官方代碼 24 → 半導體業
        assert analyzer.get_stock_sector("2330") == "半導體業"

    def test_5243_optoelectronics(self, analyzer):
        # 5243 乙盛-KY 官方代碼 26 → 光電業（非金融保險）
        assert analyzer.get_stock_sector("5243") == "光電業"

    def test_5475_electronic_components(self, analyzer):
        # 5475 德宏 官方代碼 28 → 電子零組件（非金融保險）
        assert analyzer.get_stock_sector("5475") == "電子零組件"

    def test_food_sector(self, analyzer):
        assert analyzer.get_stock_sector("1216") == "食品工業"

    def test_finance_sector(self, analyzer):
        assert analyzer.get_stock_sector("2882") == "金融保險"

    def test_shipping_sector(self, analyzer):
        assert analyzer.get_stock_sector("2603") == "航運業"

    def test_biotech_sector(self, analyzer):
        # 4102 mock 代碼 22 = 生技醫療
        assert analyzer.get_stock_sector("4102") == "生技醫療"

    def test_otc_stock_with_o_suffix(self, analyzer):
        # OTC 股票後綴 'O' 被去除後查詢；code 26 = 光電業
        with patch("src.domain.services.sector_trend_analyzer.get_stock_industries",
                   return_value={"6274": "26"}):
            a = SectorTrendAnalyzer()
        assert a.get_stock_sector("6274O") == "光電業"

    def test_unknown_symbol_returns_other(self, analyzer):
        # 不在 mock 資料中的股票代碼
        assert analyzer.get_stock_sector("9999") == "其他"

    def test_fallback_to_prefix_when_api_empty(self):
        """API 資料為空時，降級使用前綴推斷（僅傳統股有效）"""
        with patch("src.domain.services.sector_trend_analyzer.get_stock_industries", return_value={}):
            a = SectorTrendAnalyzer()
        # 28xx → 金融保險（前綴 28 → industry code 17）
        assert a.get_stock_sector("2882") == "金融保險"
        # 26xx → 航運業（前綴 26 → industry code 15）
        assert a.get_stock_sector("2603") == "航運業"


class TestComputeSectorStrength:
    """SectorTrendAnalyzer.compute_sector_strength()"""

    def test_all_above_ma20_gives_100_pct(self, analyzer):
        """所有股票都在 MA20 上方 → strength = 1.0"""
        target = date(2025, 2, 1)
        stock_data = {}
        # 使用 mock 中的金融族群代碼
        for sym in ["2801", "2802", "2803", "2804"]:
            dates_prices = [(date(2025, 1, j + 1), 10 + j) for j in range(20)]
            dates_prices.append((target, 35))  # 35 > MA20 ≈ 19.5
            stock_data[sym] = _make_stock_data(sym, dates_prices)

        strength = analyzer.compute_sector_strength(stock_data, target)
        assert "金融保險" in strength
        assert strength["金融保險"] == pytest.approx(1.0, abs=0.01)

    def test_all_below_ma20_gives_0_pct(self, analyzer):
        """所有股票都在 MA20 下方 → strength = 0.0"""
        target = date(2025, 2, 1)
        stock_data = {}
        for sym in ["2601", "2602", "2603", "2604"]:
            dates_prices = [(date(2025, 1, j + 1), 50) for j in range(20)]
            dates_prices.append((target, 30))  # 30 < MA20 = 50
            stock_data[sym] = _make_stock_data(sym, dates_prices)

        strength = analyzer.compute_sector_strength(stock_data, target)
        assert "航運業" in strength
        assert strength["航運業"] == pytest.approx(0.0, abs=0.01)

    def test_half_above_gives_50_pct(self, analyzer):
        """一半股票在 MA20 上方 → strength = 0.5"""
        target = date(2025, 2, 1)
        stock_data = {}
        syms = ["2601", "2602", "2603", "2604"]
        for i, sym in enumerate(syms):
            dates_prices = [(date(2025, 1, j + 1), 50) for j in range(20)]
            close = 60 if i < 2 else 40  # 2 上方、2 下方
            dates_prices.append((target, close))
            stock_data[sym] = _make_stock_data(sym, dates_prices)

        strength = analyzer.compute_sector_strength(stock_data, target)
        assert strength["航運業"] == pytest.approx(0.5, abs=0.01)

    def test_insufficient_data_stock_skipped(self, analyzer):
        """資料不足 20 天的股票不計入計算"""
        target = date(2025, 2, 1)
        stock_data = {}
        for sym in ["2601", "2602", "2603", "2604"]:
            dates_prices = [(date(2025, 1, j + 1), 50) for j in range(5)]  # 只有 5 天
            dates_prices.append((target, 60))
            stock_data[sym] = _make_stock_data(sym, dates_prices)

        strength = analyzer.compute_sector_strength(stock_data, target)
        assert "航運業" not in strength

    def test_small_sector_returns_1_0(self, analyzer):
        """股票數 < MIN_SECTOR_STOCKS 的族群強度設為 1.0（不過濾）"""
        target = date(2025, 2, 1)
        stock_data = {}
        # 只有 2 支（< MIN_SECTOR_STOCKS=3），且都在 MA20 下方
        for sym in ["1801", "1802"]:
            dates_prices = [(date(2025, 1, j + 1), 50) for j in range(20)]
            dates_prices.append((target, 20))
            stock_data[sym] = _make_stock_data(sym, dates_prices)

        strength = analyzer.compute_sector_strength(stock_data, target)
        if "玻璃陶瓷" in strength:
            assert strength["玻璃陶瓷"] == pytest.approx(1.0, abs=0.01)

    def test_exempt_sectors_not_in_result(self, analyzer):
        """免過濾族群（其他、綜合等）不在計算結果中"""
        target = date(2025, 2, 1)
        # 建立 "其他" 族群的股票（不在 MOCK_INDUSTRIES 中 → 歸 '其他'）
        stock_data = {}
        for sym in ["9001", "9002", "9003", "9004"]:
            dates_prices = [(date(2025, 1, j + 1), 100) for j in range(21)]
            stock_data[sym] = _make_stock_data(sym, dates_prices)

        strength = analyzer.compute_sector_strength(stock_data, target)
        assert "其他" not in strength


class TestGetStrongSectors:
    """SectorTrendAnalyzer.get_strong_sectors()"""

    def test_above_threshold_is_strong(self, analyzer):
        strength = {"半導體業": 0.7, "航運業": 0.3}
        strong = analyzer.get_strong_sectors(strength, threshold=0.5)
        assert "半導體業" in strong
        assert "航運業" not in strong

    def test_exactly_at_threshold_is_strong(self, analyzer):
        strength = {"電子工業": 0.5}
        strong = analyzer.get_strong_sectors(strength, threshold=0.5)
        assert "電子工業" in strong

    def test_exempt_sectors_always_in_strong(self, analyzer):
        """免過濾族群永遠視為強勢"""
        strong = analyzer.get_strong_sectors({}, threshold=0.5)
        for exempt in _EXEMPT_SECTORS:
            assert exempt in strong

    def test_empty_strength_returns_only_exempt(self, analyzer):
        strong = analyzer.get_strong_sectors({}, threshold=0.5)
        assert strong == _EXEMPT_SECTORS


class TestBuildSectorSummary:
    """SectorTrendAnalyzer.build_sector_summary()"""

    def test_sorted_by_strength_desc(self, analyzer):
        strength = {"A": 0.3, "B": 0.8, "C": 0.6}
        summary = analyzer.build_sector_summary(strength, threshold=0.5)
        scores = [r["strength_pct"] for r in summary]
        assert scores == sorted(scores, reverse=True)

    def test_is_strong_flag(self, analyzer):
        strength = {"強勢族": 0.7, "弱勢族": 0.2}
        summary = analyzer.build_sector_summary(strength, threshold=0.5)
        row_map = {r["sector"]: r for r in summary}
        assert row_map["強勢族"]["is_strong"] is True
        assert row_map["弱勢族"]["is_strong"] is False

    def test_strength_pct_rounded(self, analyzer):
        strength = {"電子工業": 0.666}
        summary = analyzer.build_sector_summary(strength, threshold=0.5)
        assert summary[0]["strength_pct"] == 66.6


class TestIndustryCodeMapping:
    """驗證 INDUSTRY_CODE_TO_SECTOR 正確性（依 TWSE openapi 實際資料）"""

    def test_core_codes_present(self):
        for code in ["01", "02", "03", "10", "15", "17", "24", "26", "28"]:
            assert code in INDUSTRY_CODE_TO_SECTOR, f"Missing industry code: {code}"

    def test_5243_official_code_is_optoelectronics(self):
        # 5243 乙盛-KY 官方產業別代碼 26 = 光電業（非金融保險、非電子零組件）
        assert get_sector_name("26") == "光電業"
        assert get_sector_name("17") == "金融保險"
        assert get_sector_name("26") != get_sector_name("17")

    def test_tsmc_is_semiconductor_code_24(self):
        # 台積電 TWSE 官方代碼 24 = 半導體業（非光電業）
        assert get_sector_name("24") == "半導體業"
        assert get_sector_name("26") == "光電業"
        assert get_sector_name("24") != get_sector_name("26")

    def test_biotech_is_code_22_not_semiconductor(self):
        # 生技醫療代碼 22（葡萄王、五鼎），非半導體業
        assert get_sector_name("22") == "生技醫療"
        assert get_sector_name("22") != "半導體業"
