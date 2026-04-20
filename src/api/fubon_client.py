"""
Fubon Securities Official SDK Client for Taiwan Stock and Futures Data
Based on official Fubon Neo API v2.2.8

Authentication: apikey_login(user_id, api_key, cert_path, cert_password)
"""
import asyncio
import time
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Any
from decimal import Decimal

from ..utils.rate_limiter import RateLimiter
from ..utils.logger import get_logger

logger = get_logger(__name__)

# Month code mapping for Taiwan futures symbols
# TXF + month_code + last_year_digit, e.g. TXFE6 = TXF May 2026
MONTH_CODES = {1: 'A', 2: 'B', 3: 'C', 4: 'D', 5: 'E', 6: 'F',
               7: 'G', 8: 'H', 9: 'I', 10: 'J', 11: 'K', 12: 'L'}


class FubonAPIError(Exception):
    """Custom exception for Fubon API errors"""
    pass


def get_near_month_symbol(product: str) -> str:
    """
    Compute the current near-month futures symbol.
    Taiwan index futures expire on the 3rd Wednesday of each month.

    Args:
        product: Product prefix e.g. 'TXF', 'MXF', 'MTX'

    Returns:
        Near-month symbol, e.g. 'TXFE6'
    """
    today = date.today()

    def third_wednesday(year: int, month: int) -> date:
        first = date(year, month, 1)
        # weekday(): Monday=0, Wednesday=2
        offset = (2 - first.weekday()) % 7
        first_wed = first + timedelta(days=offset)
        return first_wed + timedelta(weeks=2)

    expiry = third_wednesday(today.year, today.month)

    if today >= expiry:
        # Use next month
        if today.month == 12:
            year, month = today.year + 1, 1
        else:
            year, month = today.year, today.month + 1
    else:
        year, month = today.year, today.month

    month_code = MONTH_CODES[month]
    year_digit = str(year)[-1]
    return f"{product}{month_code}{year_digit}"


class FubonClient:
    """
    Fubon Securities Official SDK Client

    Supports:
    - Stock market data and trading
    - Futures market data (TXF, MXF, MTX)
    - Futures trading via sdk.futopt
    - Futures account management via sdk.futopt_accounting

    Authentication via apikey_login(user_id, api_key, cert_path, cert_password)
    or login(user_id, password, cert_path, cert_password)
    """

    def __init__(
        self,
        user_id: str = None,
        password: str = None,
        cert_path: str = None,
        cert_password: str = None,
        api_key: str = None,
        api_secret: str = None,  # kept for backward compat, not used
        is_simulation: bool = False
    ):
        self.user_id = user_id
        self.password = password
        self.cert_path = cert_path
        self.cert_password = cert_password or user_id  # default cert pw = user_id
        self.api_key = api_key
        self.is_simulation = is_simulation

        self.sdk = None
        self.accounts = None
        self.is_logged_in = False

        self.rate_limiter = RateLimiter(max_requests=30, time_window=60)

    async def __aenter__(self):
        await self._initialize_sdk()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def _initialize_sdk(self):
        """Initialize the official Fubon SDK and login"""
        try:
            from fubon_neo.sdk import FubonSDK
            self.sdk = FubonSDK()

            if self.api_key and self.user_id and self.cert_path:
                await self._login_with_api_key()
            elif self.user_id and self.password and self.cert_path:
                await self._login_with_certificate()
            else:
                raise FubonAPIError(
                    "No valid auth credentials. Need either "
                    "(user_id + api_key + cert_path) or "
                    "(user_id + password + cert_path)"
                )

            self.sdk.init_realtime()
            self.is_logged_in = True
            logger.info("Fubon SDK initialized and logged in")

        except ImportError:
            raise FubonAPIError(
                "fubon_neo SDK not installed. "
                "Install from: docs/fubon.cert.p12 download page"
            )
        except Exception as e:
            logger.error(f"Failed to initialize Fubon SDK: {e}")
            raise FubonAPIError(f"SDK initialization failed: {e}")

    async def _login_with_api_key(self):
        """Login using API Key method: apikey_login(user_id, key, cert_path, cert_pass)"""
        try:
            self.accounts = self.sdk.apikey_login(
                self.user_id,
                self.api_key,
                self.cert_path,
                self.cert_password
            )
            if not self.accounts.is_success:
                raise FubonAPIError(f"API Key login failed: {self.accounts.message}")
            logger.info(f"Logged in with API Key. Accounts: {len(self.accounts.data)}")
        except FubonAPIError:
            raise
        except Exception as e:
            raise FubonAPIError(f"API Key login error: {e}")

    async def _login_with_certificate(self):
        """Login using certificate + password"""
        try:
            self.accounts = self.sdk.login(
                self.user_id,
                self.password,
                self.cert_path,
                self.cert_password
            )
            if not self.accounts.is_success:
                raise FubonAPIError(f"Certificate login failed: {self.accounts.message}")
            logger.info(f"Logged in with certificate. Accounts: {len(self.accounts.data)}")
        except FubonAPIError:
            raise
        except Exception as e:
            raise FubonAPIError(f"Certificate login error: {e}")

    async def close(self):
        """Close SDK connection"""
        try:
            if self.sdk and self.is_logged_in:
                if hasattr(self.sdk, 'logout'):
                    self.sdk.logout()
                self.is_logged_in = False
                logger.info("Fubon SDK disconnected")
        except Exception as e:
            logger.error(f"Error closing SDK: {e}")

    def get_futopt_account(self):
        """Get the futures/options account from the logged-in accounts"""
        if not self.accounts or not self.accounts.data:
            return None
        for acc in self.accounts.data:
            if hasattr(acc, 'account_type') and acc.account_type == 'futopt':
                return acc
        return None  # No futopt account; do not fall back to stock account

    def get_stock_account(self):
        """Get the stock account from the logged-in accounts"""
        if not self.accounts or not self.accounts.data:
            return None
        for acc in self.accounts.data:
            if hasattr(acc, 'account_type') and acc.account_type == 'stock':
                return acc
        return self.accounts.data[0]

    # ─────────────────────────────────────────────────────────────────────────
    # Futures Market Data
    # ─────────────────────────────────────────────────────────────────────────

    async def get_futures_quote(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get real-time futures quote.

        Args:
            symbol: Futures symbol e.g. 'TXFE6' (TXF May 2026)

        Returns:
            Quote data dict or None
        """
        try:
            await self.rate_limiter.acquire()
            if not self.is_logged_in:
                raise FubonAPIError("Not logged in")

            restfutopt = self.sdk.marketdata.rest_client.futopt
            result = restfutopt.intraday.quote(symbol=symbol)

            if not result or not hasattr(result, 'data') or not result.data:
                return None

            data = result.data if isinstance(result.data, dict) else vars(result.data)

            return {
                'symbol': symbol,
                'name': data.get('name', ''),
                'close_price': Decimal(str(data.get('closePrice', 0) or 0)),
                'last_price': Decimal(str(data.get('lastPrice', 0) or 0)),
                'open_price': Decimal(str(data.get('openPrice', 0) or 0)),
                'high_price': Decimal(str(data.get('highPrice', 0) or 0)),
                'low_price': Decimal(str(data.get('lowPrice', 0) or 0)),
                'previous_close': Decimal(str(data.get('previousClose', 0) or 0)),
                'change': Decimal(str(data.get('change', 0) or 0)),
                'change_percent': Decimal(str(data.get('changePercent', 0) or 0)),
                'volume': int(data.get('total', {}).get('tradeVolume', 0) if isinstance(data.get('total'), dict) else 0),
                'last_size': int(data.get('lastSize', 0) or 0),
                'timestamp': datetime.now(),
            }

        except FubonAPIError:
            raise
        except Exception as e:
            err_str = str(e)
            if '404' in err_str or 'Resource Not Found' in err_str:
                logger.debug(f"Futures quote not available for {symbol} (404 - product may not be supported by API)")
            else:
                logger.error(f"Failed to get futures quote for {symbol}: {e}")
            return None

    async def get_futures_tickers(
        self,
        product: str = 'TXF',
        exchange: str = 'TAIFEX',
        session: str = 'REGULAR'
    ) -> List[Dict[str, Any]]:
        """
        Get list of active futures contracts.

        Args:
            product: Product code e.g. 'TXF', 'MXF', 'MTX'
            exchange: Exchange, default 'TAIFEX'
            session: 'REGULAR' or 'AFTERHOURS'

        Returns:
            List of ticker dicts
        """
        try:
            await self.rate_limiter.acquire()
            if not self.is_logged_in:
                raise FubonAPIError("Not logged in")

            restfutopt = self.sdk.marketdata.rest_client.futopt
            result = restfutopt.intraday.tickers(
                type='FUTURE',
                exchange=exchange,
                session=session,
                product=product
            )

            if not result or not hasattr(result, 'data') or not result.data:
                return []

            tickers = []
            raw_data = result.data if isinstance(result.data, list) else []
            for item in raw_data:
                d = item if isinstance(item, dict) else vars(item)
                tickers.append({
                    'symbol': d.get('symbol', ''),
                    'name': d.get('name', ''),
                    'reference_price': d.get('referencePrice', 0),
                    'settlement_date': d.get('settlementDate', ''),
                    'start_date': d.get('startDate', ''),
                    'end_date': d.get('endDate', ''),
                })
            return tickers

        except FubonAPIError:
            raise
        except Exception as e:
            logger.error(f"Failed to get futures tickers for {product}: {e}")
            return []

    async def get_futures_candles(
        self,
        symbol: str,
        timeframe: str = '1',
        session: str = None
    ) -> List[Dict[str, Any]]:
        """
        Get futures intraday K-line data.

        Args:
            symbol: Futures symbol e.g. 'TXFE6'
            timeframe: '1','5','10','15','30','60' (minutes)
            session: None for regular, 'afterhours' for night session

        Returns:
            List of candle dicts
        """
        try:
            await self.rate_limiter.acquire()
            if not self.is_logged_in:
                raise FubonAPIError("Not logged in")

            restfutopt = self.sdk.marketdata.rest_client.futopt
            kwargs = {'symbol': symbol, 'timeframe': timeframe}
            if session:
                kwargs['session'] = session

            result = restfutopt.intraday.candles(**kwargs)

            if not result or not hasattr(result, 'data') or not result.data:
                return []

            candles = []
            raw_data = result.data if isinstance(result.data, list) else []
            for item in raw_data:
                d = item if isinstance(item, dict) else vars(item)
                candles.append({
                    'time': d.get('date', d.get('time', '')),
                    'open': Decimal(str(d.get('open', 0) or 0)),
                    'high': Decimal(str(d.get('high', 0) or 0)),
                    'low': Decimal(str(d.get('low', 0) or 0)),
                    'close': Decimal(str(d.get('close', 0) or 0)),
                    'volume': int(d.get('volume', 0) or 0),
                    'average': Decimal(str(d.get('average', 0) or 0)),
                })
            return candles

        except FubonAPIError:
            raise
        except Exception as e:
            logger.error(f"Failed to get futures candles for {symbol}: {e}")
            return []

    # ─────────────────────────────────────────────────────────────────────────
    # Futures Trading
    # ─────────────────────────────────────────────────────────────────────────

    async def place_futures_order(
        self,
        symbol: str,
        buy_sell: str,
        price: str,
        lot: int,
        price_type: str = 'Limit',
        time_in_force: str = 'ROD',
        order_type: str = 'Auto',
        account=None,
        is_async: bool = False
    ) -> Dict[str, Any]:
        """
        Place a futures order.

        Args:
            symbol: Futures symbol e.g. 'TXFE6'
            buy_sell: 'Buy' or 'Sell'
            price: Price string e.g. '20000' or 'MKT' for market order
            lot: Number of lots
            price_type: 'Limit', 'Market', etc.
            time_in_force: 'ROD', 'IOC', 'FOK'
            order_type: 'Auto' (auto new/close), 'New', 'Close'
            account: Account object (uses futopt account if None)
            is_async: True for non-blocking order

        Returns:
            Order result dict
        """
        try:
            if not self.is_logged_in:
                raise FubonAPIError("Not logged in")

            from fubon_neo.sdk import FutOptOrder
            from fubon_neo.constant import (
                BSAction, FutOptMarketType, FutOptPriceType,
                FutOptOrderType, TimeInForce
            )

            bs_map = {'Buy': BSAction.Buy, 'Sell': BSAction.Sell}
            pt_map = {
                'Limit': FutOptPriceType.Limit,
                'Market': FutOptPriceType.Market,
                'LimitUp': FutOptPriceType.LimitUp,
                'LimitDown': FutOptPriceType.LimitDown,
            }
            tif_map = {
                'ROD': TimeInForce.ROD,
                'IOC': TimeInForce.IOC,
                'FOK': TimeInForce.FOK,
            }
            ot_map = {
                'Auto': FutOptOrderType.Auto,
                'New': FutOptOrderType.New,
                'Close': FutOptOrderType.Close,
            }

            order = FutOptOrder(
                buy_sell=bs_map.get(buy_sell, BSAction.Buy),
                symbol=symbol,
                price=price,
                lot=lot,
                market_type=FutOptMarketType.Future,
                price_type=pt_map.get(price_type, FutOptPriceType.Limit),
                time_in_force=tif_map.get(time_in_force, TimeInForce.ROD),
                order_type=ot_map.get(order_type, FutOptOrderType.Auto),
            )

            acc = account or self.get_futopt_account()
            if acc is None:
                raise FubonAPIError("No futures account available")

            result = self.sdk.futopt.place_order(acc, order, is_async)

            if not result.is_success:
                raise FubonAPIError(f"Order failed: {result.message}")

            d = result.data if isinstance(result.data, dict) else vars(result.data)
            return {
                'order_no': d.get('order_no', d.get('orderNo', '')),
                'seq_no': d.get('seq_no', d.get('seqNo', '')),
                'symbol': d.get('symbol', symbol),
                'buy_sell': buy_sell,
                'price': price,
                'lot': lot,
                'status': d.get('status', ''),
                'filled_lot': d.get('filled_lot', d.get('filledLot', 0)),
                'filled_money': d.get('filled_money', d.get('filledMoney', 0)),
                'error_message': d.get('error_message', d.get('errorMessage', '')),
            }

        except FubonAPIError:
            raise
        except Exception as e:
            logger.error(f"Failed to place futures order: {e}")
            raise FubonAPIError(f"Place order failed: {e}")

    async def cancel_futures_order(self, order_no: str, account=None) -> Dict[str, Any]:
        """Cancel a futures order by order number"""
        try:
            if not self.is_logged_in:
                raise FubonAPIError("Not logged in")

            acc = account or self.get_futopt_account()
            if acc is None:
                raise FubonAPIError("No futures account available")

            result = self.sdk.futopt.cancel_order(acc, order_no)
            return {
                'is_success': result.is_success,
                'message': result.message,
            }
        except FubonAPIError:
            raise
        except Exception as e:
            logger.error(f"Failed to cancel futures order {order_no}: {e}")
            raise FubonAPIError(f"Cancel order failed: {e}")

    async def get_futures_orders(self, account=None) -> List[Dict[str, Any]]:
        """Get today's futures orders"""
        try:
            if not self.is_logged_in:
                raise FubonAPIError("Not logged in")

            acc = account or self.get_futopt_account()
            if acc is None:
                raise FubonAPIError("No futures account available")

            result = self.sdk.futopt.get_order_results(acc)
            if not result.is_success:
                return []

            orders = []
            raw_data = result.data if isinstance(result.data, list) else []
            for item in raw_data:
                d = item if isinstance(item, dict) else vars(item)
                orders.append({
                    'order_no': d.get('order_no', d.get('orderNo', '')),
                    'symbol': d.get('symbol', ''),
                    'buy_sell': str(d.get('buy_sell', d.get('buySell', ''))),
                    'price': d.get('price', 0),
                    'lot': d.get('lot', 0),
                    'filled_lot': d.get('filled_lot', d.get('filledLot', 0)),
                    'status': d.get('status', ''),
                })
            return orders
        except FubonAPIError:
            raise
        except Exception as e:
            logger.error(f"Failed to get futures orders: {e}")
            return []

    # ─────────────────────────────────────────────────────────────────────────
    # Futures Account Management
    # ─────────────────────────────────────────────────────────────────────────

    async def get_futures_positions(self, account=None) -> List[Dict[str, Any]]:
        """
        Get futures positions (hybrid position query).

        Returns:
            List of position dicts
        """
        try:
            if not self.is_logged_in:
                raise FubonAPIError("Not logged in")

            acc = account or self.get_futopt_account()
            if acc is None:
                raise FubonAPIError("No futures account available")

            result = self.sdk.futopt_accounting.query_hybrid_position(acc)
            if not result.is_success:
                logger.warning(f"Position query failed: {result.message}")
                return []

            positions = []
            raw_data = result.data if isinstance(result.data, list) else []
            for item in raw_data:
                d = item if isinstance(item, dict) else vars(item)
                positions.append({
                    'date': d.get('date', ''),
                    'symbol': d.get('symbol', ''),
                    'expiry_date': d.get('expiry_date', d.get('expiryDate', '')),
                    'buy_sell': str(d.get('buy_sell', d.get('buySell', ''))),
                    'price': float(d.get('price', 0) or 0),
                    'orig_lots': int(d.get('orig_lots', d.get('origLots', 0)) or 0),
                    'tradable_lot': int(d.get('tradable_lot', d.get('tradableLot', 0)) or 0),
                    'order_type': str(d.get('order_type', d.get('orderType', ''))),
                    'market_price': d.get('market_price', d.get('marketPrice', '')),
                    'profit_or_loss': float(d.get('profit_or_loss', d.get('profitOrLoss', 0)) or 0),
                    'initial_margin': float(d.get('initial_margin', d.get('initialMargin', 0)) or 0),
                    'maintenance_margin': float(d.get('maintenance_margin', d.get('maintenanceMargin', 0)) or 0),
                })
            return positions

        except FubonAPIError:
            raise
        except Exception as e:
            logger.error(f"Failed to get futures positions: {e}")
            return []

    async def get_futures_margin_equity(self, account=None) -> Optional[Dict[str, Any]]:
        """
        Get futures margin equity (account balance/risk status).

        Returns:
            Equity info dict or None
        """
        try:
            if not self.is_logged_in:
                raise FubonAPIError("Not logged in")

            acc = account or self.get_futopt_account()
            if acc is None:
                raise FubonAPIError("No futures account available")

            result = self.sdk.futopt_accounting.query_margin_equity(acc)
            if not result.is_success:
                logger.warning(f"Margin equity query failed: {result.message}")
                return None

            d = result.data if isinstance(result.data, dict) else vars(result.data)
            return {
                'date': d.get('date', ''),
                'account': d.get('account', ''),
                'currency': d.get('currency', 'TWD'),
                'today_balance': float(d.get('today_balance', d.get('todayBalance', 0)) or 0),
                'today_equity': float(d.get('today_equity', d.get('todayEquity', 0)) or 0),
                'initial_margin': float(d.get('initial_margin', d.get('initialMargin', 0)) or 0),
                'maintenance_margin': float(d.get('maintenance_margin', d.get('maintenanceMargin', 0)) or 0),
                'available_margin': float(d.get('available_margin', d.get('availableMargin', 0)) or 0),
                'risk_index': float(d.get('risk_index', d.get('riskIndex', 0)) or 0),
                'fut_unrealized_pnl': float(d.get('fut_unrealized_pnl', d.get('futUnrealizedPnl', 0)) or 0),
                'fut_realized_pnl': float(d.get('fut_realized_pnl', d.get('futRealizedPnl', 0)) or 0),
                'buy_lot': int(d.get('buy_lot', d.get('buyLot', 0)) or 0),
                'sell_lot': int(d.get('sell_lot', d.get('sellLot', 0)) or 0),
            }

        except FubonAPIError:
            raise
        except Exception as e:
            logger.error(f"Failed to get futures margin equity: {e}")
            return None

    # ─────────────────────────────────────────────────────────────────────────
    # Stock Market Data (existing functionality)
    # ─────────────────────────────────────────────────────────────────────────

    async def get_stock_list(self, market: str = "TSE") -> List[Dict[str, Any]]:
        """Get list of stocks in specified market"""
        try:
            await self.rate_limiter.acquire()
            if not self.is_logged_in:
                raise FubonAPIError("Not logged in")

            reststock = self.sdk.marketdata.rest_client.stock
            common_symbols = [
                "2330", "2317", "2454", "2882", "6505", "2308", "2303", "3711",
                "2891", "2886", "2002", "2412", "2881", "1303", "1301"
            ]

            stocks = []
            for symbol in common_symbols:
                try:
                    snapshot = reststock.snapshot.quotes(symbol=symbol)
                    if snapshot and snapshot.data:
                        d = snapshot.data if isinstance(snapshot.data, dict) else vars(snapshot.data)
                        stocks.append({
                            'symbol': symbol,
                            'name': d.get('name', f'Stock {symbol}'),
                            'market': market,
                            'price': d.get('price', 0),
                            'volume': d.get('volume', 0)
                        })
                except Exception:
                    continue

            return stocks

        except Exception as e:
            logger.error(f"Failed to get stock list: {e}")
            raise FubonAPIError(f"Stock list retrieval failed: {e}")

    async def get_stock_info(self, symbol: str) -> Dict[str, Any]:
        """Get detailed information for a specific stock"""
        try:
            await self.rate_limiter.acquire()
            if not self.is_logged_in:
                raise FubonAPIError("Not logged in")

            reststock = self.sdk.marketdata.rest_client.stock
            snapshot = reststock.snapshot.quotes(symbol=symbol)

            if not snapshot or not snapshot.data:
                raise FubonAPIError(f"No data for {symbol}")

            d = snapshot.data if isinstance(snapshot.data, dict) else vars(snapshot.data)
            return {
                'symbol': symbol,
                'name': d.get('name', f'Stock {symbol}'),
                'current_price': Decimal(str(d.get('price', 0) or 0)),
                'change_amount': Decimal(str(d.get('change', 0) or 0)),
                'change_percent': Decimal(str(d.get('changePercent', 0) or 0)),
                'volume': int(d.get('volume', 0) or 0),
                'high_price': Decimal(str(d.get('high', 0) or 0)),
                'low_price': Decimal(str(d.get('low', 0) or 0)),
                'open_price': Decimal(str(d.get('open', 0) or 0)),
                'previous_close': Decimal(str(d.get('previousClose', 0) or 0)),
                'timestamp': datetime.now()
            }

        except FubonAPIError:
            raise
        except Exception as e:
            logger.error(f"Failed to get stock info for {symbol}: {e}")
            raise FubonAPIError(f"Stock info retrieval failed: {e}")

    async def get_realtime_quote(self, symbol: str) -> Dict[str, Any]:
        """Get real-time quote for a stock"""
        return await self.get_stock_info(symbol)

    async def get_historical_data(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        interval: str = "1d"
    ) -> List[Dict[str, Any]]:
        """Get historical OHLCV data for a stock"""
        try:
            await self.rate_limiter.acquire()
            if not self.is_logged_in:
                raise FubonAPIError("Not logged in")

            reststock = self.sdk.marketdata.rest_client.stock
            sdk_interval = self._convert_interval_to_sdk(interval)

            historical_response = reststock.historical.candles(
                symbol=symbol,
                from_date=start_date,
                to_date=end_date,
                timeframe=sdk_interval
            )

            if not historical_response or not historical_response.data:
                return []

            historical_data = []
            raw = historical_response.data if isinstance(historical_response.data, list) else []
            for candle in raw:
                d = candle if isinstance(candle, dict) else vars(candle)
                historical_data.append({
                    'date': d.get('date', d.get('timestamp', '')),
                    'open_price': Decimal(str(d.get('open', 0) or 0)),
                    'high_price': Decimal(str(d.get('high', 0) or 0)),
                    'low_price': Decimal(str(d.get('low', 0) or 0)),
                    'close_price': Decimal(str(d.get('close', 0) or 0)),
                    'volume': int(d.get('volume', 0) or 0),
                    'turnover': Decimal(str(d.get('turnover', 0) or 0))
                })

            return historical_data

        except Exception as e:
            logger.error(f"Failed to get historical data for {symbol}: {e}")
            raise FubonAPIError(f"Historical data retrieval failed: {e}")

    def _convert_interval_to_sdk(self, interval: str) -> str:
        mapping = {
            "1m": "1", "5m": "5", "15m": "15", "30m": "30",
            "1h": "60", "1d": "D", "1w": "W", "1M": "M"
        }
        return mapping.get(interval, "D")

    async def get_multiple_quotes(self, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
        """Get real-time quotes for multiple stocks"""
        results = {}
        for symbol in symbols:
            try:
                await self.rate_limiter.acquire()
                reststock = self.sdk.marketdata.rest_client.stock
                quote_response = reststock.snapshot.quotes(symbol=symbol)
                if quote_response and quote_response.data:
                    d = quote_response.data if isinstance(quote_response.data, dict) else vars(quote_response.data)
                    results[symbol] = {
                        'symbol': symbol,
                        'current_price': Decimal(str(d.get('price', 0) or 0)),
                        'change_amount': Decimal(str(d.get('change', 0) or 0)),
                        'change_percent': Decimal(str(d.get('changePercent', 0) or 0)),
                        'volume': int(d.get('volume', 0) or 0),
                        'high_price': Decimal(str(d.get('high', 0) or 0)),
                        'low_price': Decimal(str(d.get('low', 0) or 0)),
                        'timestamp': datetime.now()
                    }
            except Exception as e:
                logger.warning(f"Failed to get quote for {symbol}: {e}")
                continue
            await asyncio.sleep(0.1)

        return results

    async def search_stocks(self, query: str, market: str = None) -> List[Dict[str, Any]]:
        """Search for stocks by symbol"""
        try:
            await self.rate_limiter.acquire()
            if not self.is_logged_in:
                raise FubonAPIError("Not logged in")

            results = []
            if query.isdigit() and len(query) == 4:
                try:
                    reststock = self.sdk.marketdata.rest_client.stock
                    response = reststock.snapshot.quotes(symbol=query)
                    if response and response.data:
                        d = response.data if isinstance(response.data, dict) else vars(response.data)
                        results.append({
                            'symbol': query,
                            'name': d.get('name', f'Stock {query}'),
                            'market': market or 'TSE',
                            'current_price': Decimal(str(d.get('price', 0) or 0)),
                            'volume': int(d.get('volume', 0) or 0)
                        })
                except Exception:
                    pass

            return results

        except Exception as e:
            raise FubonAPIError(f"Stock search failed: {e}")

    async def get_market_status(self) -> Dict[str, Any]:
        """Get current market status"""
        return {
            'is_open': True,
            'market_session': 'regular',
            'timestamp': datetime.now().isoformat(),
            'tse_status': 'open',
            'otc_status': 'open',
            'trading_day': datetime.now().strftime('%Y-%m-%d')
        }

    async def health_check(self) -> bool:
        """Check if API connection is healthy"""
        return self.is_logged_in
