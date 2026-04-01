"""
YFinance client for downloading Taiwan stock data
"""
import yfinance as yf
import pandas as pd
import requests
import json
from datetime import datetime, timedelta
from typing import List, Optional, Dict
import os
from pathlib import Path
import time
from tqdm import tqdm

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.append(str(project_root))

from src.utils.logger import get_logger
from config.settings import settings

logger = get_logger(__name__)

class YFinanceClient:
    """Client for downloading Taiwan stock data using yfinance"""

    def __init__(self):
        self.logger = get_logger(self.__class__.__name__)

    def fetch_tse_stock_list(self) -> List[str]:
        """
        Fetch complete TSE (上市) stock list from Taiwan Stock Exchange API

        Returns:
            List of TSE stock symbols with .TW suffix
        """
        try:
            # 使用證交所 API 獲取上市股票清單
            url = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"

            self.logger.info("Fetching TSE stock list from Taiwan Stock Exchange API...")

            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            }

            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()

            data = response.json()

            # 從 API 回應中提取股票代號
            stock_codes = []
            for item in data:
                if 'Code' in item:
                    code = item['Code'].strip()
                    # 只取數字股票代號，排除指數和其他非股票項目
                    if code.isdigit() and len(code) == 4:
                        stock_codes.append(f"{code}.TW")

            self.logger.info(f"Successfully fetched {len(stock_codes)} TSE stocks")
            return stock_codes

        except Exception as e:
            self.logger.error(f"Failed to fetch TSE stock list from API: {e}")
            self.logger.error("Cannot proceed without TSE stock list")
            return []

    def get_tse_listed_stocks(self) -> List[str]:
        """Get list of TSE listed stock symbols (dynamic fetch with fallback)"""
        return self.fetch_tse_stock_list()

    def fetch_otc_stock_list(self) -> List[str]:
        """
        Fetch complete OTC (上櫃) stock list from Taipei Exchange API

        Returns:
            List of OTC stock symbols with .TWO suffix
        """
        try:
            # 使用櫃買中心 API 獲取上櫃股票清單
            url = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes"

            self.logger.info("Fetching OTC stock list from Taipei Exchange API...")

            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            }

            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()

            data = response.json()

            # 從 API 回應中提取股票代號
            stock_codes = []
            for item in data:
                if 'SecuritiesCompanyCode' in item:
                    code = item['SecuritiesCompanyCode'].strip()
                    # 只取數字股票代號，排除指數和其他非股票項目
                    if code.isdigit() and len(code) == 4:
                        stock_codes.append(f"{code}.TWO")

            self.logger.info(f"Successfully fetched {len(stock_codes)} OTC stocks")
            return stock_codes

        except Exception as e:
            self.logger.error(f"Failed to fetch OTC stock list from API: {e}")
            self.logger.error("Cannot proceed without OTC stock list")
            return []

    def get_otc_listed_stocks(self) -> List[str]:
        """Get list of OTC listed stock symbols (dynamic fetch with fallback)"""
        return self.fetch_otc_stock_list()

    def get_stock_data(
        self,
        symbol: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Optional[pd.DataFrame]:
        """
        Download stock data for a specific symbol

        Args:
            symbol: Stock symbol (e.g. "2330.TW")
            start_date: Start date for data download
            end_date: End date for data download

        Returns:
            DataFrame with stock data or None if failed
        """
        try:
            if start_date is None:
                start_date = datetime.now() - timedelta(days=1)
            if end_date is None:
                end_date = datetime.now()

            stock = yf.Ticker(symbol)
            data = stock.history(start=start_date, end=end_date)

            if data.empty:
                return None

            # Add symbol column
            data['Symbol'] = symbol

            # Reset index to make Date a column
            data = data.reset_index()

            # Rename columns to be more consistent
            data.columns = [col.replace(' ', '_').lower() for col in data.columns]

            return data

        except Exception as e:
            self.logger.error(f"Error downloading data for {symbol}: {e}")
            return None

    def save_stock_data(self, symbol: str, data: pd.DataFrame) -> bool:
        """
        Save stock data to CSV file

        Args:
            symbol: Stock symbol
            data: DataFrame with stock data

        Returns:
            True if saved successfully, False otherwise
        """
        try:
            # Create directory if it doesn't exist
            data_dir = Path(settings.data.stocks_path)
            data_dir.mkdir(parents=True, exist_ok=True)

            # Clean symbol for filename (replace dots and slashes)
            clean_symbol = symbol.replace('.', '_').replace('/', '_')
            filename = f"{clean_symbol}.csv"
            filepath = data_dir / filename

            # Save to CSV
            data.to_csv(filepath, index=False)
            return True

        except Exception as e:
            self.logger.error(f"Error saving data for {symbol}: {e}")
            return False

    def download_all_stocks(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        markets: List[str] = None,
        limit: Optional[int] = None
    ) -> int:
        """
        Download data for all listed stocks

        Args:
            start_date: Start date for data download
            end_date: End date for data download
            markets: List of markets to download ("TSE", "OTC")
            limit: Maximum number of stocks to download (for testing)

        Returns:
            Number of stocks successfully downloaded
        """
        if markets is None:
            markets = ["TSE", "OTC"]

        # Get all stock symbols
        all_symbols = []
        if "TSE" in markets:
            all_symbols.extend(self.get_tse_listed_stocks())
        if "OTC" in markets:
            all_symbols.extend(self.get_otc_listed_stocks())

        # Apply limit if specified
        if limit and limit > 0:
            all_symbols = all_symbols[:limit]
            self.logger.info(f"Limited to first {limit} stocks for testing")

        if not all_symbols:
            self.logger.error("No stock symbols to download")
            return 0

        self.logger.info(f"Starting download for {len(all_symbols)} stocks")

        successful_downloads = 0
        failed_downloads = 0

        # 使用 tqdm 進度條
        progress_bar = tqdm(
            all_symbols,
            desc="下載股票資料",
            unit="股票",
            bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]'
        )

        for symbol in progress_bar:
            try:
                # 更新進度條描述
                progress_bar.set_description(f"下載中: {symbol}")

                data = self.get_stock_data(symbol, start_date, end_date)
                if data is not None and not data.empty:
                    if self.save_stock_data(symbol, data):
                        successful_downloads += 1
                        progress_bar.write(f"✅ {symbol} - 下載成功")
                    else:
                        failed_downloads += 1
                        progress_bar.write(f"❌ {symbol} - 儲存失敗")
                else:
                    failed_downloads += 1
                    progress_bar.write(f"⚠️ {symbol} - 無資料 (可能已下市)")

                # Add small delay to avoid hitting rate limits
                time.sleep(0.2)

            except Exception as e:
                failed_downloads += 1
                progress_bar.write(f"⚠️ {symbol} - 錯誤: {e}")
                continue

        progress_bar.close()

        # 完成摘要
        total_processed = len(all_symbols)
        success_rate = (successful_downloads / total_processed * 100) if total_processed > 0 else 0

        self.logger.info(f"下載完成: {successful_downloads}/{total_processed} 支股票成功 ({success_rate:.1f}%)")
        if failed_downloads > 0:
            self.logger.info(f"失敗: {failed_downloads} 支股票")

        return successful_downloads

    def get_last_trading_date(self) -> datetime:
        """Get the last trading date (excluding weekends)"""
        today = datetime.now()

        # If today is Monday, last trading day was Friday
        if today.weekday() == 0:  # Monday
            return today - timedelta(days=3)
        # If today is Sunday, last trading day was Friday
        elif today.weekday() == 6:  # Sunday
            return today - timedelta(days=2)
        # Otherwise, it was yesterday
        else:
            return today - timedelta(days=1)

    def download_recent_data(self, days_back: int = 2) -> int:
        """
        Download recent data (default: yesterday to today)

        Args:
            days_back: Number of days back to download

        Returns:
            Number of stocks successfully downloaded
        """
        end_date = datetime.now()
        start_date = self.get_last_trading_date()

        if days_back > 1:
            start_date = start_date - timedelta(days=days_back - 1)

        self.logger.info(f"Downloading recent data from {start_date.date()} to {end_date.date()}")

        return self.download_all_stocks(start_date, end_date)