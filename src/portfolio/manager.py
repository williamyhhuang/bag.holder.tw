"""
portfolio.manager - backward compatibility shim
"""
from src.application.services.portfolio_manager import (
    PortfolioManager, PerformanceAnalyzer, HoldingInfo, PortfolioSummary,
)

__all__ = ['PortfolioManager', 'PerformanceAnalyzer', 'HoldingInfo', 'PortfolioSummary']
