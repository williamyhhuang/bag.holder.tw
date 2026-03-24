"""
Market scanner main entry point
"""
import asyncio
import sys
from pathlib import Path

# Add src to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import settings
from api.fubon_client import FubonClient
from utils.logger import get_logger, setup_logging
from utils.rate_limiter import setup_rate_limiters
from database.connection import db_manager
from .engine import MarketScanner, HistoricalDataUpdater

# Setup logging
logger = setup_logging(
    level=settings.logging.level,
    log_file=settings.logging.file_path.replace('app.log', 'scanner.log'),
    enable_database_logging=True
)

logger = get_logger(__name__)

async def main():
    """Main scanner function"""
    logger.info("🔍 Starting Taiwan Stock Market Scanner...")

    try:
        # Initialize services
        await setup_rate_limiters(redis_url=settings.redis.url)

        # Create Fubon API client
        async with FubonClient(
            api_key=settings.fubon.api_key,
            secret=settings.fubon.secret,
            rate_limit_per_minute=settings.fubon.rate_limit_per_minute
        ) as fubon_client:

            # Create scanner
            scanner = MarketScanner(
                fubon_client=fubon_client,
                batch_size=settings.scanner.batch_size,
                max_concurrent=settings.scanner.max_concurrent,
                scan_interval=settings.scanner.interval_seconds
            )

            # Create historical data updater
            history_updater = HistoricalDataUpdater(fubon_client)

            # Update historical data first (if needed)
            logger.info("Updating historical data...")
            await history_updater.update_all_stocks(days_back=7)

            # Start market scanning
            await scanner.start_scanning(markets=settings.scanner.enabled_markets)

    except KeyboardInterrupt:
        logger.info("Scanner stopped by user")
    except Exception as e:
        logger.error(f"Scanner error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())