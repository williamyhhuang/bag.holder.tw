"""
Fubon market data adapter - implements IMarketDataProvider port
"""
from datetime import datetime
from typing import List, Optional

from ...domain.ports.market_data_port import IMarketDataProvider
from ...domain.models.stock import StockData


class FubonAdapter(IMarketDataProvider):
    """Fubon Securities implementation of IMarketDataProvider"""

    def __init__(self):
        from ...api.fubon_client import FubonClient
        self._client = FubonClient()

    def get_stock_data(
        self,
        symbol: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Optional[List[StockData]]:
        """Fetch historical stock data for a symbol via Fubon API."""
        # Fubon client primarily handles realtime/futures data
        # Historical data fetch would need specific implementation
        raise NotImplementedError("Fubon adapter historical data not yet implemented")

    def get_stock_list(self, market: str = "TSE") -> List[str]:
        """Get list of stock symbols for a market."""
        raise NotImplementedError("Fubon adapter stock list not yet implemented")
