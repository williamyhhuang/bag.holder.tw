"""
Signal detector domain service (pure business logic, no external dependencies)
"""
from typing import Dict, List
from decimal import Decimal

from ...utils.logger import get_logger

logger = get_logger(__name__)


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
