"""
Data models for backtesting system
"""
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List, Dict, Any
from enum import Enum


class SignalType(Enum):
    """Trading signal types"""
    BUY = "BUY"
    SELL = "SELL"
    WATCH = "WATCH"


class OrderType(Enum):
    """Order types"""
    MARKET = "MARKET"
    LIMIT = "LIMIT"


class PositionStatus(Enum):
    """Position status"""
    OPEN = "OPEN"
    CLOSED = "CLOSED"


@dataclass
class StockData:
    """Stock price data structure"""
    symbol: str
    date: date
    open_price: Decimal
    high_price: Decimal
    low_price: Decimal
    close_price: Decimal
    volume: int
    adj_close: Optional[Decimal] = None


@dataclass
class TechnicalIndicators:
    """Technical indicators data structure"""
    date: date
    ma5: Optional[Decimal] = None
    ma10: Optional[Decimal] = None
    ma20: Optional[Decimal] = None
    ma60: Optional[Decimal] = None
    rsi14: Optional[Decimal] = None
    macd: Optional[Decimal] = None
    macd_signal: Optional[Decimal] = None
    macd_histogram: Optional[Decimal] = None
    bb_upper: Optional[Decimal] = None
    bb_middle: Optional[Decimal] = None
    bb_lower: Optional[Decimal] = None
    volume_ma20: Optional[int] = None


@dataclass
class TradingSignal:
    """Trading signal data structure"""
    symbol: str
    date: date
    signal_type: SignalType
    signal_name: str
    price: Decimal
    description: str
    strength: str
    indicators: TechnicalIndicators


@dataclass
class Order:
    """Order data structure"""
    order_id: str
    symbol: str
    order_type: OrderType
    signal_type: SignalType
    quantity: int
    price: Decimal
    timestamp: datetime
    executed_price: Optional[Decimal] = None
    executed_quantity: Optional[int] = None
    executed_time: Optional[datetime] = None
    commission: Optional[Decimal] = None
    tax: Optional[Decimal] = None


@dataclass
class Position:
    """Position data structure"""
    symbol: str
    quantity: int
    entry_price: Decimal
    entry_date: date
    current_price: Decimal
    current_date: date
    status: PositionStatus
    stop_loss: Optional[Decimal] = None
    take_profit: Optional[Decimal] = None
    exit_price: Optional[Decimal] = None
    exit_date: Optional[date] = None
    pnl: Optional[Decimal] = None
    pnl_percent: Optional[Decimal] = None
    holding_days: Optional[int] = None
    entry_signal_name: Optional[str] = None
    # P6: per-signal exit overrides (trend signals use wider stop / longer holding)
    max_holding_days_override: Optional[int] = None
    trailing_stop_pct_override: Optional[Decimal] = None
    # P3-B: signal-based exit — exit when one of these sell signal names fires for this symbol
    # None = no signal-based exit (use trailing stop / stop loss only)
    # Decimal('0') for trailing_stop_pct_override = trailing stop disabled (use signal exit instead)
    exit_on_signals: Optional[List[str]] = None


@dataclass
class Portfolio:
    """Portfolio data structure"""
    cash: Decimal
    total_value: Decimal
    positions: List[Position]
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    total_pnl: Decimal
    date: date


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