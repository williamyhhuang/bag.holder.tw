"""
Database models for Taiwan Stock Monitoring Robot
"""
from datetime import datetime, date
from decimal import Decimal
from typing import List, Optional
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean, Column, Date, DateTime, ForeignKey, Integer, String, Text,
    DECIMAL, BigInteger, ARRAY, JSON, UniqueConstraint, Index
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

Base = declarative_base()

class TimestampMixin:
    """Base mixin for created_at and updated_at timestamps"""
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

class Stock(Base, TimestampMixin):
    """股票主檔"""
    __tablename__ = 'stocks'

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    symbol = Column(String(10), nullable=False, unique=True, index=True)
    name = Column(String(100), nullable=False)
    market = Column(String(10), nullable=False, index=True)  # TSE, OTC
    industry = Column(String(50))
    is_active = Column(Boolean, default=True)

    # Relationships
    prices = relationship("StockPrice", back_populates="stock", cascade="all, delete-orphan")
    realtime = relationship("StockRealtime", back_populates="stock", uselist=False, cascade="all, delete-orphan")
    indicators = relationship("TechnicalIndicator", back_populates="stock", cascade="all, delete-orphan")
    alerts = relationship("Alert", back_populates="stock", cascade="all, delete-orphan")
    holdings = relationship("PortfolioHolding", back_populates="stock")
    transactions = relationship("Transaction", back_populates="stock")
    watchlists = relationship("Watchlist", back_populates="stock")

class StockPrice(Base, TimestampMixin):
    """股價歷史資料 (OHLCV)"""
    __tablename__ = 'stock_prices'
    __table_args__ = (
        UniqueConstraint('stock_id', 'date'),
        Index('idx_stock_prices_stock_date', 'stock_id', 'date'),
    )

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    stock_id = Column(PG_UUID(as_uuid=True), ForeignKey('stocks.id'), nullable=False)
    date = Column(Date, nullable=False, index=True)
    open_price = Column(DECIMAL(10, 2), nullable=False)
    high_price = Column(DECIMAL(10, 2), nullable=False)
    low_price = Column(DECIMAL(10, 2), nullable=False)
    close_price = Column(DECIMAL(10, 2), nullable=False)
    volume = Column(BigInteger, nullable=False)
    turnover = Column(DECIMAL(15, 2))  # 成交金額

    # Relationships
    stock = relationship("Stock", back_populates="prices")

class StockRealtime(Base, TimestampMixin):
    """即時股價資料"""
    __tablename__ = 'stock_realtime'
    __table_args__ = (
        UniqueConstraint('stock_id'),
        Index('idx_stock_realtime_timestamp', 'timestamp'),
    )

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    stock_id = Column(PG_UUID(as_uuid=True), ForeignKey('stocks.id'), nullable=False)
    current_price = Column(DECIMAL(10, 2), nullable=False)
    change_amount = Column(DECIMAL(10, 2), nullable=False)
    change_percent = Column(DECIMAL(5, 2), nullable=False)
    volume = Column(BigInteger, nullable=False)
    bid_price = Column(DECIMAL(10, 2))
    ask_price = Column(DECIMAL(10, 2))
    bid_volume = Column(Integer)
    ask_volume = Column(Integer)
    timestamp = Column(DateTime(timezone=True), nullable=False)

    # Relationships
    stock = relationship("Stock", back_populates="realtime")

class TechnicalIndicator(Base, TimestampMixin):
    """技術指標"""
    __tablename__ = 'technical_indicators'
    __table_args__ = (
        UniqueConstraint('stock_id', 'date'),
        Index('idx_technical_indicators_stock_date', 'stock_id', 'date'),
    )

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    stock_id = Column(PG_UUID(as_uuid=True), ForeignKey('stocks.id'), nullable=False)
    date = Column(Date, nullable=False)

    # 移動平均線
    ma5 = Column(DECIMAL(10, 2))
    ma10 = Column(DECIMAL(10, 2))
    ma20 = Column(DECIMAL(10, 2))
    ma60 = Column(DECIMAL(10, 2))

    # RSI
    rsi14 = Column(DECIMAL(5, 2))

    # MACD
    macd = Column(DECIMAL(10, 4))
    macd_signal = Column(DECIMAL(10, 4))
    macd_histogram = Column(DECIMAL(10, 4))

    # 布林通道
    bb_upper = Column(DECIMAL(10, 2))
    bb_middle = Column(DECIMAL(10, 2))
    bb_lower = Column(DECIMAL(10, 2))

    # 成交量
    volume_ma20 = Column(BigInteger)

    # Relationships
    stock = relationship("Stock", back_populates="indicators")

class Alert(Base, TimestampMixin):
    """警報訊號"""
    __tablename__ = 'alerts'
    __table_args__ = (
        Index('idx_alerts_triggered_at', 'triggered_at'),
        Index('idx_alerts_is_sent', 'is_sent'),
        Index('idx_alerts_stock_type', 'stock_id', 'alert_type'),
    )

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    stock_id = Column(PG_UUID(as_uuid=True), ForeignKey('stocks.id'), nullable=False)
    alert_type = Column(String(20), nullable=False)  # BUY, SELL, WATCH
    signal_name = Column(String(50), nullable=False)
    price = Column(DECIMAL(10, 2), nullable=False)
    description = Column(Text)
    is_sent = Column(Boolean, default=False)
    triggered_at = Column(DateTime(timezone=True), nullable=False)
    sent_at = Column(DateTime(timezone=True))

    # Relationships
    stock = relationship("Stock", back_populates="alerts")

class TelegramUser(Base, TimestampMixin):
    """Telegram 用戶設定"""
    __tablename__ = 'telegram_users'

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    telegram_id = Column(String(50), nullable=False, unique=True)
    username = Column(String(100))
    first_name = Column(String(100))
    is_active = Column(Boolean, default=True)
    alert_enabled = Column(Boolean, default=True)
    alert_types = Column(ARRAY(String), default=['BUY', 'SELL'])

    # Relationships
    portfolios = relationship("Portfolio", back_populates="user")
    watchlists = relationship("Watchlist", back_populates="user")

class Portfolio(Base, TimestampMixin):
    """投資組合"""
    __tablename__ = 'portfolios'
    __table_args__ = (
        UniqueConstraint('user_id', 'name'),
    )

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(String(50), ForeignKey('telegram_users.telegram_id'), nullable=False)
    name = Column(String(100), default='Default Portfolio')
    is_active = Column(Boolean, default=True)

    # Relationships
    user = relationship("TelegramUser", back_populates="portfolios")
    holdings = relationship("PortfolioHolding", back_populates="portfolio", cascade="all, delete-orphan")
    transactions = relationship("Transaction", back_populates="portfolio")

class PortfolioHolding(Base, TimestampMixin):
    """投資組合持股"""
    __tablename__ = 'portfolio_holdings'
    __table_args__ = (
        UniqueConstraint('portfolio_id', 'stock_id'),
    )

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    portfolio_id = Column(PG_UUID(as_uuid=True), ForeignKey('portfolios.id'), nullable=False)
    stock_id = Column(PG_UUID(as_uuid=True), ForeignKey('stocks.id'), nullable=False)
    quantity = Column(Integer, nullable=False)  # 持股數量（以股為單位）
    avg_cost = Column(DECIMAL(10, 2), nullable=False)  # 平均成本

    # Relationships
    portfolio = relationship("Portfolio", back_populates="holdings")
    stock = relationship("Stock", back_populates="holdings")

class Transaction(Base, TimestampMixin):
    """交易記錄"""
    __tablename__ = 'transactions'
    __table_args__ = (
        Index('idx_transactions_date', 'transaction_date'),
        Index('idx_transactions_portfolio', 'portfolio_id'),
    )

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    portfolio_id = Column(PG_UUID(as_uuid=True), ForeignKey('portfolios.id'), nullable=False)
    stock_id = Column(PG_UUID(as_uuid=True), ForeignKey('stocks.id'), nullable=False)
    transaction_type = Column(String(10), nullable=False)  # BUY, SELL
    quantity = Column(Integer, nullable=False)  # 交易數量（以股為單位）
    price = Column(DECIMAL(10, 2), nullable=False)  # 交易價格
    fee = Column(DECIMAL(10, 2), default=0)  # 手續費
    tax = Column(DECIMAL(10, 2), default=0)  # 稅費
    total_amount = Column(DECIMAL(15, 2), nullable=False)  # 總金額
    transaction_date = Column(Date, nullable=False)
    notes = Column(Text)

    # Relationships
    portfolio = relationship("Portfolio", back_populates="transactions")
    stock = relationship("Stock", back_populates="transactions")

class Watchlist(Base, TimestampMixin):
    """關注清單"""
    __tablename__ = 'watchlists'
    __table_args__ = (
        UniqueConstraint('user_id', 'stock_id'),
    )

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(String(50), ForeignKey('telegram_users.telegram_id'), nullable=False)
    stock_id = Column(PG_UUID(as_uuid=True), ForeignKey('stocks.id'), nullable=False)

    # Relationships
    user = relationship("TelegramUser", back_populates="watchlists")
    stock = relationship("Stock", back_populates="watchlists")

class SystemLog(Base):
    """系統日誌"""
    __tablename__ = 'system_logs'
    __table_args__ = (
        Index('idx_system_logs_created_at', 'created_at'),
        Index('idx_system_logs_level', 'level'),
    )

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    level = Column(String(10), nullable=False)  # DEBUG, INFO, WARNING, ERROR, CRITICAL
    module = Column(String(50), nullable=False)  # api, scanner, telegram, etc.
    message = Column(Text, nullable=False)
    details = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class APIRateLimit(Base):
    """API 速率限制"""
    __tablename__ = 'api_rate_limits'
    __table_args__ = (
        UniqueConstraint('api_name', 'endpoint', 'window_start'),
        Index('idx_api_rate_limits_window', 'api_name', 'window_start'),
    )

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    api_name = Column(String(50), nullable=False)  # fubon_api, telegram_api
    endpoint = Column(String(100))
    request_count = Column(Integer, default=0)
    window_start = Column(DateTime(timezone=True), nullable=False)
    window_duration_minutes = Column(Integer, default=1)
    created_at = Column(DateTime(timezone=True), server_default=func.now())