"""
Test portfolio management functionality
"""
import pytest
from decimal import Decimal
from datetime import date, timedelta

from src.portfolio.manager import PortfolioManager, PerformanceAnalyzer
from src.portfolio.transaction_recorder import TransactionRecorder, TransactionMethod
from src.database.models import Portfolio, Stock, Transaction

class TestPortfolioManager:
    """Test portfolio management functionality"""

    @pytest.fixture
    def portfolio_manager(self, test_db_manager):
        """Create portfolio manager with test database"""
        manager = PortfolioManager()
        manager.db_manager = test_db_manager
        return manager

    @pytest.fixture
    def test_portfolio(self, test_db_session, sample_stocks):
        """Create test portfolio with sample data"""
        # Add stocks to session
        for stock in sample_stocks[:3]:  # Add first 3 stocks
            test_db_session.add(stock)
        test_db_session.commit()

        # Create portfolio
        portfolio = Portfolio(
            user_id="test_user",
            name="Test Portfolio"
        )
        test_db_session.add(portfolio)
        test_db_session.commit()

        return portfolio

    def test_create_portfolio(self, portfolio_manager):
        """Test portfolio creation"""
        portfolio_id = portfolio_manager.create_portfolio(
            user_id="test_user",
            name="Test Portfolio"
        )

        assert portfolio_id is not None

        # Test duplicate portfolio name
        with pytest.raises(Exception):
            portfolio_manager.create_portfolio(
                user_id="test_user",
                name="Test Portfolio"
            )

    def test_get_user_portfolios(self, portfolio_manager, test_db_session):
        """Test getting user portfolios"""
        # Create test portfolios
        portfolio1 = Portfolio(user_id="test_user", name="Portfolio 1")
        portfolio2 = Portfolio(user_id="test_user", name="Portfolio 2")
        portfolio3 = Portfolio(user_id="other_user", name="Portfolio 3")

        test_db_session.add_all([portfolio1, portfolio2, portfolio3])
        test_db_session.commit()

        # Test getting portfolios for specific user
        user_portfolios = portfolio_manager.get_user_portfolios("test_user")

        assert len(user_portfolios) == 2
        assert all(p.user_id == "test_user" for p in user_portfolios)

    def test_portfolio_summary_empty(self, portfolio_manager, test_portfolio):
        """Test portfolio summary with no holdings"""
        summary = portfolio_manager.get_portfolio_summary(str(test_portfolio.id))

        assert summary is not None
        assert summary.total_cost_basis == Decimal('0')
        assert summary.total_market_value == Decimal('0')
        assert summary.holdings_count == 0

class TestTransactionRecorder:
    """Test transaction recording functionality"""

    @pytest.fixture
    def transaction_recorder(self):
        """Create transaction recorder"""
        return TransactionRecorder(method=TransactionMethod.FIFO)

    @pytest.fixture
    def test_portfolio_with_stock(self, test_db_session):
        """Create test portfolio with stock"""
        # Create stock
        stock = Stock(
            symbol="TEST",
            name="Test Stock",
            market="TSE",
            is_active=True
        )
        test_db_session.add(stock)

        # Create portfolio
        portfolio = Portfolio(
            user_id="test_user",
            name="Test Portfolio"
        )
        test_db_session.add(portfolio)
        test_db_session.commit()

        return portfolio, stock

    def test_record_buy_transaction(self, transaction_recorder, test_db_session, test_portfolio_with_stock):
        """Test recording buy transaction"""
        portfolio, stock = test_portfolio_with_stock

        transaction_id = transaction_recorder.record_buy_transaction(
            portfolio_id=str(portfolio.id),
            stock_symbol=stock.symbol,
            quantity=1000,
            price=Decimal('100.0'),
            fee=Decimal('10.0'),
            tax=Decimal('5.0')
        )

        assert transaction_id is not None

        # Verify transaction was recorded
        transaction = test_db_session.query(Transaction).filter(
            Transaction.id == transaction_id
        ).first()

        assert transaction is not None
        assert transaction.transaction_type == 'BUY'
        assert transaction.quantity == 1000
        assert transaction.price == Decimal('100.0')
        assert transaction.total_amount == Decimal('100015.0')  # 100*1000 + 10 + 5

    def test_record_sell_transaction(self, transaction_recorder, test_db_session, test_portfolio_with_stock):
        """Test recording sell transaction"""
        portfolio, stock = test_portfolio_with_stock

        # First, record a buy transaction
        transaction_recorder.record_buy_transaction(
            portfolio_id=str(portfolio.id),
            stock_symbol=stock.symbol,
            quantity=1000,
            price=Decimal('100.0')
        )

        # Then record a sell transaction
        transaction_id, realized_gains = transaction_recorder.record_sell_transaction(
            portfolio_id=str(portfolio.id),
            stock_symbol=stock.symbol,
            quantity=500,
            price=Decimal('110.0'),
            fee=Decimal('10.0')
        )

        assert transaction_id is not None
        assert isinstance(realized_gains, list)

        # Verify transaction was recorded
        transaction = test_db_session.query(Transaction).filter(
            Transaction.id == transaction_id
        ).first()

        assert transaction is not None
        assert transaction.transaction_type == 'SELL'
        assert transaction.quantity == 500
        assert transaction.price == Decimal('110.0')

    def test_sell_insufficient_shares(self, transaction_recorder, test_portfolio_with_stock):
        """Test selling more shares than available"""
        portfolio, stock = test_portfolio_with_stock

        # Try to sell without buying first
        with pytest.raises(Exception):
            transaction_recorder.record_sell_transaction(
                portfolio_id=str(portfolio.id),
                stock_symbol=stock.symbol,
                quantity=1000,
                price=Decimal('100.0')
            )

    def test_transaction_history(self, transaction_recorder, test_db_session, test_portfolio_with_stock):
        """Test getting transaction history"""
        portfolio, stock = test_portfolio_with_stock

        # Record some transactions
        transaction_recorder.record_buy_transaction(
            portfolio_id=str(portfolio.id),
            stock_symbol=stock.symbol,
            quantity=1000,
            price=Decimal('100.0')
        )

        transaction_recorder.record_sell_transaction(
            portfolio_id=str(portfolio.id),
            stock_symbol=stock.symbol,
            quantity=500,
            price=Decimal('110.0')
        )

        # Get transaction history
        history = transaction_recorder.get_transaction_history(
            portfolio_id=str(portfolio.id)
        )

        assert len(history) == 2
        assert history[0].transaction_type in ['BUY', 'SELL']  # Most recent first
        assert history[1].transaction_type in ['BUY', 'SELL']

    def test_import_transactions_csv(self, transaction_recorder, test_portfolio_with_stock):
        """Test importing transactions from CSV data"""
        portfolio, stock = test_portfolio_with_stock

        csv_data = [
            {
                'symbol': stock.symbol,
                'type': 'BUY',
                'quantity': '1000',
                'price': '100.0',
                'date': '2025-01-01',
                'fee': '10.0',
                'tax': '5.0',
                'notes': 'Test transaction'
            },
            {
                'symbol': stock.symbol,
                'type': 'SELL',
                'quantity': '500',
                'price': '110.0',
                'date': '2025-01-15',
                'fee': '10.0',
                'tax': '0.0',
                'notes': 'Test sale'
            }
        ]

        success_count, error_count, errors = transaction_recorder.import_transactions_from_csv(
            portfolio_id=str(portfolio.id),
            csv_data=csv_data
        )

        assert success_count == 2
        assert error_count == 0
        assert len(errors) == 0

class TestPerformanceAnalyzer:
    """Test portfolio performance analysis"""

    @pytest.fixture
    def performance_analyzer(self, portfolio_manager):
        """Create performance analyzer"""
        return PerformanceAnalyzer(portfolio_manager)

    def test_calculate_portfolio_metrics_empty(self, performance_analyzer, test_portfolio):
        """Test metrics calculation for empty portfolio"""
        metrics = performance_analyzer.calculate_portfolio_metrics(str(test_portfolio.id))

        assert isinstance(metrics, dict)
        # Should return empty dict or zero values for empty portfolio

    def test_get_top_performers_empty(self, performance_analyzer, test_portfolio):
        """Test getting top performers from empty portfolio"""
        top_performers = performance_analyzer.get_top_performers(str(test_portfolio.id))

        assert isinstance(top_performers, list)
        assert len(top_performers) == 0

    def test_get_worst_performers_empty(self, performance_analyzer, test_portfolio):
        """Test getting worst performers from empty portfolio"""
        worst_performers = performance_analyzer.get_worst_performers(str(test_portfolio.id))

        assert isinstance(worst_performers, list)
        assert len(worst_performers) == 0