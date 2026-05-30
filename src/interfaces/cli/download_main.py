"""
Main data downloader module
"""
import argparse
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent.parent
sys.path.append(str(project_root))

from src.infrastructure.market_data.yfinance_client import YFinanceClient
from src.utils.logger import get_logger
from config.settings import settings

logger = get_logger(__name__)

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