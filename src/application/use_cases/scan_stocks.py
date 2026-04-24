"""
ScanStocksUseCase - orchestrates the stock scanning workflow
"""
from ...scanner.signals_scanner import SignalsScanner
from ...utils.logger import get_logger

logger = get_logger(__name__)


class ScanStocksUseCase:
    """Use case for scanning stocks using P1 strategy"""

    def __init__(self, scanner: SignalsScanner = None):
        self._scanner = scanner or SignalsScanner()

    def execute(
        self,
        target_date=None,
        send_telegram: bool = False,
        ai_filter: bool = False,
    ) -> dict:
        """
        Execute stock scan for a given date.

        Args:
            target_date: Target date for scanning (defaults to latest trading day)
            send_telegram: Whether to send results via Telegram
            ai_filter: Whether to apply AI second-pass filtering

        Returns:
            Dict with 'buy', 'sell', 'watch' lists and 'target_date'
        """
        return self._scanner.scan(
            target_date=target_date,
            send_telegram=send_telegram,
            ai_filter=ai_filter,
        )
