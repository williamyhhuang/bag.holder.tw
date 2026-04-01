"""
Main data downloader module
"""
import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent.parent
sys.path.append(str(project_root))

from src.data_downloader.yfinance_client import YFinanceClient
from src.utils.logger import get_logger

logger = get_logger(__name__)

class DataDownloaderCLI:
    """Command line interface for data downloader"""

    def __init__(self):
        self.yf_client = YFinanceClient()
        self.logger = get_logger(self.__class__.__name__)

    def parse_date(self, date_str: str) -> datetime:
        """Parse date string to datetime object"""
        try:
            return datetime.strptime(date_str, '%Y-%m-%d')
        except ValueError:
            self.logger.error(f"Invalid date format: {date_str}. Use YYYY-MM-DD")
            sys.exit(1)

    def run_download(self, args):
        """Run the download command"""
        try:
            start_date = None
            end_date = None

            if args.start_date:
                start_date = self.parse_date(args.start_date)
            if args.end_date:
                end_date = self.parse_date(args.end_date)

            # If no dates provided, download recent data
            if start_date is None and end_date is None:
                self.logger.info("No dates provided, downloading recent data")
                count = self.yf_client.download_recent_data()
            else:
                # If only start date provided, use today as end date
                if start_date and not end_date:
                    end_date = datetime.now()

                # If only end date provided, use yesterday as start date
                if end_date and not start_date:
                    start_date = self.yf_client.get_last_trading_date()

                markets = args.markets if args.markets else ["TSE", "OTC"]
                count = self.yf_client.download_all_stocks(start_date, end_date, markets)

            self.logger.info(f"Download completed: {count} stocks processed")
            return count

        except Exception as e:
            self.logger.error(f"Download failed: {e}")
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
    else:
        parser.print_help()
        sys.exit(1)

if __name__ == "__main__":
    main()