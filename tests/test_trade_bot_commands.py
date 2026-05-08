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
        patch("src.infrastructure.notification.telegram_trade_bot.GoogleSheetsReader"),
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
        b.sheets_reader = MagicMock()
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

    def test_pnl_command_dispatched(self, bot):
        bot.sheets_recorder.is_available.return_value = True
        bot.sheets_reader.get_pnl_summary.return_value = None
        response = bot.process_telegram_command("/pnl", "chat1")
        bot.sheets_reader.get_pnl_summary.assert_called_once()
        assert response  # non-empty response


class TestHandlePnlCommand:
    """Tests for handle_pnl_command()"""

    def _make_summary(self, unrealized=None, realized=None,
                      total_unrealized=0.0, total_realized=0.0):
        from src.infrastructure.persistence.google_sheets_reader import (
            PnlSummary, UnrealizedPosition, RealizedTrade
        )
        return PnlSummary(
            unrealized=unrealized or [],
            realized=realized or [],
            total_unrealized_pnl=total_unrealized,
            total_realized_pnl=total_realized,
            fetch_time="2026-05-08 10:00",
        )

    def test_sheets_not_available_returns_error(self, bot):
        bot.sheets_recorder.is_available.return_value = False
        response = bot.handle_pnl_command()
        assert "❌" in response

    def test_sheets_reader_returns_none(self, bot):
        bot.sheets_recorder.is_available.return_value = True
        bot.sheets_reader.get_pnl_summary.return_value = None
        response = bot.handle_pnl_command()
        assert "❌" in response

    def test_empty_summary(self, bot):
        bot.sheets_recorder.is_available.return_value = True
        bot.sheets_reader.get_pnl_summary.return_value = self._make_summary()
        response = bot.handle_pnl_command()
        assert "損益摘要" in response
        assert "目前無持倉" in response
        assert "尚無已實現" in response

    def test_unrealized_profit_position(self, bot):
        from src.infrastructure.persistence.google_sheets_reader import UnrealizedPosition
        pos = UnrealizedPosition(
            stock_code="2330",
            stock_name="台積電",
            entry_price=150.0,
            entry_date="2026-04-01",
            quantity=1000,
            current_price=180.0,
            unrealized_pnl=30000.0,
            pnl_pct=20.0,
        )
        bot.sheets_recorder.is_available.return_value = True
        bot.sheets_reader.get_pnl_summary.return_value = self._make_summary(
            unrealized=[pos], total_unrealized=30000.0
        )
        response = bot.handle_pnl_command()
        assert "2330" in response
        assert "台積電" in response
        assert "30,000" in response
        assert "📈" in response
        assert "+20.0%" in response

    def test_unrealized_loss_position(self, bot):
        from src.infrastructure.persistence.google_sheets_reader import UnrealizedPosition
        pos = UnrealizedPosition(
            stock_code="2303",
            stock_name="聯電",
            entry_price=52.0,
            entry_date="2026-04-15",
            quantity=1000,
            current_price=48.0,
            unrealized_pnl=-4000.0,
            pnl_pct=-7.69,
        )
        bot.sheets_recorder.is_available.return_value = True
        bot.sheets_reader.get_pnl_summary.return_value = self._make_summary(
            unrealized=[pos], total_unrealized=-4000.0
        )
        response = bot.handle_pnl_command()
        assert "📉" in response
        assert "-4,000" in response

    def test_unrealized_no_current_price(self, bot):
        from src.infrastructure.persistence.google_sheets_reader import UnrealizedPosition
        pos = UnrealizedPosition(
            stock_code="9999",
            stock_name="",
            entry_price=100.0,
            entry_date="2026-04-01",
            quantity=1000,
            current_price=0.0,
            unrealized_pnl=0.0,
            pnl_pct=0.0,
        )
        bot.sheets_recorder.is_available.return_value = True
        bot.sheets_reader.get_pnl_summary.return_value = self._make_summary(unrealized=[pos])
        response = bot.handle_pnl_command()
        assert "⚠️" in response
        assert "無法取得即時股價" in response

    def test_realized_profit_trade(self, bot):
        from src.infrastructure.persistence.google_sheets_reader import RealizedTrade
        trade = RealizedTrade(
            stock_code="2330",
            stock_name="台積電",
            entry_price=140.0,
            exit_price=160.0,
            exit_date="2026-04-30",
            quantity=1000,
            realized_pnl=20000.0,
            pnl_pct=14.29,
        )
        bot.sheets_recorder.is_available.return_value = True
        bot.sheets_reader.get_pnl_summary.return_value = self._make_summary(
            realized=[trade], total_realized=20000.0
        )
        response = bot.handle_pnl_command()
        assert "✅" in response
        assert "20,000" in response
        assert "+14.3%" in response

    def test_realized_loss_trade(self, bot):
        from src.infrastructure.persistence.google_sheets_reader import RealizedTrade
        trade = RealizedTrade(
            stock_code="2454",
            stock_name="聯發科",
            entry_price=200.0,
            exit_price=180.0,
            exit_date="2026-04-20",
            quantity=500,
            realized_pnl=-10000.0,
            pnl_pct=-10.0,
        )
        bot.sheets_recorder.is_available.return_value = True
        bot.sheets_reader.get_pnl_summary.return_value = self._make_summary(
            realized=[trade], total_realized=-10000.0
        )
        response = bot.handle_pnl_command()
        assert "🔴" in response
        assert "-10,000" in response

    def test_total_pnl_shown(self, bot):
        bot.sheets_recorder.is_available.return_value = True
        bot.sheets_reader.get_pnl_summary.return_value = self._make_summary(
            total_unrealized=10000.0, total_realized=5000.0
        )
        response = bot.handle_pnl_command()
        assert "15,000" in response
        assert "💰" in response

    def test_total_pnl_negative(self, bot):
        bot.sheets_recorder.is_available.return_value = True
        bot.sheets_reader.get_pnl_summary.return_value = self._make_summary(
            total_unrealized=-8000.0, total_realized=-3000.0
        )
        response = bot.handle_pnl_command()
        assert "-11,000" in response
        assert "💸" in response

    def test_help_includes_pnl(self, bot):
        response = bot.handle_pnl_command.__doc__ or ""
        # Just verify the help message mentions /pnl
        help_resp = bot._get_help_message()
        assert "/pnl" in help_resp
