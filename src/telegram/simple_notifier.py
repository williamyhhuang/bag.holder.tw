"""
telegram.simple_notifier - backward compatibility shim
"""
from src.infrastructure.notification.telegram_notifier import TelegramNotifier

__all__ = ["TelegramNotifier"]
