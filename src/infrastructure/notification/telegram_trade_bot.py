"""
Telegram bot for handling user trade inputs
"""
import re
from datetime import datetime
from typing import Optional

from ...infrastructure.persistence.user_trades_recorder import UserTradesRecorder
from ...infrastructure.persistence.google_sheets_recorder import GoogleSheetsRecorder
from .telegram_notifier import TelegramNotifier
from ...utils.logger import get_logger

logger = get_logger(__name__)


class TradingBot:
    """Telegram bot for handling trading commands"""

    def __init__(self):
        self.trade_recorder = UserTradesRecorder()
        self.sheets_recorder = GoogleSheetsRecorder()
        self.notifier = TelegramNotifier()
        self.logger = get_logger(self.__class__.__name__)

    def parse_trade_message(self, message: str) -> Optional[dict]:
        """
        Parse trade message from user.

        Supported formats:
          買入 2330 150.5 1000   → buy 1000 shares of 2330 at 150.5
          賣出 2330 165          → sell 1000 shares of 2330 at 165 (default qty)
          做多 2330 100          → legacy long format
          做空 2454 50.5         → legacy short format
          long 2330 100          → English long
          short TSMC 95.5        → English short

        Returns:
            dict with keys: action ('買入'/'賣出'), symbol, price, quantity
            or None if parsing failed
        """
        try:
            clean_msg = message.strip()

            # 中文買入/賣出格式: [買入|賣出] symbol price [quantity]
            tw_pattern = r'(買入|賣出)\s+([A-Za-z0-9._]+)\s+([0-9.]+)(?:\s+([0-9]+))?'
            tw_match = re.match(tw_pattern, clean_msg)
            if tw_match:
                action_tw, symbol, price_str, qty_str = tw_match.groups()
                return {
                    'action': action_tw,
                    'symbol': symbol,
                    'price': float(price_str),
                    'quantity': int(qty_str) if qty_str else 1000,
                    # keep legacy 'cost' alias for UserTradesRecorder
                    'cost': float(price_str),
                }

            # 中文做多/做空格式（向後相容）
            chinese_pattern = r'(做多|做空)\s+([A-Za-z0-9._]+)\s+([0-9.]+)'
            chinese_match = re.match(chinese_pattern, clean_msg)
            if chinese_match:
                action_chinese, symbol, price_str = chinese_match.groups()
                action = '買入' if action_chinese == '做多' else '賣出'
                return {
                    'action': action,
                    'symbol': symbol,
                    'price': float(price_str),
                    'quantity': 1000,
                    'cost': float(price_str),
                }

            # English long/short format: [long|short] symbol price [quantity]
            en_pattern = r'(long|short)\s+([A-Za-z0-9._]+)\s+([0-9.]+)(?:\s+([0-9]+))?'
            en_match = re.match(en_pattern, clean_msg, re.IGNORECASE)
            if en_match:
                action_en, symbol, price_str, qty_str = en_match.groups()
                action = '買入' if action_en.lower() == 'long' else '賣出'
                return {
                    'action': action,
                    'symbol': symbol,
                    'price': float(price_str),
                    'quantity': int(qty_str) if qty_str else 1000,
                    'cost': float(price_str),
                }

            return None

        except Exception as e:
            self.logger.error(f"Error parsing trade message '{message}': {e}")
            return None

    def handle_trade_input(self, message: str, chat_id: str) -> str:
        """
        Handle trade input from user.

        Args:
            message: User message
            chat_id: Telegram chat ID

        Returns:
            Response message
        """
        try:
            trade_info = self.parse_trade_message(message)

            if not trade_info:
                return self._get_help_message()

            symbol = trade_info['symbol']
            action = trade_info['action']
            price = trade_info['price']
            quantity = trade_info['quantity']
            amount = price * quantity

            # --- CSV 記錄 ---
            self.trade_recorder.record_trade(
                symbol=symbol,
                action='long' if action == '買入' else 'short',
                cost=price,
                quantity=quantity,
                notes=f"From Telegram chat: {chat_id}",
            )

            # --- Google Sheets 同步（若已設定則同步，否則略過）---
            sheets_status = ""
            if self.sheets_recorder.is_available():
                ok = self.sheets_recorder.record_trade(
                    stock_code=symbol,
                    action=action,
                    price=price,
                    quantity=quantity,
                    notes=f"Telegram {chat_id}",
                )
                sheets_status = "\n📊 已同步 Google Sheets" if ok else "\n⚠️ Google Sheets 同步失敗"

            action_emoji = "📈" if action == "買入" else "📉"
            response = (
                f"✅ 交易記錄已確認\n\n"
                f"{action_emoji} 股票: {symbol}\n"
                f"操作: {action}\n"
                f"價格: {price:.2f}\n"
                f"股數: {quantity:,}\n"
                f"金額: {amount:,.0f}\n"
                f"時間: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
                f"{sheets_status}"
            )
            return response

        except Exception as e:
            self.logger.error(f"Error handling trade input: {e}")
            return "❌ 處理交易資料時發生錯誤"

    def handle_stats_request(self, days_back: int = 30) -> str:
        """Handle request for trading statistics"""
        try:
            stats = self.trade_recorder.get_trade_statistics(days_back)

            if not stats:
                return "📊 暫無交易記錄"

            response = f"📊 *交易統計* (近{days_back}天)\n\n"
            response += f"總交易數: {stats.get('total_trades', 0)}\n"
            response += f"買入: {stats.get('long_trades', 0)} | 賣出: {stats.get('short_trades', 0)}\n"
            response += f"進行中: {stats.get('open_trades', 0)} | 已結束: {stats.get('closed_trades', 0)}\n"

            if 'total_pnl' in stats:
                pnl = stats['total_pnl']
                pnl_emoji = "💰" if pnl >= 0 else "📉"
                response += f"{pnl_emoji} 總損益: {pnl:.2f}\n"

            if 'win_rate' in stats:
                response += f"🎯 勝率: {stats['win_rate']:.1f}%\n"

            return response

        except Exception as e:
            self.logger.error(f"Error getting trading stats: {e}")
            return "❌ 統計資料讀取失敗"

    def handle_recent_trades(self, count: int = 10) -> str:
        """Handle request for recent trades"""
        try:
            df = self.trade_recorder.get_user_trades()

            if df.empty:
                return "📋 暫無交易記錄"

            recent = df.head(count)
            response = f"📋 *最近交易記錄* (前{len(recent)}筆)\n\n"

            for _, trade in recent.iterrows():
                action = "買入" if trade['action'] == 'long' else "賣出"
                qty = int(trade.get('quantity', 1000))
                response += f"• {trade['symbol']} {action} @ {float(trade['cost']):.2f} x {qty:,}\n"
                response += f"  日期: {trade['date']}\n\n"

            return response

        except Exception as e:
            self.logger.error(f"Error getting recent trades: {e}")
            return "❌ 交易記錄讀取失敗"

    def _get_help_message(self) -> str:
        """Get help message for trade commands"""
        return (
            "📖 *交易記錄指令說明*\n\n"
            "記錄買入:\n"
            "  買入 2330 150.5 1000\n"
            "  買入 2330 150.5        (預設 1000 股)\n\n"
            "記錄賣出:\n"
            "  賣出 2330 165 1000\n\n"
            "查看統計: /stats\n"
            "查看記錄: /trades\n\n"
            "格式說明:\n"
            "[買入|賣出] [股票代號] [價格] [股數(選填)]"
        )

    def process_telegram_command(self, message: str, chat_id: str) -> str:
        """
        Process incoming Telegram command.

        Args:
            message: Full message from user
            chat_id: Telegram chat ID

        Returns:
            Response message
        """
        try:
            message = message.strip()

            if message.startswith('/stats'):
                return self.handle_stats_request()
            elif message.startswith('/trades'):
                return self.handle_recent_trades()
            elif message.startswith('/help'):
                return self._get_help_message()
            else:
                return self.handle_trade_input(message, chat_id)

        except Exception as e:
            self.logger.error(f"Error processing telegram command: {e}")
            return "❌ 指令處理失敗"
