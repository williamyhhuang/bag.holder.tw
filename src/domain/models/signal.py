"""
Domain models for trading signals
"""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum

from .stock import TechnicalIndicators


class SignalType(Enum):
    """Trading signal types"""
    BUY = "BUY"
    SELL = "SELL"
    WATCH = "WATCH"


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
