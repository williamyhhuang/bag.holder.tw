"""
api.fubon_client - backward compatibility shim
"""
from src.infrastructure.market_data.fubon_client import (
    FubonClient, FubonAPIError, get_near_month_symbol, MONTH_CODES,
)

__all__ = ["FubonClient", "FubonAPIError", "get_near_month_symbol", "MONTH_CODES"]
