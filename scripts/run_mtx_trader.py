#!/usr/bin/env python
"""
MTX (微台指) Auto Trader — CLI 入口

用法：
  python scripts/run_mtx_trader.py [--session day|night|auto] [--dry-run]
  python scripts/run_mtx_trader.py --session night --dry-run

選項：
  --session  {day,night,auto}  交易時段（預設：auto 自動偵測）
  --dry-run                    模擬模式：計算訊號但不實際下單
"""
import argparse
import asyncio
import sys
from pathlib import Path

# ── 讓 src/ 以及 config/ 可被 import ──────────────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import settings
from src.application.services.mtx_auto_trader import MTXAutoTrader, SessionType
from src.infrastructure.market_data.fubon_client import FubonClient
from src.infrastructure.notification.telegram_notifier import TelegramNotifier
from src.utils.logger import get_logger

logger = get_logger(__name__)


def _build_client() -> FubonClient:
    fubon = settings.fubon
    return FubonClient(
        user_id=fubon.user_id,
        password=fubon.password,
        cert_path=fubon.cert_path,
        cert_password=fubon.cert_password or fubon.user_id,
        api_key=fubon.api_key,
        is_simulation=fubon.is_simulation,
    )


async def main(session_arg: str, dry_run: bool) -> None:
    client = _build_client()
    notifier = TelegramNotifier()

    async with client:
        trader = MTXAutoTrader(
            fubon_client=client,
            notifier=notifier,
            dry_run=dry_run,
        )
        await trader.initialize()

        forced_session: dict = {
            "day": SessionType.DAY,
            "night": SessionType.NIGHT,
            "auto": None,
        }
        await trader.run(session=forced_session.get(session_arg))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="MTX 微台指自動交易程式",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--session",
        choices=["day", "night", "auto"],
        default="auto",
        help="交易時段（預設：auto）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="模擬模式，不實際下單",
    )
    args = parser.parse_args()

    logger.info(
        f"MTX Auto Trader starting  "
        f"session={args.session}  dry_run={args.dry_run}  "
        f"simulation={settings.fubon.is_simulation}"
    )

    try:
        asyncio.run(main(args.session, args.dry_run))
    except KeyboardInterrupt:
        logger.info("Stopped by user")
