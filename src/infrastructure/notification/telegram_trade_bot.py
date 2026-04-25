"""
Telegram bot for handling user trade inputs
"""
import re
from datetime import datetime
from typing import Optional

from ...infrastructure.persistence.user_trades_recorder import UserTradesRecorder
from .telegram_notifier import TelegramNotifier
from ...utils.logger import get_logger

logger = get_logger(__name__)

class TradingBot:
    """Telegram bot for handling trading commands"""

    def __init__(self):
        self.trade_recorder = UserTradesRecorder()
        self.notifier = TelegramNotifier()
        self.logger = get_logger(self.__class__.__name__)

    def parse_trade_message(self, message: str) -> Optional[dict]:
        """
        Parse trade message from user

        Expected format examples:
        "做多 2330 100"
        "做空 2454 50.5"
        "long 2330.TW 100"
        "short TSMC 95.5"

        Args:
            message: User message

        Returns:
            Dict with trade info or None if parsing failed
        """
        try:
            # Remove extra whitespace and convert to lowercase for processing
            clean_msg = message.strip()

            # Pattern for Chinese format: 做多/做空 symbol price
            chinese_pattern = r'(做多|做空)\s+([A-Za-z0-9._]+)\s+([0-9.]+)'
            chinese_match = re.match(chinese_pattern, clean_msg)

            if chinese_match:
                action_chinese, symbol, cost = chinese_match.groups()
                action = 'long' if action_chinese == '做多' else 'short'
                return {
                    'action': action,
                    'symbol': symbol,
                    'cost': float(cost)
                }

            # Pattern for English format: long/short symbol price
            english_pattern = r'(long|short)\s+([A-Za-z0-9._]+)\s+([0-9.]+)'
            english_match = re.match(english_pattern, clean_msg, re.IGNORECASE)

            if english_match:
                action, symbol, cost = english_match.groups()
                return {
                    'action': action.lower(),
                    'symbol': symbol,
                    'cost': float(cost)
                }

            return None

        except Exception as e:
            self.logger.error(f"Error parsing trade message '{message}': {e}")
            return None

    def handle_trade_input(self, message: str, chat_id: str) -> str:
        """
        Handle trade input from user

        Args:
            message: User message
            chat_id: Telegram chat ID

        Returns:
            Response message
        """
        try:
            # Parse the trade message
            trade_info = self.parse_trade_message(message)

            if not trade_info:
                return self._get_help_message()

            # Record the trade
            success = self.trade_recorder.record_trade(
                symbol=trade_info['symbol'],
                action=trade_info['action'],
                cost=trade_info['cost'],
                notes=f"From Telegram chat: {chat_id}"
            )

            if success:
                # Send confirmation
                action_chinese = "做多" if trade_info['action'] == 'long' else "做空"
                response = f"✅ 交易記錄已確認\\n\\n"
                response += f"股票: {trade_info['symbol']}\\n"
                response += f"操作: {action_chinese}\\n"
                response += f"成本: {trade_info['cost']:.2f}\\n"
                response += f"時間: {datetime.now().strftime('%Y-%m-%d %H:%M')}"

                return response
            else:
                return "❌ 交易記錄失敗，請稍後再試"

        except Exception as e:
            self.logger.error(f"Error handling trade input: {e}")
            return "❌ 處理交易資料時發生錯誤"

    def handle_stats_request(self, days_back: int = 30) -> str:
        """
        Handle request for trading statistics

        Args:
            days_back: Number of days to analyze

        Returns:
            Formatted statistics message
        """
        try:
            stats = self.trade_recorder.get_trade_statistics(days_back)

            if not stats:
                return "📊 暫無交易記錄"

            response = f"📊 *交易統計* (近{days_back}天)\\n\\n"
            response += f"總交易數: {stats.get('total_trades', 0)}\\n"
            response += f"做多: {stats.get('long_trades', 0)} | 做空: {stats.get('short_trades', 0)}\\n"
            response += f"進行中: {stats.get('open_trades', 0)} | 已結束: {stats.get('closed_trades', 0)}\\n"

            if 'total_pnl' in stats:
                pnl = stats['total_pnl']
                pnl_emoji = "💰" if pnl >= 0 else "📉"
                response += f"{pnl_emoji} 總損益: {pnl:.2f}\\n"

            if 'win_rate' in stats:
                win_rate = stats['win_rate']
                response += f"🎯 勝率: {win_rate:.1f}%\\n"

            return response

        except Exception as e:
            self.logger.error(f"Error getting trading stats: {e}")
            return "❌ 統計資料讀取失敗"

    def handle_recent_trades(self, count: int = 10) -> str:
        """
        Handle request for recent trades

        Args:
            count: Number of recent trades to show

        Returns:
            Formatted recent trades message
        """
        try:
            df = self.trade_recorder.get_user_trades()

            if df.empty:
                return "📋 暫無交易記錄"

            recent_trades = df.head(count)
            response = f"📋 *最近交易記錄* (前{len(recent_trades)}筆)\\n\\n"

            for idx, trade in recent_trades.iterrows():
                action = "做多" if trade['action'] == 'long' else "做空"
                symbol = trade['symbol']
                cost = trade['cost']
                date = trade['date']

                response += f"• {symbol} {action} @ {cost:.2f}\\n"
                response += f"  日期: {date}\\n\\n"

            return response

        except Exception as e:
            self.logger.error(f"Error getting recent trades: {e}")
            return "❌ 交易記錄讀取失敗"

    def _get_help_message(self) -> str:
        """Get help message for trade commands"""
        return """
📖 *交易記錄指令說明*

記錄交易:
• 做多 2330 100
• 做空 2454 50.5

查看統計: /stats
查看記錄: /trades

格式說明:
[做多/做空] [股票代號] [成本]
"""

    def process_telegram_command(self, message: str, chat_id: str) -> str:
        """
        Process incoming Telegram command

        Args:
            message: Full message from user
            chat_id: Telegram chat ID

        Returns:
            Response message
        """
        try:
            message = message.strip()

            # Handle commands
            if message.startswith('/stats'):
                return self.handle_stats_request()
            elif message.startswith('/trades'):
                return self.handle_recent_trades()
            elif message.startswith('/help'):
                return self._get_help_message()
            else:
                # Try to parse as trade input
                return self.handle_trade_input(message, chat_id)

        except Exception as e:
            self.logger.error(f"Error processing telegram command: {e}")
            return "❌ 指令處理失敗"
