"""單元測試：_calculate_price_range()"""
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.application.services.signals_scanner import _calculate_price_range
from src.domain.models import TechnicalIndicators

_TEST_DATE = date(2026, 1, 1)


def _make_indicators(**kwargs) -> TechnicalIndicators:
    """建立測試用 TechnicalIndicators，預設各欄位為 None"""
    defaults = dict(
        date=_TEST_DATE,
        ma5=None, ma10=None, ma20=None, ma60=None,
        rsi14=None,
        bb_upper=None, bb_middle=None, bb_lower=None,
        volume_ma20=None,
    )
    defaults.update(kwargs)
    return TechnicalIndicators(**defaults)


class TestGoldenCross:
    def test_price_above_ma20(self):
        ind = _make_indicators(ma20=Decimal("100"))
        result = _calculate_price_range("Golden Cross", Decimal("110"), ind)
        assert result == {"entry_low": 100.0, "entry_high": 110.0, "stop_loss": round(100 * 0.97, 2)}

    def test_price_below_ma20(self):
        ind = _make_indicators(ma20=Decimal("100"))
        result = _calculate_price_range("Golden Cross", Decimal("95"), ind)
        assert result["entry_low"] == 95.0
        assert result["entry_high"] == 100.0

    def test_missing_ma20_returns_none(self):
        ind = _make_indicators()
        assert _calculate_price_range("Golden Cross", Decimal("100"), ind) is None


class TestMACDGoldenCross:
    def test_basic(self):
        ind = _make_indicators(ma20=Decimal("200"))
        result = _calculate_price_range("MACD Golden Cross", Decimal("210"), ind)
        assert result["entry_low"] == 200.0
        assert result["entry_high"] == 210.0
        assert result["stop_loss"] == round(200 * 0.97, 2)

    def test_missing_ma20_returns_none(self):
        ind = _make_indicators()
        assert _calculate_price_range("MACD Golden Cross", Decimal("100"), ind) is None


class TestRSIOversold:
    def test_with_bb_lower(self):
        ind = _make_indicators(bb_lower=Decimal("85"))
        result = _calculate_price_range("RSI Oversold", Decimal("90"), ind)
        assert result["entry_low"] == 90.0
        assert result["entry_high"] == round(90 * 1.02, 2)
        assert result["stop_loss"] == 85.0

    def test_fallback_without_bb_lower(self):
        ind = _make_indicators()
        result = _calculate_price_range("RSI Oversold", Decimal("100"), ind)
        assert result["entry_low"] == 100.0
        assert result["stop_loss"] == round(100 * 0.95, 2)


class TestBBSqueezeBreak:
    def test_basic(self):
        ind = _make_indicators(bb_middle=Decimal("50"), bb_upper=Decimal("60"))
        result = _calculate_price_range("BB Squeeze Break", Decimal("55"), ind)
        assert result["entry_low"] == 50.0
        assert result["entry_high"] == 60.0
        assert result["stop_loss"] == round(50 * 0.97, 2)

    def test_missing_bb_middle_returns_none(self):
        ind = _make_indicators(bb_upper=Decimal("60"))
        assert _calculate_price_range("BB Squeeze Break", Decimal("55"), ind) is None

    def test_missing_bb_upper_returns_none(self):
        ind = _make_indicators(bb_middle=Decimal("50"))
        assert _calculate_price_range("BB Squeeze Break", Decimal("55"), ind) is None


class TestDonchianBreakout:
    def test_with_ma20(self):
        ind = _make_indicators(ma20=Decimal("80"))
        result = _calculate_price_range("Donchian Breakout", Decimal("100"), ind)
        assert result["entry_low"] == 100.0
        assert result["entry_high"] == round(100 * 1.03, 2)
        assert result["stop_loss"] == round(80 * 0.97, 2)

    def test_fallback_without_ma20(self):
        ind = _make_indicators()
        result = _calculate_price_range("Donchian Breakout", Decimal("100"), ind)
        assert result["stop_loss"] == round(100 * 0.95, 2)


class TestFallback:
    def test_unknown_signal(self):
        ind = _make_indicators()
        result = _calculate_price_range("Unknown Signal", Decimal("100"), ind)
        assert result["entry_low"] == round(100 * 0.99, 2)
        assert result["entry_high"] == round(100 * 1.01, 2)
        assert result["stop_loss"] == round(100 * 0.95, 2)


class TestEntryLowLeEntryHigh:
    """entry_low 永遠 <= entry_high"""

    def test_golden_cross_price_above_ma20(self):
        ind = _make_indicators(ma20=Decimal("100"))
        result = _calculate_price_range("Golden Cross", Decimal("120"), ind)
        assert result["entry_low"] <= result["entry_high"]

    def test_golden_cross_price_below_ma20(self):
        ind = _make_indicators(ma20=Decimal("100"))
        result = _calculate_price_range("Golden Cross", Decimal("80"), ind)
        assert result["entry_low"] <= result["entry_high"]
