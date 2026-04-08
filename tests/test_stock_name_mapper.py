"""Unit tests for stock_name_mapper utility"""
import json
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.stock_name_mapper import lookup_name, get_stock_names, _fetch_tse_names, _fetch_otc_names


MOCK_TSE_DATA = [
    {"Code": "2330", "Name": "台積電", "TradeVolume": "1000"},
    {"Code": "0050", "Name": "元大台灣50", "TradeVolume": "500"},
    {"Code": "ABCD", "Name": "非股票", "TradeVolume": "0"},  # non-numeric, should be skipped
]

MOCK_OTC_DATA = [
    {"SecuritiesCompanyCode": "6116", "CompanyName": "彩晶", "Close": "10.0"},
    {"SecuritiesCompanyCode": "XY12", "CompanyName": "非股票", "Close": "0"},  # non-numeric, skipped
]


def test_fetch_tse_names_returns_dot_tw_keys():
    with patch("requests.get") as mock_get:
        mock_get.return_value = MagicMock(status_code=200)
        mock_get.return_value.json.return_value = MOCK_TSE_DATA
        result = _fetch_tse_names()

    assert "2330.TW" in result
    assert result["2330.TW"] == "台積電"
    assert "0050.TW" in result
    assert "ABCD.TW" not in result  # non-numeric code filtered out


def test_fetch_otc_names_returns_dot_two_keys():
    with patch("requests.get") as mock_get:
        mock_get.return_value = MagicMock(status_code=200)
        mock_get.return_value.json.return_value = MOCK_OTC_DATA
        result = _fetch_otc_names()

    assert "6116.TWO" in result
    assert result["6116.TWO"] == "彩晶"
    assert "XY12.TWO" not in result


def test_lookup_name_underscore_format():
    names = {"2330.TW": "台積電", "6116.TWO": "彩晶"}
    assert lookup_name("2330_TW", names) == "台積電"
    assert lookup_name("6116_TWO", names) == "彩晶"


def test_lookup_name_dot_format():
    names = {"2330.TW": "台積電"}
    assert lookup_name("2330.TW", names) == "台積電"


def test_lookup_name_missing_returns_empty():
    names = {"2330.TW": "台積電"}
    assert lookup_name("9999_TW", names) == ""


def test_get_stock_names_uses_cache(tmp_path, monkeypatch):
    cache_data = {"cached_at": "2099-01-01T00:00:00", "names": {"2330.TW": "台積電"}}
    cache_file = tmp_path / "stock_names.json"
    cache_file.write_text(json.dumps(cache_data, ensure_ascii=False))

    import src.utils.stock_name_mapper as mapper
    monkeypatch.setattr(mapper, "CACHE_FILE", cache_file)

    result = get_stock_names(use_cache=True)
    assert result == {"2330.TW": "台積電"}


def test_get_stock_names_refreshes_stale_cache(tmp_path, monkeypatch):
    cache_data = {"cached_at": "2000-01-01T00:00:00", "names": {"2330.TW": "台積電"}}
    cache_file = tmp_path / "stock_names.json"
    cache_file.write_text(json.dumps(cache_data, ensure_ascii=False))

    import src.utils.stock_name_mapper as mapper
    monkeypatch.setattr(mapper, "CACHE_FILE", cache_file)

    with patch("src.utils.stock_name_mapper._fetch_tse_names", return_value={"2330.TW": "台積電新版"}), \
         patch("src.utils.stock_name_mapper._fetch_otc_names", return_value={}):
        result = get_stock_names(use_cache=True)

    assert result["2330.TW"] == "台積電新版"
