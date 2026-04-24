"""
Notification service port (abstract interface)
"""
from abc import ABC, abstractmethod
from typing import Optional


class INotificationService(ABC):
    """Abstract interface for notification services"""

    @abstractmethod
    def send_message(
        self,
        message: str,
        chat_id: Optional[str] = None,
        parse_mode: str = "Markdown",
    ) -> bool:
        """
        Send a notification message.

        Args:
            message: Message text
            chat_id: Target recipient identifier (uses default if not provided)
            parse_mode: Message formatting mode

        Returns:
            True if sent successfully
        """
