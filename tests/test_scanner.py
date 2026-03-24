"""
Test market scanner functionality
"""
import pytest
import asyncio
from decimal import Decimal
from datetime import date, timedelta

from src.scanner.engine import MarketScanner, HistoricalDataUpdater
from src.scanner.filters import StockFilter, FilterCriteria, FilterOperator, MarketScreener
from src.database.models import Stock, StockPrice, StockRealtime

class TestMarketScanner:
    """Test market scanner functionality"""

    @pytest.fixture
    def market_scanner(self, mock_fubon_client):
        """Create market scanner with mock client"""
        return MarketScanner(
            fubon_client=mock_fubon_client,
            batch_size=10,
            max_concurrent=2,
            scan_interval=60
        )

    @pytest.fixture
    def test_stocks_in_db(self, test_db_session, sample_stocks):
        """Add sample stocks to test database"""
        for stock in sample_stocks:
            test_db_session.add(stock)
        test_db_session.commit()
        return sample_stocks

    def test_scanner_initialization(self, market_scanner):
        """Test scanner initialization"""
        assert market_scanner.batch_size == 10
        assert market_scanner.max_concurrent == 2
        assert market_scanner.scan_interval == 60
        assert not market_scanner.is_running

    def test_get_active_stocks(self, market_scanner, test_stocks_in_db):
        """Test getting active stocks from database"""
        # This would require mocking the database session
        # For now, just test that the method exists and can be called
        active_stocks = market_scanner._get_active_stocks(['TSE'])
        assert isinstance(active_stocks, list)

    @pytest.mark.asyncio
    async def test_scan_single_stock(self, market_scanner, test_db_session, sample_stocks):
        """Test scanning a single stock"""
        stock = sample_stocks[0]
        test_db_session.add(stock)
        test_db_session.commit()

        # Mock the database manager for this test
        original_db_manager = market_scanner.__dict__.get('db_manager')

        try:
            # This would test the actual scanning logic
            # For now, just ensure the method exists and doesn't crash
            result = await market_scanner._scan_single_stock(stock)
            assert isinstance(result, int)  # Should return signal count

        finally:
            # Restore original db_manager if it existed
            if original_db_manager:
                market_scanner.db_manager = original_db_manager

    def test_start_stop_scanning(self, market_scanner):
        """Test starting and stopping scanner"""
        assert not market_scanner.is_running

        market_scanner.stop_scanning()
        assert not market_scanner.is_running

class TestHistoricalDataUpdater:
    """Test historical data updater"""

    @pytest.fixture
    def data_updater(self, mock_fubon_client):
        """Create data updater with mock client"""
        return HistoricalDataUpdater(mock_fubon_client)

    def test_updater_initialization(self, data_updater):
        """Test updater initialization"""
        assert data_updater.fubon_client is not None

    @pytest.mark.asyncio
    async def test_update_single_stock(self, data_updater, test_db_session, sample_stocks):
        """Test updating historical data for single stock"""
        stock = sample_stocks[0]
        test_db_session.add(stock)
        test_db_session.commit()

        start_date = date.today() - timedelta(days=30)
        end_date = date.today()

        # This would test the actual update logic
        result = await data_updater._update_stock_history(stock, start_date, end_date)
        assert isinstance(result, bool)

class TestStockFilter:
    """Test stock filtering system"""

    @pytest.fixture
    def stock_filter(self):
        """Create stock filter instance"""
        return StockFilter()

    @pytest.fixture
    def test_stocks_with_data(self, test_db_session, sample_stocks):
        """Create stocks with associated data in database"""
        for stock in sample_stocks:
            test_db_session.add(stock)

        test_db_session.commit()

        # Add some price data
        for i, stock in enumerate(sample_stocks):
            if stock.is_active:  # Only for active stocks
                realtime = StockRealtime(
                    stock_id=stock.id,
                    current_price=Decimal(str(500 + i * 10)),
                    change_amount=Decimal(str(i * 2)),
                    change_percent=Decimal(str(i * 0.5)),
                    volume=1000000 + (i * 100000),
                    timestamp=date.today()
                )
                test_db_session.add(realtime)

        test_db_session.commit()
        return sample_stocks

    def test_filter_criteria_creation(self):
        """Test creating filter criteria"""
        criteria = FilterCriteria(
            field='price_current',
            operator=FilterOperator.GREATER_THAN,
            value=Decimal('100.0')
        )

        assert criteria.field == 'price_current'
        assert criteria.operator == FilterOperator.GREATER_THAN
        assert criteria.value == Decimal('100.0')

    def test_filter_by_market(self, stock_filter):
        """Test filtering stocks by market"""
        criteria = [FilterCriteria(
            field='market',
            operator=FilterOperator.EQUAL,
            value='TSE'
        )]

        results = stock_filter.filter_stocks(
            criteria_list=criteria,
            markets=['TSE']
        )

        assert isinstance(results, list)

    def test_filter_by_price_range(self, stock_filter):
        """Test filtering stocks by price range"""
        criteria = [FilterCriteria(
            field='price_current',
            operator=FilterOperator.BETWEEN,
            value=Decimal('100.0'),
            value2=Decimal('200.0')
        )]

        results = stock_filter.filter_stocks(criteria_list=criteria)
        assert isinstance(results, list)

    def test_evaluate_criteria_operators(self, stock_filter):
        """Test different filter operators"""
        # Test GREATER_THAN
        assert stock_filter._evaluate_criteria(
            Decimal('150'),
            FilterCriteria('price', FilterOperator.GREATER_THAN, Decimal('100'))
        )
        assert not stock_filter._evaluate_criteria(
            Decimal('50'),
            FilterCriteria('price', FilterOperator.GREATER_THAN, Decimal('100'))
        )

        # Test BETWEEN
        assert stock_filter._evaluate_criteria(
            Decimal('150'),
            FilterCriteria('price', FilterOperator.BETWEEN, Decimal('100'), Decimal('200'))
        )
        assert not stock_filter._evaluate_criteria(
            Decimal('250'),
            FilterCriteria('price', FilterOperator.BETWEEN, Decimal('100'), Decimal('200'))
        )

        # Test IN
        assert stock_filter._evaluate_criteria(
            'TSE',
            FilterCriteria('market', FilterOperator.IN, ['TSE', 'OTC'])
        )
        assert not stock_filter._evaluate_criteria(
            'NASDAQ',
            FilterCriteria('market', FilterOperator.IN, ['TSE', 'OTC'])
        )

class TestMarketScreener:
    """Test market screener functionality"""

    @pytest.fixture
    def market_screener(self):
        """Create market screener instance"""
        return MarketScreener()

    def test_screener_initialization(self, market_screener):
        """Test screener initialization"""
        assert market_screener.stock_filter is not None

    def test_get_available_presets(self, market_screener):
        """Test getting available preset filters"""
        presets = market_screener.get_available_presets()

        assert isinstance(presets, list)
        assert len(presets) > 0
        assert 'momentum' in presets
        assert 'oversold' in presets

    def test_screen_with_preset(self, market_screener):
        """Test screening with preset filter"""
        results = market_screener.screen_market(
            preset_name='momentum',
            limit=10
        )

        assert isinstance(results, list)

    def test_screen_with_custom_criteria(self, market_screener):
        """Test screening with custom criteria"""
        custom_criteria = [
            FilterCriteria(
                field='price_current',
                operator=FilterOperator.GREATER_THAN,
                value=Decimal('50.0')
            )
        ]

        results = market_screener.screen_market(
            custom_criteria=custom_criteria,
            limit=5
        )

        assert isinstance(results, list)

    def test_screen_for_signals(self, market_screener):
        """Test screening for different signal types"""
        results = market_screener.screen_for_signals()

        assert isinstance(results, dict)
        assert len(results) > 0

        # Check that each category returns a list
        for category, stocks in results.items():
            assert isinstance(stocks, list)

    def test_invalid_preset(self, market_screener):
        """Test screening with invalid preset"""
        results = market_screener.screen_market(preset_name='invalid_preset')

        assert isinstance(results, list)
        assert len(results) == 0