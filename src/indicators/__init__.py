"""
indicators package - backward compatibility shim
"""
from src.domain.services.indicator_calculator import IndicatorCalculator
from src.domain.services.signal_detector import SignalDetector

__all__ = ["IndicatorCalculator", "SignalDetector"]
