"""
AI analyzer port (abstract interface)
"""
from abc import ABC, abstractmethod
from typing import List


class IAIAnalyzer(ABC):
    """Abstract interface for AI analysis services"""

    @abstractmethod
    def analyze_signals(
        self,
        signals_result: dict,
        max_stocks_per_batch: int = 50,
    ) -> dict:
        """
        Analyze trading signals and re-classify stocks.

        Args:
            signals_result: Dict with 'buy', 'watch' lists and 'target_date'
            max_stocks_per_batch: Maximum stocks to process per API call

        Returns:
            Dict with 'strong_buy', 'buy', 'watch', 'avoid' lists and 'target_date'
        """

    @abstractmethod
    def format_for_telegram(self, result: dict) -> List[str]:
        """
        Format analysis result for Telegram messages.

        Args:
            result: Analysis result dict

        Returns:
            List of message strings (auto-split for Telegram limits)
        """
