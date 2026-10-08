"""
Unit tests for src/infrastructure/market_data/exchange_daily_client.py
"""
import os
import sys
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.infrastructure.market_data import exchange_daily_client as edc

TWSE_PAYLOAD = {
    "stat": "OK",
    "tables": [
        {"title": "價格指數", "fields": ["x"], "data": [["y"]]},
        {
            "title": "115年10月07日 每日收盤行情(全部(不含權證、牛熊證、可展延牛熊證))",
            "fields": ["證券代號", "證券名稱", "成交股數", "成交筆數", "成交金額", "開盤價", "最高價",
                       "最低價", "收盤價", "漲跌(+/-)", "漲跌價差"],
            "data": [
                ["2484", "希華", "23,318,668", "1", "1", "80.70", "88.20", "80.00", "87.10", "+", "6.7"],
                ["9999", "無成交", "0", "0", "0", "--", "--", "--", "--", "", "0"],
            ],
        },
    ],
}

TPEX_PAYLOAD = {
    "stat": "ok",
    "tables": [
        {
            "title": "上櫃股票行情",
            "fields": ["代號", "名稱", "收盤", "漲跌", "開盤", "最高", "最低", "均價", "成交股數"],
            "data": [
                ["8042", "金山電", "126.00", "+9", "118.00", "128.50", "118.00", "1", "18,346,618"],
                ["8888", "停牌", "----", "", "----", "----", "----", "", "0"],
            ],
        },
        {"title": "管理股票", "fields": [], "data": []},
    ],
}


class TestParse:
    def test_parse_twse(self):
        df = edc.parse_twse(TWSE_PAYLOAD)
        assert list(df["code"]) == ["2484"]  # 無成交（--）略過
        row = df.iloc[0]
        assert (row["open"], row["high"], row["low"], row["close"]) == (80.7, 88.2, 80.0, 87.1)
        assert row["volume"] == 23318668

    def test_parse_tpex(self):
        df = edc.parse_tpex(TPEX_PAYLOAD)
        assert list(df["code"]) == ["8042"]
        row = df.iloc[0]
        assert (row["open"], row["close"], row["volume"]) == (118.0, 126.0, 18346618)

    def test_non_trading_day_returns_empty(self):
        assert edc.parse_twse({"stat": "很抱歉，沒有符合條件的資料!"}).empty
        assert edc.parse_tpex({"stat": "ok", "tables": [{"title": "上櫃股票行情", "fields": ["代號"], "data": []}]}).empty

    def test_num(self):
        assert edc._num("1,234.5") == 1234.5
        assert edc._num("--") is None and edc._num("") is None


class TestClient:
    def test_fetch_day_builds_requests(self):
        client = edc.ExchangeDailyClient(request_interval=0)
        with patch.object(client, "_get_json", side_effect=[TWSE_PAYLOAD, TPEX_PAYLOAD]) as g:
            out = client.fetch_day(date(2026, 10, 7))
        assert list(out["TW"]["code"]) == ["2484"]
        assert list(out["TWO"]["code"]) == ["8042"]
        (twse_url, twse_params), (tpex_url, tpex_params) = [c.args for c in g.call_args_list]
        assert twse_url == edc.TWSE_URL and twse_params["date"] == "20261007"
        assert tpex_url == edc.TPEX_URL and tpex_params["date"] == "2026/10/07"

    def test_get_json_retries_then_raises(self):
        client = edc.ExchangeDailyClient(request_interval=0, max_retries=2)
        with patch.object(edc.requests, "get", side_effect=ConnectionError("down")) as get, \
                patch.object(edc.time, "sleep"):
            with pytest.raises(RuntimeError):
                client._get_json("http://x", {})
        assert get.call_count == 2

    def test_get_json_success(self):
        client = edc.ExchangeDailyClient(request_interval=0)
        resp = MagicMock()
        resp.json.return_value = {"ok": 1}
        with patch.object(edc.requests, "get", return_value=resp), patch.object(edc.time, "sleep"):
            assert client._get_json("http://x", {}) == {"ok": 1}
