"""
Market scanning engine for Taiwan stock market
"""
import asyncio
from datetime import datetime, date, timedelta
from typing import List, Dict, Set, Optional, Tuple
from decimal import Decimal

from sqlalchemy.orm import Session
from sqlalchemy import desc, and_

from ..database.connection import db_manager
from ..database.models import (
    Stock, StockPrice, StockRealtime, TechnicalIndicator, Alert
)
from ..infrastructure.market_data.fubon_client import FubonClient, FubonAPIError
from ..domain.services.indicator_calculator import IndicatorCalculator
from ..domain.services.signal_detector import SignalDetector
from ..utils.logger import get_logger
from ..utils.error_handler import handle_errors, retry_on_failure, CircuitBreaker

# Create circuit breaker instance
circuit_breaker = CircuitBreaker(failure_threshold=5, recovery_timeout=300)
from ..utils.rate_limiter import rate_limit_manager

logger = get_logger(__name__)

class MarketScanner:
    """Market scanning engine for Taiwan stock market"""

    def __init__(
        self,
        fubon_client: FubonClient,
        batch_size: int = 50,
        max_concurrent: int = 10,
        scan_interval: int = 300
    ):
        self.fubon_client = fubon_client
        self.batch_size = batch_size
        self.max_concurrent = max_concurrent
        self.scan_interval = scan_interval

        self.indicator_calculator = IndicatorCalculator()
        self.signal_detector = SignalDetector()

        self.logger = get_logger(self.__class__.__name__)
        self.is_running = False
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=5,
            recovery_timeout=300.0,
            expected_exception=FubonAPIError
        )

    async def start_scanning(self, markets: List[str] = ['TSE', 'OTC']):
        """
        Start continuous market scanning

        Args:
            markets: List of markets to scan (TSE, OTC)
        """
        self.is_running = True
        self.logger.info(f"Starting market scanner for markets: {markets}")

        while self.is_running:
            try:
                # Full market scan
                await self.scan_markets(markets)

                # Wait for next scan interval
                await asyncio.sleep(self.scan_interval)

            except KeyboardInterrupt:
                self.logger.info("Received stop signal")
                break
            except Exception as e:
                self.logger.error(f"Scanner error: {e}")
                await asyncio.sleep(60)  # Wait 1 minute on error

        self.logger.info("Market scanner stopped")

    def stop_scanning(self):
        """Stop the market scanner"""
        self.is_running = False

    @circuit_breaker
    @retry_on_failure(max_retries=3, delay=5.0, exceptions=(FubonAPIError,))
    async def scan_markets(self, markets: List[str]):
        """
        Scan all stocks in specified markets

        Args:
            markets: List of markets to scan
        """
        self.logger.info(f"Starting full market scan for {markets}")
        start_time = datetime.now()

        try:
            # Get all active stocks
            active_stocks = self._get_active_stocks(markets)
            self.logger.info(f"Found {len(active_stocks)} active stocks")

            if not active_stocks:
                self.logger.warning("No active stocks found")
                return

            # Process stocks in batches
            batches = [
                active_stocks[i:i + self.batch_size]
                for i in range(0, len(active_stocks), self.batch_size)
            ]

            total_signals = 0
            processed_count = 0

            # Process batches with concurrency control
            semaphore = asyncio.Semaphore(self.max_concurrent)

            for batch_num, batch in enumerate(batches, 1):
                self.logger.info(f"Processing batch {batch_num}/{len(batches)}")

                # Create tasks for batch
                tasks = [
                    self._scan_stock_with_semaphore(semaphore, stock)
                    for stock in batch
                ]

                # Process batch
                results = await asyncio.gather(*tasks, return_exceptions=True)

                # Count results
                for result in results:
                    if isinstance(result, Exception):
                        self.logger.error(f"Stock scan failed: {result}")
                    else:
                        processed_count += 1
                        if result:  # Signal count
                            total_signals += result

                # Rate limiting delay between batches
                await asyncio.sleep(1.0)

            # Scan summary
            duration = (datetime.now() - start_time).total_seconds()
            self.logger.info(
                f"Market scan completed: "
                f"{processed_count}/{len(active_stocks)} stocks, "
                f"{total_signals} signals, "
                f"{duration:.1f}s"
            )

        except Exception as e:
            self.logger.error(f"Market scan failed: {e}")
            raise

    async def _scan_stock_with_semaphore(self, semaphore: asyncio.Semaphore, stock: Stock) -> int:
        """Scan single stock with concurrency control"""
        async with semaphore:
            return await self._scan_single_stock(stock)

    @handle_errors(default_return_value=0)
    async def _scan_single_stock(self, stock: Stock) -> int:
        """
        Scan a single stock and generate signals

        Args:
            stock: Stock object to scan

        Returns:
            Number of signals generated
        """
        try:
            # Get real-time quote
            quote_data = await self.fubon_client.get_realtime_quote(stock.symbol)

            if not quote_data:
                return 0

            # Update real-time data
            await self._update_realtime_data(stock, quote_data)

            # Get recent price data for indicator calculation
            price_data = self._get_recent_prices(stock.id, days=100)

            if len(price_data) < 20:  # Minimum data required
                return 0

            # Calculate current indicators
            indicators_data = self.indicator_calculator.calculate_all_indicators(price_data)

            if not indicators_data:
                return 0

            # Get latest indicators
            latest_date = max(indicators_data.keys())
            current_indicators = indicators_data[latest_date]

            # Get previous indicators for comparison
            dates = sorted(indicators_data.keys())
            if len(dates) >= 2:
                previous_date = dates[-2]
                previous_indicators = indicators_data[previous_date]
            else:
                previous_indicators = {}

            # Update database with calculated indicators
            await self._save_indicators(stock.id, latest_date, current_indicators)

            # Detect signals
            signals = self.signal_detector.detect_signals(
                current_indicators=current_indicators,
                previous_indicators=previous_indicators,
                current_price=quote_data['current_price'],
                volume=quote_data['volume']
            )

            # Save signals
            signal_count = 0
            for signal in signals:
                if await self._save_signal(stock, signal):
                    signal_count += 1

            return signal_count

        except Exception as e:
            self.logger.error(f"Error scanning stock {stock.symbol}: {e}")
            return 0

    def _get_active_stocks(self, markets: List[str]) -> List[Stock]:
        """Get all active stocks from specified markets"""
        try:
            with db_manager.get_session() as session:
                return session.query(Stock).filter(
                    and_(
                        Stock.is_active == True,
                        Stock.market.in_(markets)
                    )
                ).all()
        except Exception as e:
            self.logger.error(f"Error getting active stocks: {e}")
            return []

    def _get_recent_prices(self, stock_id: str, days: int = 100) -> List[StockPrice]:
        """Get recent price data for a stock"""
        try:
            with db_manager.get_session() as session:
                cutoff_date = date.today() - timedelta(days=days)

                return session.query(StockPrice).filter(
                    and_(
                        StockPrice.stock_id == stock_id,
                        StockPrice.date >= cutoff_date
                    )
                ).order_by(StockPrice.date).all()
        except Exception as e:
            self.logger.error(f"Error getting recent prices: {e}")
            return []

    async def _update_realtime_data(self, stock: Stock, quote_data: Dict):
        """Update real-time stock data"""
        try:
            with db_manager.get_session() as session:
                # Check if real-time record exists
                existing = session.query(StockRealtime).filter(
                    StockRealtime.stock_id == stock.id
                ).first()

                if existing:
                    # Update existing record
                    existing.current_price = quote_data['current_price']
                    existing.change_amount = quote_data['change_amount']
                    existing.change_percent = quote_data['change_percent']
                    existing.volume = quote_data['volume']
                    existing.bid_price = quote_data.get('bid_price')
                    existing.ask_price = quote_data.get('ask_price')
                    existing.bid_volume = quote_data.get('bid_volume')
                    existing.ask_volume = quote_data.get('ask_volume')
                    existing.timestamp = quote_data['timestamp']
                else:
                    # Create new record
                    realtime = StockRealtime(
                        stock_id=stock.id,
                        current_price=quote_data['current_price'],
                        change_amount=quote_data['change_amount'],
                        change_percent=quote_data['change_percent'],
                        volume=quote_data['volume'],
                        bid_price=quote_data.get('bid_price'),
                        ask_price=quote_data.get('ask_price'),
                        bid_volume=quote_data.get('bid_volume'),
                        ask_volume=quote_data.get('ask_volume'),
                        timestamp=quote_data['timestamp']
                    )
                    session.add(realtime)

                session.commit()

        except Exception as e:
            self.logger.error(f"Error updating realtime data for {stock.symbol}: {e}")

    async def _save_indicators(self, stock_id: str, trade_date: date, indicators: Dict[str, Decimal]):
        """Save calculated indicators to database"""
        try:
            with db_manager.get_session() as session:
                # Check if indicators already exist
                existing = session.query(TechnicalIndicator).filter(
                    and_(
                        TechnicalIndicator.stock_id == stock_id,
                        TechnicalIndicator.date == trade_date
                    )
                ).first()

                if existing:
                    # Update existing indicators
                    for key, value in indicators.items():
                        if hasattr(existing, key):
                            setattr(existing, key, value)
                else:
                    # Create new indicators record
                    indicator = TechnicalIndicator(
                        stock_id=stock_id,
                        date=trade_date,
                        **indicators
                    )
                    session.add(indicator)

                session.commit()

        except Exception as e:
            self.logger.error(f"Error saving indicators: {e}")

    async def _save_signal(self, stock: Stock, signal: Dict) -> bool:
        """Save detected signal to database"""
        try:
            # Check for duplicate signals (cooldown period)
            if await self._check_signal_cooldown(stock.id, signal['name']):
                return False

            with db_manager.get_session() as session:
                alert = Alert(
                    stock_id=stock.id,
                    alert_type=signal['type'],
                    signal_name=signal['name'],
                    price=signal['price'],
                    description=signal['description'],
                    triggered_at=datetime.now()
                )
                session.add(alert)
                session.commit()

                self.logger.info(
                    f"Signal detected: {stock.symbol} - {signal['name']} "
                    f"({signal['type']}) @ {signal['price']}"
                )

                return True

        except Exception as e:
            self.logger.error(f"Error saving signal: {e}")
            return False

    async def _check_signal_cooldown(self, stock_id: str, signal_name: str, cooldown_minutes: int = 60) -> bool:
        """Check if signal is in cooldown period"""
        try:
            with db_manager.get_session() as session:
                cutoff_time = datetime.now() - timedelta(minutes=cooldown_minutes)

                existing = session.query(Alert).filter(
                    and_(
                        Alert.stock_id == stock_id,
                        Alert.signal_name == signal_name,
                        Alert.triggered_at >= cutoff_time
                    )
                ).first()

                return existing is not None

        except Exception as e:
            self.logger.error(f"Error checking signal cooldown: {e}")
            return False

class HistoricalDataUpdater:
    """Update historical price data for all stocks"""

    def __init__(self, fubon_client: FubonClient):
        self.fubon_client = fubon_client
        self.logger = get_logger(self.__class__.__name__)

    async def update_all_stocks(self, days_back: int = 30):
        """
        Update historical data for all active stocks

        Args:
            days_back: Number of days to fetch historical data
        """
        self.logger.info(f"Starting historical data update for {days_back} days")

        try:
            # Get all active stocks
            with db_manager.get_session() as session:
                stocks = session.query(Stock).filter(Stock.is_active == True).all()

            self.logger.info(f"Updating {len(stocks)} stocks")

            # Calculate date range
            end_date = date.today()
            start_date = end_date - timedelta(days=days_back)

            # Update each stock
            updated_count = 0
            for stock in stocks:
                try:
                    if await self._update_stock_history(stock, start_date, end_date):
                        updated_count += 1
                except Exception as e:
                    self.logger.error(f"Failed to update {stock.symbol}: {e}")

                # Rate limiting
                await asyncio.sleep(2)

            self.logger.info(f"Historical data update completed: {updated_count}/{len(stocks)} stocks")

        except Exception as e:
            self.logger.error(f"Historical data update failed: {e}")

    @retry_on_failure(max_retries=3, delay=5.0)
    async def _update_stock_history(self, stock: Stock, start_date: date, end_date: date) -> bool:
        """Update historical data for a single stock"""
        try:
            # Check what dates we already have
            existing_dates = self._get_existing_dates(stock.id, start_date, end_date)

            # Get historical data from API
            historical_data = await self.fubon_client.get_historical_data(
                symbol=stock.symbol,
                start_date=start_date.strftime('%Y-%m-%d'),
                end_date=end_date.strftime('%Y-%m-%d')
            )

            if not historical_data:
                return False

            # Filter out existing dates
            new_data = [
                data for data in historical_data
                if data['date'] not in existing_dates
            ]

            if not new_data:
                return True

            # Save new data
            with db_manager.get_session() as session:
                for data in new_data:
                    price_record = StockPrice(
                        stock_id=stock.id,
                        date=data['date'],
                        open_price=data['open_price'],
                        high_price=data['high_price'],
                        low_price=data['low_price'],
                        close_price=data['close_price'],
                        volume=data['volume'],
                        turnover=data.get('turnover')
                    )
                    session.add(price_record)

                session.commit()

            self.logger.debug(f"Updated {stock.symbol}: {len(new_data)} new records")
            return True

        except Exception as e:
            self.logger.error(f"Error updating {stock.symbol}: {e}")
            return False

    def _get_existing_dates(self, stock_id: str, start_date: date, end_date: date) -> Set[date]:
        """Get existing price dates for a stock in date range"""
        try:
            with db_manager.get_session() as session:
                existing = session.query(StockPrice.date).filter(
                    and_(
                        StockPrice.stock_id == stock_id,
                        StockPrice.date >= start_date,
                        StockPrice.date <= end_date
                    )
                ).all()

                return {row.date for row in existing}

        except Exception as e:
            self.logger.error(f"Error getting existing dates: {e}")
            return set()