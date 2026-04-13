"""
Unit tests for MonthlyRevenueLoader (src/scanner/revenue_filter.py)
"""
import json
import sys
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.scanner.revenue_filter import MonthlyRevenueLoader, _fetch_revenue_from_api


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_tse_rows():
    return [
        {
            "公司代號": "2330",
            "公司名稱": "台積電",
            "營業收入-當月營收": "200000000",  # 200,000,000 千元 → 200,000 百萬元
        },
        {
            "公司代號": "9999",
            "公司名稱": "小公司",
            "營業收入-當月營收": "50000",  # 50,000 千元 → 50 百萬元
        },
        {
            "公司代號": "BAD",
            "公司名稱": "壞資料",
            "營業收入-當月營收": "",  # 空白 → 略過
        },
    ]


def _make_otc_rows():
    return [
        {
            "公司代號": "6657",
            "公司名稱": "OTC股",
            "營業收入-當月營收": "150000",  # 150,000 千元 → 150 百萬元
        },
    ]


# ── _fetch_revenue_from_api ────────────────────────────────────────────────────

class TestFetchRevenueFromApi:
    def _mock_response(self, rows, is_json=True):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        if is_json:
            mock_resp.text = json.dumps(rows)
            mock_resp.json.return_value = rows
        else:
            mock_resp.text = "<html>error</html>"
        return mock_resp

    def test_parses_tse_and_otc(self):
        tse_resp = self._mock_response(_make_tse_rows())
        otc_resp = self._mock_response(_make_otc_rows())

        with patch("src.scanner.revenue_filter.requests") as mock_req:
            mock_req.get.side_effect = [tse_resp, otc_resp]
            result = _fetch_revenue_from_api()

        # 2330: 200,000,000 / 1000 = 200,000 百萬元
        assert result["2330"] == pytest.approx(200_000.0)
        # 9999: 50,000 / 1000 = 50 百萬元
        assert result["9999"] == pytest.approx(50.0)
        # OTC 6657: 150,000 / 1000 = 150 百萬元
        assert result["6657"] == pytest.approx(150.0)
        # BAD row skipped
        assert "BAD" not in result

    def test_html_response_skipped(self):
        tse_resp = self._mock_response([], is_json=False)
        otc_resp = self._mock_response(_make_otc_rows())

        with patch("src.scanner.revenue_filter.requests") as mock_req:
            mock_req.get.side_effect = [tse_resp, otc_resp]
            result = _fetch_revenue_from_api()

        # TSE skipped, OTC ok
        assert "2330" not in result
        assert result["6657"] == pytest.approx(150.0)

    def test_api_exception_returns_partial(self):
        tse_resp = self._mock_response(_make_tse_rows())

        with patch("src.scanner.revenue_filter.requests") as mock_req:
            mock_req.get.side_effect = [tse_resp, Exception("timeout")]
            result = _fetch_revenue_from_api()

        # TSE ok, OTC failed but TSE data still returned
        assert "2330" in result
        assert "6657" not in result


# ── MonthlyRevenueLoader ───────────────────────────────────────────────────────

class TestMonthlyRevenueLoader:
    def test_load_from_api_and_cache(self, tmp_path):
        cache_file = tmp_path / "revenue_cache.json"
        loader = MonthlyRevenueLoader(cache_path=cache_file)

        api_data = {"2330": 200_000.0, "9999": 50.0}

        with patch("src.scanner.revenue_filter._fetch_revenue_from_api", return_value=api_data):
            result = loader.load()

        assert result == api_data
        # Cache file should now exist
        assert cache_file.exists()
        payload = json.loads(cache_file.read_text())
        assert payload["date"] == date.today().isoformat()
        assert payload["data"]["2330"] == 200_000.0

    def test_uses_today_cache(self, tmp_path):
        cache_file = tmp_path / "revenue_cache.json"
        cached_data = {"2330": 99_999.0}
        cache_file.write_text(json.dumps({
            "date": date.today().isoformat(),
            "data": cached_data,
        }))

        loader = MonthlyRevenueLoader(cache_path=cache_file)

        with patch("src.scanner.revenue_filter._fetch_revenue_from_api") as mock_api:
            result = loader.load()
            mock_api.assert_not_called()  # API should NOT be called

        assert result == cached_data

    def test_ignores_stale_cache(self, tmp_path):
        cache_file = tmp_path / "revenue_cache.json"
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        cache_file.write_text(json.dumps({
            "date": yesterday,
            "data": {"2330": 1.0},
        }))

        fresh_data = {"2330": 200_000.0}
        loader = MonthlyRevenueLoader(cache_path=cache_file)

        with patch("src.scanner.revenue_filter._fetch_revenue_from_api", return_value=fresh_data):
            result = loader.load()

        assert result["2330"] == 200_000.0

    def test_returns_empty_dict_when_api_fails_and_no_cache(self, tmp_path):
        cache_file = tmp_path / "revenue_cache.json"
        loader = MonthlyRevenueLoader(cache_path=cache_file)

        with patch("src.scanner.revenue_filter._fetch_revenue_from_api", return_value={}):
            result = loader.load()

        assert result == {}
        # Empty data → no cache written
        assert not cache_file.exists()

    def test_threshold_logic(self, tmp_path):
        """Simulate how signals_scanner uses the revenue map."""
        cache_file = tmp_path / "revenue_cache.json"
        loader = MonthlyRevenueLoader(cache_path=cache_file)
        api_data = {"2330": 200_000.0, "9999": 50.0, "6657": 150.0}

        with patch("src.scanner.revenue_filter._fetch_revenue_from_api", return_value=api_data):
            revenue_map = loader.load()

        min_revenue = 100.0  # 1億元

        passing = {k for k, v in revenue_map.items() if v >= min_revenue}
        failing = {k for k, v in revenue_map.items() if v < min_revenue}

        assert "2330" in passing
        assert "6657" in passing
        assert "9999" in failing


# ── OTC symbol 正規化（signals_scanner 邏輯） ─────────────────────────────────

class TestOtcSymbolLookup:
    """驗證 signals_scanner 的 OTC symbol 正規化：4741O → 4741"""

    def _revenue_ok(self, internal_symbol: str, revenue_map: dict, min_revenue: float) -> bool:
        """複製 signals_scanner 的月營收過濾邏輯"""
        revenue_key = internal_symbol[:-1] if internal_symbol.endswith('O') else internal_symbol
        rev = revenue_map.get(revenue_key)
        return not (rev is None or rev < min_revenue)

    def test_otc_symbol_strips_O(self):
        revenue_map = {"4741": 200.0}  # API key 無 O 後綴
        assert self._revenue_ok("4741O", revenue_map, 100.0) is True

    def test_otc_low_revenue_filtered(self):
        revenue_map = {"4741": 50.0}
        assert self._revenue_ok("4741O", revenue_map, 100.0) is False

    def test_tse_symbol_unaffected(self):
        revenue_map = {"2330": 200_000.0}
        assert self._revenue_ok("2330", revenue_map, 100.0) is True

    def test_missing_from_map_is_filtered(self):
        """revenue_map 查無資料 → revenue_ok = False（不讓來源不明的股票通過）"""
        revenue_map = {}
        assert self._revenue_ok("9999", revenue_map, 100.0) is False

    def test_missing_otc_from_map_is_filtered(self):
        revenue_map = {}
        assert self._revenue_ok("4741O", revenue_map, 100.0) is False
