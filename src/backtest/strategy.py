"""
Trading strategy implementation for backtesting
"""
from datetime import date, timedelta
from decimal import Decimal
from typing import List, Dict, Optional, Set, Tuple

from .models import StockData, TradingSignal, TechnicalIndicators, SignalType
from ..indicators.calculator import IndicatorCalculator, SignalDetector
from ..utils.logger import get_logger

logger = get_logger(__name__)


class TechnicalStrategy:
    """Technical analysis strategy using existing indicator logic"""

    # P1 (2026-04-08): Restored Golden Cross + MACD Golden Cross.
    # Filter diagnosis showed disabling them degraded return by -5.90%.
    # Despite low win rates (22-32%), their position timing had positive portfolio effect.
    DEFAULT_DISABLED_SIGNALS: list = []

    # Signals that use trend-following logic (skip MA alignment filter)
    TREND_SIGNAL_NAMES: List[str] = [
        "Donchian Breakout",
        "Golden Cross",
        "MACD Golden Cross",
    ]

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
        donchian_period: int = 20,
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
        self.donchian_period = donchian_period

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

                # P3-B/A: RSI Momentum Loss — RSI crosses below 50 (trend losing momentum)
                # Faster than MACD Death Cross; signals early trend reversal for exit
                curr_rsi = current_indicators.rsi14
                prev_rsi = previous_indicators.rsi14
                if (curr_rsi is not None and prev_rsi is not None
                        and curr_rsi < Decimal('50') and prev_rsi >= Decimal('50')):
                    detected_signals.append({
                        'type': 'SELL',
                        'name': 'RSI Momentum Loss',
                        'description': f'RSI 跌破 50（{float(curr_rsi):.1f}），趨勢動能衰退',
                        'strength': 'MEDIUM',
                        'price': current_price_data.close_price,
                    })

                # P6: Donchian Channel Breakout (trend-following signal)
                # Close > highest high of last donchian_period trading dates → upside breakout
                if self.donchian_period > 0 and i >= self.donchian_period:
                    lookback_dates = sorted_dates[i - self.donchian_period: i]
                    donchian_high = max(
                        (price_lookup[d].high_price for d in lookback_dates if d in price_lookup),
                        default=None,
                    )
                    if donchian_high is not None and current_price_data.close_price > donchian_high:
                        detected_signals.append({
                            'type': 'BUY',
                            'name': 'Donchian Breakout',
                            'description': f'收盤突破近 {self.donchian_period} 日最高（{donchian_high}）',
                            'strength': 'STRONG',
                            'price': current_price_data.close_price,
                        })

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
        # Skipped for trend signals (Donchian Breakout / Golden Cross / MACD GC): the breakout
        # itself is the trend confirmation; requiring prior MA alignment would block early entries.
        if signal_name not in self.TREND_SIGNAL_NAMES:
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

    def build_momentum_rankings(
        self,
        stock_data_dict: Dict[str, List[StockData]],
        lookback_days: int = 20,
        top_n: int = 50,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> Dict[date, Set[str]]:
        """Build a daily top-N momentum whitelist from historical price data.

        For each trading date in [start_date, end_date], rank all stocks by their
        lookback_days price return (close[t] / close[t-lookback_days] - 1) and
        return the set of symbols that rank in the top_n.

        Stocks without enough history to compute the lookback return are excluded
        from consideration (not promoted to top-N by default).

        Args:
            stock_data_dict: Symbol → list of StockData (sorted by date ascending).
            lookback_days:   Number of calendar days to look back when computing
                             momentum (default 20 ≈ 1 trading month).
            top_n:           Maximum number of symbols allowed per day (0 = no limit).
            start_date:      First date to include in the output dict.
            end_date:        Last date to include in the output dict.

        Returns:
            Dict mapping each trading date to a set of the top_n symbol strings.
        """
        if top_n <= 0:
            return {}

        # Build per-symbol price lookups: {symbol: {date: close_price}}
        price_lookup: Dict[str, Dict[date, Decimal]] = {}
        for symbol, records in stock_data_dict.items():
            price_lookup[symbol] = {r.date: r.close_price for r in records}

        # Collect all unique trading dates across the universe
        all_dates: Set[date] = set()
        for records in stock_data_dict.values():
            for r in records:
                all_dates.add(r.date)

        # Filter to the requested range
        if start_date:
            all_dates = {d for d in all_dates if d >= start_date}
        if end_date:
            all_dates = {d for d in all_dates if d <= end_date}

        whitelist: Dict[date, Set[str]] = {}

        for target_date in sorted(all_dates):
            lookback_target = target_date - timedelta(days=lookback_days)

            momentum_scores: Dict[str, float] = {}
            for symbol, prices in price_lookup.items():
                current_close = prices.get(target_date)
                if current_close is None:
                    continue  # symbol not traded on this date

                # Find the closest available date on or before the lookback target
                past_dates = [d for d in prices if d <= lookback_target]
                if not past_dates:
                    continue  # not enough history

                past_close = prices[max(past_dates)]
                if past_close == 0:
                    continue

                momentum = float(current_close / past_close) - 1.0
                momentum_scores[symbol] = momentum

            # Rank by momentum descending, keep top_n
            ranked = sorted(momentum_scores, key=lambda s: momentum_scores[s], reverse=True)
            whitelist[target_date] = set(ranked[:top_n])

        self.logger.info(
            f"Built momentum rankings for {len(whitelist)} dates "
            f"(lookback={lookback_days}d, top_n={top_n})"
        )
        return whitelist