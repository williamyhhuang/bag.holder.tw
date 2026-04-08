"""
Technical indicators calculation engine
"""
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from decimal import Decimal
from datetime import date, datetime

import talib

from ..utils.logger import get_logger
from ..utils.error_handler import handle_errors, ApplicationError
from ..database.models import StockPrice, TechnicalIndicator

logger = get_logger(__name__)

class IndicatorCalculator:
    """Technical indicators calculation engine"""

    def __init__(self):
        self.logger = get_logger(self.__class__.__name__)

    @handle_errors(default_return_value={})
    def calculate_all_indicators(
        self,
        price_data: List[StockPrice],
        ma_periods: List[int] = [5, 10, 20, 60],
        rsi_period: int = 14,
        macd_fast: int = 12,
        macd_slow: int = 26,
        macd_signal: int = 9,
        bb_period: int = 20,
        bb_std_dev: float = 2.0
    ) -> Dict[date, Dict[str, Decimal]]:
        """
        Calculate all technical indicators for given price data

        Args:
            price_data: List of StockPrice objects
            ma_periods: Moving average periods
            rsi_period: RSI calculation period
            macd_fast: MACD fast period
            macd_slow: MACD slow period
            macd_signal: MACD signal line period
            bb_period: Bollinger Bands period
            bb_std_dev: Bollinger Bands standard deviation

        Returns:
            Dictionary mapping dates to indicator values
        """
        if not price_data or len(price_data) < max(ma_periods + [rsi_period, macd_slow, bb_period]):
            self.logger.warning(f"Insufficient data for indicator calculation: {len(price_data)} records")
            return {}

        # Convert to pandas DataFrame
        df = self._to_dataframe(price_data)

        if df.empty:
            return {}

        results = {}

        try:
            # Calculate indicators
            ma_data = self._calculate_moving_averages(df, ma_periods)
            rsi_data = self._calculate_rsi(df, rsi_period)
            macd_data = self._calculate_macd(df, macd_fast, macd_slow, macd_signal)
            bb_data = self._calculate_bollinger_bands(df, bb_period, bb_std_dev)
            volume_ma = self._calculate_volume_ma(df, 20)
            high_20 = self._calculate_high_n(df, 20)

            # Combine all indicators by date
            for idx, (i, row) in enumerate(df.iterrows()):
                trade_date = i.date() if hasattr(i, 'date') else i  # convert Timestamp to date

                indicators = {
                    'ma5': ma_data.get('ma5', {}).get(idx),
                    'ma10': ma_data.get('ma10', {}).get(idx),
                    'ma20': ma_data.get('ma20', {}).get(idx),
                    'ma60': ma_data.get('ma60', {}).get(idx),
                    'rsi14': rsi_data.get(idx),
                    'macd': macd_data.get('macd', {}).get(idx),
                    'macd_signal': macd_data.get('signal', {}).get(idx),
                    'macd_histogram': macd_data.get('histogram', {}).get(idx),
                    'bb_upper': bb_data.get('upper', {}).get(idx),
                    'bb_middle': bb_data.get('middle', {}).get(idx),
                    'bb_lower': bb_data.get('lower', {}).get(idx),
                    'volume_ma20': volume_ma.get(idx),
                    'high_20': high_20.get(idx),
                }

                # Convert to Decimal and filter None values
                filtered_indicators = {}
                for key, value in indicators.items():
                    if value is not None and not (isinstance(value, float) and np.isnan(value)):
                        if key == 'volume_ma20':
                            filtered_indicators[key] = int(value) if value > 0 else None
                        else:
                            filtered_indicators[key] = Decimal(str(round(float(value), 4)))

                if filtered_indicators:
                    results[trade_date] = filtered_indicators

            self.logger.info(f"Calculated indicators for {len(results)} dates")
            return results

        except Exception as e:
            self.logger.error(f"Error calculating indicators: {e}")
            raise ApplicationError(f"Indicator calculation failed: {e}")

    def _to_dataframe(self, price_data: List[StockPrice]) -> pd.DataFrame:
        """Convert StockPrice list to pandas DataFrame"""
        data = []
        for price in sorted(price_data, key=lambda x: x.date):
            data.append({
                'date': price.date,
                'open': float(price.open_price),
                'high': float(price.high_price),
                'low': float(price.low_price),
                'close': float(price.close_price),
                'volume': int(price.volume)
            })

        df = pd.DataFrame(data)
        df['date'] = pd.to_datetime(df['date'])
        return df.set_index('date') if not df.empty else df

    def _calculate_moving_averages(self, df: pd.DataFrame, periods: List[int]) -> Dict[str, Dict[int, float]]:
        """Calculate moving averages"""
        results = {}

        for period in periods:
            if len(df) >= period:
                ma_values = talib.SMA(df['close'].values, timeperiod=period)
                results[f'ma{period}'] = {i: val for i, val in enumerate(ma_values) if not np.isnan(val)}

        return results

    def _calculate_rsi(self, df: pd.DataFrame, period: int) -> Dict[int, float]:
        """Calculate RSI"""
        if len(df) >= period:
            rsi_values = talib.RSI(df['close'].values, timeperiod=period)
            return {i: val for i, val in enumerate(rsi_values) if not np.isnan(val)}
        return {}

    def _calculate_macd(self, df: pd.DataFrame, fast: int, slow: int, signal: int) -> Dict[str, Dict[int, float]]:
        """Calculate MACD"""
        if len(df) >= slow:
            macd_line, signal_line, histogram = talib.MACD(
                df['close'].values,
                fastperiod=fast,
                slowperiod=slow,
                signalperiod=signal
            )

            return {
                'macd': {i: val for i, val in enumerate(macd_line) if not np.isnan(val)},
                'signal': {i: val for i, val in enumerate(signal_line) if not np.isnan(val)},
                'histogram': {i: val for i, val in enumerate(histogram) if not np.isnan(val)}
            }
        return {'macd': {}, 'signal': {}, 'histogram': {}}

    def _calculate_bollinger_bands(self, df: pd.DataFrame, period: int, std_dev: float) -> Dict[str, Dict[int, float]]:
        """Calculate Bollinger Bands"""
        if len(df) >= period:
            upper, middle, lower = talib.BBANDS(
                df['close'].values,
                timeperiod=period,
                nbdevup=std_dev,
                nbdevdn=std_dev
            )

            return {
                'upper': {i: val for i, val in enumerate(upper) if not np.isnan(val)},
                'middle': {i: val for i, val in enumerate(middle) if not np.isnan(val)},
                'lower': {i: val for i, val in enumerate(lower) if not np.isnan(val)}
            }
        return {'upper': {}, 'middle': {}, 'lower': {}}

    def _calculate_volume_ma(self, df: pd.DataFrame, period: int) -> Dict[int, float]:
        """Calculate volume moving average"""
        if len(df) >= period:
            volume_ma = talib.SMA(df['volume'].values.astype(float), timeperiod=period)
            return {i: val for i, val in enumerate(volume_ma) if not np.isnan(val)}
        return {}

    def _calculate_high_n(self, df: pd.DataFrame, period: int) -> Dict[int, float]:
        """Calculate rolling N-period highest close price"""
        if len(df) >= period:
            high_n = talib.MAX(df['close'].values, timeperiod=period)
            return {i: val for i, val in enumerate(high_n) if not np.isnan(val)}
        return {}

class SignalDetector:
    """Signal detection based on technical indicators"""

    def __init__(self):
        self.logger = get_logger(self.__class__.__name__)

    def detect_signals(
        self,
        current_indicators: Dict[str, Decimal],
        previous_indicators: Dict[str, Decimal],
        current_price: Decimal,
        volume: int
    ) -> List[Dict[str, any]]:
        """
        Detect buy/sell signals based on technical indicators

        Args:
            current_indicators: Current period indicators
            previous_indicators: Previous period indicators
            current_price: Current stock price
            volume: Current volume

        Returns:
            List of detected signals
        """
        signals = []

        try:
            # Golden Cross (MA5 crosses above MA20)
            if self._check_golden_cross(current_indicators, previous_indicators):
                signals.append({
                    'type': 'BUY',
                    'name': 'Golden Cross',
                    'description': 'MA5 突破 MA20 向上',
                    'strength': 'MEDIUM',
                    'price': current_price
                })

            # Death Cross (MA5 crosses below MA20)
            if self._check_death_cross(current_indicators, previous_indicators):
                signals.append({
                    'type': 'SELL',
                    'name': 'Death Cross',
                    'description': 'MA5 跌破 MA20 向下',
                    'strength': 'MEDIUM',
                    'price': current_price
                })

            # RSI Oversold
            if self._check_rsi_oversold(current_indicators):
                signals.append({
                    'type': 'BUY',
                    'name': 'RSI Oversold',
                    'description': 'RSI 低於 30，超賣訊號',
                    'strength': 'STRONG',
                    'price': current_price
                })

            # RSI Overbought
            if self._check_rsi_overbought(current_indicators):
                signals.append({
                    'type': 'SELL',
                    'name': 'RSI Overbought',
                    'description': 'RSI 高於 70，超買訊號',
                    'strength': 'STRONG',
                    'price': current_price
                })

            # MACD Golden Cross
            if self._check_macd_golden_cross(current_indicators, previous_indicators):
                signals.append({
                    'type': 'BUY',
                    'name': 'MACD Golden Cross',
                    'description': 'MACD 線突破訊號線向上',
                    'strength': 'STRONG',
                    'price': current_price
                })

            # MACD Death Cross
            if self._check_macd_death_cross(current_indicators, previous_indicators):
                signals.append({
                    'type': 'SELL',
                    'name': 'MACD Death Cross',
                    'description': 'MACD 線跌破訊號線向下',
                    'strength': 'STRONG',
                    'price': current_price
                })

            # Bollinger Bands Squeeze Break
            if self._check_bb_squeeze_break(current_indicators, current_price):
                signals.append({
                    'type': 'BUY',
                    'name': 'BB Squeeze Break',
                    'description': '突破布林通道上軌',
                    'strength': 'MEDIUM',
                    'price': current_price
                })

            # Volume Surge
            if self._check_volume_surge(current_indicators, volume):
                signals.append({
                    'type': 'WATCH',
                    'name': 'Volume Surge',
                    'description': '成交量異常放大',
                    'strength': 'LOW',
                    'price': current_price
                })

            # MA Trend Breakout: 多頭排列（MA5>MA20>MA60）且突破近 20 日新高
            if self._check_ma_trend_breakout(current_indicators, previous_indicators, current_price):
                signals.append({
                    'type': 'BUY',
                    'name': 'MA Trend Breakout',
                    'description': 'MA5>MA20>MA60 多頭排列且突破近 20 日新高',
                    'strength': 'STRONG',
                    'price': current_price
                })

            # MACD Zero Cross: MACD 在零軸上方發生黃金交叉（趨勢確認）
            if self._check_macd_zero_cross(current_indicators, previous_indicators):
                signals.append({
                    'type': 'BUY',
                    'name': 'MACD Zero Cross',
                    'description': 'MACD 零軸上方黃金交叉，趨勢強勢確認',
                    'strength': 'STRONG',
                    'price': current_price
                })

            return signals

        except Exception as e:
            self.logger.error(f"Error detecting signals: {e}")
            return []

    def _check_golden_cross(self, current: Dict[str, Decimal], previous: Dict[str, Decimal]) -> bool:
        """Check for golden cross signal"""
        try:
            curr_ma5 = current.get('ma5')
            curr_ma20 = current.get('ma20')
            prev_ma5 = previous.get('ma5')
            prev_ma20 = previous.get('ma20')

            if all([curr_ma5, curr_ma20, prev_ma5, prev_ma20]):
                # Current MA5 > MA20 and Previous MA5 <= MA20
                return curr_ma5 > curr_ma20 and prev_ma5 <= prev_ma20

            return False
        except Exception:
            return False

    def _check_death_cross(self, current: Dict[str, Decimal], previous: Dict[str, Decimal]) -> bool:
        """Check for death cross signal"""
        try:
            curr_ma5 = current.get('ma5')
            curr_ma20 = current.get('ma20')
            prev_ma5 = previous.get('ma5')
            prev_ma20 = previous.get('ma20')

            if all([curr_ma5, curr_ma20, prev_ma5, prev_ma20]):
                # Current MA5 < MA20 and Previous MA5 >= MA20
                return curr_ma5 < curr_ma20 and prev_ma5 >= prev_ma20

            return False
        except Exception:
            return False

    def _check_rsi_oversold(self, current: Dict[str, Decimal]) -> bool:
        """Check for RSI oversold condition"""
        rsi = current.get('rsi14')
        return rsi is not None and rsi < Decimal('30')

    def _check_rsi_overbought(self, current: Dict[str, Decimal]) -> bool:
        """Check for RSI overbought condition"""
        rsi = current.get('rsi14')
        return rsi is not None and rsi > Decimal('70')

    def _check_macd_golden_cross(self, current: Dict[str, Decimal], previous: Dict[str, Decimal]) -> bool:
        """Check for MACD golden cross"""
        try:
            curr_macd = current.get('macd')
            curr_signal = current.get('macd_signal')
            prev_macd = previous.get('macd')
            prev_signal = previous.get('macd_signal')

            if all([curr_macd, curr_signal, prev_macd, prev_signal]):
                return curr_macd > curr_signal and prev_macd <= prev_signal

            return False
        except Exception:
            return False

    def _check_macd_death_cross(self, current: Dict[str, Decimal], previous: Dict[str, Decimal]) -> bool:
        """Check for MACD death cross"""
        try:
            curr_macd = current.get('macd')
            curr_signal = current.get('macd_signal')
            prev_macd = previous.get('macd')
            prev_signal = previous.get('macd_signal')

            if all([curr_macd, curr_signal, prev_macd, prev_signal]):
                return curr_macd < curr_signal and prev_macd >= prev_signal

            return False
        except Exception:
            return False

    def _check_bb_squeeze_break(self, current: Dict[str, Decimal], price: Decimal) -> bool:
        """Check for Bollinger Bands squeeze breakout"""
        bb_upper = current.get('bb_upper')
        return bb_upper is not None and price > bb_upper

    def _check_volume_surge(self, current: Dict[str, Decimal], volume: int) -> bool:
        """Check for volume surge"""
        volume_ma20 = current.get('volume_ma20')
        if volume_ma20 is not None:
            return volume > volume_ma20 * Decimal('2')  # 2x average volume
        return False

    def _check_ma_trend_breakout(
        self,
        current: Dict[str, Decimal],
        previous: Dict[str, Decimal],
        price: Decimal,
    ) -> bool:
        """MA Trend Breakout: 多頭排列（MA5>MA20>MA60）且收盤突破昨日近 20 日收盤新高。

        Logic:
        - MA5 > MA20 > MA60 ensures all three timeframes are bullish.
        - price > previous high_20 means today's close breaks out of the prior
          20-day range, avoiding look-ahead bias (we use yesterday's high_20).
        """
        try:
            ma5 = current.get('ma5')
            ma20 = current.get('ma20')
            ma60 = current.get('ma60')
            prev_high20 = previous.get('high_20')

            if any(v is None for v in [ma5, ma20, ma60, prev_high20]):
                return False

            return ma5 > ma20 > ma60 and price > prev_high20
        except Exception:
            return False

    def _check_macd_zero_cross(
        self,
        current: Dict[str, Decimal],
        previous: Dict[str, Decimal],
    ) -> bool:
        """MACD Zero Cross: MACD 線在零軸上方發生黃金交叉。

        Standard MACD Golden Cross (MACD crosses above Signal line) filtered
        by requiring MACD > 0, confirming the underlying trend is already bullish.
        This eliminates crossovers that happen in negative territory (often
        dead-cat bounces or early recovery attempts with weak momentum).
        """
        try:
            curr_macd = current.get('macd')
            curr_signal = current.get('macd_signal')
            prev_macd = previous.get('macd')
            prev_signal = previous.get('macd_signal')

            if any(v is None for v in [curr_macd, curr_signal, prev_macd, prev_signal]):
                return False

            golden_cross = curr_macd > curr_signal and prev_macd <= prev_signal
            above_zero = curr_macd > Decimal('0')
            return golden_cross and above_zero
        except Exception:
            return False