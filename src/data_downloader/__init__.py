"""
data_downloader package - backward compatibility shim
"""
from src.infrastructure.market_data.yfinance_client import YFinanceClient

__all__ = ["YFinanceClient"]
