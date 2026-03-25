"""
台指期貨監控主程式
僅追蹤大台(TXF)、小台(MXF)、微台(MTX)近月合約
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
from .monitor import TaiwanFuturesMonitor

# Setup logging
logger = setup_logging(
    level=settings.logging.level,
    log_file=settings.logging.file_path.replace('app.log', 'futures.log'),
    enable_database_logging=True
)

logger = get_logger(__name__)

async def main():
    """台指期貨監控主函式"""
    logger.info("🚀 Starting Taiwan Index Futures Monitor...")
    logger.info("📊 Tracking contracts: TXF(大台), MXF(小台), MTX(微台)")

    try:
        # Initialize services
        await setup_rate_limiters(redis_url=settings.redis.url)

        # Create Fubon API client
        fubon_kwargs = {}
        if settings.fubon.has_api_key_auth():
            fubon_kwargs.update({
                'api_key': settings.fubon.api_key,
                'api_secret': settings.fubon.api_secret,
            })
        elif settings.fubon.has_cert_auth():
            fubon_kwargs.update({
                'user_id': settings.fubon.user_id,
                'password': settings.fubon.password,
                'cert_path': settings.fubon.cert_path,
                'cert_password': settings.fubon.cert_password,
            })
        else:
            logger.error("❌ No valid Fubon authentication configured")
            sys.exit(1)

        fubon_kwargs['is_simulation'] = settings.fubon.is_simulation

        async with FubonClient(**fubon_kwargs) as fubon_client:
            # Create futures monitor
            futures_monitor = TaiwanFuturesMonitor(fubon_client)

            # Get enabled contracts from settings
            enabled_contracts = settings.futures.enabled_contracts
            monitor_interval = settings.futures.monitor_interval

            logger.info(f"🔧 Configuration:")
            logger.info(f"  • Enabled contracts: {', '.join(enabled_contracts)}")
            logger.info(f"  • Monitor interval: {monitor_interval} seconds")
            logger.info(f"  • Max position size: {settings.futures.max_position_size}")
            logger.info(f"  • Simulation mode: {settings.fubon.is_simulation}")

            # Display contract details
            logger.info(f"📋 Contract Details:")
            for contract_symbol in enabled_contracts:
                contract_info = futures_monitor.get_contract_info(contract_symbol)
                if contract_info:
                    logger.info(
                        f"  • {contract_info.name} ({contract_symbol}): "
                        f"合約大小={contract_info.contract_size}, "
                        f"跳動點={contract_info.tick_size}, "
                        f"到期日={contract_info.expiry_date}"
                    )

            # Start futures monitoring
            logger.info("🎯 Starting futures monitoring...")
            await futures_monitor.start_monitoring(
                contracts=enabled_contracts,
                monitor_interval=monitor_interval
            )

    except KeyboardInterrupt:
        logger.info("👋 Futures monitor stopped by user")
    except Exception as e:
        logger.error(f"❌ Futures monitor error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)
    finally:
        logger.info("🏁 Taiwan Index Futures Monitor shutdown complete")

if __name__ == "__main__":
    asyncio.run(main())