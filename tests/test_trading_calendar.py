"""
Unit tests for src/utils/trading_calendar.py
"""
import json
import os
import sys
from datetime import date, datetime, timedelta
from unittest.mock import MagicMock, patch

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.utils import trading_calendar as tc

PAYLOAD = [
    {"Name": "中華民國開國紀念日", "Date": "1150101"},
    {"Name": "國曆新年開始交易日", "Date": "1150102"},
    {"Name": "農曆春節前最後交易日", "Date": "1150211"},
    {"Name": "市場無交易，僅辦理結算交割作業", "Date": "1150212"},
    {"Name": "國慶日", "Date": "1151009"},
    {"Name": "壞資料", "Date": "abc"},
]


class TestParse:
    def test_roc_date(self):
        assert tc._roc_to_date("1151009") == date(2026, 10, 9)
        assert tc._roc_to_date("abc") is None
        assert tc._roc_to_date("1151399") is None

    def test_excludes_trading_markers(self):
        holidays = tc.parse_holidays(PAYLOAD)
        assert holidays == {date(2026, 1, 1), date(2026, 2, 12), date(2026, 10, 9)}


class TestIsTradingDay:
    def test_weekend_and_holiday(self):
        holidays = {date(2026, 10, 9)}
        assert tc.is_trading_day(date(2026, 10, 8), holidays)        # 週四
        assert not tc.is_trading_day(date(2026, 10, 9), holidays)    # 國慶日（週五）
        assert not tc.is_trading_day(date(2026, 10, 10), holidays)   # 週六

    def test_weekend_never_queries(self):
        with patch.object(tc, "get_holidays") as g:
            assert not tc.is_trading_day(date(2026, 10, 11))
            g.assert_not_called()


class TestGetHolidays:
    def test_fetch_and_cache(self, tmp_path):
        resp = MagicMock()
        resp.json.return_value = PAYLOAD
        with patch.object(tc, "CACHE_FILE", tmp_path / "h.json"), \
                patch.object(tc.requests, "get", return_value=resp) as get:
            assert date(2026, 10, 9) in tc.get_holidays()
            assert date(2026, 10, 9) in tc.get_holidays()   # 第二次讀快取
            assert get.call_count == 1

    def test_fetch_failure_uses_stale_cache(self, tmp_path):
        cache = tmp_path / "h.json"
        cache.write_text(json.dumps({
            "cached_at": (datetime.now() - timedelta(days=30)).isoformat(),
            "holidays": ["2026-10-09"],
        }))
        with patch.object(tc, "CACHE_FILE", cache), \
                patch.object(tc.requests, "get", side_effect=ConnectionError("down")):
            assert tc.get_holidays() == {date(2026, 10, 9)}

    def test_fetch_failure_without_cache_returns_empty(self, tmp_path):
        with patch.object(tc, "CACHE_FILE", tmp_path / "none.json"), \
                patch.object(tc.requests, "get", side_effect=ConnectionError("down")):
            assert tc.get_holidays() == set()
