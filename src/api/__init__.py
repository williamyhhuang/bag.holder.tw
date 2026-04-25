"""
api package - backward compatibility shim
"""
from src.infrastructure.market_data.fubon_client import FubonClient, FubonAPIError

__all__ = ['FubonClient', 'FubonAPIError']
