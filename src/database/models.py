"""
Database models for Taiwan Stock Monitoring Robot - thin re-export shim for backward compatibility
"""
# Re-export from new infrastructure location
from src.infrastructure.persistence.orm_models import (
    Base,
    TimestampMixin,
    Stock,
    StockPrice,
    StockRealtime,
    TechnicalIndicator,
    Alert,
    TelegramUser,
    Portfolio,
    PortfolioHolding,
    Transaction,
    Watchlist,
    SystemLog,
    APIRateLimit,
)

__all__ = [
    "Base",
    "TimestampMixin",
    "Stock",
    "StockPrice",
    "StockRealtime",
    "TechnicalIndicator",
    "Alert",
    "TelegramUser",
    "Portfolio",
    "PortfolioHolding",
    "Transaction",
    "Watchlist",
    "SystemLog",
    "APIRateLimit",
]
