"""
YFinance market data adapter - implements IMarketDataProvider port
"""
from datetime import datetime
from typing import List, Optional

from ...domain.ports.market_data_port import IMarketDataProvider
from ...domain.models.stock import StockData
from .yfinance_client import YFinanceClient


class YFinanceAdapter(IMarketDataProvider):
    """YFinance implementation of IMarketDataProvider"""

    def __init__(self):
        self._client = YFinanceClient()

    def get_stock_data(
        self,
        symbol: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Optional[List[StockData]]:
        """Fetch historical stock data for a symbol via yfinance."""
        df = self._client.get_stock_data(symbol, start_date, end_date)
        if df is None or df.empty:
            return None

        result = []
        for _, row in df.iterrows():
            from decimal import Decimal
            result.append(StockData(
                symbol=symbol,
                date=row['date'].date() if hasattr(row['date'], 'date') else row['date'],
                open_price=Decimal(str(row.get('open', 0))),
                high_price=Decimal(str(row.get('high', 0))),
                low_price=Decimal(str(row.get('low', 0))),
                close_price=Decimal(str(row.get('close', 0))),
                volume=int(row.get('volume', 0)),
            ))
        return result

    def get_stock_list(self, market: str = "TSE") -> List[str]:
        """Get list of stock symbols for a market."""
        if market.upper() == "TSE":
            return self._client.get_tse_listed_stocks()
        elif market.upper() == "OTC":
            return self._client.get_otc_listed_stocks()
        return []
