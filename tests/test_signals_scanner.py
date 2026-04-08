"""
Unit tests for src/scanner/signals_scanner.py
"""
import sys
import os
from datetime import date

import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.scanner.signals_scanner import _display_symbol, _lookup_name, P1_SELL_SIGNALS


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
        # 2330 is TSMC — should be in the name dict
        from src.utils.stock_name_mapper import get_stock_names
        names = get_stock_names()
        result = _lookup_name("2330", names)
        assert isinstance(result, str)
        # TSMC name exists
        assert len(result) > 0

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
