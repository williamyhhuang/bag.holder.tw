"""
DownloadDataUseCase - orchestrates the data download workflow
"""
from datetime import datetime
from typing import List, Optional

from ...utils.logger import get_logger

logger = get_logger(__name__)


def _make_client(source: str):
    """Return the appropriate download client for the given source name."""
    if source == "fubon":
        from ...infrastructure.market_data.fubon_download_client import (
            FubonDownloadClient,
            FubonDownloadError,
        )
        client = FubonDownloadClient()
        client.login()  # raises FubonDownloadError on failure
        return client
    else:
        from ...infrastructure.market_data.yfinance_client import YFinanceClient
        return YFinanceClient()


class DownloadDataUseCase:
    """Use case for downloading market data"""

    def __init__(self, client=None, source: str = "yfinance"):
        if client is not None:
            self._client = client
        else:
            from config.settings import settings
            effective_source = source or settings.download.data_source
            self._client = _make_client(effective_source)

    def execute(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        markets: Optional[List[str]] = None,
        limit: Optional[int] = None,
    ) -> int:
        """
        Execute data download for specified markets and date range.

        Args:
            start_date: Start date for data download
            end_date: End date for data download
            markets: List of markets to download ("TSE", "OTC")
            limit: Maximum number of stocks to download

        Returns:
            Number of stocks successfully downloaded
        """
        return self._client.download_all_stocks(
            start_date=start_date,
            end_date=end_date,
            markets=markets,
            limit=limit,
        )

    def execute_recent(self, days_back: int = 2) -> int:
        """
        Download recent trading data.

        Args:
            days_back: Number of days back to download

        Returns:
            Number of stocks successfully downloaded
        """
        return self._client.download_recent_data(days_back=days_back)
