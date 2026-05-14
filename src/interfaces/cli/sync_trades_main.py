"""
CLI entry point — 同步 Fubon 今日成交記錄至 Google Sheets
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.parent.parent))

from src.application.services.fubon_trades_syncer import FubonTradesSyncer
from src.utils.logger import get_logger

logger = get_logger(__name__)


def run_sync_trades(args):
    """執行今日成交記錄同步"""
    try:
        syncer = FubonTradesSyncer()
        result = syncer.sync()

        synced  = result['synced']
        skipped = result['skipped']
        errors  = result['errors']

        print(f"\n{'='*50}")
        print(f"  Fubon 成交記錄同步完成")
        print(f"  已寫入：{synced} 筆")
        if skipped:
            print(f"  略過（Google Sheets 未設定）：{skipped} 筆")
        if errors:
            print(f"  寫入失敗：{errors} 筆")
        print(f"{'='*50}\n")

        if errors and synced == 0:
            os._exit(1)

        # fubon_neo SDK 在 Python 正常退出時可能觸發 SIGSEGV，用 os._exit 繞過
        os._exit(0)

    except Exception as e:
        logger.error(f"sync-trades 失敗：{e}")
        print(f"❌ sync-trades 失敗：{e}")
        os._exit(1)


def create_parser():
    parser = argparse.ArgumentParser(description="同步 Fubon 今日成交記錄至 Google Sheets")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("sync-trades", help="同步今日 Fubon 成交記錄至 Google Sheets 交易記錄頁籤")
    return parser


def main():
    parser = create_parser()
    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)
    if args.command == "sync-trades":
        run_sync_trades(args)


if __name__ == "__main__":
    main()
