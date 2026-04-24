"""
Market data provider port (abstract interface)
"""
from abc import ABC, abstractmethod
from datetime import date, datetime
from typing import List, Optional

from ..models.stock import StockData


class IMarketDataProvider(ABC):
    """Abstract interface for market data providers"""

    @abstractmethod
    def get_stock_data(
        self,
        symbol: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Optional[List[StockData]]:
        """
        Fetch historical stock data for a symbol.

        Args:
            symbol: Stock symbol (e.g. "2330.TW")
            start_date: Start date for data
            end_date: End date for data

        Returns:
            List of StockData or None if not available
        """

    @abstractmethod
    def get_stock_list(self, market: str = "TSE") -> List[str]:
        """
        Get list of stock symbols for a market.

        Args:
            market: Market identifier (TSE, OTC)

        Returns:
            List of stock symbols
        """
