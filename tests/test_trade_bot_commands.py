"""
Unit tests for TradingBot command parsing and handling
"""
import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def bot():
    """Return a TradingBot with mocked recorders"""
    with (
        patch("src.infrastructure.notification.telegram_trade_bot.UserTradesRecorder"),
        patch("src.infrastructure.notification.telegram_trade_bot.GoogleSheetsRecorder"),
        patch("src.infrastructure.notification.telegram_trade_bot.TelegramNotifier"),
    ):
        from src.infrastructure.notification.telegram_trade_bot import TradingBot
        b = TradingBot()
        b.trade_recorder = MagicMock()
        b.trade_recorder.record_trade.return_value = True
        b.trade_recorder.get_user_trades.return_value = __import__("pandas").DataFrame()
        b.trade_recorder.get_trade_statistics.return_value = {}
        b.sheets_recorder = MagicMock()
        b.sheets_recorder.is_available.return_value = False
        return b


class TestParseTradeMessage:
    def test_chinese_buy_with_quantity(self, bot):
        result = bot.parse_trade_message("買入 2330 150.5 1000")
        assert result is not None
        assert result["action"] == "買入"
        assert result["symbol"] == "2330"
        assert result["price"] == pytest.approx(150.5)
        assert result["quantity"] == 1000

    def test_chinese_buy_default_quantity(self, bot):
        result = bot.parse_trade_message("買入 2330 150.5")
        assert result is not None
        assert result["quantity"] == 1000

    def test_chinese_sell(self, bot):
        result = bot.parse_trade_message("賣出 2330 165 2000")
        assert result is not None
        assert result["action"] == "賣出"
        assert result["quantity"] == 2000

    def test_legacy_zuoduo(self, bot):
        result = bot.parse_trade_message("做多 2330 100")
        assert result is not None
        assert result["action"] == "買入"
        assert result["symbol"] == "2330"
        assert result["price"] == pytest.approx(100.0)

    def test_legacy_zuokong(self, bot):
        result = bot.parse_trade_message("做空 2454 50.5")
        assert result is not None
        assert result["action"] == "賣出"

    def test_english_long(self, bot):
        result = bot.parse_trade_message("long 2330 150")
        assert result is not None
        assert result["action"] == "買入"

    def test_english_short(self, bot):
        result = bot.parse_trade_message("short TSMC 95.5")
        assert result is not None
        assert result["action"] == "賣出"

    def test_invalid_message_returns_none(self, bot):
        assert bot.parse_trade_message("hello world") is None
        assert bot.parse_trade_message("") is None
        assert bot.parse_trade_message("買入") is None

    def test_symbol_with_dot(self, bot):
        result = bot.parse_trade_message("買入 2330.TW 150 1000")
        assert result is not None
        assert result["symbol"] == "2330.TW"


class TestHandleTradeInput:
    def test_successful_buy_records_to_csv(self, bot):
        response = bot.handle_trade_input("買入 2330 150 1000", "chat123")
        assert "✅" in response
        assert "2330" in response
        assert "買入" in response
        bot.trade_recorder.record_trade.assert_called_once()

    def test_successful_sell(self, bot):
        response = bot.handle_trade_input("賣出 2330 165 1000", "chat123")
        assert "賣出" in response

    def test_sheets_sync_when_available(self, bot):
        bot.sheets_recorder.is_available.return_value = True
        bot.sheets_recorder.record_trade.return_value = True

        response = bot.handle_trade_input("買入 2330 150 1000", "chat123")
        assert "Google Sheets" in response
        bot.sheets_recorder.record_trade.assert_called_once()

    def test_sheets_sync_failure_shows_warning(self, bot):
        bot.sheets_recorder.is_available.return_value = True
        bot.sheets_recorder.record_trade.return_value = False

        response = bot.handle_trade_input("買入 2330 150 1000", "chat123")
        assert "⚠️" in response

    def test_invalid_message_returns_help(self, bot):
        response = bot.handle_trade_input("gibberish", "chat123")
        assert "📖" in response or "說明" in response


class TestProcessTelegramCommand:
    def test_stats_command(self, bot):
        bot.trade_recorder.get_trade_statistics.return_value = {
            "total_trades": 5, "long_trades": 3, "short_trades": 2,
            "open_trades": 1, "closed_trades": 4,
        }
        response = bot.process_telegram_command("/stats", "chat1")
        assert "統計" in response

    def test_trades_command_empty(self, bot):
        response = bot.process_telegram_command("/trades", "chat1")
        assert "暫無" in response

    def test_help_command(self, bot):
        response = bot.process_telegram_command("/help", "chat1")
        assert "買入" in response

    def test_trade_command_dispatched(self, bot):
        response = bot.process_telegram_command("買入 2330 150 1000", "chat1")
        assert "✅" in response
