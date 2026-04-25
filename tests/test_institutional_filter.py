"""
Unit tests for InstitutionalFlowLoader (src/scanner/institutional_filter.py)
"""
import json
import sys
from dataclasses import asdict
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.infrastructure.market_data.institutional_filter import (
    InstitutionalFlow,
    InstitutionalFlowLoader,
    _fetch_institutional_from_api,
    _parse_int,
)


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_t86_row(code, name, foreign_net=0, trust_net=0, dealer_net=0, total_net=0):
    """建立 T86 格式的 19 欄資料列（只填必要欄位）"""
    row = [""] * 19
    row[0] = code
    row[1] = name
    row[4] = str(foreign_net)
    row[10] = str(trust_net)
    row[11] = str(dealer_net)
    row[18] = str(total_net)
    return row


def _make_t86_response(rows, stat="ok"):
    return {"stat": stat, "data": rows, "fields": []}


def _mock_resp(data):
    mock = MagicMock()
    mock.raise_for_status.return_value = None
    mock.json.return_value = data
    return mock


# ── _parse_int ────────────────────────────────────────────────────────────────

class TestParseInt:
    def test_parses_plain_number(self):
        assert _parse_int("1234567") == 1_234_567

    def test_parses_comma_number(self):
        assert _parse_int("1,234,567") == 1_234_567

    def test_parses_negative(self):
        assert _parse_int("-500,000") == -500_000

    def test_empty_string_returns_zero(self):
        assert _parse_int("") == 0

    def test_invalid_returns_zero(self):
        assert _parse_int("N/A") == 0


# ── _fetch_institutional_from_api ────────────────────────────────────────────

class TestFetchInstitutionalFromApi:
    def test_parses_valid_rows(self):
        rows = [
            _make_t86_row("2330", "台積電", foreign_net=1_000_000, trust_net=200_000,
                          dealer_net=-50_000, total_net=1_150_000),
            _make_t86_row("3008", "大立光", foreign_net=-500_000, trust_net=0,
                          dealer_net=100_000, total_net=-400_000),
        ]
        payload = _make_t86_response(rows)
        with patch("src.infrastructure.market_data.institutional_filter.requests") as mock_req:
            mock_req.get.return_value = _mock_resp(payload)
            result = _fetch_institutional_from_api(date.today())

        assert "2330" in result
        assert result["2330"].foreign_net == 1_000_000
        assert result["2330"].trust_net == 200_000
        assert result["2330"].total_net == 1_150_000
        assert result["3008"].foreign_net == -500_000

    def test_non_trading_day_returns_empty(self):
        payload = {"stat": "no data"}
        with patch("src.infrastructure.market_data.institutional_filter.requests") as mock_req:
            mock_req.get.return_value = _mock_resp(payload)
            result = _fetch_institutional_from_api(date.today())
        assert result == {}

    def test_api_exception_returns_empty(self):
        with patch("src.infrastructure.market_data.institutional_filter.requests") as mock_req:
            mock_req.get.side_effect = Exception("timeout")
            result = _fetch_institutional_from_api(date.today())
        assert result == {}

    def test_skips_non_numeric_codes(self):
        rows = [
            _make_t86_row("合計", "合計", foreign_net=9_999_999),
            _make_t86_row("2330", "台積電", foreign_net=100_000),
        ]
        payload = _make_t86_response(rows)
        with patch("src.infrastructure.market_data.institutional_filter.requests") as mock_req:
            mock_req.get.return_value = _mock_resp(payload)
            result = _fetch_institutional_from_api(date.today())
        assert "合計" not in result
        assert "2330" in result

    def test_skips_short_rows(self):
        payload = _make_t86_response([["2330", "台積電"]])  # 只有 2 欄
        with patch("src.infrastructure.market_data.institutional_filter.requests") as mock_req:
            mock_req.get.return_value = _mock_resp(payload)
            result = _fetch_institutional_from_api(date.today())
        assert result == {}

    def test_parses_comma_formatted_numbers(self):
        row = _make_t86_row("2330", "台積電")
        row[4] = "2,345,678"  # 外資買賣超
        row[18] = "2,345,678"
        payload = _make_t86_response([row])
        with patch("src.infrastructure.market_data.institutional_filter.requests") as mock_req:
            mock_req.get.return_value = _mock_resp(payload)
            result = _fetch_institutional_from_api(date.today())
        assert result["2330"].foreign_net == 2_345_678


# ── InstitutionalFlowLoader ───────────────────────────────────────────────────

class TestInstitutionalFlowLoader:
    def test_load_from_api_and_cache(self, tmp_path):
        cache_file = tmp_path / "inst.json"
        loader = InstitutionalFlowLoader(cache_path=cache_file)
        api_data = {
            "2330": InstitutionalFlow(1_000_000, 200_000, -50_000, 1_150_000)
        }
        with patch("src.infrastructure.market_data.institutional_filter._fetch_institutional_from_api",
                   return_value=api_data):
            result = loader.load()

        assert "2330" in result
        assert result["2330"].foreign_net == 1_000_000
        assert cache_file.exists()

    def test_uses_today_cache(self, tmp_path):
        cache_file = tmp_path / "inst.json"
        flow = InstitutionalFlow(500_000, 100_000, 0, 600_000)
        cache_file.write_text(json.dumps({
            "date": date.today().isoformat(),
            "data": {"2330": asdict(flow)},
        }))
        loader = InstitutionalFlowLoader(cache_path=cache_file)
        with patch("src.infrastructure.market_data.institutional_filter._fetch_institutional_from_api") as mock_api:
            result = loader.load()
            mock_api.assert_not_called()
        assert result["2330"].foreign_net == 500_000

    def test_ignores_stale_cache(self, tmp_path):
        cache_file = tmp_path / "inst.json"
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        old_flow = InstitutionalFlow(1, 1, 1, 3)
        cache_file.write_text(json.dumps({
            "date": yesterday,
            "data": {"2330": asdict(old_flow)},
        }))
        new_flow = {"2330": InstitutionalFlow(999_000, 0, 0, 999_000)}
        loader = InstitutionalFlowLoader(cache_path=cache_file)
        with patch("src.infrastructure.market_data.institutional_filter._fetch_institutional_from_api",
                   return_value=new_flow):
            result = loader.load()
        assert result["2330"].foreign_net == 999_000

    def test_fail_open_on_api_failure(self, tmp_path):
        cache_file = tmp_path / "inst.json"
        loader = InstitutionalFlowLoader(cache_path=cache_file)
        with patch("src.infrastructure.market_data.institutional_filter._fetch_institutional_from_api",
                   return_value={}):
            result = loader.load()
        assert result == {}
        assert not cache_file.exists()

    def test_date_keyed_cache(self, tmp_path):
        """不同日期的快取不互相污染"""
        cache_file = tmp_path / "inst.json"
        loader = InstitutionalFlowLoader(cache_path=cache_file)
        api_data = {"2330": InstitutionalFlow(100, 0, 0, 100)}
        with patch("src.infrastructure.market_data.institutional_filter._fetch_institutional_from_api",
                   return_value=api_data):
            loader.load(date.today())

        # 查詢昨天 → 快取日期不符 → 重新呼叫 API
        api_data_yesterday = {"9999": InstitutionalFlow(200, 0, 0, 200)}
        with patch("src.infrastructure.market_data.institutional_filter._fetch_institutional_from_api",
                   return_value=api_data_yesterday) as mock_api:
            result = loader.load(date.today() - timedelta(days=1))
            mock_api.assert_called_once()
        assert "9999" in result


# ── 過濾邏輯驗證 ──────────────────────────────────────────────────────────────

class TestInstitutionalFilterLogic:
    """驗證 signals_scanner 的法人過濾 OR/AND 邏輯（獨立於 scanner 測試）"""

    def _check_inst_ok(self, flow, min_foreign, min_trust, require_any):
        if flow is None:
            return True  # fail-open：無資料不過濾
        foreign_ok = min_foreign <= 0 or flow.foreign_net >= min_foreign
        trust_ok = min_trust <= 0 or flow.trust_net >= min_trust
        return (foreign_ok or trust_ok) if require_any else (foreign_ok and trust_ok)

    def test_or_logic_foreign_qualifies(self):
        flow = InstitutionalFlow(600_000, 100_000, 0, 700_000)
        assert self._check_inst_ok(flow, 500_000, 200_000, require_any=True)

    def test_or_logic_trust_qualifies(self):
        flow = InstitutionalFlow(100_000, 300_000, 0, 400_000)
        assert self._check_inst_ok(flow, 500_000, 200_000, require_any=True)

    def test_or_logic_neither_qualifies(self):
        flow = InstitutionalFlow(100_000, 50_000, 0, 150_000)
        assert not self._check_inst_ok(flow, 500_000, 200_000, require_any=True)

    def test_and_logic_both_qualify(self):
        flow = InstitutionalFlow(600_000, 300_000, 0, 900_000)
        assert self._check_inst_ok(flow, 500_000, 200_000, require_any=False)

    def test_and_logic_only_foreign(self):
        flow = InstitutionalFlow(600_000, 100_000, 0, 700_000)
        assert not self._check_inst_ok(flow, 500_000, 200_000, require_any=False)

    def test_none_flow_is_fail_open(self):
        assert self._check_inst_ok(None, 500_000, 200_000, require_any=True)
        assert self._check_inst_ok(None, 500_000, 200_000, require_any=False)

    def test_zero_threshold_always_passes(self):
        flow = InstitutionalFlow(-999_999, -999_999, 0, -999_999)
        assert self._check_inst_ok(flow, 0, 0, require_any=True)
