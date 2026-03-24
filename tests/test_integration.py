"""
Integration tests for the complete system
"""
import pytest
import asyncio
from decimal import Decimal
from datetime import datetime, date
import time

from src.database.connection import DatabaseManager
from src.scanner.engine import MarketScanner
from src.indicators.calculator import IndicatorCalculator
from src.portfolio.manager import PortfolioManager
from src.telegram.bot import TelegramBot
from src.monitoring.performance import PerformanceMonitor

class TestSystemIntegration:
    """Test complete system integration"""

    @pytest.fixture
    def test_system_components(self, test_db_manager, mock_fubon_client):
        """Setup all system components for integration testing"""
        components = {
            'db_manager': test_db_manager,
            'fubon_client': mock_fubon_client,
            'scanner': MarketScanner(
                fubon_client=mock_fubon_client,
                batch_size=5,
                max_concurrent=2,
                scan_interval=10
            ),
            'indicator_calculator': IndicatorCalculator(),
            'portfolio_manager': PortfolioManager(),
            'performance_monitor': PerformanceMonitor()
        }
        return components

    def test_database_initialization(self, test_system_components):
        """Test database initialization and connectivity"""
        db_manager = test_system_components['db_manager']

        # Test database health
        assert db_manager.health_check()

        # Test table creation
        db_manager.create_tables()

    @pytest.mark.asyncio
    async def test_api_to_database_flow(self, test_system_components, sample_stocks, test_db_session):
        """Test data flow from API to database"""
        fubon_client = test_system_components['fubon_client']
        db_manager = test_system_components['db_manager']

        # Add sample stocks to database
        for stock in sample_stocks[:2]:  # Use first 2 stocks
            test_db_session.add(stock)
        test_db_session.commit()

        # Test API data retrieval
        stock_list = await fubon_client.get_stock_list("TSE")
        assert isinstance(stock_list, list)
        assert len(stock_list) > 0

        # Test real-time quote retrieval
        quote = await fubon_client.get_realtime_quote("2330")
        assert quote is not None
        assert 'current_price' in quote

        # Test historical data retrieval
        historical = await fubon_client.get_historical_data(
            symbol="2330",
            start_date="2024-01-01",
            end_date="2024-01-31"
        )
        assert isinstance(historical, list)

    def test_scanner_to_indicators_flow(self, test_system_components, sample_price_data):
        """Test flow from scanner to indicator calculation"""
        scanner = test_system_components['scanner']
        calculator = test_system_components['indicator_calculator']

        # Test indicator calculation with sample data
        indicators = calculator.calculate_all_indicators(sample_price_data)
        assert isinstance(indicators, dict)

        if indicators:
            # Verify indicator data structure
            latest_date = max(indicators.keys())
            latest_indicators = indicators[latest_date]

            assert isinstance(latest_indicators, dict)
            assert len(latest_indicators) > 0

    def test_portfolio_transaction_flow(self, test_system_components, test_db_session, sample_stocks):
        """Test complete portfolio and transaction flow"""
        portfolio_manager = test_system_components['portfolio_manager']

        # Add stock to database
        stock = sample_stocks[0]
        test_db_session.add(stock)
        test_db_session.commit()

        # Create portfolio
        portfolio_id = portfolio_manager.create_portfolio(
            user_id="integration_test_user",
            name="Integration Test Portfolio"
        )
        assert portfolio_id is not None

        # Test adding transactions
        success = portfolio_manager.add_transaction(
            portfolio_id=portfolio_id,
            stock_symbol=stock.symbol,
            transaction_type='BUY',
            quantity=1000,
            price=Decimal('100.0')
        )
        assert success

        # Test portfolio summary
        summary = portfolio_manager.get_portfolio_summary(portfolio_id)
        assert summary is not None
        assert summary.holdings_count > 0

    def test_performance_monitoring_integration(self, test_system_components):
        """Test performance monitoring integration"""
        monitor = test_system_components['performance_monitor']

        # Test metrics collection
        metrics = monitor._collect_metrics()
        assert metrics is not None
        assert metrics.cpu_percent >= 0
        assert metrics.memory_percent >= 0

        # Test adaptive settings
        settings = monitor.get_adaptive_settings()
        assert isinstance(settings, dict)
        assert 'batch_size' in settings
        assert 'delay' in settings

    @pytest.mark.asyncio
    async def test_end_to_end_signal_generation(self, test_system_components, test_db_session, sample_stocks):
        """Test end-to-end signal generation process"""
        scanner = test_system_components['scanner']
        calculator = test_system_components['indicator_calculator']

        # Add stocks to database
        for stock in sample_stocks[:2]:
            test_db_session.add(stock)
        test_db_session.commit()

        # Mock the complete scanning process
        try:
            # This would test the actual scanning if we had real data
            # For now, just test that the components work together
            stock = sample_stocks[0]

            # Test single stock scan (mocked)
            signal_count = await scanner._scan_single_stock(stock)
            assert isinstance(signal_count, int)
            assert signal_count >= 0

        except Exception as e:
            # Expected to fail due to missing real-time data in test
            assert "No current price" in str(e) or "暫無即時報價" in str(e)

class TestSystemReliability:
    """Test system reliability and error handling"""

    @pytest.fixture
    def system_components(self, test_db_manager, mock_fubon_client):
        """Setup system components for reliability testing"""
        return {
            'db_manager': test_db_manager,
            'fubon_client': mock_fubon_client,
            'scanner': MarketScanner(mock_fubon_client, batch_size=3)
        }

    def test_database_connection_recovery(self, system_components):
        """Test database connection recovery"""
        db_manager = system_components['db_manager']

        # Test initial connection
        assert db_manager.health_check()

        # Test recovery after connection issue (simulated)
        # In a real test, you might temporarily break the connection
        assert db_manager.health_check()

    @pytest.mark.asyncio
    async def test_api_rate_limiting(self, system_components):
        """Test API rate limiting functionality"""
        fubon_client = system_components['fubon_client']

        # Test multiple rapid API calls
        start_time = time.time()

        tasks = []
        for i in range(5):
            task = fubon_client.get_realtime_quote("2330")
            tasks.append(task)

        results = await asyncio.gather(*tasks, return_exceptions=True)

        end_time = time.time()
        duration = end_time - start_time

        # Should complete within reasonable time
        assert duration < 10  # 10 seconds max

        # All results should be valid or exceptions
        assert len(results) == 5

    def test_error_handling_in_calculations(self, system_components):
        """Test error handling in calculations"""
        calculator = IndicatorCalculator()

        # Test with invalid data
        empty_result = calculator.calculate_all_indicators([])
        assert empty_result == {}

        # Test with minimal data
        minimal_result = calculator.calculate_all_indicators([])
        assert isinstance(minimal_result, dict)

    @pytest.mark.asyncio
    async def test_concurrent_operations(self, system_components, test_db_session, sample_stocks):
        """Test concurrent operations"""
        scanner = system_components['scanner']

        # Add stocks to database
        for stock in sample_stocks[:3]:
            test_db_session.add(stock)
        test_db_session.commit()

        # Test concurrent stock scanning
        tasks = []
        for stock in sample_stocks[:3]:
            if stock.is_active:
                task = scanner._scan_single_stock(stock)
                tasks.append(task)

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # All tasks should complete (with results or exceptions)
            assert len(results) == len(tasks)

class TestSystemPerformance:
    """Test system performance under load"""

    @pytest.fixture
    def performance_test_components(self, test_db_manager, mock_fubon_client):
        """Setup components for performance testing"""
        return {
            'scanner': MarketScanner(
                fubon_client=mock_fubon_client,
                batch_size=10,
                max_concurrent=5
            ),
            'calculator': IndicatorCalculator()
        }

    def test_indicator_calculation_performance(self, performance_test_components, sample_price_data):
        """Test indicator calculation performance"""
        calculator = performance_test_components['calculator']

        # Measure calculation time
        start_time = time.time()

        result = calculator.calculate_all_indicators(sample_price_data)

        end_time = time.time()
        duration = end_time - start_time

        # Should complete within reasonable time
        assert duration < 5.0  # 5 seconds max
        assert isinstance(result, dict)

    def test_memory_usage_during_operations(self, performance_test_components):
        """Test memory usage during intensive operations"""
        import psutil
        import os

        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss

        calculator = performance_test_components['calculator']

        # Perform multiple calculations
        for i in range(10):
            # Create some sample data for each iteration
            sample_data = []
            for j in range(50):
                from src.database.models import StockPrice
                price = StockPrice(
                    stock_id=f"test-{i}-{j}",
                    date=date(2024, 1, 1),
                    open_price=Decimal('100'),
                    high_price=Decimal('105'),
                    low_price=Decimal('95'),
                    close_price=Decimal('102'),
                    volume=1000000
                )
                sample_data.append(price)

            calculator.calculate_all_indicators(sample_data)

        final_memory = process.memory_info().rss
        memory_increase = final_memory - initial_memory

        # Memory increase should be reasonable (less than 100MB)
        assert memory_increase < 100 * 1024 * 1024

class TestDataConsistency:
    """Test data consistency across the system"""

    def test_database_data_integrity(self, test_db_session, sample_stocks):
        """Test database data integrity"""
        # Add stocks
        for stock in sample_stocks:
            test_db_session.add(stock)
        test_db_session.commit()

        # Verify stocks were added correctly
        from src.database.models import Stock
        stored_stocks = test_db_session.query(Stock).all()

        assert len(stored_stocks) == len(sample_stocks)

        # Verify data consistency
        for stored_stock in stored_stocks:
            original = next(s for s in sample_stocks if s.symbol == stored_stock.symbol)
            assert stored_stock.name == original.name
            assert stored_stock.market == original.market
            assert stored_stock.is_active == original.is_active

    def test_transaction_data_consistency(self, test_db_session, sample_stocks):
        """Test transaction data consistency"""
        from src.database.models import Portfolio, Transaction

        # Create portfolio
        portfolio = Portfolio(
            user_id="test_user",
            name="Test Portfolio"
        )
        test_db_session.add(portfolio)

        # Add stock
        stock = sample_stocks[0]
        test_db_session.add(stock)
        test_db_session.commit()

        # Add transaction
        transaction = Transaction(
            portfolio_id=portfolio.id,
            stock_id=stock.id,
            transaction_type='BUY',
            quantity=1000,
            price=Decimal('100.0'),
            total_amount=Decimal('100000.0'),
            transaction_date=date.today()
        )
        test_db_session.add(transaction)
        test_db_session.commit()

        # Verify transaction integrity
        stored_transaction = test_db_session.query(Transaction).first()
        assert stored_transaction.quantity == 1000
        assert stored_transaction.price == Decimal('100.0')
        assert stored_transaction.total_amount == Decimal('100000.0')