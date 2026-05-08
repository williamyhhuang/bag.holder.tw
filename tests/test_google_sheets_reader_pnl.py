"""
Unit tests for GoogleSheetsReader.get_pnl_summary()
"""
import pytest
from unittest.mock import MagicMock, patch


def _make_reader_with_records(records):
    """Return a GoogleSheetsReader whose worksheet returns the given records."""
    from src.infrastructure.persistence.google_sheets_reader import GoogleSheetsReader
    reader = GoogleSheetsReader()
    mock_ws = MagicMock()
    mock_ws.get_all_records.return_value = records
    reader._worksheet = mock_ws
    return reader


class TestGetPnlSummaryEmpty:
    def test_empty_sheet_returns_empty_summary(self):
        reader = _make_reader_with_records([])
        summary = reader.get_pnl_summary()
        assert summary is not None
        assert summary.unrealized == []
        assert summary.realized == []
        assert summary.total_unrealized_pnl == 0.0
        assert summary.total_realized_pnl == 0.0


class TestGetPnlSummaryUnrealized:
    def _records(self):
        return [
            {
                "timestamp": "2026-04-01T10:00:00",
                "date": "2026-04-01",
                "stock_code": "2330",
                "stock_name": "台積電",
                "action": "買入",
                "price": 150.0,
                "quantity": 1000,
            }
        ]

    def test_open_position_in_unrealized(self):
        reader = _make_reader_with_records(self._records())
        with patch.object(reader, "_fetch_current_prices", return_value={"2330": 180.0}):
            summary = reader.get_pnl_summary()

        assert len(summary.unrealized) == 1
        pos = summary.unrealized[0]
        assert pos.stock_code == "2330"
        assert pos.stock_name == "台積電"
        assert pos.entry_price == pytest.approx(150.0)
        assert pos.current_price == pytest.approx(180.0)
        assert pos.quantity == 1000
        assert pos.unrealized_pnl == pytest.approx(30000.0)
        assert pos.pnl_pct == pytest.approx(20.0)

    def test_unrealized_pnl_negative_when_price_drops(self):
        reader = _make_reader_with_records(self._records())
        with patch.object(reader, "_fetch_current_prices", return_value={"2330": 130.0}):
            summary = reader.get_pnl_summary()

        pos = summary.unrealized[0]
        assert pos.unrealized_pnl == pytest.approx(-20000.0)
        assert pos.pnl_pct < 0

    def test_no_current_price_yields_zero_pnl(self):
        reader = _make_reader_with_records(self._records())
        with patch.object(reader, "_fetch_current_prices", return_value={"2330": 0.0}):
            summary = reader.get_pnl_summary()

        pos = summary.unrealized[0]
        assert pos.current_price == 0.0
        assert pos.unrealized_pnl == 0.0

    def test_vwap_for_multiple_buy_lots(self):
        records = [
            {
                "timestamp": "2026-04-01T10:00:00",
                "date": "2026-04-01",
                "stock_code": "2330",
                "stock_name": "台積電",
                "action": "買入",
                "price": 100.0,
                "quantity": 1000,
            },
            {
                "timestamp": "2026-04-02T10:00:00",
                "date": "2026-04-02",
                "stock_code": "2330",
                "stock_name": "台積電",
                "action": "買入",
                "price": 120.0,
                "quantity": 1000,
            },
        ]
        reader = _make_reader_with_records(records)
        with patch.object(reader, "_fetch_current_prices", return_value={"2330": 110.0}):
            summary = reader.get_pnl_summary()

        pos = summary.unrealized[0]
        assert pos.entry_price == pytest.approx(110.0)   # VWAP = (100*1000+120*1000)/2000
        assert pos.quantity == 2000
        assert pos.unrealized_pnl == pytest.approx(0.0)


class TestGetPnlSummaryRealized:
    def test_buy_then_sell_creates_realized_trade(self):
        records = [
            {
                "timestamp": "2026-04-01T10:00:00",
                "date": "2026-04-01",
                "stock_code": "2330",
                "stock_name": "台積電",
                "action": "買入",
                "price": 150.0,
                "quantity": 1000,
            },
            {
                "timestamp": "2026-04-10T10:00:00",
                "date": "2026-04-10",
                "stock_code": "2330",
                "stock_name": "台積電",
                "action": "賣出",
                "price": 170.0,
                "quantity": 1000,
            },
        ]
        reader = _make_reader_with_records(records)
        with patch.object(reader, "_fetch_current_prices", return_value={}):
            summary = reader.get_pnl_summary()

        assert len(summary.realized) == 1
        trade = summary.realized[0]
        assert trade.stock_code == "2330"
        assert trade.entry_price == pytest.approx(150.0)
        assert trade.exit_price == pytest.approx(170.0)
        assert trade.quantity == 1000
        assert trade.realized_pnl == pytest.approx(20000.0)
        assert abs(trade.pnl_pct - 13.33) < 0.01
        assert len(summary.unrealized) == 0

    def test_partial_sell_leaves_open_position(self):
        records = [
            {
                "timestamp": "2026-04-01T09:00:00",
                "date": "2026-04-01",
                "stock_code": "2330",
                "stock_name": "台積電",
                "action": "買入",
                "price": 100.0,
                "quantity": 2000,
            },
            {
                "timestamp": "2026-04-05T09:00:00",
                "date": "2026-04-05",
                "stock_code": "2330",
                "stock_name": "台積電",
                "action": "賣出",
                "price": 120.0,
                "quantity": 1000,
            },
        ]
        reader = _make_reader_with_records(records)
        with patch.object(reader, "_fetch_current_prices", return_value={"2330": 130.0}):
            summary = reader.get_pnl_summary()

        assert len(summary.realized) == 1
        assert summary.realized[0].realized_pnl == pytest.approx(20000.0)

        assert len(summary.unrealized) == 1
        pos = summary.unrealized[0]
        assert pos.quantity == 1000
        assert pos.unrealized_pnl == pytest.approx(30000.0)

    def test_multiple_cycles_same_stock(self):
        records = [
            # Cycle 1: buy 1000 at 100, sell 1000 at 110 → +10000
            {
                "timestamp": "2026-03-01T09:00:00",
                "date": "2026-03-01",
                "stock_code": "2330",
                "stock_name": "台積電",
                "action": "買入",
                "price": 100.0,
                "quantity": 1000,
            },
            {
                "timestamp": "2026-03-10T09:00:00",
                "date": "2026-03-10",
                "stock_code": "2330",
                "stock_name": "台積電",
                "action": "賣出",
                "price": 110.0,
                "quantity": 1000,
            },
            # Cycle 2: buy 1000 at 120, still open
            {
                "timestamp": "2026-04-01T09:00:00",
                "date": "2026-04-01",
                "stock_code": "2330",
                "stock_name": "台積電",
                "action": "買入",
                "price": 120.0,
                "quantity": 1000,
            },
        ]
        reader = _make_reader_with_records(records)
        with patch.object(reader, "_fetch_current_prices", return_value={"2330": 130.0}):
            summary = reader.get_pnl_summary()

        assert len(summary.realized) == 1
        assert summary.realized[0].realized_pnl == pytest.approx(10000.0)

        assert len(summary.unrealized) == 1
        assert summary.unrealized[0].unrealized_pnl == pytest.approx(10000.0)

        assert summary.total_realized_pnl == pytest.approx(10000.0)
        assert summary.total_unrealized_pnl == pytest.approx(10000.0)

    def test_total_pnl_aggregation(self):
        records = [
            {
                "timestamp": "2026-04-01T10:00:00",
                "date": "2026-04-01",
                "stock_code": "2330",
                "stock_name": "台積電",
                "action": "買入",
                "price": 100.0,
                "quantity": 1000,
            },
            {
                "timestamp": "2026-04-10T10:00:00",
                "date": "2026-04-10",
                "stock_code": "2330",
                "stock_name": "台積電",
                "action": "賣出",
                "price": 90.0,
                "quantity": 1000,
            },
        ]
        reader = _make_reader_with_records(records)
        with patch.object(reader, "_fetch_current_prices", return_value={}):
            summary = reader.get_pnl_summary()

        assert summary.total_realized_pnl == pytest.approx(-10000.0)
        assert summary.total_unrealized_pnl == 0.0


class TestGetPnlSummaryWorksheetError:
    def test_worksheet_error_returns_none(self):
        from src.infrastructure.persistence.google_sheets_reader import GoogleSheetsReader
        reader = GoogleSheetsReader()
        mock_ws = MagicMock()
        mock_ws.get_all_records.side_effect = Exception("network error")
        reader._worksheet = mock_ws

        summary = reader.get_pnl_summary()
        assert summary is None
