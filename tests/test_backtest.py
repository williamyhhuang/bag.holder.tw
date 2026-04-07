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

    def test_load_from_stocks_dir(self, tmp_path):
        """load_from_stocks_dir should parse per-stock CSVs from data/stocks/"""
        csv_content = (
            "date,open,high,low,close,volume,dividends,stock_splits,capital_gains,symbol\n"
            "2026-03-30 00:00:00+08:00,500.0,510.0,495.0,505.0,1000000,0.0,0.0,0.0,2330.TW\n"
            "2026-03-31 00:00:00+08:00,505.0,515.0,500.0,510.0,1200000,0.0,0.0,0.0,2330.TW\n"
        )
        csv_file = tmp_path / "2330_TW.csv"
        csv_file.write_text(csv_content)

        result = self.data_source.load_from_stocks_dir(str(tmp_path))

        assert "2330" in result
        assert len(result["2330"]) == 2
        assert result["2330"][0].date == date(2026, 3, 30)
        assert result["2330"][0].close_price == Decimal("505.0")
        assert result["2330"][1].date == date(2026, 3, 31)

    def test_load_from_stocks_dir_date_filter(self, tmp_path):
        """load_from_stocks_dir should honour start_date/end_date filters"""
        csv_content = (
            "date,open,high,low,close,volume,dividends,stock_splits,capital_gains,symbol\n"
            "2026-03-28 00:00:00+08:00,490.0,495.0,485.0,492.0,900000,0.0,0.0,0.0,2330.TW\n"
            "2026-03-30 00:00:00+08:00,500.0,510.0,495.0,505.0,1000000,0.0,0.0,0.0,2330.TW\n"
            "2026-03-31 00:00:00+08:00,505.0,515.0,500.0,510.0,1200000,0.0,0.0,0.0,2330.TW\n"
        )
        csv_file = tmp_path / "2330_TW.csv"
        csv_file.write_text(csv_content)

        result = self.data_source.load_from_stocks_dir(
            str(tmp_path),
            start_date=date(2026, 3, 30),
            end_date=date(2026, 3, 30)
        )

        assert "2330" in result
        assert len(result["2330"]) == 1
        assert result["2330"][0].date == date(2026, 3, 30)

    def test_load_from_stocks_dir_empty(self, tmp_path):
        """load_from_stocks_dir should return empty dict when directory has no CSVs"""
        result = self.data_source.load_from_stocks_dir(str(tmp_path))
        assert result == {}

    def teardown_method(self):
        # Clean up test cache
        import shutil
        if os.path.exists("test_cache"):
            shutil.rmtree("test_cache")


class TestBacktestEngine:
    """Test BacktestEngine"""

    def setup_method(self):
        self.engine = BacktestEngine(
            initial_capital=Decimal('200000'),
            position_sizing=Decimal('0.2')  # 20% per position
        )

    def test_initialization(self):
        assert self.engine.initial_capital == Decimal('200000')
        assert self.engine.cash == Decimal('200000')
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
        # Engine: initial_capital=200,000, position_sizing=0.2 → target=40,000
        # price=10: target/price=4000 shares → 4 lots of 1000 → 4000
        price = Decimal('10')
        size = self.engine.calculate_position_size(price)
        assert size == 4000

    def test_calculate_position_size_too_expensive(self):
        # price=50: target=40,000 / 50 = 800 shares → 0 lots → skip
        price = Decimal('50')
        size = self.engine.calculate_position_size(price)
        assert size == 0  # 1 lot (50,000) exceeds 40,000 position limit

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
        # Engine: initial_capital=200,000, position_sizing=0.2 → target=40,000
        # Use price=10: 1 lot=10,000 which fits within 40,000 target
        stock_data = [
            StockData(
                symbol="TEST",
                date=date(2025, 9, 1),
                open_price=Decimal('10'),
                high_price=Decimal('10.5'),
                low_price=Decimal('9.5'),
                close_price=Decimal('10.2'),
                volume=10000
            )
        ]
        self.engine.add_price_data("TEST", stock_data)

        signal = TradingSignal(
            symbol="TEST",
            date=date(2025, 9, 1),
            signal_type=SignalType.BUY,
            signal_name="Test Buy",
            price=Decimal('10'),
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

    def _make_indicators(self, ma60=None, volume_ma20=None):
        return TechnicalIndicators(
            date=date(2025, 9, 1),
            ma60=Decimal(str(ma60)) if ma60 is not None else None,
            volume_ma20=volume_ma20,
        )

    def test_disabled_signal_becomes_watch(self):
        """MACD Golden Cross should be demoted to WATCH (disabled by default)."""
        result = self.strategy._apply_buy_filters(
            signal_name='MACD Golden Cross',
            price=Decimal('100'),
            volume=200000,
            indicators=self._make_indicators(ma60=80, volume_ma20=100000),
        )
        assert result == SignalType.WATCH

    def test_price_below_ma60_becomes_watch(self):
        """BUY signal should be blocked when price is below MA60."""
        result = self.strategy._apply_buy_filters(
            signal_name='BB Squeeze Break',
            price=Decimal('50'),
            volume=200000,
            indicators=self._make_indicators(ma60=60, volume_ma20=100000),
        )
        assert result == SignalType.WATCH

    def test_low_volume_becomes_watch(self):
        """BUY signal should be blocked when volume < 1.5× MA20 volume."""
        result = self.strategy._apply_buy_filters(
            signal_name='BB Squeeze Break',
            price=Decimal('100'),
            volume=100000,                                  # only 1× MA20
            indicators=self._make_indicators(ma60=80, volume_ma20=100000),
        )
        assert result == SignalType.WATCH

    def test_valid_buy_passes_all_filters(self):
        """BUY signal that passes all checks should remain BUY."""
        result = self.strategy._apply_buy_filters(
            signal_name='BB Squeeze Break',
            price=Decimal('100'),
            volume=200000,                                  # 2× MA20 > 1.5×
            indicators=self._make_indicators(ma60=80, volume_ma20=100000),
        )
        assert result == SignalType.BUY


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

    def test_analyze_signals_real_success_rate(self):
        """Success rate should reflect actual trade win/loss, not a fixed 50%."""
        from src.backtest.models import Position, PositionStatus
        signals = [
            TradingSignal(
                symbol="A",
                date=date(2025, 9, 1),
                signal_type=SignalType.BUY,
                signal_name="MACD Golden Cross",
                price=Decimal('100'),
                description="",
                strength="MEDIUM",
                indicators=TechnicalIndicators(date=date(2025, 9, 1))
            ),
            TradingSignal(
                symbol="B",
                date=date(2025, 9, 2),
                signal_type=SignalType.BUY,
                signal_name="MACD Golden Cross",
                price=Decimal('50'),
                description="",
                strength="MEDIUM",
                indicators=TechnicalIndicators(date=date(2025, 9, 2))
            ),
        ]
        closed = [
            Position(
                symbol="A", quantity=1000,
                entry_price=Decimal('100'), entry_date=date(2025, 9, 1),
                current_price=Decimal('110'), current_date=date(2025, 9, 5),
                status=PositionStatus.CLOSED,
                pnl=Decimal('10000'), entry_signal_name="MACD Golden Cross",
            ),
            Position(
                symbol="B", quantity=1000,
                entry_price=Decimal('50'), entry_date=date(2025, 9, 2),
                current_price=Decimal('45'), current_date=date(2025, 9, 6),
                status=PositionStatus.CLOSED,
                pnl=Decimal('-5000'), entry_signal_name="MACD Golden Cross",
            ),
        ]

        result = self.reporter.analyze_signals(signals, closed_positions=closed)
        perf = result['signal_performance']['MACD Golden Cross']
        assert perf['traded'] == 2
        assert perf['success_rate'] == 50.0  # 1 win / 2 trades

    def teardown_method(self):
        # Clean up test reports
        import shutil
        if os.path.exists("test_reports"):
            shutil.rmtree("test_reports")


class TestBacktestEngineNew:
    """Tests for new engine features: trailing stop and market filter."""

    def _make_stock_data(self, symbol, prices):
        """Helper: list of StockData from a price sequence starting 2025-09-01."""
        result = []
        for i, p in enumerate(prices):
            d = date(2025, 9, 1) + __import__('datetime').timedelta(days=i)
            result.append(StockData(
                symbol=symbol, date=d,
                open_price=Decimal(str(p)), high_price=Decimal(str(p)),
                low_price=Decimal(str(p)), close_price=Decimal(str(p)),
                volume=100000
            ))
        return result

    def test_trailing_stop_ratchets_up(self):
        """When price rises, trailing stop should move up and protect profits."""
        engine = BacktestEngine(
            initial_capital=Decimal('1000000'),
            stop_loss_pct=Decimal('0.05'),
            take_profit_pct=Decimal('0.5'),  # High take_profit so trailing stop fires first
            trailing_stop_pct=Decimal('0.05'),
        )
        # Day1: entry 10, stop=9.50
        # Day2: price=12 → trailing stop ratchets to 12*0.95=11.40
        # Day3: price=11 → 11 < 11.40 → trailing stop fires
        stock_data = self._make_stock_data("TEST", [10, 12, 11])
        engine.add_price_data("TEST", stock_data)

        signal = TradingSignal(
            symbol="TEST", date=date(2025, 9, 1),
            signal_type=SignalType.BUY, signal_name="Test",
            price=Decimal('10'), description="", strength="MEDIUM",
            indicators=TechnicalIndicators(date=date(2025, 9, 1))
        )
        result = engine.run_backtest([signal], date(2025, 9, 1), date(2025, 9, 3))
        assert result.total_trades == 1
        closed = result.trades[0]
        # Trailing stop from peak 12 → 12*0.95=11.40 → exit at 11 (below stop)
        assert closed.exit_price <= Decimal('11.40')

    def test_market_filter_blocks_buy_when_bearish(self):
        """BUY signals should be suppressed when TAIEX is below its MA20."""
        engine = BacktestEngine(initial_capital=Decimal('1000000'))

        stock_data = self._make_stock_data("TEST", [100, 105, 110])
        engine.add_price_data("TEST", stock_data)

        # Benchmark: 25 days of data, last day price drops well below MA20
        benchmark_prices = [100] * 20 + [70, 70, 70, 70, 70]  # sharp drop at end
        benchmark_data = self._make_stock_data("^TWII", benchmark_prices)
        # Shift benchmark dates to align with signal date 2025-09-01
        from datetime import timedelta
        for i, bd in enumerate(benchmark_data):
            bd.date = date(2025, 8, 1) + timedelta(days=i)

        engine.build_benchmark_filter(benchmark_data)
        # The signal date 2025-09-01 is after the drop → market should be bearish
        assert not engine.is_market_bullish(date(2025, 9, 1))

        signal = TradingSignal(
            symbol="TEST", date=date(2025, 9, 1),
            signal_type=SignalType.BUY, signal_name="Test",
            price=Decimal('100'), description="", strength="MEDIUM",
            indicators=TechnicalIndicators(date=date(2025, 9, 1))
        )
        result = engine.run_backtest(
            [signal], date(2025, 9, 1), date(2025, 9, 3),
            benchmark_data=benchmark_data
        )
        # Signal should be blocked → no trades executed
        assert result.total_trades == 0

    def test_entry_signal_name_stored_on_position(self):
        """Position should record which signal triggered the entry."""
        engine = BacktestEngine(initial_capital=Decimal('1000000'))
        stock_data = self._make_stock_data("TEST", [10, 11, 12])
        engine.add_price_data("TEST", stock_data)

        signal = TradingSignal(
            symbol="TEST", date=date(2025, 9, 1),
            signal_type=SignalType.BUY, signal_name="Golden Cross",
            price=Decimal('10'), description="", strength="MEDIUM",
            indicators=TechnicalIndicators(date=date(2025, 9, 1))
        )
        engine.run_backtest([signal], date(2025, 9, 1), date(2025, 9, 3))
        assert len(engine.closed_positions) == 1
        assert engine.closed_positions[0].entry_signal_name == "Golden Cross"


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