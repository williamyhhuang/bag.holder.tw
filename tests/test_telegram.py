"""
Tests for telegram module
"""
import pytest
from datetime import datetime
from unittest.mock import Mock, MagicMock, patch

from src.infrastructure.notification.telegram_notifier import TelegramNotifier
from src.infrastructure.notification.telegram_trade_bot import TradingBot

class TestTelegramNotifier:
    """Test Telegram notifier functionality"""

    def setup_method(self):
        """Setup for each test"""
        self.notifier = TelegramNotifier()

    def test_format_stock_results(self):
        """Test formatting stock results"""
        mock_results = {
            'momentum': [
                {
                    'symbol': '2330_TW',
                    'action': 'long',
                    'price': 580.0,
                    'price_change_pct': 2.5
                }
            ],
            'oversold': [],
            'breakout': [
                {
                    'symbol': '2454_TW',
                    'action': 'long',
                    'price': 95.5,
                    'price_change_pct': 3.2
                }
            ]
        }

        message = self.notifier.format_stock_results(mock_results)

        assert isinstance(message, str)
        assert '動能股' in message
        assert '突破股' in message
        assert '2330' in message
        assert '2454' in message

    def test_format_empty_results(self):
        """Test formatting empty results"""
        empty_results = {
            'momentum': [],
            'oversold': [],
            'breakout': []
        }

        message = self.notifier.format_stock_results(empty_results)

        assert isinstance(message, str)
        assert '無符合條件的股票' in message

    @patch('requests.get')
    def test_test_connection_success(self, mock_get):
        """Test successful bot connection test"""
        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'result': {'username': 'test_bot'}
        }
        mock_get.return_value = mock_response

        # Override bot token for testing
        original_token = self.notifier.bot_token
        self.notifier.bot_token = 'test_token'

        result = self.notifier.test_connection()

        assert result is True

        # Restore original token
        self.notifier.bot_token = original_token

    def test_test_connection_no_token(self):
        """Test connection test with no token"""
        original_token = self.notifier.bot_token
        self.notifier.bot_token = 'dummy_token'

        result = self.notifier.test_connection()

        assert result is False

        self.notifier.bot_token = original_token

class TestTradingBot:
    """Test trading bot functionality"""

    def setup_method(self):
        """Setup for each test"""
        self.trading_bot = TradingBot()

    def test_parse_trade_message_chinese(self):
        """Test parsing Chinese trade messages"""
        # Test long position
        result = self.trading_bot.parse_trade_message("做多 2330 580")
        assert result is not None
        assert result['action'] == 'long'
        assert result['symbol'] == '2330'
        assert result['cost'] == 580.0

        # Test short position
        result = self.trading_bot.parse_trade_message("做空 2454 95.5")
        assert result is not None
        assert result['action'] == 'short'
        assert result['symbol'] == '2454'
        assert result['cost'] == 95.5

    def test_parse_trade_message_english(self):
        """Test parsing English trade messages"""
        # Test long position
        result = self.trading_bot.parse_trade_message("long TSMC 580")
        assert result is not None
        assert result['action'] == 'long'
        assert result['symbol'] == 'TSMC'
        assert result['cost'] == 580.0

        # Test short position
        result = self.trading_bot.parse_trade_message("short 2454.TW 95.5")
        assert result is not None
        assert result['action'] == 'short'
        assert result['symbol'] == '2454.TW'
        assert result['cost'] == 95.5

    def test_parse_trade_message_invalid(self):
        """Test parsing invalid trade messages"""
        invalid_messages = [
            "invalid message",
            "買入 2330",  # Missing price
            "做多",       # Missing symbol and price
            "abc def ghi" # Completely invalid
        ]

        for msg in invalid_messages:
            result = self.trading_bot.parse_trade_message(msg)
            assert result is None

    def test_get_help_message(self):
        """Test getting help message"""
        help_msg = self.trading_bot._get_help_message()
        assert isinstance(help_msg, str)
        assert '做多' in help_msg
        assert '做空' in help_msg
        assert '/stats' in help_msg

    def test_handle_trade_input_success(self):
        """Test successful trade input handling"""
        # Mock successful recording on the instance
        self.trading_bot.trade_recorder.record_trade = MagicMock(return_value=True)

        response = self.trading_bot.handle_trade_input("做多 2330 580", "test_chat")

        assert isinstance(response, str)
        assert '交易記錄已確認' in response
        assert '2330' in response
        self.trading_bot.trade_recorder.record_trade.assert_called_once()

    def test_handle_trade_input_failure(self):
        """Test failed trade input handling"""
        # Mock failed recording on the instance
        self.trading_bot.trade_recorder.record_trade = MagicMock(return_value=False)

        response = self.trading_bot.handle_trade_input("做多 2330 580", "test_chat")

        assert isinstance(response, str)
        assert '記錄失敗' in response

    def test_handle_trade_input_invalid(self):
        """Test invalid trade input handling"""
        response = self.trading_bot.handle_trade_input("invalid message", "test_chat")

        assert isinstance(response, str)
        assert '指令說明' in response  # Should return help message

    def test_process_telegram_command(self):
        """Test processing various Telegram commands"""
        # Test help command
        response = self.trading_bot.process_telegram_command("/help", "test_chat")
        assert '指令說明' in response

        # Test stats command
        response = self.trading_bot.process_telegram_command("/stats", "test_chat")
        assert isinstance(response, str)  # Should return some stats message

        # Test trades command
        response = self.trading_bot.process_telegram_command("/trades", "test_chat")
        assert isinstance(response, str)  # Should return some trades message