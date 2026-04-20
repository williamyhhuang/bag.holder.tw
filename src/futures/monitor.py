"""
Taiwan futures monitoring and analysis system
"""
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional, NamedTuple
from decimal import Decimal
from dataclasses import dataclass
import asyncio

from ..api.fubon_client import FubonClient
from ..utils.logger import get_logger
from ..utils.error_handler import handle_errors, retry_on_failure
from ..utils.rate_limiter import rate_limit_manager

logger = get_logger(__name__)

@dataclass
class FuturesContract:
    """Futures contract information"""
    symbol: str
    name: str
    underlying: str  # Underlying stock/index
    expiry_date: date
    contract_size: int
    tick_size: Decimal
    is_active: bool

@dataclass
class FuturesQuote:
    """Futures real-time quote"""
    symbol: str
    price: Decimal
    volume: int
    timestamp: datetime
    bid_price: Optional[Decimal] = None
    ask_price: Optional[Decimal] = None
    bid_volume: Optional[int] = None
    ask_volume: Optional[int] = None
    change_amount: Optional[Decimal] = None
    change_percent: Optional[Decimal] = None
    open_interest: Optional[int] = None
    high_price: Optional[Decimal] = None
    low_price: Optional[Decimal] = None
    settlement_price: Optional[Decimal] = None

@dataclass
class FuturesSignal:
    """Futures trading signal"""
    contract_symbol: str
    signal_type: str  # LONG, SHORT, CLOSE_LONG, CLOSE_SHORT
    signal_name: str
    current_price: Decimal
    target_price: Optional[Decimal]
    stop_loss: Optional[Decimal]
    confidence: float
    description: str
    triggered_at: datetime

class TaiwanFuturesMonitor:
    """Monitor Taiwan futures market"""

    def __init__(self, fubon_client: FubonClient):
        self.fubon_client = fubon_client
        self.logger = get_logger(self.__class__.__name__)

        # Taiwan futures contracts - 僅追蹤大台、小台、微台近月合約
        self.futures_contracts = {
            'TXF': FuturesContract(
                symbol='TXF',
                name='台指期貨(大台)',
                underlying='台灣加權指數',
                expiry_date=self._get_near_month_expiry(),
                contract_size=200,
                tick_size=Decimal('1'),
                is_active=True
            ),
            'MXF': FuturesContract(
                symbol='MXF',
                name='小台指期貨(小台)',
                underlying='台灣加權指數',
                expiry_date=self._get_near_month_expiry(),
                contract_size=50,
                tick_size=Decimal('1'),
                is_active=True
            ),
            'MTX': FuturesContract(
                symbol='MTX',
                name='微型台指期貨(微台)',
                underlying='台灣加權指數',
                expiry_date=self._get_near_month_expiry(),
                contract_size=10,
                tick_size=Decimal('1'),
                is_active=True
            )
        }

        self.is_monitoring = False

    def _get_near_month_expiry(self) -> date:
        """
        計算台指期貨近月合約到期日
        台指期貨到期日為每月第三個週三
        """
        today = date.today()
        current_month = today.month
        current_year = today.year

        # 找到當月第三個週三
        first_day = date(current_year, current_month, 1)
        first_weekday = first_day.weekday()  # 0=Monday, 2=Wednesday

        # 計算第一個週三是幾號
        if first_weekday <= 2:  # 如果1號是週一、二、三
            first_wednesday = 3 - first_weekday
        else:  # 如果1號是週四到週日
            first_wednesday = 10 - first_weekday

        # 第三個週三
        third_wednesday = first_wednesday + 14

        try:
            expiry_date = date(current_year, current_month, third_wednesday)

            # 如果今天已過當月到期日，使用下月合約
            if today >= expiry_date:
                if current_month == 12:
                    next_month = 1
                    next_year = current_year + 1
                else:
                    next_month = current_month + 1
                    next_year = current_year

                # 計算下月第三個週三
                first_day_next = date(next_year, next_month, 1)
                first_weekday_next = first_day_next.weekday()

                if first_weekday_next <= 2:
                    first_wednesday_next = 3 - first_weekday_next
                else:
                    first_wednesday_next = 10 - first_weekday_next

                third_wednesday_next = first_wednesday_next + 14
                expiry_date = date(next_year, next_month, third_wednesday_next)

        except ValueError:
            # 如果日期無效（如2月沒有29、30、31日），回退到月底
            if current_month == 12:
                expiry_date = date(current_year + 1, 1, 15)  # 使用下年1月中
            else:
                expiry_date = date(current_year, current_month + 1, 15)  # 使用下月中

        return expiry_date

    async def start_monitoring(self, contracts: List[str] = None, monitor_interval: int = 30):
        """
        Start futures monitoring

        Args:
            contracts: List of contract symbols to monitor (None for enabled contracts)
            monitor_interval: Monitoring interval in seconds
        """
        if contracts is None:
            # 只監控啟用的合約：TXF(大台), MXF(小台), MTX(微台)
            contracts = ['TXF', 'MXF', 'MTX']

        # 過濾出實際存在的合約
        valid_contracts = [c for c in contracts if c in self.futures_contracts]

        if not valid_contracts:
            self.logger.warning("No valid contracts to monitor")
            return

        self.is_monitoring = True
        self.logger.info(f"🔍 Starting futures monitoring for Taiwan Index Futures:")
        for contract in valid_contracts:
            contract_info = self.futures_contracts[contract]
            self.logger.info(f"  • {contract_info.name} ({contract}) - 合約大小: {contract_info.contract_size}")

        while self.is_monitoring:
            try:
                await self._monitor_cycle(valid_contracts)
                await asyncio.sleep(monitor_interval)
            except KeyboardInterrupt:
                break
            except Exception as e:
                self.logger.error(f"Futures monitoring error: {e}")
                await asyncio.sleep(60)

        self.logger.info("Futures monitoring stopped")

    def stop_monitoring(self):
        """Stop futures monitoring"""
        self.is_monitoring = False

    @handle_errors()
    async def _monitor_cycle(self, contracts: List[str]):
        """Single monitoring cycle"""
        tasks = []

        for contract_symbol in contracts:
            if contract_symbol in self.futures_contracts:
                task = self._monitor_single_contract(contract_symbol)
                tasks.append(task)

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    @retry_on_failure(max_retries=3, delay=2.0)
    async def _monitor_single_contract(self, contract_symbol: str):
        """Monitor a single futures contract"""
        try:
            contract = self.futures_contracts[contract_symbol]

            # Get real-time quote (simulated - adapt to actual API)
            quote = await self._get_futures_quote(contract_symbol)

            if quote:
                # Analyze for signals
                signals = await self._analyze_futures_signals(contract, quote)

                # Process any detected signals
                for signal in signals:
                    await self._process_futures_signal(signal)

        except Exception as e:
            self.logger.error(f"Error monitoring {contract_symbol}: {e}")

    @handle_errors()
    async def _get_futures_quote(self, contract_symbol: str) -> Optional[FuturesQuote]:
        """
        Get futures real-time quote using Fubon API.
        Computes the current near-month symbol automatically.
        """
        try:
            from ..api.fubon_client import get_near_month_symbol

            # Compute near-month symbol e.g. 'TXFE6'
            near_month = get_near_month_symbol(contract_symbol)

            await rate_limit_manager.acquire("fubon_db", f"futures_{contract_symbol}")

            quote_data = await self.fubon_client.get_futures_quote(near_month)

            if not quote_data:
                self.logger.debug(f"No quote data for {near_month}")
                return None

            price = quote_data.get('last_price') or quote_data.get('close_price') or Decimal('0')

            return FuturesQuote(
                symbol=contract_symbol,
                price=price,
                volume=int(quote_data.get('volume', 0)),
                timestamp=quote_data.get('timestamp', datetime.now()),
                change_amount=quote_data.get('change'),
                change_percent=quote_data.get('change_percent'),
                high_price=quote_data.get('high_price'),
                low_price=quote_data.get('low_price'),
            )

        except Exception as e:
            self.logger.error(f"Error getting futures quote for {contract_symbol}: {e}")
            return None

    @handle_errors()
    async def _analyze_futures_signals(
        self,
        contract: FuturesContract,
        quote: FuturesQuote
    ) -> List[FuturesSignal]:
        """
        Analyze futures data for trading signals

        Args:
            contract: Futures contract info
            quote: Current quote data

        Returns:
            List of detected signals
        """
        signals = []

        try:
            # 台指期貨專用信號檢測邏輯

            # 大台成交量異常檢測 (TXF)
            if contract.symbol == 'TXF' and quote.volume > 5000:
                signals.append(FuturesSignal(
                    contract_symbol=contract.symbol,
                    signal_type='LONG' if quote.change_amount > 0 else 'SHORT',
                    signal_name='大台成交量暴增',
                    current_price=quote.price,
                    target_price=None,
                    stop_loss=None,
                    confidence=0.7,
                    description=f'大台異常成交量: {quote.volume:,} 口 (正常約1000-3000口)',
                    triggered_at=datetime.now()
                ))

            # 小台成交量異常檢測 (MXF)
            elif contract.symbol == 'MXF' and quote.volume > 8000:
                signals.append(FuturesSignal(
                    contract_symbol=contract.symbol,
                    signal_type='LONG' if quote.change_amount > 0 else 'SHORT',
                    signal_name='小台成交量暴增',
                    current_price=quote.price,
                    target_price=None,
                    stop_loss=None,
                    confidence=0.6,
                    description=f'小台異常成交量: {quote.volume:,} 口 (正常約3000-6000口)',
                    triggered_at=datetime.now()
                ))

            # 微台成交量異常檢測 (MTX)
            elif contract.symbol == 'MTX' and quote.volume > 10000:
                signals.append(FuturesSignal(
                    contract_symbol=contract.symbol,
                    signal_type='LONG' if quote.change_amount > 0 else 'SHORT',
                    signal_name='微台成交量暴增',
                    current_price=quote.price,
                    target_price=None,
                    stop_loss=None,
                    confidence=0.5,
                    description=f'微台異常成交量: {quote.volume:,} 口 (正常約2000-5000口)',
                    triggered_at=datetime.now()
                ))

            # 台指期貨價格突破檢測 (適用所有合約)
            if abs(quote.change_percent) > Decimal('1.5'):  # 台指期貨1.5%突破
                signal_type = 'LONG' if quote.change_percent > 0 else 'SHORT'
                confidence = min(0.9, 0.5 + abs(float(quote.change_percent)) / 10)

                signals.append(FuturesSignal(
                    contract_symbol=contract.symbol,
                    signal_type=signal_type,
                    signal_name='台指期貨價格突破',
                    current_price=quote.price,
                    target_price=None,
                    stop_loss=None,
                    confidence=confidence,
                    description=f'{contract.name} 價格突破: {quote.change_percent:+.2f}% (當前: {quote.price})',
                    triggered_at=datetime.now()
                ))

            # 台指期貨盤中急漲急跌檢測
            if quote.high_price is not None and quote.low_price is not None and quote.high_price > 0 and quote.low_price > 0:
                intraday_range = ((quote.high_price - quote.low_price) / quote.low_price) * 100
                if intraday_range > Decimal('3.0'):  # 當日振幅超過3%
                    signals.append(FuturesSignal(
                        contract_symbol=contract.symbol,
                        signal_type='NEUTRAL',
                        signal_name='台指期貨高波動',
                        current_price=quote.price,
                        target_price=None,
                        stop_loss=None,
                        confidence=0.8,
                        description=f'{contract.name} 當日振幅: {intraday_range:.2f}% (高: {quote.high_price}, 低: {quote.low_price})',
                        triggered_at=datetime.now()
                    ))

            return signals

        except Exception as e:
            self.logger.error(f"Error analyzing futures signals: {e}")
            return []

    @handle_errors()
    async def _process_futures_signal(self, signal: FuturesSignal):
        """
        Process detected futures signal

        Args:
            signal: Detected signal
        """
        try:
            self.logger.info(
                f"Futures signal: {signal.contract_symbol} - {signal.signal_name} "
                f"({signal.signal_type}) @ {signal.current_price}"
            )

            # TODO: Implement signal notification
            # - Send to Telegram bot
            # - Save to database
            # - Trigger automated trading (if enabled)

        except Exception as e:
            self.logger.error(f"Error processing futures signal: {e}")

    def get_contract_info(self, symbol: str) -> Optional[FuturesContract]:
        """Get futures contract information"""
        return self.futures_contracts.get(symbol)

    def get_active_contracts(self) -> List[FuturesContract]:
        """Get list of active futures contracts"""
        return [contract for contract in self.futures_contracts.values() if contract.is_active]

class FuturesAnalyzer:
    """Advanced futures analysis and strategies"""

    def __init__(self):
        self.logger = get_logger(self.__class__.__name__)

    @handle_errors()
    def calculate_basis(self, futures_price: Decimal, spot_price: Decimal) -> Decimal:
        """
        Calculate basis (futures - spot)

        Args:
            futures_price: Futures price
            spot_price: Underlying spot price

        Returns:
            Basis value
        """
        return futures_price - spot_price

    @handle_errors()
    def calculate_fair_value(
        self,
        spot_price: Decimal,
        risk_free_rate: Decimal,
        dividend_yield: Decimal,
        time_to_expiry: float
    ) -> Decimal:
        """
        Calculate theoretical fair value of futures

        Args:
            spot_price: Current spot price
            risk_free_rate: Risk-free interest rate
            dividend_yield: Dividend yield
            time_to_expiry: Time to expiry in years

        Returns:
            Theoretical fair value
        """
        try:
            import math

            # Fair value = S * e^((r-d)*t)
            exponent = (risk_free_rate - dividend_yield) * time_to_expiry
            fair_value = spot_price * Decimal(str(math.exp(float(exponent))))

            return fair_value

        except Exception as e:
            self.logger.error(f"Error calculating fair value: {e}")
            return spot_price

    @handle_errors()
    def detect_arbitrage_opportunities(
        self,
        futures_price: Decimal,
        fair_value: Decimal,
        threshold: Decimal = Decimal('0.5')
    ) -> Optional[Dict[str, any]]:
        """
        Detect arbitrage opportunities

        Args:
            futures_price: Current futures price
            fair_value: Theoretical fair value
            threshold: Minimum price difference for arbitrage

        Returns:
            Arbitrage opportunity details or None
        """
        try:
            price_diff = futures_price - fair_value
            price_diff_pct = (price_diff / fair_value * 100) if fair_value > 0 else Decimal('0')

            if abs(price_diff) > threshold:
                opportunity_type = "Buy Futures, Sell Spot" if price_diff < 0 else "Sell Futures, Buy Spot"

                return {
                    'type': opportunity_type,
                    'price_difference': price_diff,
                    'price_difference_pct': price_diff_pct,
                    'futures_price': futures_price,
                    'fair_value': fair_value,
                    'profit_potential': abs(price_diff)
                }

            return None

        except Exception as e:
            self.logger.error(f"Error detecting arbitrage: {e}")
            return None

    @handle_errors()
    def analyze_term_structure(self, contracts_data: Dict[str, Decimal]) -> Dict[str, any]:
        """
        Analyze futures term structure

        Args:
            contracts_data: Dict mapping contract symbols to prices

        Returns:
            Term structure analysis
        """
        try:
            if len(contracts_data) < 2:
                return {}

            # Sort by expiry (assuming naming convention)
            sorted_contracts = sorted(contracts_data.items())
            prices = [price for _, price in sorted_contracts]

            # Calculate spreads
            spreads = []
            for i in range(len(prices) - 1):
                spread = prices[i + 1] - prices[i]
                spreads.append(spread)

            # Determine market state
            avg_spread = sum(spreads) / len(spreads) if spreads else Decimal('0')

            if avg_spread > Decimal('10'):
                market_state = "Contango"
            elif avg_spread < Decimal('-10'):
                market_state = "Backwardation"
            else:
                market_state = "Neutral"

            return {
                'market_state': market_state,
                'avg_spread': avg_spread,
                'max_spread': max(spreads) if spreads else Decimal('0'),
                'min_spread': min(spreads) if spreads else Decimal('0'),
                'contract_prices': contracts_data
            }

        except Exception as e:
            self.logger.error(f"Error analyzing term structure: {e}")
            return {}

class FuturesRiskManager:
    """Risk management for futures trading"""

    def __init__(self):
        self.logger = get_logger(self.__class__.__name__)

    @handle_errors()
    def calculate_margin_requirements(
        self,
        contract: FuturesContract,
        position_size: int,
        initial_margin_rate: Decimal = Decimal('0.1'),
        maintenance_margin_rate: Decimal = Decimal('0.075')
    ) -> Dict[str, Decimal]:
        """
        Calculate margin requirements

        Args:
            contract: Futures contract
            position_size: Number of contracts
            initial_margin_rate: Initial margin rate
            maintenance_margin_rate: Maintenance margin rate

        Returns:
            Margin requirement details
        """
        try:
            # Get current price (placeholder)
            current_price = Decimal('18000')  # Example price

            notional_value = current_price * contract.contract_size * position_size

            initial_margin = notional_value * initial_margin_rate
            maintenance_margin = notional_value * maintenance_margin_rate

            return {
                'notional_value': notional_value,
                'initial_margin': initial_margin,
                'maintenance_margin': maintenance_margin,
                'leverage': Decimal('1') / initial_margin_rate if initial_margin_rate > 0 else Decimal('0')
            }

        except Exception as e:
            self.logger.error(f"Error calculating margins: {e}")
            return {}

    @handle_errors()
    def calculate_var(
        self,
        position_value: Decimal,
        volatility: Decimal,
        confidence_level: Decimal = Decimal('0.95'),
        time_horizon: int = 1
    ) -> Decimal:
        """
        Calculate Value at Risk (VaR)

        Args:
            position_value: Position value
            volatility: Daily volatility
            confidence_level: Confidence level (0.95 = 95%)
            time_horizon: Time horizon in days

        Returns:
            VaR amount
        """
        try:
            import math
            from scipy import stats

            # Convert confidence level to z-score
            z_score = Decimal(str(abs(stats.norm.ppf((1 - float(confidence_level)) / 2))))

            # Adjust volatility for time horizon
            adjusted_volatility = volatility * Decimal(str(math.sqrt(time_horizon)))

            # Calculate VaR
            var = position_value * adjusted_volatility * z_score

            return var

        except Exception as e:
            self.logger.error(f"Error calculating VaR: {e}")
            return Decimal('0')

    @handle_errors()
    def check_position_limits(
        self,
        current_positions: Dict[str, int],
        max_position_per_contract: int = 100,
        max_total_exposure: Decimal = Decimal('10000000')  # 10M TWD
    ) -> Dict[str, any]:
        """
        Check position limits and risk constraints

        Args:
            current_positions: Dict of contract symbol to position size
            max_position_per_contract: Maximum position per contract
            max_total_exposure: Maximum total exposure

        Returns:
            Position limit check results
        """
        violations = []
        total_exposure = Decimal('0')

        for contract_symbol, position_size in current_positions.items():
            # Check individual position limits
            if abs(position_size) > max_position_per_contract:
                violations.append({
                    'type': 'Position Limit',
                    'contract': contract_symbol,
                    'current': position_size,
                    'limit': max_position_per_contract
                })

            # Estimate exposure (placeholder calculation)
            contract_value = Decimal('18000') * 200 * abs(position_size)  # Simplified
            total_exposure += contract_value

        # Check total exposure limit
        if total_exposure > max_total_exposure:
            violations.append({
                'type': 'Total Exposure',
                'current': total_exposure,
                'limit': max_total_exposure
            })

        return {
            'violations': violations,
            'total_exposure': total_exposure,
            'within_limits': len(violations) == 0
        }