"""
RunBacktestUseCase - orchestrates the backtesting workflow
"""
from datetime import date
from decimal import Decimal
from typing import Optional

from ...backtest.engine import BacktestEngine
from ...backtest.strategy import TechnicalStrategy
from ...backtest.data_source import YFinanceDataSource
from ...domain.models.backtest_result import BacktestResult
from ...utils.logger import get_logger

logger = get_logger(__name__)


class RunBacktestUseCase:
    """Use case for running backtests"""

    def __init__(
        self,
        engine: BacktestEngine = None,
        data_source: YFinanceDataSource = None,
        strategy: TechnicalStrategy = None,
    ):
        self._data_source = data_source or YFinanceDataSource()
        self._strategy = strategy or TechnicalStrategy()
        self._engine = engine or BacktestEngine(
            data_source=self._data_source,
            strategy=self._strategy,
        )

    def execute(
        self,
        symbols: list,
        start_date: date,
        end_date: date,
        initial_capital: Decimal = Decimal("1000000"),
    ) -> BacktestResult:
        """
        Execute a backtest for given symbols and date range.

        Args:
            symbols: List of stock symbols to backtest
            start_date: Backtest start date
            end_date: Backtest end date
            initial_capital: Starting capital amount

        Returns:
            BacktestResult with performance metrics
        """
        return self._engine.run(
            symbols=symbols,
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital,
        )
