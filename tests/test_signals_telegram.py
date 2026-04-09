"""
Unit tests for signals Telegram formatting (signals_main.format_for_telegram)
"""
import sys
import os
from datetime import date

import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.scanner.signals_main import format_for_telegram


def _make_signal(symbol, name, signal, price, rsi):
    return {"symbol": symbol, "name": name, "signal": signal, "price": price, "rsi": rsi}


class TestFormatForTelegram:
    def _result(self, buy=None, sell=None, watch=None, target_date=None):
        return {
            "target_date": target_date or date(2026, 4, 9),
            "buy": buy or [],
            "sell": sell or [],
            "watch": watch or [],
            "total_scanned": 100,
        }

    def test_no_signals(self):
        msg = format_for_telegram(self._result())
        assert "今日無買賣訊號" in msg

    def test_buy_signals_appear(self):
        buy = [_make_signal("2330.TW", "台積電", "BB Squeeze Break", 975.0, 65.3)]
        msg = format_for_telegram(self._result(buy=buy))
        assert "建議買入" in msg
        assert "2330.TW" in msg
        assert "台積電" in msg
        assert "975.00" in msg

    def test_sell_signals_appear(self):
        sell = [_make_signal("2454.TW", "聯發科", "MACD Death Cross", 185.5, 42.1)]
        msg = format_for_telegram(self._result(sell=sell))
        assert "賣出警示" in msg
        assert "2454.TW" in msg

    def test_buy_limited_to_10(self):
        buy = [_make_signal(f"{2000+i}.TW", f"股票{i}", "BB Squeeze Break", 100.0, 60.0)
               for i in range(15)]
        msg = format_for_telegram(self._result(buy=buy))
        # Only first 10 symbols should appear
        assert "2009.TW" in msg    # index 9 — should be present
        assert "2010.TW" not in msg  # index 10 — should be cut off

    def test_sell_limited_to_10(self):
        sell = [_make_signal(f"{3000+i}.TW", f"股票{i}", "MACD Death Cross", 100.0, 40.0)
                for i in range(15)]
        msg = format_for_telegram(self._result(sell=sell))
        assert "3009.TW" in msg
        assert "3010.TW" not in msg

    def test_date_in_message(self):
        msg = format_for_telegram(self._result(target_date=date(2026, 4, 9)))
        assert "2026-04-09" in msg

    def test_rsi_none_handled(self):
        buy = [_make_signal("2330.TW", "台積電", "BB Squeeze Break", 975.0, None)]
        msg = format_for_telegram(self._result(buy=buy))
        assert "2330.TW" in msg  # Should not crash

    def test_returns_string(self):
        msg = format_for_telegram(self._result())
        assert isinstance(msg, str)
        assert len(msg) > 0
