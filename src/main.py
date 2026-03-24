"""
Main application entry point for Taiwan Stock Monitoring Robot
"""
import asyncio
import sys
from pathlib import Path

# Add src to Python path
sys.path.insert(0, str(Path(__file__).parent))

from config.settings import settings
from utils.logger import setup_logging, get_logger
from utils.rate_limiter import setup_rate_limiters
from database.connection import db_manager

# Setup logging
logger = setup_logging(
    level=settings.logging.level,
    log_file=settings.logging.file_path,
    max_file_size=settings.logging.max_file_size,
    backup_count=settings.logging.backup_count,
    enable_database_logging=True,
    enable_structured_logging=not settings.is_development
)

logger = get_logger(__name__)

async def initialize_services():
    """Initialize all application services"""
    logger.info("Initializing Taiwan Stock Monitoring Robot...")

    # Initialize database
    try:
        logger.info("Checking database connection...")
        if not db_manager.health_check():
            raise Exception("Database connection failed")

        logger.info("Creating database tables if not exist...")
        db_manager.create_tables()
        logger.info("Database initialized successfully")

    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise

    # Initialize rate limiters
    try:
        logger.info("Setting up rate limiters...")
        await setup_rate_limiters(redis_url=settings.redis.url)
        logger.info("Rate limiters initialized successfully")

    except Exception as e:
        logger.error(f"Rate limiter initialization failed: {e}")
        raise

    logger.info("All services initialized successfully")

async def main():
    """Main application function"""
    try:
        # Initialize services
        await initialize_services()

        # Application startup message
        logger.info(f"🚀 Taiwan Stock Monitor v{settings.app.version} starting...")
        logger.info(f"Environment: {settings.app.environment}")
        logger.info(f"Debug mode: {settings.app.debug}")

        if settings.is_development:
            logger.info("Running in DEVELOPMENT mode")
            # Add development-specific initialization here
        else:
            logger.info("Running in PRODUCTION mode")

        # Keep application running
        logger.info("Application started successfully. Ctrl+C to stop.")

        # Main application loop would go here
        # For now, just keep running
        while True:
            await asyncio.sleep(60)  # Check every minute
            # Add periodic tasks here

    except KeyboardInterrupt:
        logger.info("Received shutdown signal...")
    except Exception as e:
        logger.error(f"Application error: {e}")
        raise
    finally:
        logger.info("Shutting down Taiwan Stock Monitor...")
        # Cleanup code here
        await cleanup_services()

async def cleanup_services():
    """Cleanup application services"""
    logger.info("Cleaning up services...")

    # Close database connections
    # Close Redis connections
    # Stop background tasks

    logger.info("Cleanup completed")

if __name__ == "__main__":
    # Set event loop policy for Windows compatibility
    if sys.platform.startswith('win'):
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Application terminated by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)