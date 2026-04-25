"""
Tests for simple telegram notifier
"""
import pytest
from datetime import datetime
from unittest.mock import Mock, patch
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

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