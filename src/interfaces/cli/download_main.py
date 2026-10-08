"""
Main data downloader module
"""
import argparse
import glob
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
import json
from collections import Counter
from typing import Dict, Iterable, List, Optional, Tuple

import pandas as pd

# Add project root to Python path
project_root = Path(__file__).parent.parent.parent
sys.path.append(str(project_root))

from src.infrastructure.market_data.yfinance_client import YFinanceClient
from src.utils.logger import get_logger
from config.settings import settings

logger = get_logger(__name__)


NON_TRADING_CACHE = Path(settings.data.stocks_path).parent / "cache" / "non_trading_days.json"


def _tail_dates(path: str, tail_bytes: int) -> List[date]:
    """只讀檔尾，取出最近幾筆的日期（避免整檔讀入）"""
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - tail_bytes))
            lines = f.read().decode("utf-8", errors="ignore").splitlines()
    except OSError:
        return []
    if size > tail_bytes and lines:
        lines = lines[1:]  # 第一行可能被截斷
    out = []
    for line in lines:
        try:
            out.append(datetime.strptime(line.split(",")[0][:10], "%Y-%m-%d").date())
        except ValueError:
            continue
    return out


def local_date_coverage(stocks_dir: str, tail_bytes: int) -> Tuple[Counter, int]:
    """統計本地各日期出現在幾檔股票中。Returns: (Counter{date: 檔數}, 檔案數)"""
    counter: Counter = Counter()
    files = [
        p for p in glob.glob(os.path.join(stocks_dir, "*.csv"))
        if not os.path.basename(p).upper().startswith("TEST")
    ]
    for path in files:
        counter.update(set(_tail_dates(path, tail_bytes)))
    return counter, len(files)


def find_missing_trading_days(
    coverage: Counter,
    n_files: int,
    calendar: Iterable[date],
    today: date,
    min_ratio: float = 0.5,
) -> List[date]:
    """交易日曆中（今天以前），本地不到 min_ratio 比例股票有資料的日期 = 缺口"""
    if n_files == 0:
        return []
    threshold = n_files * min_ratio
    return sorted(d for d in calendar if d < today and coverage.get(d, 0) < threshold)


def load_non_trading_days(path: Path = None) -> set:
    """已確認的非交易日（交易所查無資料），避免每天重複查詢國定假日"""
    path = path or NON_TRADING_CACHE
    try:
        return {date.fromisoformat(d) for d in json.loads(path.read_text())}
    except (OSError, ValueError, TypeError):
        return set()


def save_non_trading_days(days: set, path: Path = None) -> None:
    path = path or NON_TRADING_CACHE
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(sorted(d.isoformat() for d in days)))
    except OSError as e:
        logger.warning(f"寫入非交易日快取失敗: {e}")


def local_symbols(stocks_dir: str) -> Dict[str, List[str]]:
    """本地已有 CSV 的股票：{"TW": ["2330", ...], "TWO": [...]}（不新增權證等其他商品）"""
    out: Dict[str, List[str]] = {"TW": [], "TWO": []}
    for path in glob.glob(os.path.join(stocks_dir, "*.csv")):
        stem = os.path.splitext(os.path.basename(path))[0]
        if stem.upper().startswith("TEST") or "_" not in stem:
            continue
        code, market = stem.rsplit("_", 1)
        if market in out:
            out[market].append(code)
    return out


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

    def backfill_gap(self, client=None) -> int:
        """補齊近期缺漏的交易日（證交所／櫃買中心每日收盤行情，一天 2 個請求）。

        快照 API 只能抓「今天」；排程停過一段時間會留下缺口（可能在資料中間，
        例如 7/02 之後直接接上 10/08），均線與漲跌幅都會算錯。
        檢查最近 gap_check_days 天的平日，不到半數股票有資料者逐日補抓；
        交易所查無資料的日子記為非交易日（國定假日），之後不再查詢。
        失敗不中斷主流程：今日資料仍會照常下載。

        Returns: 補寫的股票檔數
        """
        import pytz
        from src.infrastructure.market_data.exchange_daily_client import ExchangeDailyClient

        cfg = settings.download
        stocks_dir = settings.data.stocks_path
        today = datetime.now(pytz.timezone("Asia/Taipei")).date()
        weekdays = [d.date() for d in pd.bdate_range(today - timedelta(days=cfg.gap_check_days), today)]
        non_trading = load_non_trading_days()
        coverage, n_files = local_date_coverage(stocks_dir, cfg.gap_check_tail_bytes)
        missing = [d for d in find_missing_trading_days(coverage, n_files, weekdays, today) if d not in non_trading]
        if not missing:
            return 0

        self.logger.warning(f"檢查 {len(missing)} 個疑似缺漏的平日：{missing[0]} ~ {missing[-1]}")
        client = client or ExchangeDailyClient()
        symbols = local_symbols(stocks_dir)
        rows: Dict[str, List[Dict]] = {}
        filled = []
        for day in missing:
            try:
                markets = client.fetch_day(day)
            except Exception as e:
                self.logger.error(f"{day} 每日行情抓取失敗: {e}")
                continue
            if all(df.empty for df in markets.values()):
                non_trading.add(day)
                continue
            filled.append(day)
            for market, df in markets.items():
                df = df[df["code"].isin(symbols.get(market, []))]
                for rec in df.to_dict("records"):
                    sym = f"{rec.pop('code')}.{market}"
                    rows.setdefault(sym, []).append({"date": pd.Timestamp(day), **rec, "symbol": sym})
        save_non_trading_days(non_trading)

        saver = YFinanceClient()
        saved = sum(saver.save_stock_data(sym, pd.DataFrame(recs)) for sym, recs in rows.items())
        self.logger.warning(f"補抓完成：{len(filled)} 個交易日、{saved} 檔股票")
        return saved

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