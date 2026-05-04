"""
Unit tests for GoogleSheetsReader.get_open_positions() and HoldingsChecker
"""
import pytest
from datetime import date, timedelta
from unittest.mock import MagicMock, patch


# ── GoogleSheetsReader Tests ──────────────────────────────────────────────────

class TestGetOpenPositions:
    """Test GoogleSheetsReader.get_open_positions()"""

    def _make_reader_with_records(self, records: list) -> object:
        """Build a GoogleSheetsReader with mocked worksheet returning given records"""
        from src.infrastructure.persistence.google_sheets_reader import GoogleSheetsReader
        reader = GoogleSheetsReader()
        mock_ws = MagicMock()
        mock_ws.get_all_records.return_value = records
        reader._worksheet = mock_ws
        return reader

    def test_basic_open_position(self):
        """一筆買入，無賣出 → open"""
        reader = self._make_reader_with_records([
            {
                "timestamp": "2024-01-10T09:00:00+08:00",
                "date": "2024-01-10",
                "stock_code": "2330",
                "action": "買入",
                "price": 850.0,
                "quantity": 1000,
            }
        ])
        positions = reader.get_open_positions()
        assert len(positions) == 1
        assert positions[0].stock_code == "2330"
        assert positions[0].entry_price == 850.0
        assert positions[0].entry_date == "2024-01-10"
        assert positions[0].quantity == 1000

    def test_closed_position(self):
        """買入後賣出（最後是賣出）→ closed，不回傳"""
        reader = self._make_reader_with_records([
            {
                "timestamp": "2024-01-10T09:00:00+08:00",
                "date": "2024-01-10",
                "stock_code": "2330",
                "action": "買入",
                "price": 850.0,
                "quantity": 1000,
            },
            {
                "timestamp": "2024-01-20T09:00:00+08:00",
                "date": "2024-01-20",
                "stock_code": "2330",
                "action": "賣出",
                "price": 900.0,
                "quantity": 1000,
            },
        ])
        positions = reader.get_open_positions()
        assert len(positions) == 0

    def test_multiple_rounds_buy_sell_buy(self):
        """買→賣→買（最後是買入）→ open"""
        reader = self._make_reader_with_records([
            {
                "timestamp": "2024-01-05T09:00:00+08:00",
                "date": "2024-01-05",
                "stock_code": "2454",
                "action": "買入",
                "price": 700.0,
                "quantity": 1000,
            },
            {
                "timestamp": "2024-01-15T09:00:00+08:00",
                "date": "2024-01-15",
                "stock_code": "2454",
                "action": "賣出",
                "price": 750.0,
                "quantity": 1000,
            },
            {
                "timestamp": "2024-02-01T09:00:00+08:00",
                "date": "2024-02-01",
                "stock_code": "2454",
                "action": "買入",
                "price": 720.0,
                "quantity": 1000,
            },
        ])
        positions = reader.get_open_positions()
        assert len(positions) == 1
        assert positions[0].stock_code == "2454"
        assert positions[0].entry_price == 720.0  # 最後一次買入價格
        assert positions[0].entry_date == "2024-02-01"

    def test_mixed_open_and_closed(self):
        """多支股票，部分平倉部分未平倉"""
        reader = self._make_reader_with_records([
            # 2330: 買入 (open)
            {"timestamp": "2024-01-10T09:00:00+08:00", "date": "2024-01-10",
             "stock_code": "2330", "action": "買入", "price": 850.0, "quantity": 1000},
            # 2454: 買入後賣出 (closed)
            {"timestamp": "2024-01-10T09:05:00+08:00", "date": "2024-01-10",
             "stock_code": "2454", "action": "買入", "price": 700.0, "quantity": 1000},
            {"timestamp": "2024-01-20T09:00:00+08:00", "date": "2024-01-20",
             "stock_code": "2454", "action": "賣出", "price": 750.0, "quantity": 1000},
        ])
        positions = reader.get_open_positions()
        codes = {p.stock_code for p in positions}
        assert codes == {"2330"}

    def test_empty_records(self):
        """無記錄 → 回傳空清單"""
        reader = self._make_reader_with_records([])
        positions = reader.get_open_positions()
        assert positions == []

    def test_google_sheets_error(self):
        """無法連線 → 回傳空清單（不拋例外）"""
        from src.infrastructure.persistence.google_sheets_reader import GoogleSheetsReader
        reader = GoogleSheetsReader()
        reader._worksheet = MagicMock()
        reader._worksheet.get_all_records.side_effect = Exception("network error")
        positions = reader.get_open_positions()
        assert positions == []


# ── HoldingsChecker Tests ─────────────────────────────────────────────────────

class TestHoldingsChecker:
    """Test HoldingsChecker.check()"""

    def _make_scan_result(self, sell_list=None, sector_summary=None):
        return {
            'target_date': date(2024, 5, 1),
            'total_scanned': 1000,
            'buy': [],
            'sell': sell_list or [],
            'watch': [],
            'sector_summary': sector_summary or [],
        }

    def test_no_open_positions(self):
        """無持倉 → 直接回傳空結果"""
        from src.application.services.holdings_checker import HoldingsChecker

        with patch('src.application.services.holdings_checker.GoogleSheetsReader') as MockReader:
            MockReader.return_value.get_open_positions.return_value = []
            checker = HoldingsChecker()
            result = checker.check()

        assert result['open_positions'] == []
        assert result['sell_alerts'] == []
        assert result['ai_result'] == {'sell': [], 'watch': [], 'hold': []}

    def test_no_sell_signals_for_holdings(self):
        """持倉股票今日無賣出訊號 → sell_alerts 為空"""
        from src.application.services.holdings_checker import HoldingsChecker
        from src.infrastructure.persistence.google_sheets_reader import HoldingRecord

        holding = HoldingRecord(stock_code='2330', entry_price=800.0, entry_date='2024-04-01', quantity=1000)
        scan = self._make_scan_result(sell_list=[
            # 不同股票的賣出訊號，不在持倉中
            {'symbol': '2454.TW', 'name': '聯發科', 'signal': 'Death Cross', 'price': 700.0, 'rsi': 42.0}
        ])

        with patch('src.application.services.holdings_checker.GoogleSheetsReader') as MockReader, \
             patch('src.application.services.holdings_checker.SignalsScanner') as MockScanner:
            MockReader.return_value.get_open_positions.return_value = [holding]
            MockScanner.return_value.scan_today.return_value = scan
            MockScanner.return_value.sector_analyzer = MagicMock()

            checker = HoldingsChecker()
            result = checker.check()

        assert result['open_positions'] == ['2330']
        assert result['sell_alerts'] == []

    def test_filters_only_open_position_sell_signals(self):
        """持倉股票有賣出訊號 → 只回傳持倉中的賣出訊號"""
        from src.application.services.holdings_checker import HoldingsChecker
        from src.infrastructure.persistence.google_sheets_reader import HoldingRecord

        holding = HoldingRecord(stock_code='2330', entry_price=800.0, entry_date='2024-04-01', quantity=1000)
        sell_list = [
            {'symbol': '2330.TW', 'name': '台積電', 'signal': 'MACD Death Cross', 'price': 820.0, 'rsi': 45.0},
            {'symbol': '2454.TW', 'name': '聯發科', 'signal': 'Death Cross', 'price': 700.0, 'rsi': 42.0},
        ]
        scan = self._make_scan_result(sell_list=sell_list)

        mock_sector_analyzer = MagicMock()
        mock_sector_analyzer.get_stock_sector.return_value = '半導體業'

        with patch('src.application.services.holdings_checker.GoogleSheetsReader') as MockReader, \
             patch('src.application.services.holdings_checker.SignalsScanner') as MockScanner, \
             patch('src.application.services.holdings_checker.MonthlyRevenueLoader') as MockRevenue:
            MockReader.return_value.get_open_positions.return_value = [holding]
            MockScanner.return_value.scan_today.return_value = scan
            MockScanner.return_value.sector_analyzer = mock_sector_analyzer
            MockRevenue.return_value.load.return_value = {}

            # Mock AI to return empty result
            with patch('src.application.services.holdings_checker.settings') as mock_settings:
                mock_settings.ai_analyzer.get_api_key.return_value = None

                checker = HoldingsChecker()
                result = checker.check()

        assert len(result['sell_alerts']) == 1
        assert result['sell_alerts'][0]['symbol'] == '2330.TW'

    def test_pnl_and_holding_days_calculation(self):
        """enrichment：pnl_pct 和 holding_days 計算正確"""
        from src.application.services.holdings_checker import HoldingsChecker
        from src.infrastructure.persistence.google_sheets_reader import HoldingRecord

        entry_date = date(2024, 4, 16)  # 15 days before scan date (May 1)
        holding = HoldingRecord(
            stock_code='2330',
            entry_price=800.0,
            entry_date=str(entry_date),
            quantity=1000,
        )
        sell_list = [
            {'symbol': '2330.TW', 'name': '台積電', 'signal': 'MACD Death Cross', 'price': 840.0, 'rsi': 45.0},
        ]
        scan = self._make_scan_result(sell_list=sell_list)

        mock_sector_analyzer = MagicMock()
        mock_sector_analyzer.get_stock_sector.return_value = '半導體業'

        with patch('src.application.services.holdings_checker.GoogleSheetsReader') as MockReader, \
             patch('src.application.services.holdings_checker.SignalsScanner') as MockScanner, \
             patch('src.application.services.holdings_checker.MonthlyRevenueLoader') as MockRevenue:
            MockReader.return_value.get_open_positions.return_value = [holding]
            MockScanner.return_value.scan_today.return_value = scan
            MockScanner.return_value.sector_analyzer = mock_sector_analyzer
            MockRevenue.return_value.load.return_value = {}

            with patch('src.application.services.holdings_checker.settings') as mock_settings:
                mock_settings.ai_analyzer.get_api_key.return_value = None

                checker = HoldingsChecker()
                result = checker.check()

        alert = result['sell_alerts'][0]
        assert alert['holding_days'] == 15
        assert abs(alert['pnl_pct'] - 5.0) < 0.1  # (840-800)/800 * 100 = 5.0%
        assert alert['entry_price'] == 800.0
