"""
Alert notification system for Telegram bot
"""
import asyncio
from datetime import datetime, timedelta
from typing import List

from sqlalchemy import and_, desc

from ...database.connection import db_manager
from ...database.models import Alert, Stock
from ...utils.logger import get_logger
from ...utils.error_handler import handle_errors

logger = get_logger(__name__)

class AlertNotifier:
    """System to monitor and send alert notifications"""

    def __init__(self, telegram_bot):
        self.telegram_bot = telegram_bot
        self.logger = get_logger(self.__class__.__name__)
        self.is_running = False
        self.check_interval = 30  # Check every 30 seconds

    async def start_monitoring(self):
        """Start monitoring for new alerts"""
        self.is_running = True
        self.logger.info("Starting alert monitoring...")

        while self.is_running:
            try:
                await self._check_and_send_alerts()
                await asyncio.sleep(self.check_interval)
            except KeyboardInterrupt:
                self.logger.info("Alert monitoring stopped by user")
                break
            except Exception as e:
                self.logger.error(f"Error in alert monitoring: {e}")
                await asyncio.sleep(60)  # Wait longer on error

        self.logger.info("Alert monitoring stopped")

    def stop_monitoring(self):
        """Stop alert monitoring"""
        self.is_running = False

    @handle_errors()
    async def _check_and_send_alerts(self):
        """Check for new unsent alerts and send notifications"""
        try:
            with db_manager.get_session() as session:
                # Get unsent alerts from the last hour
                cutoff_time = datetime.now() - timedelta(hours=1)

                unsent_alerts = session.query(Alert, Stock).join(
                    Stock, Alert.stock_id == Stock.id
                ).filter(
                    and_(
                        Alert.is_sent == False,
                        Alert.triggered_at >= cutoff_time
                    )
                ).order_by(Alert.triggered_at).all()

                if not unsent_alerts:
                    return

                self.logger.info(f"Found {len(unsent_alerts)} unsent alerts")

                # Send each alert
                for alert, stock in unsent_alerts:
                    try:
                        await self.telegram_bot.send_alert_notification(alert, stock)

                        # Mark as sent
                        alert.is_sent = True
                        alert.sent_at = datetime.now()

                    except Exception as e:
                        self.logger.error(f"Failed to send alert {alert.id}: {e}")

                # Commit changes
                session.commit()

        except Exception as e:
            self.logger.error(f"Error checking alerts: {e}")

    async def send_market_summary(self, chat_ids: List[str]):
        """Send daily market summary to specified users"""
        try:
            # Get today's alerts summary
            with db_manager.get_session() as session:
                today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

                alert_summary = session.query(Alert.alert_type).filter(
                    Alert.triggered_at >= today_start
                ).all()

                buy_count = sum(1 for alert in alert_summary if alert.alert_type == 'BUY')
                sell_count = sum(1 for alert in alert_summary if alert.alert_type == 'SELL')
                watch_count = sum(1 for alert in alert_summary if alert.alert_type == 'WATCH')

            summary_text = f"""
📊 *今日市場摘要*

🟢 買入信號：{buy_count} 個
🔴 賣出信號：{sell_count} 個
🟡 觀察信號：{watch_count} 個

📈 總計：{len(alert_summary)} 個信號

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            """

            # Send to each chat
            for chat_id in chat_ids:
                try:
                    await self.telegram_bot.application.bot.send_message(
                        chat_id=chat_id,
                        text=summary_text,
                        parse_mode='Markdown'
                    )
                except Exception as e:
                    self.logger.error(f"Failed to send summary to {chat_id}: {e}")

            self.logger.info(f"Market summary sent to {len(chat_ids)} users")

        except Exception as e:
            self.logger.error(f"Error sending market summary: {e}")

    async def send_system_notification(self, message: str, level: str = "INFO"):
        """Send system notification to admin users"""
        # This would be used for system alerts, maintenance notifications, etc.
        admin_chat_ids = []  # Configure admin chat IDs

        emoji_map = {
            "INFO": "ℹ️",
            "WARNING": "⚠️",
            "ERROR": "❌",
            "SUCCESS": "✅"
        }

        notification = f"{emoji_map.get(level, 'ℹ️')} *系統通知*\n\n{message}"

        for chat_id in admin_chat_ids:
            try:
                await self.telegram_bot.application.bot.send_message(
                    chat_id=chat_id,
                    text=notification,
                    parse_mode='Markdown'
                )
            except Exception as e:
                self.logger.error(f"Failed to send system notification to {chat_id}: {e}")