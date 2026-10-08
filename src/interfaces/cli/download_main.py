"""
Main data downloader module
"""
import argparse
import glob
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd

# Add project root to Python path
project_root = Path(__file__).parent.parent.parent
sys.path.append(str(project_root))

from src.infrastructure.market_data.yfinance_client import YFinanceClient
from src.utils.logger import get_logger
from config.settings import settings

logger = get_logger(__name__)


def _last_date_in_csv(path: str) -> Optional[date]:
    """只讀檔尾取最後一筆日期（避免整檔讀入）"""
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - 512))
            tail = f.read().decode("utf-8", errors="ignore").strip().splitlines()
        if not tail:
            return None
        return datetime.strptime(tail[-1].split(",")[0][:10], "%Y-%m-%d").date()
    except (OSError, ValueError):
        return None


def latest_local_date(stocks_dir: str) -> Optional[date]:
    """本地日K最常見的最後日期（取眾數，避免少數髒檔或停牌股影響）"""
    dates = [
        d for path in glob.glob(os.path.join(stocks_dir, "*.csv"))
        if not os.path.basename(path).upper().startswith("TEST")
        and (d := _last_date_in_csv(path)) is not None
    ]
    if not dates:
        return None
    return pd.Series(dates).mode().iloc[0]


def find_backfill_start(latest: Optional[date], today: date) -> Optional[date]:
    """本地最後日期與今天之間若有缺漏的平日，回傳需補抓的起始日；無缺口回傳 None。

    快照 API 只能抓「今天」，排程停過一段時間後會留下缺口（均線、漲跌幅都會算錯）。
    國定假日也會被當成缺口，只會多做一次小範圍補抓，不影響正確性。
    """
    if latest is None:
        return None
    missing = pd.bdate_range(latest + timedelta(days=1), today - timedelta(days=1))
    return (latest + timedelta(days=1)) if len(missing) else None


class DataDownloaderCLI:
    """Command line interface for data downloader"""

    def __init__(self):
        self.logger = get_logger(self.__class__.__name__)

    def _make_client(self, source: str):
        """Instantiate the appropriate download client based on source."""
        if source == "fubon":
            from src.infrastructure.market_data.fubon_download_client import (
                FubonDownloadClient,
                FubonDownloadError,
            )
            client = FubonDownloadClient()
            try:
                client.login()
            except FubonDownloadError as e:
                raise RuntimeError(f"Fubon login failed: {e}") from e
            return client
        else:
            return YFinanceClient()

    def parse_date(self, date_str: str) -> datetime:
        """Parse date string to datetime object"""
        try:
            return datetime.strptime(date_str, '%Y-%m-%d')
        except ValueError:
            self.logger.error(f"Invalid date format: {date_str}. Use YYYY-MM-DD")
            sys.exit(1)

    def backfill_gap(self) -> int:
        """補齊本地資料與今天之間的缺口（yfinance 批次下載，2000 檔約數分鐘）。

        失敗不中斷主流程：今日資料仍會照常下載。
        """
        import pytz
        today = datetime.now(pytz.timezone("Asia/Taipei")).date()
        start = find_backfill_start(latest_local_date(settings.data.stocks_path), today)
        if start is None:
            return 0
        self.logger.warning(f"偵測到資料缺口，補抓 {start} ~ {today - timedelta(days=1)}")
        try:
            # yfinance 的 end 不含當日；今日資料交由主要來源（富邦快照）下載
            return YFinanceClient().download_all_stocks(
                datetime.combine(start, datetime.min.time()),
                datetime.combine(today, datetime.min.time()),
            )
        except Exception as e:
            self.logger.error(f"補抓缺口失敗: {e}")
            return 0

    def run_download(self, args):
        """Run the download command.

        If the configured source (fubon) fails for any reason (e.g. non-trading day,
        WebSocket unavailable), automatically fall back to yfinance so the workflow
        never exits with an error due to a broker API outage.
        """
        source = getattr(args, 'source', None) or settings.download.data_source
        sources_to_try = [source]
        if source == "fubon":
            sources_to_try.append("yfinance")

        start_date = None
        end_date = None
        if args.start_date:
            start_date = self.parse_date(args.start_date)
        if args.end_date:
            end_date = self.parse_date(args.end_date)

        last_error = None
        for attempt_source in sources_to_try:
            try:
                client = self._make_client(attempt_source)
                self.logger.info(f"Data source: {attempt_source}")

                if start_date is None and end_date is None:
                    self.backfill_gap()
                    self.logger.info("No dates provided, downloading recent data")
                    count = client.download_recent_data()
                else:
                    effective_end = end_date or datetime.now()
                    effective_start = start_date or client.get_last_trading_date()
                    markets = args.markets if args.markets else ["TSE", "OTC"]
                    limit = args.limit if hasattr(args, 'limit') and args.limit else None
                    count = client.download_all_stocks(effective_start, effective_end, markets, limit)

                self.logger.info(f"Download completed via {attempt_source}: {count} stocks processed")
                return count

            except Exception as e:
                last_error = e
                self.logger.warning(f"Download via {attempt_source} failed: {e}")
                if attempt_source != sources_to_try[-1]:
                    self.logger.info(f"Falling back to {sources_to_try[sources_to_try.index(attempt_source) + 1]}...")

        self.logger.error(f"All download sources failed. Last error: {last_error}")
        sys.exit(1)

def create_parser():
    """Create argument parser for download command"""
    parser = argparse.ArgumentParser(
        description="Download Taiwan stock market data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m src.data_downloader.main download
  python -m src.data_downloader.main download --start-date 2024-01-01 --end-date 2024-01-31
  python -m src.data_downloader.main download --markets TSE
        """
    )

    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # Download command
    download_parser = subparsers.add_parser('download', help='Download stock data')
    download_parser.add_argument(
        '--start-date',
        type=str,
        help='Start date for download (YYYY-MM-DD format)'
    )
    download_parser.add_argument(
        '--end-date',
        type=str,
        help='End date for download (YYYY-MM-DD format)'
    )
    download_parser.add_argument(
        '--markets',
        nargs='+',
        choices=['TSE', 'OTC'],
        help='Markets to download (default: TSE OTC)'
    )
    download_parser.add_argument(
        '--limit',
        type=int,
        help='Limit number of stocks to download (for testing)'
    )
    download_parser.add_argument(
        '--source',
        choices=['yfinance', 'fubon'],
        default=None,
        help=(
            'Data source: yfinance (default) or fubon. '
            'Can also be set via DOWNLOAD_DATA_SOURCE env var.'
        ),
    )

    return parser

def main():
    """Main entry point"""
    parser = create_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    cli = DataDownloaderCLI()

    if args.command == 'download':
        cli.run_download(args)
        # Use os._exit(0) to bypass Python's cleanup sequence which can trigger
        # SIGSEGV in native SDK threads (fubon_neo) during garbage collection.
        # All data is already saved and flushed at this point.
        os._exit(0)
    else:
        parser.print_help()
        sys.exit(1)

if __name__ == "__main__":
    main()