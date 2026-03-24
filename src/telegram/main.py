"""
Telegram bot main entry point
"""
import asyncio
import sys
from pathlib import Path

# Add src to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import settings
from utils.logger import get_logger, setup_logging
from database.connection import db_manager
from .bot import TelegramBot
from .notifier import AlertNotifier

# Setup logging
logger = setup_logging(
    level=settings.logging.level,
    log_file=settings.logging.file_path.replace('app.log', 'telegram.log'),
    enable_database_logging=True
)

logger = get_logger(__name__)

async def main():
    """Main telegram bot function"""
    logger.info("📱 Starting Taiwan Stock Telegram Bot...")

    try:
        # Create bot instance
        bot = TelegramBot(token=settings.telegram.bot_token)

        # Create alert notifier
        alert_notifier = AlertNotifier(bot)

        # Start services
        await asyncio.gather(
            bot.start_bot(),
            alert_notifier.start_monitoring()
        )

    except KeyboardInterrupt:
        logger.info("Telegram bot stopped by user")
    except Exception as e:
        logger.error(f"Telegram bot error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())