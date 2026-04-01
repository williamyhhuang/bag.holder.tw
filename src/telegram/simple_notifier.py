"""
Simple Telegram notifier for sending messages
"""
import requests
from typing import Optional
import json

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.append(str(project_root))

from src.utils.logger import get_logger
from config.settings import settings

logger = get_logger(__name__)

class TelegramNotifier:
    """Simple Telegram message sender"""

    def __init__(self):
        self.bot_token = settings.telegram.bot_token
        self.chat_id = settings.telegram.chat_id
        self.logger = get_logger(self.__class__.__name__)
        self.api_base_url = f"https://api.telegram.org/bot{self.bot_token}"

    def send_message(
        self,
        message: str,
        chat_id: Optional[str] = None,
        parse_mode: str = "Markdown"
    ) -> bool:
        """
        Send a message to Telegram

        Args:
            message: Message text to send
            chat_id: Target chat ID (uses default if not provided)
            parse_mode: Message parsing mode (Markdown, HTML, or None)

        Returns:
            True if message sent successfully, False otherwise
        """
        try:
            target_chat_id = chat_id or self.chat_id

            if not target_chat_id or target_chat_id == "dummy_chat_id":
                self.logger.warning("Telegram chat ID not configured")
                return False

            if not self.bot_token or self.bot_token == "dummy_token":
                self.logger.warning("Telegram bot token not configured")
                return False

            url = f"{self.api_base_url}/sendMessage"

            payload = {
                'chat_id': target_chat_id,
                'text': message,
                'parse_mode': parse_mode
            }

            response = requests.post(url, json=payload, timeout=30)

            if response.status_code == 200:
                self.logger.info(f"Message sent to Telegram successfully")
                return True
            else:
                self.logger.error(f"Failed to send Telegram message: {response.status_code} - {response.text}")
                return False

        except requests.exceptions.RequestException as e:
            self.logger.error(f"Network error sending Telegram message: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Error sending Telegram message: {e}")
            return False

    def send_stock_analysis_results(self, results: dict) -> bool:
        """
        Send stock analysis results to Telegram

        Args:
            results: Dictionary with analysis results

        Returns:
            True if sent successfully, False otherwise
        """
        try:
            message = self.format_stock_results(results)
            return self.send_message(message)

        except Exception as e:
            self.logger.error(f"Error sending stock analysis results: {e}")
            return False

    def format_stock_results(self, results: dict) -> str:
        """Format stock analysis results for Telegram"""
        try:
            message = "📈 *台股選股分析結果*\\n\\n"

            total_stocks = sum(len(stocks) for stocks in results.values())
            if total_stocks == 0:
                message += "❌ 今日無符合條件的股票\\n"
                message += f"📊 分析時間: {self._get_current_time()}"
                return message

            for strategy, stocks in results.items():
                if not stocks:
                    continue

                strategy_name = {
                    'momentum': '🚀 動能股',
                    'oversold': '💎 超賣股',
                    'breakout': '📈 突破股',
                    'value': '💰 價值股',
                    'high_volume': '🔥 高量股'
                }.get(strategy, f"📊 {strategy}")

                message += f"*{strategy_name}* ({len(stocks)}支)\\n"

                # Show top 5 stocks per strategy
                for i, stock in enumerate(stocks[:5], 1):
                    symbol = stock['symbol'].replace('_', '\\.')
                    action = "📈 做多" if stock['action'] == 'long' else "📉 做空"
                    price = stock.get('price', 0)
                    change_pct = stock.get('price_change_pct', 0)

                    message += f"{i}\\. {symbol} \\- {action}\\n"
                    message += f"   價格: {price:.2f} ({change_pct:+.2f}%)\\n"

                if len(stocks) > 5:
                    message += f"   \\.\\.\\. 還有 {len(stocks) - 5} 支股票\\n"

                message += "\\n"

            message += f"📊 總計: {total_stocks} 支股票\\n"
            message += f"⏰ 分析時間: {self._get_current_time()}"

            return message

        except Exception as e:
            self.logger.error(f"Error formatting stock results: {e}")
            return "❌ 選股分析結果格式化失敗"

    def send_user_trade_confirmation(self, trade_data: dict) -> bool:
        """
        Send trade confirmation message

        Args:
            trade_data: Trade information dict

        Returns:
            True if sent successfully
        """
        try:
            action = "做多" if trade_data.get('action') == 'long' else "做空"
            symbol = trade_data.get('symbol', '').replace('_', '\\.')
            cost = trade_data.get('cost', 0)

            message = f"✅ *交易記錄已確認*\\n\\n"
            message += f"股票: {symbol}\\n"
            message += f"操作: {action}\\n"
            message += f"成本: {cost:.2f}\\n"
            message += f"時間: {self._get_current_time()}"

            return self.send_message(message)

        except Exception as e:
            self.logger.error(f"Error sending trade confirmation: {e}")
            return False

    def send_futures_analysis(self, analysis: dict) -> bool:
        """
        Send futures analysis to Telegram

        Args:
            analysis: Futures analysis results

        Returns:
            True if sent successfully
        """
        try:
            message = "🔮 *微台期貨分析*\\n\\n"

            if 'recommendation' in analysis:
                rec = analysis['recommendation']
                message += f"建議操作: *{rec}*\\n"

            if 'price' in analysis:
                price = analysis['price']
                message += f"目前價位: {price}\\n"

            if 'trend' in analysis:
                trend = analysis['trend']
                message += f"趨勢: {trend}\\n"

            if 'support' in analysis:
                support = analysis['support']
                resistance = analysis.get('resistance', 'N/A')
                message += f"支撐: {support} / 壓力: {resistance}\\n"

            message += f"\\n⏰ 分析時間: {self._get_current_time()}"

            return self.send_message(message)

        except Exception as e:
            self.logger.error(f"Error sending futures analysis: {e}")
            return False

    def _get_current_time(self) -> str:
        """Get current time formatted for display"""
        from datetime import datetime
        return datetime.now().strftime('%Y\\-%-m\\-%-d %H:%M')

    def test_connection(self) -> bool:
        """Test Telegram bot connection"""
        try:
            if not self.bot_token or self.bot_token == "dummy_token":
                self.logger.warning("Bot token not configured")
                return False

            url = f"{self.api_base_url}/getMe"
            response = requests.get(url, timeout=10)

            if response.status_code == 200:
                bot_info = response.json()
                self.logger.info(f"Bot connection successful: {bot_info.get('result', {}).get('username', 'Unknown')}")
                return True
            else:
                self.logger.error(f"Bot connection failed: {response.status_code}")
                return False

        except Exception as e:
            self.logger.error(f"Error testing bot connection: {e}")
            return False