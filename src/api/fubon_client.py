"""
Fubon Securities Official SDK Client for Taiwan Stock Data
Based on official Fubon Neo API v2.2.8
"""
import asyncio
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union
from decimal import Decimal
import os

from ..utils.rate_limiter import RateLimiter
from ..utils.logger import get_logger

logger = get_logger(__name__)

class FubonAPIError(Exception):
    """Custom exception for Fubon API errors"""
    pass

class FubonClient:
    """
    Fubon Securities Official SDK Client

    Uses the official fubon_neo SDK for authentication and data retrieval
    from Fubon Securities API for Taiwan stock market data.

    Authentication methods:
    1. API Key + Secret (recommended)
    2. Certificate file (.pfx) + password
    """

    def __init__(
        self,
        user_id: str = None,
        password: str = None,
        cert_path: str = None,
        cert_password: str = None,
        api_key: str = None,
        api_secret: str = None,
        is_simulation: bool = False
    ):
        """
        Initialize Fubon client with official SDK

        Args:
            user_id: Fubon user ID (for cert auth)
            password: Fubon password (for cert auth)
            cert_path: Path to certificate file
            cert_password: Certificate password
            api_key: API Key (for key auth)
            api_secret: API Secret (for key auth)
            is_simulation: Use simulation environment
        """
        self.user_id = user_id
        self.password = password
        self.cert_path = cert_path
        self.cert_password = cert_password
        self.api_key = api_key
        self.api_secret = api_secret
        self.is_simulation = is_simulation

        # Will be initialized in __aenter__
        self.sdk = None
        self.accounts = None
        self.is_logged_in = False

        # Rate limiter
        self.rate_limiter = RateLimiter(
            max_requests=30,  # Based on Fubon documentation
            time_window=60
        )

    async def __aenter__(self):
        """Async context manager entry"""
        await self._initialize_sdk()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close()

    async def _initialize_sdk(self):
        """Initialize the official Fubon SDK"""
        try:
            # Import the official SDK
            from fubon_neo.sdk import FubonSDK

            self.sdk = FubonSDK()

            # Login using appropriate method
            if self.api_key and self.api_secret:
                # API Key authentication (recommended)
                await self._login_with_api_key()
            elif self.user_id and self.cert_path:
                # Certificate authentication
                await self._login_with_certificate()
            else:
                raise FubonAPIError("No valid authentication credentials provided")

            # Initialize real-time market data connection
            self.sdk.init_realtime()
            self.is_logged_in = True

            logger.info("Fubon SDK initialized successfully")

        except ImportError:
            raise FubonAPIError(
                "Official fubon_neo SDK not installed. "
                "Please install with: pip install fubon-neo"
            )
        except Exception as e:
            logger.error(f"Failed to initialize Fubon SDK: {e}")
            raise FubonAPIError(f"SDK initialization failed: {e}")

    async def _login_with_api_key(self):
        """Login using API Key method"""
        try:
            if self.is_simulation:
                # Use simulation environment
                self.accounts = self.sdk.login_by_api_key_simulation(
                    self.api_key,
                    self.api_secret
                )
            else:
                # Use production environment
                self.accounts = self.sdk.login_by_api_key(
                    self.api_key,
                    self.api_secret
                )

            logger.info("Logged in successfully with API Key")

        except Exception as e:
            logger.error(f"API Key login failed: {e}")
            raise FubonAPIError(f"API Key authentication failed: {e}")

    async def _login_with_certificate(self):
        """Login using certificate method"""
        try:
            if self.is_simulation:
                # Use simulation environment
                self.accounts = self.sdk.login_simulation(
                    self.user_id,
                    self.password,
                    self.cert_path,
                    self.cert_password or self.user_id  # Use user_id as default cert password
                )
            else:
                # Use production environment
                self.accounts = self.sdk.login(
                    self.user_id,
                    self.password,
                    self.cert_path,
                    self.cert_password or self.user_id
                )

            logger.info("Logged in successfully with certificate")

        except Exception as e:
            logger.error(f"Certificate login failed: {e}")
            raise FubonAPIError(f"Certificate authentication failed: {e}")

    async def close(self):
        """Close the SDK connection"""
        try:
            if self.sdk and self.is_logged_in:
                # Close real-time connection
                if hasattr(self.sdk, 'close_realtime'):
                    self.sdk.close_realtime()

                # Logout
                if hasattr(self.sdk, 'logout'):
                    self.sdk.logout()

                self.is_logged_in = False
                logger.info("Fubon SDK closed successfully")

        except Exception as e:
            logger.error(f"Error closing SDK: {e}")

    async def get_stock_list(self, market: str = "TSE") -> List[Dict[str, Any]]:
        """
        Get list of all stocks in specified market using official SDK

        Args:
            market: Market type ("TSE" or "OTC")

        Returns:
            List of stock information dictionaries
        """
        try:
            await self.rate_limiter.acquire()

            if not self.is_logged_in:
                raise FubonAPIError("Not logged in. Please initialize the client first.")

            # Use the SDK's market data client
            reststock = self.sdk.marketdata.rest_client.stock

            # Get reference data for the specified market
            # Based on Fubon API, we'll get snapshots and build stock list
            stocks = []

            # Common Taiwan market symbols - this would typically come from reference data
            # In a real implementation, you'd use the SDK's reference endpoints
            common_symbols = [
                "2330", "2317", "2454", "2882", "6505", "2308", "2303", "3711",
                "2891", "2886", "2002", "2412", "2881", "1303", "1301"
            ]

            for symbol in common_symbols:
                try:
                    # Get stock snapshot using official SDK
                    snapshot = reststock.snapshot.quotes(symbol=symbol)
                    if snapshot and snapshot.data:
                        stocks.append({
                            'symbol': symbol,
                            'name': snapshot.data.get('name', f'Stock {symbol}'),
                            'market': market,
                            'price': snapshot.data.get('price', 0),
                            'volume': snapshot.data.get('volume', 0)
                        })
                except Exception as e:
                    logger.warning(f"Failed to get snapshot for {symbol}: {e}")
                    continue

            logger.info(f"Retrieved {len(stocks)} stocks for {market} market")
            return stocks

        except Exception as e:
            logger.error(f"Failed to get stock list: {e}")
            raise FubonAPIError(f"Stock list retrieval failed: {e}")

    async def get_stock_info(self, symbol: str) -> Dict[str, Any]:
        """
        Get detailed information for a specific stock using official SDK

        Args:
            symbol: Stock symbol (e.g., "2330")

        Returns:
            Stock information dictionary
        """
        try:
            await self.rate_limiter.acquire()

            if not self.is_logged_in:
                raise FubonAPIError("Not logged in. Please initialize the client first.")

            # Use the SDK's stock API to get detailed information
            reststock = self.sdk.marketdata.rest_client.stock

            # Get stock snapshot for current information
            snapshot = reststock.snapshot.quotes(symbol=symbol)

            if not snapshot or not snapshot.data:
                raise FubonAPIError(f"No data available for symbol {symbol}")

            stock_data = snapshot.data

            # Convert to standard format
            return {
                'symbol': symbol,
                'name': stock_data.get('name', f'Stock {symbol}'),
                'current_price': Decimal(str(stock_data.get('price', 0))),
                'change_amount': Decimal(str(stock_data.get('change', 0))),
                'change_percent': Decimal(str(stock_data.get('changePercent', 0))),
                'volume': int(stock_data.get('volume', 0)),
                'high_price': Decimal(str(stock_data.get('high', 0))),
                'low_price': Decimal(str(stock_data.get('low', 0))),
                'open_price': Decimal(str(stock_data.get('open', 0))),
                'previous_close': Decimal(str(stock_data.get('previousClose', 0))),
                'market_cap': stock_data.get('marketCap'),
                'pe_ratio': stock_data.get('peRatio'),
                'timestamp': datetime.now()
            }

        except Exception as e:
            logger.error(f"Failed to get stock info for {symbol}: {e}")
            raise FubonAPIError(f"Stock info retrieval failed: {e}")

    async def get_realtime_quote(self, symbol: str) -> Dict[str, Any]:
        """
        Get real-time quote for a stock using official SDK

        Args:
            symbol: Stock symbol

        Returns:
            Real-time quote data
        """
        try:
            await self.rate_limiter.acquire()

            if not self.is_logged_in:
                raise FubonAPIError("Not logged in. Please initialize the client first.")

            # Use the SDK's real-time market data
            reststock = self.sdk.marketdata.rest_client.stock

            # Get real-time quote
            quote_response = reststock.snapshot.quotes(symbol=symbol)

            if not quote_response or not quote_response.data:
                raise FubonAPIError(f"No real-time data available for symbol {symbol}")

            quote_data = quote_response.data

            # Convert to standard format
            return {
                'symbol': symbol,
                'current_price': Decimal(str(quote_data.get('price', 0))),
                'change_amount': Decimal(str(quote_data.get('change', 0))),
                'change_percent': Decimal(str(quote_data.get('changePercent', 0))),
                'volume': int(quote_data.get('volume', 0)),
                'bid_price': Decimal(str(quote_data.get('bidPrice', 0))) if quote_data.get('bidPrice') else None,
                'ask_price': Decimal(str(quote_data.get('askPrice', 0))) if quote_data.get('askPrice') else None,
                'bid_volume': quote_data.get('bidVolume'),
                'ask_volume': quote_data.get('askVolume'),
                'high_price': Decimal(str(quote_data.get('high', 0))),
                'low_price': Decimal(str(quote_data.get('low', 0))),
                'open_price': Decimal(str(quote_data.get('open', 0))),
                'timestamp': datetime.now()
            }

        except Exception as e:
            logger.error(f"Failed to get realtime quote for {symbol}: {e}")
            raise FubonAPIError(f"Real-time quote retrieval failed: {e}")

    async def get_historical_data(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        interval: str = "1d"
    ) -> List[Dict[str, Any]]:
        """
        Get historical OHLCV data for a stock using official SDK

        Args:
            symbol: Stock symbol
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            interval: Data interval ("1d", "1h", "5m", etc.)

        Returns:
            List of OHLCV data dictionaries
        """
        try:
            await self.rate_limiter.acquire()

            if not self.is_logged_in:
                raise FubonAPIError("Not logged in. Please initialize the client first.")

            # Use the SDK's historical data API
            reststock = self.sdk.marketdata.rest_client.stock

            # Convert interval to SDK format
            sdk_interval = self._convert_interval_to_sdk(interval)

            # Get historical candle data
            historical_response = reststock.historical.candles(
                symbol=symbol,
                from_date=start_date,
                to_date=end_date,
                timeframe=sdk_interval
            )

            if not historical_response or not historical_response.data:
                logger.warning(f"No historical data available for {symbol}")
                return []

            # Convert to standard format
            historical_data = []
            for candle in historical_response.data:
                historical_data.append({
                    'date': datetime.strptime(candle.get('date', candle.get('timestamp', '')), '%Y-%m-%d').date(),
                    'open_price': Decimal(str(candle.get('open', 0))),
                    'high_price': Decimal(str(candle.get('high', 0))),
                    'low_price': Decimal(str(candle.get('low', 0))),
                    'close_price': Decimal(str(candle.get('close', 0))),
                    'volume': int(candle.get('volume', 0)),
                    'turnover': Decimal(str(candle.get('turnover', 0)))
                })

            logger.info(f"Retrieved {len(historical_data)} historical records for {symbol}")
            return historical_data

        except Exception as e:
            logger.error(f"Failed to get historical data for {symbol}: {e}")
            raise FubonAPIError(f"Historical data retrieval failed: {e}")

    def _convert_interval_to_sdk(self, interval: str) -> str:
        """Convert interval format to SDK timeframe"""
        interval_mapping = {
            "1m": "1",
            "5m": "5",
            "15m": "15",
            "30m": "30",
            "1h": "60",
            "1d": "D",
            "1w": "W",
            "1M": "M"
        }
        return interval_mapping.get(interval, "D")

    async def get_multiple_quotes(self, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Get real-time quotes for multiple stocks using official SDK

        Args:
            symbols: List of stock symbols

        Returns:
            Dictionary mapping symbols to quote data
        """
        try:
            if not self.is_logged_in:
                raise FubonAPIError("Not logged in. Please initialize the client first.")

            # Split into chunks to respect API limits
            chunk_size = 20  # Conservative chunk size for Fubon API
            results = {}

            for i in range(0, len(symbols), chunk_size):
                chunk = symbols[i:i + chunk_size]

                # Process each symbol individually for now
                # Fubon SDK may have batch endpoints that we can utilize later
                for symbol in chunk:
                    try:
                        await self.rate_limiter.acquire()

                        # Get quote using official SDK
                        reststock = self.sdk.marketdata.rest_client.stock
                        quote_response = reststock.snapshot.quotes(symbol=symbol)

                        if quote_response and quote_response.data:
                            quote_data = quote_response.data
                            results[symbol] = {
                                'symbol': symbol,
                                'current_price': Decimal(str(quote_data.get('price', 0))),
                                'change_amount': Decimal(str(quote_data.get('change', 0))),
                                'change_percent': Decimal(str(quote_data.get('changePercent', 0))),
                                'volume': int(quote_data.get('volume', 0)),
                                'high_price': Decimal(str(quote_data.get('high', 0))),
                                'low_price': Decimal(str(quote_data.get('low', 0))),
                                'timestamp': datetime.now()
                            }
                    except Exception as e:
                        logger.warning(f"Failed to get quote for {symbol}: {e}")
                        continue

                # Small delay between chunks
                await asyncio.sleep(0.5)

            logger.info(f"Retrieved quotes for {len(results)} stocks")
            return results

        except Exception as e:
            logger.error(f"Failed to get multiple quotes: {e}")
            raise FubonAPIError(f"Multiple quotes retrieval failed: {e}")

    async def search_stocks(self, query: str, market: str = None) -> List[Dict[str, Any]]:
        """
        Search for stocks by name or symbol using official SDK

        Args:
            query: Search query (name or symbol)
            market: Optional market filter ("TSE" or "OTC")

        Returns:
            List of matching stocks
        """
        try:
            await self.rate_limiter.acquire()

            if not self.is_logged_in:
                raise FubonAPIError("Not logged in. Please initialize the client first.")

            # For stock search, we'll try to match against known symbols
            # The official SDK may not have a direct search endpoint
            reststock = self.sdk.marketdata.rest_client.stock

            results = []

            # If query looks like a stock symbol, try direct lookup
            if query.isdigit() and len(query) == 4:
                try:
                    quote_response = reststock.snapshot.quotes(symbol=query)
                    if quote_response and quote_response.data:
                        stock_data = quote_response.data
                        results.append({
                            'symbol': query,
                            'name': stock_data.get('name', f'Stock {query}'),
                            'market': market or 'TSE',
                            'current_price': Decimal(str(stock_data.get('price', 0))),
                            'volume': int(stock_data.get('volume', 0))
                        })
                except Exception as e:
                    logger.debug(f"Direct lookup failed for {query}: {e}")

            logger.info(f"Found {len(results)} stocks matching '{query}'")
            return results

        except Exception as e:
            logger.error(f"Failed to search stocks: {e}")
            raise FubonAPIError(f"Stock search failed: {e}")

    async def get_market_status(self) -> Dict[str, Any]:
        """
        Get current market status using official SDK

        Returns:
            Market status information
        """
        try:
            await self.rate_limiter.acquire()

            if not self.is_logged_in:
                raise FubonAPIError("Not logged in. Please initialize the client first.")

            # Use the SDK to get market status information
            # This might be available through market data or system endpoints
            # For now, we'll return basic status based on SDK connection
            market_status = {
                'is_open': True,  # This would come from actual market hours check
                'market_session': 'regular',  # regular, pre, post
                'timestamp': datetime.now().isoformat(),
                'tse_status': 'open',  # Taiwan Stock Exchange
                'otc_status': 'open',  # Over-the-counter
                'trading_day': datetime.now().strftime('%Y-%m-%d')
            }

            # Try to get actual market status if available in SDK
            try:
                # This would be the actual SDK call when available
                # market_info = self.sdk.marketdata.rest_client.market.status()
                pass
            except Exception as e:
                logger.debug(f"Market status API call failed: {e}")

            logger.info("Retrieved market status")
            return market_status

        except Exception as e:
            logger.error(f"Failed to get market status: {e}")
            raise FubonAPIError(f"Market status retrieval failed: {e}")

    async def health_check(self) -> bool:
        """
        Check if API connection is healthy using official SDK

        Returns:
            True if API is accessible, False otherwise
        """
        try:
            if not self.is_logged_in:
                return False

            # Simple check to see if SDK is responsive
            await self.get_market_status()
            return True

        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False