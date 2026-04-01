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
            self.logger.warning(f"Failed to fetch TSE stock list from API: {e}")
            # 如果 API 失敗，回退到預設清單
            return self.get_tse_fallback_list()

    def get_tse_fallback_list(self) -> List[str]:
        """Fallback TSE stock list when API fails"""
        self.logger.info("Using fallback TSE stock list")
        return [
            # 主要大型股
            "2330.TW", "2454.TW", "2317.TW", "1303.TW", "1301.TW",
            "2308.TW", "2412.TW", "2881.TW", "2882.TW", "2886.TW",
            "2002.TW", "1216.TW", "3008.TW", "2207.TW", "1101.TW",
            "2105.TW", "2474.TW", "2409.TW", "2891.TW", "2892.TW",
            "2884.TW", "2885.TW", "2887.TW", "2890.TW", "1102.TW",
            "3711.TW", "2395.TW", "2357.TW", "2303.TW", "2327.TW",
            "2379.TW", "2382.TW", "2408.TW", "2615.TW", "2376.TW",
            "2377.TW", "2324.TW", "2337.TW", "2301.TW", "2383.TW"
        ]

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
            self.logger.warning(f"Failed to fetch OTC stock list from API: {e}")
            # 如果 API 失敗，回退到預設清單
            return self.get_otc_fallback_list()

    def get_otc_fallback_list(self) -> List[str]:
        """Fallback OTC stock list when API fails"""
        self.logger.info("Using fallback OTC stock list")
        return [
            # 主要上櫃股票
            "8401.TWO", "3529.TWO", "5274.TWO", "3707.TWO", "5478.TWO",
            "4966.TWO", "6509.TWO", "3260.TWO", "6182.TWO", "6214.TWO",
            "3293.TWO", "6180.TWO", "3455.TWO", "6506.TWO", "6462.TWO"
        ]

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

            self.logger.info(f"Downloading data for {symbol} from {start_date} to {end_date}")

            stock = yf.Ticker(symbol)
            data = stock.history(start=start_date, end=end_date)

            if data.empty:
                self.logger.warning(f"No data found for {symbol}")
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
            self.logger.info(f"Saved {len(data)} rows of data to {filepath}")

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

        self.logger.info(f"Starting download for {len(all_symbols)} stocks")

        successful_downloads = 0

        for i, symbol in enumerate(all_symbols):
            try:
                self.logger.info(f"Processing {symbol} ({i+1}/{len(all_symbols)})")

                data = self.get_stock_data(symbol, start_date, end_date)
                if data is not None and not data.empty:
                    if self.save_stock_data(symbol, data):
                        successful_downloads += 1
                        self.logger.info(f"✅ Successfully downloaded {symbol}")
                    else:
                        self.logger.warning(f"❌ Failed to save data for {symbol}")
                else:
                    self.logger.warning(f"⚠️ No data available for {symbol} (possibly delisted)")

                # Add small delay to avoid hitting rate limits
                import time
                time.sleep(0.2)

            except Exception as e:
                self.logger.warning(f"⚠️ Skipping {symbol}: {e}")
                continue

        self.logger.info(f"Download completed: {successful_downloads}/{len(all_symbols)} stocks")
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