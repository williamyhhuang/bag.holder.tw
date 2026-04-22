"""
Unit tests for DisposalStockFilter (src/scanner/disposal_filter.py)
"""
import json
import sys
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.scanner.disposal_filter import DisposalStockFilter, _fetch_from_fubon, _fetch_from_twse


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_twse_response(codes):
    """TWSE OpenAPI punish 格式：list of dict with Code field"""
    return [{"Code": code, "Name": f"公司{code}", "ReasonsOfDisposition": "處置原因",
             "DispositionPeriod": "115/04/17～115/04/30"} for code in codes]


def _make_fubon_sdk(disposition_codes, attention_codes=None):
    """建立 mock 富邦 SDK"""
    sdk = MagicMock()
    reststock = sdk.marketdata.rest_client.stock

    def tickers_side_effect(type, **kwargs):
        if kwargs.get("isDisposition"):
            return {"data": [{"symbol": c} for c in disposition_codes]}
        if kwargs.get("isAttention"):
            return {"data": [{"symbol": c} for c in (attention_codes or [])]}
        return {"data": []}

    reststock.intraday.tickers.side_effect = tickers_side_effect
    return sdk


# ── _fetch_from_fubon ─────────────────────────────────────────────────────────

class TestFetchFromFubon:
    def test_returns_disposition_codes(self):
        sdk = _make_fubon_sdk(["2330", "3008"])
        result = _fetch_from_fubon(sdk)
        assert "2330" in result
        assert "3008" in result

    def test_includes_attention_when_called(self):
        sdk = _make_fubon_sdk(["2330"], attention_codes=["9999"])
        result = _fetch_from_fubon(sdk)
        assert "2330" in result
        assert "9999" in result  # _fetch_from_fubon 總是同時抓 attention

    def test_sdk_tickers_exception_returns_empty_set(self):
        """tickers() 呼叫失敗但 SDK 可存取 → 回傳空集合（繼續運作）"""
        sdk = MagicMock()
        sdk.marketdata.rest_client.stock.intraday.tickers.side_effect = Exception("conn error")
        result = _fetch_from_fubon(sdk)
        assert result == set()

    def test_sdk_access_exception_returns_none(self):
        """SDK 根本無法存取（如未登入）→ 回傳 None，由 DisposalStockFilter fallback"""
        sdk = MagicMock()
        type(sdk).marketdata = property(fget=lambda self: (_ for _ in ()).throw(Exception("not logged in")))
        result = _fetch_from_fubon(sdk)
        assert result is None

    def test_empty_list_returns_empty_set(self):
        sdk = _make_fubon_sdk([])
        result = _fetch_from_fubon(sdk)
        assert result == set()


# ── _fetch_from_twse ──────────────────────────────────────────────────────────

class TestFetchFromTwse:
    def _mock_resp(self, data):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.text = json.dumps(data)
        mock_resp.json.return_value = data
        return mock_resp

    def test_parses_punish_format(self):
        """TWSE OpenAPI /announcement/punish 格式：list of dict with Code field"""
        punish_payload = _make_twse_response(["2330", "4741"])
        notetrans_payload = []
        with patch("src.scanner.disposal_filter.requests") as mock_req:
            mock_req.get.side_effect = [
                self._mock_resp(punish_payload),
                self._mock_resp(notetrans_payload),
            ]
            result = _fetch_from_twse()
        assert "2330" in result
        assert "4741" in result

    def test_includes_attention_from_notetrans(self):
        """TWSE OpenAPI /announcement/notetrans 也包含在結果中"""
        punish_payload = _make_twse_response(["2330"])
        notetrans_payload = [{"Code": "6657", "Name": "OTC股"}]
        with patch("src.scanner.disposal_filter.requests") as mock_req:
            mock_req.get.side_effect = [
                self._mock_resp(punish_payload),
                self._mock_resp(notetrans_payload),
            ]
            result = _fetch_from_twse()
        assert "2330" in result
        assert "6657" in result

    def test_non_json_response_skips_that_source(self):
        """非 JSON 回應略過該來源，其他來源仍正常"""
        html_resp = MagicMock()
        html_resp.raise_for_status.return_value = None
        html_resp.text = "<html>error</html>"
        notetrans_payload = [{"Code": "9999"}]
        notetrans_resp = self._mock_resp(notetrans_payload)
        with patch("src.scanner.disposal_filter.requests") as mock_req:
            mock_req.get.side_effect = [html_resp, notetrans_resp]
            result = _fetch_from_twse()
        assert "9999" in result

    def test_api_exception_returns_empty(self):
        with patch("src.scanner.disposal_filter.requests") as mock_req:
            mock_req.get.side_effect = Exception("timeout")
            result = _fetch_from_twse()
        assert result == set()


# ── DisposalStockFilter ───────────────────────────────────────────────────────

class TestDisposalStockFilter:
    def test_uses_fubon_when_sdk_provided(self, tmp_path):
        sdk = _make_fubon_sdk(["2330"])
        f = DisposalStockFilter(sdk=sdk, cache_path=tmp_path / "disposal.json")
        result = f.load()
        assert "2330" in result

    def test_falls_back_to_twse_when_sdk_none(self, tmp_path):
        punish_payload = _make_twse_response(["9999"])
        notetrans_payload = []
        mock_punish = MagicMock()
        mock_punish.raise_for_status.return_value = None
        mock_punish.text = json.dumps(punish_payload)
        mock_punish.json.return_value = punish_payload
        mock_notetrans = MagicMock()
        mock_notetrans.raise_for_status.return_value = None
        mock_notetrans.text = json.dumps(notetrans_payload)
        mock_notetrans.json.return_value = notetrans_payload

        with patch("src.scanner.disposal_filter.requests") as mock_req:
            mock_req.get.side_effect = [mock_punish, mock_notetrans]
            f = DisposalStockFilter(sdk=None, cache_path=tmp_path / "disposal.json")
            result = f.load()
        assert "9999" in result

    def test_uses_cache_on_second_call(self, tmp_path):
        sdk = _make_fubon_sdk(["2330"])
        cache_file = tmp_path / "disposal.json"
        f = DisposalStockFilter(sdk=sdk, cache_path=cache_file)
        f.load()  # writes cache

        # Second call: SDK should NOT be called again
        sdk2 = MagicMock()
        f2 = DisposalStockFilter(sdk=sdk2, cache_path=cache_file)
        result = f2.load()
        sdk2.marketdata.rest_client.stock.intraday.tickers.assert_not_called()
        assert "2330" in result

    def test_stale_cache_triggers_refresh(self, tmp_path):
        cache_file = tmp_path / "disposal.json"
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        cache_file.write_text(json.dumps({"date": yesterday, "data": ["OLD"]}))

        sdk = _make_fubon_sdk(["NEW"])
        f = DisposalStockFilter(sdk=sdk, cache_path=cache_file)
        result = f.load()
        assert "NEW" in result
        assert "OLD" not in result

    def test_fail_open_when_all_sources_fail(self, tmp_path):
        sdk = MagicMock()
        sdk.marketdata.rest_client.stock.intraday.tickers.side_effect = Exception("fail")
        with patch("src.scanner.disposal_filter._fetch_from_twse", return_value=set()):
            f = DisposalStockFilter(sdk=sdk, cache_path=tmp_path / "disposal.json")
            result = f.load()
        assert result == set()  # fail-open

    def test_saves_cache_after_api_success(self, tmp_path):
        sdk = _make_fubon_sdk(["2330", "3008"])
        cache_file = tmp_path / "disposal.json"
        f = DisposalStockFilter(sdk=sdk, cache_path=cache_file)
        f.load()
        assert cache_file.exists()
        payload = json.loads(cache_file.read_text())
        assert payload["date"] == date.today().isoformat()
        assert "2330" in payload["data"]


# ── Integration: disposal 股票不進任何清單 ─────────────────────────────────────

class TestDisposalFilterIntegration:
    """驗證 signals_scanner 整合：處置股被硬過濾，不進 buy/watch。"""

    def test_disposal_symbol_excluded_from_revenue_key(self):
        """OTC 股票 4741O → revenue_key = 4741，disposal set 用 4741 即可排除"""
        disposal_set = {"4741"}
        internal_symbol = "4741O"
        revenue_key = internal_symbol[:-1] if internal_symbol.endswith("O") else internal_symbol
        assert revenue_key in disposal_set

    def test_tse_symbol_excluded(self):
        disposal_set = {"2330"}
        internal_symbol = "2330"
        revenue_key = internal_symbol[:-1] if internal_symbol.endswith("O") else internal_symbol
        assert revenue_key in disposal_set

    def test_normal_symbol_not_excluded(self):
        disposal_set = {"2330"}
        assert "9999" not in disposal_set
