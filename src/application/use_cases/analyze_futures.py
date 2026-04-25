"""
AnalyzeFuturesUseCase - orchestrates the futures analysis workflow
"""
from ...utils.logger import get_logger

logger = get_logger(__name__)


class AnalyzeFuturesUseCase:
    """Use case for analyzing Taiwan futures"""

    def __init__(self, monitor=None):
        self._monitor = monitor

    def _get_monitor(self):
        if self._monitor is None:
            from ..services.futures_monitor import TaiwanFuturesMonitor
            self._monitor = TaiwanFuturesMonitor()
        return self._monitor

    def execute(self, send_telegram: bool = False) -> dict:
        """
        Execute futures analysis.

        Args:
            send_telegram: Whether to send results via Telegram

        Returns:
            Dict with futures analysis results
        """
        monitor = self._get_monitor()
        return monitor.analyze(send_telegram=send_telegram)
