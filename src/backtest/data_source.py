"""
Data source module for fetching historical data using yfinance
"""
import yfinance as yf
import pandas as pd
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import List, Dict, Optional, Tuple
import logging
import time
import os
import csv

from .models import StockData
from ..utils.logger import get_logger

logger = get_logger(__name__)


class YFinanceDataSource:
    """YFinance data source for Taiwan stock market"""

    def __init__(self, cache_dir: str = "data/backtest"):
        self.cache_dir = cache_dir
        self.logger = get_logger(self.__class__.__name__)

        # Ensure cache directory exists
        os.makedirs(cache_dir, exist_ok=True)

        # Taiwan stock market suffix
        self.tw_suffix = ".TW"  # For TSE (Taiwan Stock Exchange)
        self.two_suffix = ".TWO"  # For OTC (Over The Counter)

    def get_taiwan_stock_list(self) -> List[Tuple[str, str]]:
        """
        Get list of Taiwan stocks with reasonable volume

        Returns:
            List of (symbol, market) tuples
        """
        # Common Taiwan large cap stocks for testing
        # In production, this should be fetched from a proper data source
        stocks = [
            # TSE stocks
            ("2330", "TSE"),  # TSMC
            ("2317", "TSE"),  # Hon Hai
            ("2454", "TSE"),  # MediaTek
            ("2412", "TSE"),  # Chunghwa Telecom
            ("2881", "TSE"),  # Fubon Financial
            ("2882", "TSE"),  # Cathay Financial
            ("2886", "TSE"),  # Mega Financial
            ("2891", "TSE"),  # CTBC Financial
            ("2892", "TSE"),  # First Financial
            ("2002", "TSE"),  # China Steel
            ("1303", "TSE"),  # Nan Ya Plastics
            ("1301", "TSE"),  # Formosa Plastics
            ("2308", "TSE"),  # Delta Electronics
            ("2382", "TSE"),  # Quanta Computer
            ("3008", "TSE"),  # Largan Precision
            ("2357", "TSE"),  # Asustek Computer
            ("6505", "TSE"),  # Taiwan Semiconductor
            ("2409", "TSE"),  # AU Optronics
            ("2303", "TSE"),  # United Microelectronics
            ("2344", "TSE"),  # Compal Electronics
        ]

        self.logger.info(f"Retrieved {len(stocks)} Taiwan stocks")
        return stocks

    def fetch_stock_data(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
        market: str = "TSE"
    ) -> List[StockData]:
        """
        Fetch historical stock data for a single stock

        Args:
            symbol: Stock symbol (without suffix)
            start_date: Start date
            end_date: End date
            market: Market type (TSE or OTC)

        Returns:
            List of StockData objects
        """
        try:
            # Add appropriate suffix
            if market == "OTC":
                yf_symbol = f"{symbol}{self.two_suffix}"
            else:
                yf_symbol = f"{symbol}{self.tw_suffix}"

            self.logger.debug(f"Fetching data for {yf_symbol}")

            # Fetch data from yfinance
            ticker = yf.Ticker(yf_symbol)
            df = ticker.history(
                start=start_date.strftime('%Y-%m-%d'),
                end=(end_date + timedelta(days=1)).strftime('%Y-%m-%d'),  # Include end date
                interval="1d"
            )

            if df.empty:
                self.logger.warning(f"No data found for {yf_symbol}")
                return []

            # Convert to StockData objects
            stock_data = []
            for trade_date, row in df.iterrows():
                try:
                    stock_data.append(StockData(
                        symbol=symbol,
                        date=trade_date.date(),
                        open_price=Decimal(str(round(float(row['Open']), 2))),
                        high_price=Decimal(str(round(float(row['High']), 2))),
                        low_price=Decimal(str(round(float(row['Low']), 2))),
                        close_price=Decimal(str(round(float(row['Close']), 2))),
                        volume=int(row['Volume']),
                        adj_close=Decimal(str(round(float(row['Close']), 2)))  # YFinance already adjusted
                    ))
                except (ValueError, TypeError) as e:
                    self.logger.warning(f"Error processing data for {symbol} on {trade_date}: {e}")
                    continue

            self.logger.info(f"Fetched {len(stock_data)} records for {symbol}")
            return stock_data

        except Exception as e:
            self.logger.error(f"Error fetching data for {symbol}: {e}")
            return []

    def fetch_multiple_stocks(
        self,
        symbols: List[Tuple[str, str]],
        start_date: date,
        end_date: date,
        delay: float = 1.0
    ) -> Dict[str, List[StockData]]:
        """
        Fetch historical data for multiple stocks

        Args:
            symbols: List of (symbol, market) tuples
            start_date: Start date
            end_date: End date
            delay: Delay between requests to avoid rate limiting

        Returns:
            Dictionary mapping symbols to StockData lists
        """
        results = {}
        total = len(symbols)

        self.logger.info(f"Fetching data for {total} stocks from {start_date} to {end_date}")

        for i, (symbol, market) in enumerate(symbols, 1):
            self.logger.info(f"Processing {symbol} ({i}/{total})")

            data = self.fetch_stock_data(symbol, start_date, end_date, market)
            if data:
                results[symbol] = data

            # Rate limiting
            if delay > 0 and i < total:
                time.sleep(delay)

        self.logger.info(f"Successfully fetched data for {len(results)} stocks")
        return results

    def save_to_csv(self, stock_data: Dict[str, List[StockData]], filename: str = None) -> str:
        """
        Save stock data to CSV file

        Args:
            stock_data: Dictionary of stock data
            filename: Output filename (optional)

        Returns:
            Path to saved file
        """
        if filename is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"historical_data_{timestamp}.csv"

        filepath = os.path.join(self.cache_dir, filename)

        try:
            with open(filepath, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)

                # Write header
                writer.writerow([
                    'Symbol', 'Date', 'Open', 'High', 'Low', 'Close', 'Volume', 'AdjClose'
                ])

                # Write data
                for symbol, data_list in stock_data.items():
                    for data in sorted(data_list, key=lambda x: x.date):
                        writer.writerow([
                            data.symbol,
                            data.date.strftime('%Y-%m-%d'),
                            str(data.open_price),
                            str(data.high_price),
                            str(data.low_price),
                            str(data.close_price),
                            data.volume,
                            str(data.adj_close)
                        ])

            self.logger.info(f"Data saved to {filepath}")
            return filepath

        except Exception as e:
            self.logger.error(f"Error saving data to CSV: {e}")
            raise

    def load_from_csv(self, filepath: str) -> Dict[str, List[StockData]]:
        """
        Load stock data from CSV file

        Args:
            filepath: Path to CSV file

        Returns:
            Dictionary of stock data
        """
        try:
            data = {}

            with open(filepath, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)

                for row in reader:
                    symbol = row['Symbol']

                    if symbol not in data:
                        data[symbol] = []

                    data[symbol].append(StockData(
                        symbol=symbol,
                        date=datetime.strptime(row['Date'], '%Y-%m-%d').date(),
                        open_price=Decimal(row['Open']),
                        high_price=Decimal(row['High']),
                        low_price=Decimal(row['Low']),
                        close_price=Decimal(row['Close']),
                        volume=int(row['Volume']),
                        adj_close=Decimal(row['AdjClose']) if row['AdjClose'] else None
                    ))

            # Sort data by date for each symbol
            for symbol in data:
                data[symbol].sort(key=lambda x: x.date)

            self.logger.info(f"Loaded data for {len(data)} stocks from {filepath}")
            return data

        except Exception as e:
            self.logger.error(f"Error loading data from CSV: {e}")
            raise

    def load_from_stocks_dir(
        self,
        stocks_dir: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> Dict[str, List[StockData]]:
        """
        Load stock data from per-file CSVs in data/stocks/ directory.

        Expects files named like ``XXXX_TW.csv`` with columns:
        date, open, high, low, close, volume, ..., symbol

        Args:
            stocks_dir: Path to the directory containing per-stock CSV files
            start_date: Optional filter – only include records on or after this date
            end_date: Optional filter – only include records on or before this date

        Returns:
            Dictionary mapping symbol (e.g. "2330") to list of StockData
        """
        import glob as _glob

        data: Dict[str, List[StockData]] = {}
        csv_files = _glob.glob(os.path.join(stocks_dir, "*.csv"))

        if not csv_files:
            self.logger.warning(f"No CSV files found in {stocks_dir}")
            return data

        for filepath in csv_files:
            # Skip test/fixture files that are not real market data
            filename = os.path.basename(filepath)
            if filename.upper().startswith('TEST'):
                self.logger.debug(f"Skipping test file: {filename}")
                continue
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        try:
                            raw_symbol = row.get('symbol', '')
                            # Normalise "2330.TW" / "2330.TWO" → "2330"
                            symbol = raw_symbol.replace('.TW', '').replace('.TWO', '').replace('.', '')
                            if not symbol:
                                continue

                            # Skip rows with empty numeric fields
                            if not all(row.get(col, '').strip() for col in ('open', 'high', 'low', 'close', 'volume')):
                                continue

                            # Parse date – handles "2026-03-30 00:00:00+08:00" and "2026-03-30"
                            raw_date = row['date'].split(' ')[0].split('+')[0].strip()
                            record_date = datetime.strptime(raw_date, '%Y-%m-%d').date()

                            if start_date and record_date < start_date:
                                continue
                            if end_date and record_date > end_date:
                                continue

                            if symbol not in data:
                                data[symbol] = []

                            close = Decimal(str(round(float(row['close']), 2)))
                            data[symbol].append(StockData(
                                symbol=symbol,
                                date=record_date,
                                open_price=Decimal(str(round(float(row['open']), 2))),
                                high_price=Decimal(str(round(float(row['high']), 2))),
                                low_price=Decimal(str(round(float(row['low']), 2))),
                                close_price=close,
                                volume=int(float(row['volume'])),
                                adj_close=close
                            ))
                        except (ValueError, KeyError):
                            continue
            except Exception as e:
                self.logger.warning(f"Error loading {filepath}: {e}")
                continue

        # Sort each symbol's data by date
        for symbol in data:
            data[symbol].sort(key=lambda x: x.date)

        self.logger.info(f"Loaded local data for {len(data)} stocks from {stocks_dir}")
        return data

    def get_market_index_data(self, start_date: date, end_date: date) -> List[StockData]:
        """
        Get Taiwan market index data for benchmark comparison

        Args:
            start_date: Start date
            end_date: End date

        Returns:
            List of StockData for TAIEX index
        """
        try:
            # Taiwan Stock Exchange Capitalization Weighted Stock Index
            ticker = yf.Ticker("^TWII")
            df = ticker.history(
                start=start_date.strftime('%Y-%m-%d'),
                end=(end_date + timedelta(days=1)).strftime('%Y-%m-%d'),
                interval="1d"
            )

            if df.empty:
                self.logger.warning("No index data found")
                return []

            index_data = []
            for trade_date, row in df.iterrows():
                try:
                    index_data.append(StockData(
                        symbol="TAIEX",
                        date=trade_date.date(),
                        open_price=Decimal(str(round(float(row['Open']), 2))),
                        high_price=Decimal(str(round(float(row['High']), 2))),
                        low_price=Decimal(str(round(float(row['Low']), 2))),
                        close_price=Decimal(str(round(float(row['Close']), 2))),
                        volume=int(row['Volume']),
                        adj_close=Decimal(str(round(float(row['Close']), 2)))
                    ))
                except (ValueError, TypeError) as e:
                    self.logger.warning(f"Error processing index data on {trade_date}: {e}")
                    continue

            self.logger.info(f"Fetched {len(index_data)} index records")
            return index_data

        except Exception as e:
            self.logger.error(f"Error fetching index data: {e}")
            return []