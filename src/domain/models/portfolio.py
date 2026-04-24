"""
Domain models for portfolio management
"""
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Optional, List

from .signal import SignalType


class OrderType(Enum):
    """Order types"""
    MARKET = "MARKET"
    LIMIT = "LIMIT"


class PositionStatus(Enum):
    """Position status"""
    OPEN = "OPEN"
    CLOSED = "CLOSED"


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
    # P3-B/C: profit-protection trailing stop
    # Activate trailing stop only after position is in profit > profit_threshold_pct.
    # Before threshold: only hard stop_loss applies.
    # After threshold: trailing stop ratchets up at profit_trailing_pct from peak.
    profit_threshold_pct: Optional[Decimal] = None   # e.g. Decimal('0.05') = 5%
    profit_trailing_pct: Optional[Decimal] = None    # e.g. Decimal('0.06') = 6% from peak


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
