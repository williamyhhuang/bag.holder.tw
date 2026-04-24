"""
Domain model for backtest results
"""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import List

from .portfolio import Position, Portfolio


@dataclass
class BacktestResult:
    """Backtest result data structure"""
    start_date: date
    end_date: date
    initial_capital: Decimal
    final_capital: Decimal
    total_return: Decimal
    total_return_pct: Decimal
    annualized_return: Decimal
    max_drawdown: Decimal
    sharpe_ratio: Decimal
    win_rate: Decimal
    profit_factor: Decimal
    total_trades: int
    winning_trades: int
    losing_trades: int
    avg_win: Decimal
    avg_loss: Decimal
    largest_win: Decimal
    largest_loss: Decimal
    avg_holding_period: Decimal
    trades: List[Position]
    portfolio_history: List[Portfolio]
