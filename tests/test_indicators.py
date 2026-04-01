"""
Test technical indicators calculation
"""
import pytest
from decimal import Decimal
from datetime import date, timedelta

from src.indicators.calculator import IndicatorCalculator, SignalDetector
from src.database.models import StockPrice

class TestIndicatorCalculator:
    """Test technical indicator calculations"""

    @pytest.fixture
    def calculator(self):
        """Create indicator calculator instance"""
        return IndicatorCalculator()

    @pytest.fixture
    def price_data(self):
        """Create test price data"""
        prices = []
        base_price = Decimal('100.0')

        # Create 60 days of price data for proper indicator calculation
        for i in range(60):
            # Simple trending price pattern
            trend = i * Decimal('0.5')
            noise = (i % 5) * Decimal('1.0') - Decimal('2.0')
            close_price = base_price + trend + noise

            price = StockPrice(
                stock_id="test-stock",
                date=date(2025, 1, 1) + timedelta(days=i),
                open_price=close_price - Decimal('1'),
                high_price=close_price + Decimal('2'),
                low_price=close_price - Decimal('2'),
                close_price=close_price,
                volume=1000000 + (i * 10000)
            )
            prices.append(price)

        return prices

    def test_calculate_all_indicators(self, calculator, price_data):
        """Test calculation of all indicators"""
        result = calculator.calculate_all_indicators(price_data)

        assert isinstance(result, dict)
        assert len(result) > 0

        # Check that we have indicators for recent dates
        latest_date = max(result.keys())
        latest_indicators = result[latest_date]

        # Check that basic indicators are calculated
        assert 'ma5' in latest_indicators
        assert 'ma20' in latest_indicators
        assert 'rsi14' in latest_indicators

        # Verify indicator values are reasonable
        assert isinstance(latest_indicators['ma5'], Decimal)
        assert latest_indicators['ma5'] > 0

        if 'rsi14' in latest_indicators:
            assert 0 <= latest_indicators['rsi14'] <= 100

    def test_calculate_with_insufficient_data(self, calculator):
        """Test behavior with insufficient data"""
        # Only 5 days of data
        short_data = []
        for i in range(5):
            price = StockPrice(
                stock_id="test-stock",
                date=date(2025, 1, 1) + timedelta(days=i),
                open_price=Decimal('100'),
                high_price=Decimal('102'),
                low_price=Decimal('98'),
                close_price=Decimal('100'),
                volume=1000000
            )
            short_data.append(price)

        result = calculator.calculate_all_indicators(short_data)

        # Should return empty dict or limited indicators
        assert isinstance(result, dict)

    def test_empty_price_data(self, calculator):
        """Test behavior with empty price data"""
        result = calculator.calculate_all_indicators([])
        assert result == {}

class TestSignalDetector:
    """Test signal detection logic"""

    @pytest.fixture
    def detector(self):
        """Create signal detector instance"""
        return SignalDetector()

    @pytest.fixture
    def sample_indicators_bullish(self):
        """Sample indicators showing bullish signals"""
        current = {
            'ma5': Decimal('105.0'),
            'ma20': Decimal('100.0'),
            'rsi14': Decimal('25.0'),  # Oversold
            'macd': Decimal('1.5'),
            'macd_signal': Decimal('1.0'),
            'bb_upper': Decimal('110.0'),
            'bb_lower': Decimal('90.0')
        }

        previous = {
            'ma5': Decimal('99.0'),    # Was below MA20
            'ma20': Decimal('100.0'),
            'rsi14': Decimal('30.0'),
            'macd': Decimal('0.5'),   # Was below signal
            'macd_signal': Decimal('1.0')
        }

        return current, previous

    @pytest.fixture
    def sample_indicators_bearish(self):
        """Sample indicators showing bearish signals"""
        current = {
            'ma5': Decimal('95.0'),
            'ma20': Decimal('100.0'),
            'rsi14': Decimal('75.0'),  # Overbought
            'macd': Decimal('0.5'),
            'macd_signal': Decimal('1.0'),
            'bb_upper': Decimal('110.0'),
            'bb_lower': Decimal('90.0')
        }

        previous = {
            'ma5': Decimal('101.0'),   # Was above MA20
            'ma20': Decimal('100.0'),
            'rsi14': Decimal('70.0'),
            'macd': Decimal('1.5'),   # Was above signal
            'macd_signal': Decimal('1.0')
        }

        return current, previous

    def test_detect_golden_cross(self, detector, sample_indicators_bullish):
        """Test golden cross detection"""
        current, previous = sample_indicators_bullish

        signals = detector.detect_signals(
            current_indicators=current,
            previous_indicators=previous,
            current_price=Decimal('105.0'),
            volume=1000000
        )

        # Should detect golden cross
        golden_cross_signals = [s for s in signals if s['name'] == 'Golden Cross']
        assert len(golden_cross_signals) > 0

        signal = golden_cross_signals[0]
        assert signal['type'] == 'BUY'
        assert 'MA5' in signal['description']

    def test_detect_death_cross(self, detector, sample_indicators_bearish):
        """Test death cross detection"""
        current, previous = sample_indicators_bearish

        signals = detector.detect_signals(
            current_indicators=current,
            previous_indicators=previous,
            current_price=Decimal('95.0'),
            volume=1000000
        )

        # Should detect death cross
        death_cross_signals = [s for s in signals if s['name'] == 'Death Cross']
        assert len(death_cross_signals) > 0

        signal = death_cross_signals[0]
        assert signal['type'] == 'SELL'

    def test_detect_rsi_oversold(self, detector):
        """Test RSI oversold detection"""
        current = {'rsi14': Decimal('25.0')}
        previous = {'rsi14': Decimal('30.0')}

        signals = detector.detect_signals(
            current_indicators=current,
            previous_indicators=previous,
            current_price=Decimal('100.0'),
            volume=1000000
        )

        oversold_signals = [s for s in signals if s['name'] == 'RSI Oversold']
        assert len(oversold_signals) > 0
        assert oversold_signals[0]['type'] == 'BUY'

    def test_detect_rsi_overbought(self, detector):
        """Test RSI overbought detection"""
        current = {'rsi14': Decimal('75.0')}
        previous = {'rsi14': Decimal('70.0')}

        signals = detector.detect_signals(
            current_indicators=current,
            previous_indicators=previous,
            current_price=Decimal('100.0'),
            volume=1000000
        )

        overbought_signals = [s for s in signals if s['name'] == 'RSI Overbought']
        assert len(overbought_signals) > 0
        assert overbought_signals[0]['type'] == 'SELL'

    def test_detect_volume_surge(self, detector):
        """Test volume surge detection"""
        current = {'volume_ma20': Decimal('500000')}
        previous = {}

        signals = detector.detect_signals(
            current_indicators=current,
            previous_indicators=previous,
            current_price=Decimal('100.0'),
            volume=1200000  # More than 2x average
        )

        volume_signals = [s for s in signals if s['name'] == 'Volume Surge']
        assert len(volume_signals) > 0
        assert volume_signals[0]['type'] == 'WATCH'

    def test_no_signals_on_normal_conditions(self, detector):
        """Test that no signals are generated under normal conditions"""
        current = {
            'ma5': Decimal('100.5'),
            'ma20': Decimal('100.0'),
            'rsi14': Decimal('50.0'),  # Neutral
            'macd': Decimal('0.1'),
            'macd_signal': Decimal('0.1'),
            'volume_ma20': Decimal('1000000')
        }

        previous = {
            'ma5': Decimal('101.0'),  # MA5 already above MA20, no cross
            'ma20': Decimal('100.0'),
            'rsi14': Decimal('50.0'),
            'macd': Decimal('0.1'),
            'macd_signal': Decimal('0.1')
        }

        signals = detector.detect_signals(
            current_indicators=current,
            previous_indicators=previous,
            current_price=Decimal('100.0'),
            volume=1000000  # Normal volume
        )

        # Should have minimal or no signals under normal conditions
        assert len(signals) == 0 or all(s['type'] == 'WATCH' for s in signals)

    def test_empty_indicators(self, detector):
        """Test behavior with empty indicators"""
        signals = detector.detect_signals(
            current_indicators={},
            previous_indicators={},
            current_price=Decimal('100.0'),
            volume=1000000
        )

        assert isinstance(signals, list)
        assert len(signals) == 0