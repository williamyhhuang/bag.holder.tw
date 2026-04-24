"""
Telegram notification adapter - implements INotificationService port
"""
from typing import Optional

from ...domain.ports.notification_port import INotificationService
from ...telegram.simple_notifier import TelegramNotifier


class TelegramAdapter(INotificationService):
    """Telegram implementation of INotificationService"""

    def __init__(self):
        self._notifier = TelegramNotifier()

    def send_message(
        self,
        message: str,
        chat_id: Optional[str] = None,
        parse_mode: str = "Markdown",
    ) -> bool:
        """Send a message via Telegram."""
        return self._notifier.send_message(message, chat_id=chat_id, parse_mode=parse_mode)
