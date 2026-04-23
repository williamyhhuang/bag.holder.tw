"""
Unit tests for signals Telegram formatting (signals_main.format_for_telegram)
"""
import sys
import os
from datetime import date

import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.scanner.signals_main import format_for_telegram, _split_into_chunks, TELEGRAM_MAX_LENGTH


def _make_signal(symbol, name, signal, price, rsi):
    return {"symbol": symbol, "name": name, "signal": signal, "price": price, "rsi": rsi}


def _full_text(chunks):
    """Join chunks back to a single string for content assertions."""
    return "\n".join(chunks)


class TestFormatForTelegram:
    def _result(self, buy=None, sell=None, watch=None, target_date=None):
        return {
            "target_date": target_date or date(2026, 4, 9),
            "buy": buy or [],
            "sell": sell or [],
            "watch": watch or [],
            "total_scanned": 100,
        }

    def test_returns_list(self):
        chunks = format_for_telegram(self._result())
        assert isinstance(chunks, list)
        assert len(chunks) >= 1

    def test_no_signals(self):
        chunks = format_for_telegram(self._result())
        assert "今日無買賣訊號" in _full_text(chunks)

    def test_buy_signals_appear(self):
        buy = [_make_signal("2330.TW", "台積電", "BB Squeeze Break", 975.0, 65.3)]
        text = _full_text(format_for_telegram(self._result(buy=buy)))
        assert "建議買入" in text
        assert "2330.TW" in text
        assert "台積電" in text

    def test_sell_signals_appear(self):
        sell = [_make_signal("2454.TW", "聯發科", "MACD Death Cross", 185.5, 42.1)]
        text = _full_text(format_for_telegram(self._result(sell=sell)))
        assert "賣出警示" in text
        assert "2454.TW" in text

    def test_all_buy_signals_included(self):
        """全部買入訊號都應出現，不截斷至 10 支"""
        buy = [_make_signal(f"{2000+i}.TW", f"股票{i}", "BB Squeeze Break", 100.0, 60.0)
               for i in range(15)]
        text = _full_text(format_for_telegram(self._result(buy=buy)))
        for i in range(15):
            assert f"{2000+i}.TW" in text

    def test_all_sell_signals_included(self):
        """全部賣出訊號都應出現，不截斷至 10 支"""
        sell = [_make_signal(f"{3000+i}.TW", f"股票{i}", "MACD Death Cross", 100.0, 40.0)
                for i in range(15)]
        text = _full_text(format_for_telegram(self._result(sell=sell)))
        for i in range(15):
            assert f"{3000+i}.TW" in text

    def test_date_in_message(self):
        text = _full_text(format_for_telegram(self._result(target_date=date(2026, 4, 9))))
        assert "2026-04-09" in text

    def test_rsi_none_handled(self):
        buy = [_make_signal("2330.TW", "台積電", "BB Squeeze Break", 975.0, None)]
        text = _full_text(format_for_telegram(self._result(buy=buy)))
        assert "2330.TW" in text

    def test_each_chunk_within_limit(self):
        """每則訊息不超過 Telegram 4096 字元上限"""
        buy = [_make_signal(f"{2000+i}.TW", f"股票{i}", "BB Squeeze Break", 100.0, 60.0)
               for i in range(200)]
        for chunk in format_for_telegram(self._result(buy=buy)):
            assert len(chunk) <= TELEGRAM_MAX_LENGTH


class TestSplitIntoChunks:
    def test_short_text_returns_single_chunk(self):
        chunks = _split_into_chunks("hello")
        assert chunks == ["hello"]

    def test_long_text_splits_correctly(self):
        line = "a" * 100 + "\n"
        text = line * 50  # 5000 chars total
        chunks = _split_into_chunks(text)
        assert len(chunks) > 1
        for chunk in chunks:
            assert len(chunk) <= TELEGRAM_MAX_LENGTH

    def test_content_preserved_after_split(self):
        lines = [f"line {i}" for i in range(200)]
        text = "\n".join(lines)
        chunks = _split_into_chunks(text, max_length=500)
        rejoined = "\n".join(chunks)
        for line in lines:
            assert line in rejoined
