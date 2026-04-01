"""
CSV-based stock scanner for analyzing downloaded stock data
"""
import pandas as pd
import numpy as np
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
import glob

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.append(str(project_root))

from src.utils.logger import get_logger
from config.settings import settings

logger = get_logger(__name__)

class CSVStockScanner:
    """Scanner that analyzes CSV files for stock selection"""

    def __init__(self):
        self.logger = get_logger(self.__class__.__name__)
        self.data_path = Path(settings.data.stocks_path)

    def calculate_technical_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate technical indicators for a stock"""
        try:
            df = df.copy()

            # Ensure we have the required columns
            if 'close' not in df.columns:
                self.logger.warning("No 'close' column found in data")
                return df

            # Sort by date
            if 'date' in df.columns:
                df = df.sort_values('date').reset_index(drop=True)

            # Calculate moving averages
            df['ma5'] = df['close'].rolling(window=5).mean()
            df['ma10'] = df['close'].rolling(window=10).mean()
            df['ma20'] = df['close'].rolling(window=20).mean()

            # Calculate RSI
            df['rsi14'] = self.calculate_rsi(df['close'], 14)

            # Calculate price change percentage
            df['price_change_pct'] = df['close'].pct_change() * 100

            # Calculate volume moving average
            if 'volume' in df.columns:
                df['volume_ma20'] = df['volume'].rolling(window=20).mean()

            return df

        except Exception as e:
            self.logger.error(f"Error calculating technical indicators: {e}")
            return df

    def calculate_rsi(self, prices: pd.Series, period: int = 14) -> pd.Series:
        """Calculate RSI indicator"""
        try:
            delta = prices.diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            return rsi

        except Exception as e:
            self.logger.error(f"Error calculating RSI: {e}")
            return pd.Series([np.nan] * len(prices))

    def load_stock_data(self, symbol_file: str) -> Optional[pd.DataFrame]:
        """Load stock data from CSV file"""
        try:
            filepath = self.data_path / symbol_file
            if not filepath.exists():
                self.logger.warning(f"File not found: {filepath}")
                return None

            df = pd.read_csv(filepath)
            if df.empty:
                self.logger.warning(f"Empty data file: {filepath}")
                return None

            # Convert date column to datetime
            if 'date' in df.columns:
                df['date'] = pd.to_datetime(df['date'])

            # Add technical indicators
            df = self.calculate_technical_indicators(df)

            return df

        except Exception as e:
            self.logger.error(f"Error loading data from {symbol_file}: {e}")
            return None

    def analyze_momentum_stocks(self) -> List[Dict]:
        """Analyze stocks for momentum strategy"""
        results = []

        try:
            csv_files = glob.glob(str(self.data_path / "*.csv"))
            self.logger.info(f"Analyzing {len(csv_files)} CSV files for momentum stocks")

            for csv_file in csv_files:
                try:
                    symbol = Path(csv_file).stem
                    df = self.load_stock_data(Path(csv_file).name)

                    if df is None or df.empty:
                        continue

                    # Get latest data
                    latest = df.iloc[-1]

                    # Check momentum criteria
                    if (
                        not pd.isna(latest.get('price_change_pct', np.nan)) and
                        not pd.isna(latest.get('volume', np.nan)) and
                        not pd.isna(latest.get('rsi14', np.nan)) and
                        latest.get('price_change_pct', 0) > settings.strategy.momentum_price_change and
                        latest.get('volume', 0) > settings.strategy.min_volume_momentum and
                        latest.get('rsi14', 0) > 50
                    ):
                        results.append({
                            'symbol': symbol,
                            'strategy': 'momentum',
                            'action': 'long',
                            'price': latest.get('close', 0),
                            'price_change_pct': latest.get('price_change_pct', 0),
                            'volume': latest.get('volume', 0),
                            'rsi14': latest.get('rsi14', 0),
                            'ma5': latest.get('ma5', 0),
                            'ma20': latest.get('ma20', 0),
                            'date': latest.get('date', datetime.now())
                        })

                except Exception as e:
                    self.logger.error(f"Error analyzing {csv_file}: {e}")
                    continue

            self.logger.info(f"Found {len(results)} momentum stocks")
            return results

        except Exception as e:
            self.logger.error(f"Error in momentum analysis: {e}")
            return []

    def analyze_oversold_stocks(self) -> List[Dict]:
        """Analyze stocks for oversold strategy"""
        results = []

        try:
            csv_files = glob.glob(str(self.data_path / "*.csv"))
            self.logger.info(f"Analyzing {len(csv_files)} CSV files for oversold stocks")

            for csv_file in csv_files:
                try:
                    symbol = Path(csv_file).stem
                    df = self.load_stock_data(Path(csv_file).name)

                    if df is None or df.empty:
                        continue

                    # Get latest data
                    latest = df.iloc[-1]

                    # Check oversold criteria
                    if (
                        not pd.isna(latest.get('rsi14', np.nan)) and
                        not pd.isna(latest.get('price_change_pct', np.nan)) and
                        not pd.isna(latest.get('volume', np.nan)) and
                        latest.get('rsi14', 100) < settings.strategy.rsi_oversold_threshold and
                        latest.get('price_change_pct', 0) < settings.strategy.oversold_price_change and
                        latest.get('volume', 0) > settings.strategy.min_volume_oversold
                    ):
                        results.append({
                            'symbol': symbol,
                            'strategy': 'oversold',
                            'action': 'long',
                            'price': latest.get('close', 0),
                            'price_change_pct': latest.get('price_change_pct', 0),
                            'volume': latest.get('volume', 0),
                            'rsi14': latest.get('rsi14', 0),
                            'ma5': latest.get('ma5', 0),
                            'ma20': latest.get('ma20', 0),
                            'date': latest.get('date', datetime.now())
                        })

                except Exception as e:
                    self.logger.error(f"Error analyzing {csv_file}: {e}")
                    continue

            self.logger.info(f"Found {len(results)} oversold stocks")
            return results

        except Exception as e:
            self.logger.error(f"Error in oversold analysis: {e}")
            return []

    def analyze_breakout_stocks(self) -> List[Dict]:
        """Analyze stocks for breakout strategy"""
        results = []

        try:
            csv_files = glob.glob(str(self.data_path / "*.csv"))
            self.logger.info(f"Analyzing {len(csv_files)} CSV files for breakout stocks")

            for csv_file in csv_files:
                try:
                    symbol = Path(csv_file).stem
                    df = self.load_stock_data(Path(csv_file).name)

                    if df is None or df.empty:
                        continue

                    # Get latest data
                    latest = df.iloc[-1]

                    # Check breakout criteria (high volume + price above MA)
                    if (
                        not pd.isna(latest.get('volume', np.nan)) and
                        not pd.isna(latest.get('close', np.nan)) and
                        not pd.isna(latest.get('ma20', np.nan)) and
                        latest.get('volume', 0) > settings.strategy.min_volume_breakout and
                        latest.get('close', 0) > latest.get('ma20', 0) and
                        latest.get('close', 0) > settings.strategy.min_price
                    ):
                        results.append({
                            'symbol': symbol,
                            'strategy': 'breakout',
                            'action': 'long',
                            'price': latest.get('close', 0),
                            'price_change_pct': latest.get('price_change_pct', 0),
                            'volume': latest.get('volume', 0),
                            'rsi14': latest.get('rsi14', 0),
                            'ma5': latest.get('ma5', 0),
                            'ma20': latest.get('ma20', 0),
                            'date': latest.get('date', datetime.now())
                        })

                except Exception as e:
                    self.logger.error(f"Error analyzing {csv_file}: {e}")
                    continue

            self.logger.info(f"Found {len(results)} breakout stocks")
            return results

        except Exception as e:
            self.logger.error(f"Error in breakout analysis: {e}")
            return []

    def run_all_strategies(self) -> Dict[str, List[Dict]]:
        """Run all screening strategies"""
        results = {
            'momentum': self.analyze_momentum_stocks(),
            'oversold': self.analyze_oversold_stocks(),
            'breakout': self.analyze_breakout_stocks()
        }

        total_stocks = sum(len(stocks) for stocks in results.values())
        self.logger.info(f"Screening completed: {total_stocks} total stocks found")

        return results

    def format_results_for_telegram(self, results: Dict[str, List[Dict]]) -> str:
        """Format screening results for Telegram message"""
        try:
            message = "📈 台股選股分析結果\\n\\n"

            for strategy, stocks in results.items():
                if not stocks:
                    continue

                strategy_name = {
                    'momentum': '動能股',
                    'oversold': '超賣股',
                    'breakout': '突破股'
                }.get(strategy, strategy)

                message += f"🎯 *{strategy_name}* ({len(stocks)}支)\\n"

                for stock in stocks[:5]:  # Limit to top 5 per strategy
                    symbol = stock['symbol'].replace('_', '.')
                    action = "做多" if stock['action'] == 'long' else "做空"
                    price = stock['price']
                    change_pct = stock['price_change_pct']

                    message += f"• {symbol} - {action}\\n"
                    message += f"  價格: {price:.2f} ({change_pct:+.2f}%)\\n"

                message += "\\n"

            message += f"📊 分析時間: {datetime.now().strftime('%Y-%m-%d %H:%M')}"

            return message

        except Exception as e:
            self.logger.error(f"Error formatting results: {e}")
            return "選股分析發生錯誤"