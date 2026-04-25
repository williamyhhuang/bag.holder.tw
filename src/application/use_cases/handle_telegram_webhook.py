"""
Use Case: Handle Telegram Webhook Event
Application layer — orchestrates processing of incoming Telegram updates.
"""
from ...infrastructure.notification.telegram_trade_bot import TradingBot
from ...utils.logger import get_logger

logger = get_logger(__name__)


class HandleTelegramWebhookUseCase:
    """
    Processes an incoming Telegram webhook update.

    Receives the raw message text and chat_id, delegates to TradingBot
    for command parsing and trade recording, and returns the reply text.
    """

    def __init__(self, trading_bot: TradingBot | None = None):
        self._bot = trading_bot or TradingBot()

    def execute(self, message_text: str, chat_id: str) -> str:
        """
        Args:
            message_text: Raw text received from Telegram
            chat_id: Telegram chat / channel ID (string)

        Returns:
            Reply text to send back to the user
        """
        logger.info(f"Webhook message from chat {chat_id}: {message_text!r}")
        return self._bot.process_telegram_command(message_text, chat_id)
