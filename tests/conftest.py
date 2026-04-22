"""
Pytest configuration and fixtures
"""
import pytest
import asyncio
from datetime import datetime, date
from decimal import Decimal
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler

# Allow PostgreSQL UUID type to render in SQLite as VARCHAR for testing
if not hasattr(SQLiteTypeCompiler, 'visit_UUID'):
    SQLiteTypeCompiler.visit_UUID = lambda self, type_, **kw: 'VARCHAR(36)'

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from src.database.models import Base, Stock, StockPrice, TechnicalIndicator
from src.database.connection import DatabaseManager
from config.settings import settings

# Test database URL
TEST_DATABASE_URL = "sqlite:///:memory:"

@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture(scope="session")
def test_engine():
    """Create test database engine"""
    engine = create_engine(
        TEST_DATABASE_URL,
        poolclass=StaticPool,
        echo=False,
        connect_args={"check_same_thread": False}
    )

    # Create all tables
    Base.metadata.create_all(bind=engine)
    yield engine

    # Cleanup
    Base.metadata.drop_all(bind=engine)
    engine.dispose()

@pytest.fixture
def test_db_session(test_engine):
    """Create test database session"""
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    session = TestingSessionLocal()

    try:
        yield session
        session.rollback()
    finally:
        session.close()

@pytest.fixture
def test_db_manager(test_engine):
    """Create test database manager"""
    db_manager = DatabaseManager(database_url=TEST_DATABASE_URL)
    db_manager.engine = test_engine
    db_manager.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    yield db_manager

@pytest.fixture
def sample_stock():
    """Create sample stock data"""
    return Stock(
        symbol="2330",
        name="台積電",
        market="TSE",
        industry="半導體",
        is_active=True
    )

@pytest.fixture
def sample_stocks():
    """Create multiple sample stocks"""
    stocks = [
        Stock(symbol="2330", name="台積電", market="TSE", industry="半導體", is_active=True),
        Stock(symbol="2454", name="聯發科", market="TSE", industry="半導體", is_active=True),
        Stock(symbol="2317", name="鴻海", market="TSE", industry="電子", is_active=True),
        Stock(symbol="2412", name="中華電", market="TSE", industry="通信", is_active=True),
        Stock(symbol="3008", name="大立光", market="TSE", industry="光電", is_active=False)
    ]
    return stocks

@pytest.fixture
def sample_price_data():
    """Create sample price data for testing indicators"""
    prices = []
    base_price = Decimal('500.0')

    for i in range(100):
        price_variation = Decimal(str((i % 10) * 5 - 20))  # ±20 variation
        close_price = base_price + price_variation

        price = StockPrice(
            stock_id="test-stock-id",
            date=date(2025, 1, 1) + timedelta(days=i),
            open_price=close_price - Decimal('5'),
            high_price=close_price + Decimal('10'),
            low_price=close_price - Decimal('10'),
            close_price=close_price,
            volume=1000000 + (i * 10000),
            turnover=close_price * (1000000 + (i * 10000))
        )
        prices.append(price)

    return prices

@pytest.fixture
def sample_technical_indicators():
    """Create sample technical indicators"""
    return TechnicalIndicator(
        stock_id="test-stock-id",
        date=date.today(),
        ma5=Decimal('500.0'),
        ma10=Decimal('495.0'),
        ma20=Decimal('490.0'),
        ma60=Decimal('485.0'),
        rsi14=Decimal('65.5'),
        macd=Decimal('2.5'),
        macd_signal=Decimal('2.0'),
        macd_histogram=Decimal('0.5'),
        bb_upper=Decimal('520.0'),
        bb_middle=Decimal('500.0'),
        bb_lower=Decimal('480.0'),
        volume_ma20=1500000
    )

@pytest.fixture
def mock_fubon_client():
    """Mock Fubon API client for testing"""
    class MockFubonClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

        async def get_stock_list(self, market="TSE"):
            return [
                {"symbol": "2330", "name": "台積電", "market": "TSE"},
                {"symbol": "2454", "name": "聯發科", "market": "TSE"}
            ]

        async def get_realtime_quote(self, symbol):
            return {
                'symbol': symbol,
                'current_price': Decimal('500.0'),
                'change_amount': Decimal('5.0'),
                'change_percent': Decimal('1.0'),
                'volume': 1000000,
                'timestamp': datetime.now()
            }

        async def get_historical_data(self, symbol, start_date, end_date):
            return [
                {
                    'date': date(2025, 1, 1),
                    'open_price': Decimal('495.0'),
                    'high_price': Decimal('510.0'),
                    'low_price': Decimal('490.0'),
                    'close_price': Decimal('500.0'),
                    'volume': 1000000,
                    'turnover': Decimal('500000000.0')
                }
            ]

    return MockFubonClient()

@pytest.fixture
def mock_telegram_update():
    """Mock Telegram update object"""
    class MockUser:
        def __init__(self):
            self.id = 123456789
            self.username = "testuser"
            self.first_name = "Test"

    class MockChat:
        def __init__(self):
            self.id = 123456789

    class MockMessage:
        def __init__(self, text="test"):
            self.text = text

        async def reply_text(self, text, **kwargs):
            return {"text": text}

    class MockUpdate:
        def __init__(self, message_text="test"):
            self.effective_user = MockUser()
            self.effective_chat = MockChat()
            self.message = MockMessage(message_text)

    return MockUpdate

@pytest.fixture
def sample_portfolio_data():
    """Create sample portfolio data"""
    return {
        'user_id': 'test_user_123',
        'portfolio_id': 'test_portfolio_123',
        'stocks': [
            {'symbol': '2330', 'quantity': 2000, 'avg_cost': Decimal('480.0')},
            {'symbol': '2454', 'quantity': 1000, 'avg_cost': Decimal('720.0')},
        ]
    }