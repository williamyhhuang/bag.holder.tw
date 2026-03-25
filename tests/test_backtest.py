"""
Unit tests for backtesting system
"""
import pytest
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import Mock, patch, MagicMock
import os
import sys

# Add src directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.backtest.models import (
    StockData, TradingSignal, TechnicalIndicators,
    SignalType, Position, Portfolio, BacktestResult
)
from src.backtest.data_source import YFinanceDataSource
from src.backtest.engine import BacktestEngine
from src.backtest.strategy import TechnicalStrategy
from src.backtest.analyzer import PerformanceAnalyzer
from src.backtest.reporter import BacktestReporter


class TestStockData:
    """Test StockData model"""

    def test_stock_data_creation(self):
        data = StockData(
            symbol="2330",
            date=date(2025, 9, 1),
            open_price=Decimal('500.0'),
            high_price=Decimal('510.0'),
            low_price=Decimal('495.0'),
            close_price=Decimal('505.0'),
            volume=1000000
        )

        assert data.symbol == "2330"
        assert data.date == date(2025, 9, 1)
        assert data.close_price == Decimal('505.0')
        assert data.volume == 1000000


class TestYFinanceDataSource:
    """Test YFinanceDataSource"""

    def setup_method(self):
        self.data_source = YFinanceDataSource(cache_dir="test_cache")

    def test_initialization(self):
        assert self.data_source.tw_suffix == ".TW"
        assert self.data_source.two_suffix == ".TWO"

    def test_get_taiwan_stock_list(self):
        stocks = self.data_source.get_taiwan_stock_list()
        assert isinstance(stocks, list)
        assert len(stocks) > 0
        assert ("2330", "TSE") in stocks

    @patch('yfinance.Ticker')
    def test_fetch_stock_data_success(self, mock_ticker):
        # Mock yfinance data
        mock_df = Mock()
        mock_df.empty = False
        mock_df.iterrows.return_value = [
            (Mock(date=Mock(return_value=date(2025, 9, 1))), {
                'Open': 500.0, 'High': 510.0, 'Low': 495.0,
                'Close': 505.0, 'Volume': 1000000
            })
        ]

        mock_ticker_instance = Mock()
        mock_ticker_instance.history.return_value = mock_df
        mock_ticker.return_value = mock_ticker_instance

        result = self.data_source.fetch_stock_data(
            "2330", date(2025, 9, 1), date(2025, 9, 2)
        )

        assert len(result) == 1
        assert result[0].symbol == "2330"

    @patch('yfinance.Ticker')
    def test_fetch_stock_data_empty(self, mock_ticker):
        # Mock empty data
        mock_df = Mock()
        mock_df.empty = True

        mock_ticker_instance = Mock()
        mock_ticker_instance.history.return_value = mock_df
        mock_ticker.return_value = mock_ticker_instance

        result = self.data_source.fetch_stock_data(
            "INVALID", date(2025, 9, 1), date(2025, 9, 2)
        )

        assert len(result) == 0

    def teardown_method(self):
        # Clean up test cache
        import shutil
        if os.path.exists("test_cache"):
            shutil.rmtree("test_cache")


class TestBacktestEngine:
    """Test BacktestEngine"""

    def setup_method(self):
        self.engine = BacktestEngine(
            initial_capital=Decimal('100000'),
            position_sizing=Decimal('0.2')  # 20% per position
        )

    def test_initialization(self):
        assert self.engine.initial_capital == Decimal('100000')
        assert self.engine.cash == Decimal('100000')
        assert len(self.engine.positions) == 0

    def test_add_price_data(self):
        stock_data = [
            StockData(
                symbol="TEST",
                date=date(2025, 9, 1),
                open_price=Decimal('100'),
                high_price=Decimal('105'),
                low_price=Decimal('95'),
                close_price=Decimal('102'),
                volume=10000
            )
        ]

        self.engine.add_price_data("TEST", stock_data)

        assert "TEST" in self.engine.price_data
        assert date(2025, 9, 1) in self.engine.price_data["TEST"]

    def test_get_current_price(self):
        stock_data = [
            StockData(
                symbol="TEST",
                date=date(2025, 9, 1),
                open_price=Decimal('100'),
                high_price=Decimal('105'),
                low_price=Decimal('95'),
                close_price=Decimal('102'),
                volume=10000
            )
        ]

        self.engine.add_price_data("TEST", stock_data)
        price = self.engine.get_current_price("TEST", date(2025, 9, 1))

        assert price == Decimal('102')

    def test_calculate_position_size(self):
        price = Decimal('100')
        size = self.engine.calculate_position_size(price)

        # 20% of 100,000 = 20,000, divided by 100 = 200 shares, rounded to 1000
        expected_size = 1000  # Minimum 1張 (1000 shares)
        assert size == expected_size

    def test_calculate_trading_costs(self):
        price = Decimal('100')
        quantity = 1000

        # Test buy order
        commission, tax = self.engine.calculate_trading_costs(price, quantity, is_buy=True)
        expected_commission = Decimal('100000') * Decimal('0.001425')

        assert commission == expected_commission.quantize(Decimal('0.01'))
        assert tax == Decimal('0')  # No tax on buying

        # Test sell order
        commission, tax = self.engine.calculate_trading_costs(price, quantity, is_buy=False)
        expected_tax = Decimal('100000') * Decimal('0.003')

        assert tax == expected_tax.quantize(Decimal('0.01'))

    def test_execute_buy_order(self):
        # Add test data
        stock_data = [
            StockData(
                symbol="TEST",
                date=date(2025, 9, 1),
                open_price=Decimal('100'),
                high_price=Decimal('105'),
                low_price=Decimal('95'),
                close_price=Decimal('102'),
                volume=10000
            )
        ]
        self.engine.add_price_data("TEST", stock_data)

        # Create buy signal
        signal = TradingSignal(
            symbol="TEST",
            date=date(2025, 9, 1),
            signal_type=SignalType.BUY,
            signal_name="Test Buy",
            price=Decimal('100'),
            description="Test signal",
            strength="MEDIUM",
            indicators=TechnicalIndicators(date=date(2025, 9, 1))
        )

        initial_cash = self.engine.cash
        success = self.engine.execute_buy_order(signal)

        assert success is True
        assert "TEST" in self.engine.positions
        assert self.engine.cash < initial_cash
        assert len(self.engine.orders) == 1


class TestTechnicalStrategy:
    """Test TechnicalStrategy"""

    def setup_method(self):
        self.strategy = TechnicalStrategy()

    def test_initialization(self):
        assert self.strategy.ma_periods == [5, 10, 20, 60]
        assert self.strategy.rsi_period == 14

    def test_prepare_price_data(self):
        stock_data = [
            StockData(
                symbol="TEST",
                date=date(2025, 9, 1),
                open_price=Decimal('100'),
                high_price=Decimal('105'),
                low_price=Decimal('95'),
                close_price=Decimal('102'),
                volume=10000
            )
        ]

        prepared = self.strategy.prepare_price_data(stock_data)

        assert len(prepared) == 1
        assert hasattr(prepared[0], 'date')
        assert hasattr(prepared[0], 'close_price')

    def test_map_signal_type(self):
        assert self.strategy.map_signal_type('BUY') == SignalType.BUY
        assert self.strategy.map_signal_type('SELL') == SignalType.SELL
        assert self.strategy.map_signal_type('WATCH') == SignalType.WATCH
        assert self.strategy.map_signal_type('INVALID') == SignalType.WATCH


class TestPerformanceAnalyzer:
    """Test PerformanceAnalyzer"""

    def setup_method(self):
        self.analyzer = PerformanceAnalyzer(output_dir="test_output")

    def test_initialization(self):
        assert self.analyzer.output_dir == "test_output"

    def test_analyze_trades_empty(self):
        result = self.analyzer.analyze_trades([])

        assert result['total_trades'] == 0
        assert result['win_rate'] == Decimal('0')

    def test_analyze_trades_with_data(self):
        trades = [
            Position(
                symbol="TEST1",
                quantity=1000,
                entry_price=Decimal('100'),
                entry_date=date(2025, 9, 1),
                current_price=Decimal('110'),
                current_date=date(2025, 9, 5),
                status="CLOSED",
                exit_price=Decimal('110'),
                exit_date=date(2025, 9, 5),
                pnl=Decimal('10000'),
                pnl_percent=Decimal('10'),
                holding_days=4
            ),
            Position(
                symbol="TEST2",
                quantity=1000,
                entry_price=Decimal('100'),
                entry_date=date(2025, 9, 2),
                current_price=Decimal('95'),
                current_date=date(2025, 9, 6),
                status="CLOSED",
                exit_price=Decimal('95'),
                exit_date=date(2025, 9, 6),
                pnl=Decimal('-5000'),
                pnl_percent=Decimal('-5'),
                holding_days=4
            )
        ]

        result = self.analyzer.analyze_trades(trades)

        assert result['total_trades'] == 2
        assert result['winning_trades'] == 1
        assert result['losing_trades'] == 1
        assert result['win_rate'] == Decimal('50.00')

    def teardown_method(self):
        # Clean up test output
        import shutil
        if os.path.exists("test_output"):
            shutil.rmtree("test_output")


class TestBacktestReporter:
    """Test BacktestReporter"""

    def setup_method(self):
        self.reporter = BacktestReporter(output_dir="test_reports")

    def test_initialization(self):
        assert self.reporter.output_dir == "test_reports"

    def test_analyze_signals_empty(self):
        result = self.reporter.analyze_signals([])

        assert result['total_signals'] == 0
        assert result['buy_count'] == 0

    def test_analyze_signals_with_data(self):
        signals = [
            TradingSignal(
                symbol="TEST",
                date=date(2025, 9, 1),
                signal_type=SignalType.BUY,
                signal_name="Test Buy",
                price=Decimal('100'),
                description="Test signal",
                strength="MEDIUM",
                indicators=TechnicalIndicators(date=date(2025, 9, 1))
            ),
            TradingSignal(
                symbol="TEST",
                date=date(2025, 9, 2),
                signal_type=SignalType.SELL,
                signal_name="Test Sell",
                price=Decimal('105'),
                description="Test signal",
                strength="STRONG",
                indicators=TechnicalIndicators(date=date(2025, 9, 2))
            )
        ]

        result = self.reporter.analyze_signals(signals)

        assert result['total_signals'] == 2
        assert result['buy_count'] == 1
        assert result['sell_count'] == 1
        assert result['buy_percentage'] == 50.0

    def teardown_method(self):
        # Clean up test reports
        import shutil
        if os.path.exists("test_reports"):
            shutil.rmtree("test_reports")


class TestIntegration:
    """Integration tests"""

    def test_simple_backtest_flow(self):
        """Test a simple end-to-end backtest flow"""

        # Create test data
        test_data = {
            "TEST": [
                StockData(
                    symbol="TEST",
                    date=date(2025, 9, 1),
                    open_price=Decimal('100'),
                    high_price=Decimal('105'),
                    low_price=Decimal('95'),
                    close_price=Decimal('102'),
                    volume=10000
                ),
                StockData(
                    symbol="TEST",
                    date=date(2025, 9, 2),
                    open_price=Decimal('102'),
                    high_price=Decimal('108'),
                    low_price=Decimal('100'),
                    close_price=Decimal('105'),
                    volume=12000
                )
            ]
        }

        # Create engine and add data
        engine = BacktestEngine(initial_capital=Decimal('100000'))
        for symbol, data in test_data.items():
            engine.add_price_data(symbol, data)

        # Create simple buy signal
        signals = [
            TradingSignal(
                symbol="TEST",
                date=date(2025, 9, 1),
                signal_type=SignalType.BUY,
                signal_name="Test Buy",
                price=Decimal('102'),
                description="Test signal",
                strength="MEDIUM",
                indicators=TechnicalIndicators(date=date(2025, 9, 1))
            )
        ]

        # Run backtest
        result = engine.run_backtest(
            signals,
            date(2025, 9, 1),
            date(2025, 9, 2)
        )

        # Verify results
        assert isinstance(result, BacktestResult)
        assert result.initial_capital == Decimal('100000')
        assert result.start_date == date(2025, 9, 1)
        assert result.end_date == date(2025, 9, 2)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])