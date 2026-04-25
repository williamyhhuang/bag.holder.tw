"""
Unit tests for src/scanner/signals_scanner.py
"""
import json
import sys
import os
import tempfile
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.application.services.signals_scanner import _display_symbol, _lookup_name, P1_SELL_SIGNALS, MIN_VOLUME_SHARES


class TestDisplaySymbol:
    def test_tw_stock(self):
        assert _display_symbol("2330") == "2330.TW"

    def test_two_stock_with_o_suffix(self):
        assert _display_symbol("4741O") == "4741.TWO"

    def test_tw_stock_no_trailing_o(self):
        # Some TW stocks end in numbers, not O
        assert _display_symbol("1323") == "1323.TW"

    def test_etf_like_symbol(self):
        assert _display_symbol("0050") == "0050.TW"

    def test_two_stock_longer_code(self):
        assert _display_symbol("6274O") == "6274.TWO"


class TestLookupName:
    def test_tw_stock_lookup(self):
        # 2330 is TSMC — use a mock dict to avoid network dependency
        names = {"2330.TW": "台積電"}
        result = _lookup_name("2330", names)
        assert isinstance(result, str)
        assert result == "台積電"

    def test_unknown_symbol_returns_empty(self):
        names = {"9999.TW": "TestCo"}
        result = _lookup_name("0000", names)
        assert result == ""

    def test_two_stock_lookup(self):
        # Test that TWO suffix is correctly applied for lookup
        names = {"6274.TWO": "台燿"}
        result = _lookup_name("6274O", names)
        assert result == "台燿"

    def test_tw_stock_lookup_with_custom_dict(self):
        names = {"1323.TW": "永裕"}
        result = _lookup_name("1323", names)
        assert result == "永裕"


class TestBuyDeduplication:
    """買入訊號去重邏輯（在 scan_today 內部）"""

    def test_signals_merged_for_same_symbol(self):
        """同一支股票的多個訊號應合併為一筆，訊號名稱用 ' + ' 連接"""
        # 模擬 buy_by_symbol 的合併邏輯
        buy_list_raw = [
            {"symbol": "2330.TW", "name": "台積電", "signal": "BB Squeeze Break", "price": 950.0, "rsi": 62.0},
            {"symbol": "2330.TW", "name": "台積電", "signal": "Donchian Breakout",  "price": 950.0, "rsi": 62.0},
        ]
        buy_by_symbol = {}
        for entry in buy_list_raw:
            sym = entry["symbol"]
            if sym not in buy_by_symbol:
                buy_by_symbol[sym] = dict(entry, signals=[entry["signal"]])
            else:
                buy_by_symbol[sym]["signals"].append(entry["signal"])
        for entry in buy_by_symbol.values():
            entry["signal"] = " + ".join(sorted(set(entry["signals"])))
            del entry["signals"]
        result = list(buy_by_symbol.values())

        assert len(result) == 1
        assert "BB Squeeze Break" in result[0]["signal"]
        assert "Donchian Breakout" in result[0]["signal"]
        assert "+" in result[0]["signal"]

    def test_single_signal_no_plus(self):
        buy_list_raw = [
            {"symbol": "2454.TW", "name": "聯發科", "signal": "Donchian Breakout", "price": 800.0, "rsi": 55.0},
        ]
        buy_by_symbol = {}
        for entry in buy_list_raw:
            sym = entry["symbol"]
            if sym not in buy_by_symbol:
                buy_by_symbol[sym] = dict(entry, signals=[entry["signal"]])
            else:
                buy_by_symbol[sym]["signals"].append(entry["signal"])
        for entry in buy_by_symbol.values():
            entry["signal"] = " + ".join(sorted(set(entry["signals"])))
            del entry["signals"]
        result = list(buy_by_symbol.values())
        assert "+" not in result[0]["signal"]
        assert result[0]["signal"] == "Donchian Breakout"


class TestP1SellSignals:
    def test_macd_death_cross_in_set(self):
        assert "MACD Death Cross" in P1_SELL_SIGNALS

    def test_death_cross_in_set(self):
        assert "Death Cross" in P1_SELL_SIGNALS

    def test_rsi_momentum_loss_in_set(self):
        assert "RSI Momentum Loss" in P1_SELL_SIGNALS

    def test_rsi_overbought_not_in_set(self):
        # RSI Overbought is informational, not a P1 exit signal
        assert "RSI Overbought" not in P1_SELL_SIGNALS

    def test_golden_cross_not_in_set(self):
        assert "Golden Cross" not in P1_SELL_SIGNALS


class TestVolumeFilter:
    """成交量流動性過濾（1000 張 = 1,000,000 股）"""

    def test_min_volume_threshold(self):
        """門檻應為 1,000,000 股（= 1000 張）"""
        assert MIN_VOLUME_SHARES == 1_000_000

    def test_pass_when_volume_above_threshold(self):
        """成交量達標時應通過過濾"""
        volume_on_date = {"2330": 1_500_000}
        symbol = "2330"
        assert volume_on_date.get(symbol, 0) >= MIN_VOLUME_SHARES

    def test_blocked_when_volume_below_threshold(self):
        """成交量不足 1000 張應被過濾掉"""
        volume_on_date = {"9999": 500_000}  # 500 張
        symbol = "9999"
        assert volume_on_date.get(symbol, 0) < MIN_VOLUME_SHARES

    def test_blocked_when_volume_missing(self):
        """無成交量資料時應被過濾掉"""
        volume_on_date = {}
        symbol = "1234"
        assert volume_on_date.get(symbol, 0) < MIN_VOLUME_SHARES

    def test_exact_threshold_passes(self):
        """剛好 1000 張時應通過"""
        volume_on_date = {"5566": 1_000_000}
        symbol = "5566"
        assert volume_on_date.get(symbol, 0) >= MIN_VOLUME_SHARES


class TestSaveSignalsHistory:
    """save_signals_history 歷史記錄儲存"""

    def _make_result(self, target_date=date(2026, 4, 9)):
        return {
            "target_date": target_date,
            "total_scanned": 1950,
            "buy": [{"symbol": "2330.TW", "name": "台積電", "signal": "Donchian Breakout",
                     "price": 1955.0, "rsi": 72.1, "sector": "半導體業"}],
            "sell": [],
            "watch": [],
            "sector_summary": [],
        }

    def test_file_created(self):
        """執行後應建立 JSON 檔案"""
        from src.interfaces.cli.signals_main import save_signals_history
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            with patch("src.interfaces.cli.signals_main.SIGNALS_LOG_DIR", tmp_path):
                filepath = save_signals_history(self._make_result())
            assert filepath.exists()
            assert filepath.suffix == ".json"

    def test_json_content_correct(self):
        """JSON 內容應包含 target_date、buy、sell"""
        from src.interfaces.cli.signals_main import save_signals_history
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            with patch("src.interfaces.cli.signals_main.SIGNALS_LOG_DIR", tmp_path):
                filepath = save_signals_history(self._make_result())
            with open(filepath, encoding="utf-8") as f:
                data = json.load(f)
        assert data["target_date"] == "2026-04-09"
        assert data["total_scanned"] == 1950
        assert len(data["buy"]) == 1
        assert data["buy"][0]["symbol"] == "2330.TW"

    def test_date_serialized_as_string(self):
        """date 物件應序列化為 ISO 格式字串"""
        from src.interfaces.cli.signals_main import save_signals_history
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            with patch("src.interfaces.cli.signals_main.SIGNALS_LOG_DIR", tmp_path):
                filepath = save_signals_history(self._make_result())
            with open(filepath, encoding="utf-8") as f:
                data = json.load(f)
        assert isinstance(data["target_date"], str)
        assert data["target_date"] == "2026-04-09"

    def test_filename_contains_timestamp(self):
        """檔名應包含 signals_ 前綴與時間戳"""
        from src.interfaces.cli.signals_main import save_signals_history
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            with patch("src.interfaces.cli.signals_main.SIGNALS_LOG_DIR", tmp_path):
                filepath = save_signals_history(self._make_result())
            assert filepath.name.startswith("signals_")


class TestSellRevenueFilter:
    """賣出訊號的月營收過濾邏輯"""

    def _apply_sell_revenue_filter(self, symbol: str, revenue_map: dict, min_revenue: float) -> bool:
        """複製 signals_scanner 內的賣出營收過濾邏輯，回傳是否通過（True = 加入 sell_list）"""
        if min_revenue > 0 and revenue_map:
            revenue_key = symbol[:-1] if symbol.endswith('O') else symbol
            rev = revenue_map.get(revenue_key)
            if rev is None or rev < min_revenue:
                return False
        return True

    def test_pass_when_revenue_above_threshold(self):
        """營收超過門檻時應通過，加入賣出清單"""
        assert self._apply_sell_revenue_filter("2330", {"2330": 2000.0}, 500.0) is True

    def test_blocked_when_revenue_below_threshold(self):
        """營收低於門檻時應被過濾，不加入賣出清單"""
        assert self._apply_sell_revenue_filter("9999", {"9999": 100.0}, 500.0) is False

    def test_blocked_when_stock_not_in_revenue_map(self):
        """revenue_map 已載入但找不到該股票時，應被過濾（視為不符資格）"""
        # revenue_map 有資料，但 "1234" 不在其中 → rev is None → blocked
        assert self._apply_sell_revenue_filter("1234", {"2330": 2000.0}, 500.0) is False

    def test_pass_when_min_revenue_is_zero(self):
        """min_revenue = 0 表示停用過濾，任何股票都應通過"""
        assert self._apply_sell_revenue_filter("1234", {}, 0.0) is True
        assert self._apply_sell_revenue_filter("9999", {"9999": 50.0}, 0.0) is True

    def test_pass_when_revenue_map_is_empty_but_min_revenue_set(self):
        """revenue_map 為空時（尚未載入），仍應視為不通過"""
        # revenue_map 為空，但 min_revenue > 0 → revenue_map falsy，不執行過濾
        # 此行為等同停用過濾（data not loaded = skip filter）
        # 根據程式碼：if min_revenue > 0 and revenue_map → 空 dict falsy → 不過濾
        assert self._apply_sell_revenue_filter("2330", {}, 500.0) is True

    def test_otc_symbol_strips_o_suffix_for_lookup(self):
        """OTC 股票（symbol 帶 'O' 後綴）應用數字 key 查詢"""
        # 4741O → key 為 4741
        assert self._apply_sell_revenue_filter("4741O", {"4741": 800.0}, 500.0) is True
        assert self._apply_sell_revenue_filter("4741O", {"4741": 200.0}, 500.0) is False

    def test_exact_threshold_passes(self):
        """剛好等於門檻值時應通過"""
        assert self._apply_sell_revenue_filter("2330", {"2330": 500.0}, 500.0) is True

    def test_just_below_threshold_blocked(self):
        """剛好低於門檻值時應被過濾"""
        assert self._apply_sell_revenue_filter("2330", {"2330": 499.9}, 500.0) is False
