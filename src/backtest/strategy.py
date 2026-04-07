"""
Trading strategy implementation for backtesting
"""
from datetime import date
from decimal import Decimal
from typing import List, Dict, Optional, Tuple

from .models import StockData, TradingSignal, TechnicalIndicators, SignalType
from ..indicators.calculator import IndicatorCalculator, SignalDetector
from ..utils.logger import get_logger

logger = get_logger(__name__)


class TechnicalStrategy:
    """Technical analysis strategy using existing indicator logic"""

    # Signals disabled based on backtest results:
    #   - MACD Golden Cross: 13-17% win rate across multiple runs
    #   - Golden Cross (MA5 > MA20): 0% in Q4-2025, 45.5% in Q1-2026 — consistently < 50%
    DEFAULT_DISABLED_SIGNALS = ['MACD Golden Cross', 'Golden Cross']

    def __init__(
        self,
        ma_periods: List[int] = [5, 10, 20, 60],
        rsi_period: int = 14,
        macd_fast: int = 12,
        macd_slow: int = 26,
        macd_signal: int = 9,
        bb_period: int = 20,
        bb_std_dev: float = 2.0,
        disabled_signals: Optional[List[str]] = None,
        require_ma60_uptrend: bool = True,
        require_volume_confirmation: bool = True,
        volume_confirmation_multiplier: float = 1.5,
        rsi_overbought_threshold: float = 70.0,
        rsi_min_entry: float = 50.0,
    ):
        self.ma_periods = ma_periods
        self.rsi_period = rsi_period
        self.macd_fast = macd_fast
        self.macd_slow = macd_slow
        self.macd_signal = macd_signal
        self.bb_period = bb_period
        self.bb_std_dev = bb_std_dev

        # Buy-signal quality filters (evidence-based from backtests)
        self.disabled_signals: List[str] = (
            disabled_signals if disabled_signals is not None
            else self.DEFAULT_DISABLED_SIGNALS
        )
        self.require_ma60_uptrend = require_ma60_uptrend
        self.require_volume_confirmation = require_volume_confirmation
        self.volume_confirmation_multiplier = Decimal(str(volume_confirmation_multiplier))
        self.rsi_overbought_threshold = Decimal(str(rsi_overbought_threshold))
        self.rsi_min_entry = Decimal(str(rsi_min_entry))

        self.indicator_calculator = IndicatorCalculator()
        self.signal_detector = SignalDetector()
        self.logger = get_logger(self.__class__.__name__)

        # Strategy state
        self.indicators_cache: Dict[str, Dict[date, TechnicalIndicators]] = {}

    def prepare_price_data(self, stock_data: List[StockData]) -> List:
        """Convert StockData to format compatible with IndicatorCalculator"""
        # Create mock StockPrice objects for indicator calculation
        from ..database.models import StockPrice

        price_objects = []
        for data in stock_data:
            # Create a mock object with required attributes
            class MockStockPrice:
                def __init__(self, stock_data: StockData):
                    self.date = stock_data.date
                    self.open_price = stock_data.open_price
                    self.high_price = stock_data.high_price
                    self.low_price = stock_data.low_price
                    self.close_price = stock_data.close_price
                    self.volume = stock_data.volume

            price_objects.append(MockStockPrice(data))

        return price_objects

    def calculate_indicators(self, symbol: str, price_data: List[StockData]) -> Dict[date, TechnicalIndicators]:
        """
        Calculate technical indicators for a stock

        Args:
            symbol: Stock symbol
            price_data: List of stock price data

        Returns:
            Dictionary mapping dates to TechnicalIndicators
        """
        if symbol in self.indicators_cache:
            return self.indicators_cache[symbol]

        try:
            # Prepare data for indicator calculation
            prepared_data = self.prepare_price_data(price_data)

            if len(prepared_data) < max(self.ma_periods + [self.rsi_period, self.macd_slow, self.bb_period]):
                self.logger.warning(f"Insufficient data for {symbol}: {len(prepared_data)} records")
                return {}

            # Calculate indicators using existing logic
            indicators_data = self.indicator_calculator.calculate_all_indicators(
                price_data=prepared_data,
                ma_periods=self.ma_periods,
                rsi_period=self.rsi_period,
                macd_fast=self.macd_fast,
                macd_slow=self.macd_slow,
                macd_signal=self.macd_signal,
                bb_period=self.bb_period,
                bb_std_dev=self.bb_std_dev
            )

            # Convert to TechnicalIndicators objects
            result = {}
            for trade_date, indicators in indicators_data.items():
                result[trade_date] = TechnicalIndicators(
                    date=trade_date,
                    ma5=indicators.get('ma5'),
                    ma10=indicators.get('ma10'),
                    ma20=indicators.get('ma20'),
                    ma60=indicators.get('ma60'),
                    rsi14=indicators.get('rsi14'),
                    macd=indicators.get('macd'),
                    macd_signal=indicators.get('macd_signal'),
                    macd_histogram=indicators.get('macd_histogram'),
                    bb_upper=indicators.get('bb_upper'),
                    bb_middle=indicators.get('bb_middle'),
                    bb_lower=indicators.get('bb_lower'),
                    volume_ma20=indicators.get('volume_ma20')
                )

            self.indicators_cache[symbol] = result
            self.logger.info(f"Calculated indicators for {symbol}: {len(result)} dates")
            return result

        except Exception as e:
            self.logger.error(f"Error calculating indicators for {symbol}: {e}")
            return {}

    def convert_indicators_to_dict(self, indicators: TechnicalIndicators) -> Dict[str, Decimal]:
        """Convert TechnicalIndicators object to dictionary format for SignalDetector"""
        result = {}

        if indicators.ma5 is not None:
            result['ma5'] = indicators.ma5
        if indicators.ma10 is not None:
            result['ma10'] = indicators.ma10
        if indicators.ma20 is not None:
            result['ma20'] = indicators.ma20
        if indicators.ma60 is not None:
            result['ma60'] = indicators.ma60
        if indicators.rsi14 is not None:
            result['rsi14'] = indicators.rsi14
        if indicators.macd is not None:
            result['macd'] = indicators.macd
        if indicators.macd_signal is not None:
            result['macd_signal'] = indicators.macd_signal
        if indicators.macd_histogram is not None:
            result['macd_histogram'] = indicators.macd_histogram
        if indicators.bb_upper is not None:
            result['bb_upper'] = indicators.bb_upper
        if indicators.bb_middle is not None:
            result['bb_middle'] = indicators.bb_middle
        if indicators.bb_lower is not None:
            result['bb_lower'] = indicators.bb_lower
        if indicators.volume_ma20 is not None:
            result['volume_ma20'] = indicators.volume_ma20

        return result

    def generate_signals(
        self,
        symbol: str,
        price_data: List[StockData],
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> List[TradingSignal]:
        """
        Generate trading signals for a stock

        Args:
            symbol: Stock symbol
            price_data: List of stock price data
            start_date: Start date for signal generation
            end_date: End date for signal generation

        Returns:
            List of trading signals
        """
        signals = []

        try:
            # Calculate indicators
            indicators_data = self.calculate_indicators(symbol, price_data)
            if not indicators_data:
                return signals

            # Create price lookup
            price_lookup = {data.date: data for data in price_data}

            # Sort dates for chronological processing
            sorted_dates = sorted(indicators_data.keys())

            for i, current_date in enumerate(sorted_dates):
                # Skip if outside date range
                if start_date and current_date < start_date:
                    continue
                if end_date and current_date > end_date:
                    break

                # Need at least one previous date for signal detection
                if i == 0:
                    continue

                current_indicators = indicators_data[current_date]
                previous_indicators = indicators_data[sorted_dates[i-1]]

                # Get current price data
                if current_date not in price_lookup:
                    continue

                current_price_data = price_lookup[current_date]

                # Convert to format for SignalDetector
                current_dict = self.convert_indicators_to_dict(current_indicators)
                previous_dict = self.convert_indicators_to_dict(previous_indicators)

                # Detect signals using existing logic
                detected_signals = self.signal_detector.detect_signals(
                    current_indicators=current_dict,
                    previous_indicators=previous_dict,
                    current_price=current_price_data.close_price,
                    volume=current_price_data.volume
                )

                # Convert to TradingSignal objects, applying buy-quality filters
                for signal_data in detected_signals:
                    signal_type = self.map_signal_type(signal_data['type'])

                    # Apply filters only to BUY signals
                    if signal_type == SignalType.BUY:
                        signal_type = self._apply_buy_filters(
                            signal_name=signal_data['name'],
                            price=current_price_data.close_price,
                            volume=current_price_data.volume,
                            indicators=current_indicators,
                        )

                    trading_signal = TradingSignal(
                        symbol=symbol,
                        date=current_date,
                        signal_type=signal_type,
                        signal_name=signal_data['name'],
                        price=current_price_data.close_price,
                        description=signal_data['description'],
                        strength=signal_data['strength'],
                        indicators=current_indicators
                    )

                    signals.append(trading_signal)

            self.logger.info(f"Generated {len(signals)} signals for {symbol}")
            return signals

        except Exception as e:
            self.logger.error(f"Error generating signals for {symbol}: {e}")
            return []

    def _apply_buy_filters(
        self,
        signal_name: str,
        price: Decimal,
        volume: int,
        indicators: TechnicalIndicators,
    ) -> SignalType:
        """Apply quality filters to a BUY signal.

        Returns SignalType.BUY if all checks pass, SignalType.WATCH otherwise.
        Degrading to WATCH keeps the signal in reports for analysis without
        triggering actual trades.

        Filters (all evidence-based from backtests):
        1. Disabled signals list  — MACD Golden Cross / Golden Cross: win rate < 50%
        2. MA60 uptrend check     — price must be above MA60 (long-term trend)
        3. Volume confirmation     — today's volume > 1.5× MA20 volume
        4. MA alignment check     — MA5 > MA10 > MA20 (short/mid trend must be bullish)
        5. RSI momentum check     — RSI >= rsi_min_entry (avoid entering on false breakouts
                                    when momentum is weak; BB Squeeze Break had 44.8% win
                                    rate in Q4-2025 without this filter)
        """
        # Filter 1: disabled signals (poor historical win rate)
        if signal_name in self.disabled_signals:
            self.logger.debug(f"Signal '{signal_name}' is disabled → WATCH")
            return SignalType.WATCH

        # Filter 2: price above MA60 (stock in long-term uptrend)
        if self.require_ma60_uptrend:
            ma60 = indicators.ma60
            if ma60 is not None and price < ma60:
                self.logger.debug(
                    f"Signal '{signal_name}' blocked: price {price} < MA60 {ma60} → WATCH"
                )
                return SignalType.WATCH

        # Filter 3: volume confirmation (avoid low-liquidity breakouts)
        if self.require_volume_confirmation:
            volume_ma20 = indicators.volume_ma20
            if volume_ma20 is not None and volume_ma20 > 0:
                if Decimal(str(volume)) < Decimal(str(volume_ma20)) * self.volume_confirmation_multiplier:
                    self.logger.debug(
                        f"Signal '{signal_name}' blocked: volume {volume} < "
                        f"{self.volume_confirmation_multiplier}× MA20 {volume_ma20} → WATCH"
                    )
                    return SignalType.WATCH

        # Filter 4: MA alignment — MA5 > MA10 > MA20 ensures short AND mid-term trend is bullish.
        # Prevents entering on a single-day spike above upper BB when the underlying trend is weak.
        ma5 = indicators.ma5
        ma10 = indicators.ma10
        ma20 = indicators.ma20
        if ma5 is not None and ma10 is not None and ma20 is not None:
            if not (ma5 > ma10 > ma20):
                self.logger.debug(
                    f"Signal '{signal_name}' blocked: MA alignment failed "
                    f"(MA5={ma5}, MA10={ma10}, MA20={ma20}) → WATCH"
                )
                return SignalType.WATCH

        # Filter 5: RSI momentum confirmation.
        # Require RSI >= rsi_min_entry (default 50) to ensure the stock has upward momentum.
        # A BB breakout with weak RSI (< 50) is typically a false breakout or dead-cat bounce.
        # Evidence: BB Squeeze Break win rate dropped from 54.1% (Q1-2026) to 44.8% (Q4-2025);
        # adding this filter aims to reject low-momentum breakouts that quickly reverse.
        if self.rsi_min_entry > 0:
            rsi = indicators.rsi14
            if rsi is not None and rsi < self.rsi_min_entry:
                self.logger.debug(
                    f"Signal '{signal_name}' blocked: RSI {rsi} < min entry "
                    f"{self.rsi_min_entry} → WATCH"
                )
                return SignalType.WATCH

        return SignalType.BUY

    def map_signal_type(self, signal_type_str: str) -> SignalType:
        """Map string signal type to SignalType enum"""
        mapping = {
            'BUY': SignalType.BUY,
            'SELL': SignalType.SELL,
            'WATCH': SignalType.WATCH
        }
        return mapping.get(signal_type_str, SignalType.WATCH)

    def generate_signals_for_multiple_stocks(
        self,
        stock_data_dict: Dict[str, List[StockData]],
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> List[TradingSignal]:
        """
        Generate trading signals for multiple stocks

        Args:
            stock_data_dict: Dictionary mapping symbols to price data
            start_date: Start date for signal generation
            end_date: End date for signal generation

        Returns:
            List of trading signals for all stocks
        """
        all_signals = []
        total_stocks = len(stock_data_dict)

        self.logger.info(f"Generating signals for {total_stocks} stocks")

        for i, (symbol, price_data) in enumerate(stock_data_dict.items(), 1):
            self.logger.info(f"Processing {symbol} ({i}/{total_stocks})")

            signals = self.generate_signals(symbol, price_data, start_date, end_date)
            all_signals.extend(signals)

        self.logger.info(f"Generated {len(all_signals)} total signals")
        return all_signals

    def get_signal_summary(self, signals: List[TradingSignal]) -> Dict:
        """
        Get summary statistics of generated signals

        Args:
            signals: List of trading signals

        Returns:
            Dictionary with signal summary
        """
        summary = {
            'total_signals': len(signals),
            'buy_signals': len([s for s in signals if s.signal_type == SignalType.BUY]),
            'sell_signals': len([s for s in signals if s.signal_type == SignalType.SELL]),
            'watch_signals': len([s for s in signals if s.signal_type == SignalType.WATCH]),
            'signals_by_name': {},
            'signals_by_symbol': {},
            'date_range': None
        }

        if signals:
            # Count by signal name
            for signal in signals:
                name = signal.signal_name
                if name not in summary['signals_by_name']:
                    summary['signals_by_name'][name] = 0
                summary['signals_by_name'][name] += 1

            # Count by symbol
            for signal in signals:
                symbol = signal.symbol
                if symbol not in summary['signals_by_symbol']:
                    summary['signals_by_symbol'][symbol] = 0
                summary['signals_by_symbol'][symbol] += 1

            # Date range
            dates = [s.date for s in signals]
            summary['date_range'] = {
                'start': min(dates),
                'end': max(dates)
            }

        return summary

    def filter_signals(
        self,
        signals: List[TradingSignal],
        signal_types: Optional[List[SignalType]] = None,
        signal_names: Optional[List[str]] = None,
        symbols: Optional[List[str]] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> List[TradingSignal]:
        """
        Filter signals based on various criteria

        Args:
            signals: List of trading signals
            signal_types: Filter by signal types
            signal_names: Filter by signal names
            symbols: Filter by symbols
            start_date: Filter by start date
            end_date: Filter by end date

        Returns:
            Filtered list of trading signals
        """
        filtered = signals

        if signal_types:
            filtered = [s for s in filtered if s.signal_type in signal_types]

        if signal_names:
            filtered = [s for s in filtered if s.signal_name in signal_names]

        if symbols:
            filtered = [s for s in filtered if s.symbol in symbols]

        if start_date:
            filtered = [s for s in filtered if s.date >= start_date]

        if end_date:
            filtered = [s for s in filtered if s.date <= end_date]

        return filtered