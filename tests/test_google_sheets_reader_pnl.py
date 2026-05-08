"""
Unit tests for GoogleSheetsReader P&L methods.

Covers:
- _parse_pct / _parse_num helpers
- _read_unrealized_sheet
- _read_realized_sheet
- get_pnl_summary (integration of both sheets)
"""
import pytest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helper parser tests
# ---------------------------------------------------------------------------

class TestParsePct:
    def test_formatted_string_positive(self):
        from src.infrastructure.persistence.google_sheets_reader import _parse_pct
        assert _parse_pct("32.74%") == pytest.approx(32.74)

    def test_formatted_string_negative(self):
        from src.infrastructure.persistence.google_sheets_reader import _parse_pct
        assert _parse_pct("-1.31%") == pytest.approx(-1.31)

    def test_decimal_float_positive(self):
        from src.infrastructure.persistence.google_sheets_reader import _parse_pct
        assert _parse_pct(0.3274) == pytest.approx(32.74)

    def test_decimal_float_negative(self):
        from src.infrastructure.persistence.google_sheets_reader import _parse_pct
        assert _parse_pct(-0.0131) == pytest.approx(-1.31)

    def test_zero(self):
        from src.infrastructure.persistence.google_sheets_reader import _parse_pct
        assert _parse_pct(0) == pytest.approx(0.0)
        assert _parse_pct("0%") == pytest.approx(0.0)


class TestParseNum:
    def test_plain_int(self):
        from src.infrastructure.persistence.google_sheets_reader import _parse_num
        assert _parse_num(1000) == pytest.approx(1000.0)

    def test_plain_float(self):
        from src.infrastructure.persistence.google_sheets_reader import _parse_num
        assert _parse_num(156.04) == pytest.approx(156.04)

    def test_formatted_string_with_comma(self):
        from src.infrastructure.persistence.google_sheets_reader import _parse_num
        assert _parse_num("1,000") == pytest.approx(1000.0)

    def test_negative_with_comma(self):
        from src.infrastructure.persistence.google_sheets_reader import _parse_num
        assert _parse_num("-15,000") == pytest.approx(-15000.0)

    def test_empty_string_returns_default(self):
        from src.infrastructure.persistence.google_sheets_reader import _parse_num
        assert _parse_num("", default=0.0) == 0.0

    def test_none_returns_default(self):
        from src.infrastructure.persistence.google_sheets_reader import _parse_num
        assert _parse_num(None, default=99.0) == 99.0


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_reader():
    from src.infrastructure.persistence.google_sheets_reader import GoogleSheetsReader
    reader = GoogleSheetsReader()
    # Bypass _connect() by injecting a fake spreadsheet
    reader._spreadsheet = MagicMock()
    return reader


UNREALIZED_RECORDS = [
    {"股票代號": "3042", "股票名稱": "晶技", "持倉股數": 1000,
     "平均成本(元)": 156.04, "即時股價": 154.0,
     "未實現損益(元)": -2040, "報酬率": "-1.31%"},
    {"股票代號": "2330", "股票名稱": "台積電", "持倉股數": 12,
     "平均成本(元)": 1965.0, "即時股價": 2290.0,
     "未實現損益(元)": 3900, "報酬率": "16.54%"},
    # Empty row (should be skipped)
    {"股票代號": "", "股票名稱": "", "持倉股數": "",
     "平均成本(元)": "", "即時股價": "", "未實現損益(元)": "", "報酬率": ""},
]

REALIZED_RECORDS = [
    {"股票代號": "6147", "股票名稱": "頎邦", "賣出股數": 1000,
     "買入均價(元)": 129.58, "賣出均價(元)": 172.0,
     "出場日期": "2026-05-06", "已實現損益(元)": 42420, "報酬率": "32.74%"},
    {"股票代號": "8064", "股票名稱": "東捷", "賣出股數": 1000,
     "買入均價(元)": 123.0, "賣出均價(元)": 108.0,
     "出場日期": "2026-05-08", "已實現損益(元)": -15000, "報酬率": "-12.20%"},
    # Empty row
    {"股票代號": "", "股票名稱": "", "賣出股數": "",
     "買入均價(元)": "", "賣出均價(元)": "",
     "出場日期": "", "已實現損益(元)": "", "報酬率": ""},
]


# ---------------------------------------------------------------------------
# _read_unrealized_sheet
# ---------------------------------------------------------------------------

class TestReadUnrealizedSheet:
    def _reader_with_records(self, records):
        reader = _make_reader()
        mock_ws = MagicMock()
        mock_ws.get_all_records.return_value = records
        reader._unrealized_ws = mock_ws
        return reader

    def test_parses_positions(self):
        reader = self._reader_with_records(UNREALIZED_RECORDS)
        with patch("src.infrastructure.persistence.google_sheets_reader.GoogleSheetsReader._unrealized_worksheet",
                   return_value=reader._unrealized_ws):
            result = reader._read_unrealized_sheet()

        assert result is not None
        assert len(result) == 2  # empty row skipped

    def test_values_parsed_correctly(self):
        reader = self._reader_with_records(UNREALIZED_RECORDS)
        with patch("src.infrastructure.persistence.google_sheets_reader.GoogleSheetsReader._unrealized_worksheet",
                   return_value=reader._unrealized_ws):
            result = reader._read_unrealized_sheet()

        pos = result[0]
        assert pos.stock_code == "3042"
        assert pos.stock_name == "晶技"
        assert pos.quantity == 1000
        assert pos.entry_price == pytest.approx(156.04)
        assert pos.current_price == pytest.approx(154.0)
        assert pos.unrealized_pnl == pytest.approx(-2040.0)
        assert pos.pnl_pct == pytest.approx(-1.31)

    def test_returns_none_on_worksheet_error(self):
        reader = _make_reader()
        mock_ws = MagicMock()
        mock_ws.get_all_records.side_effect = Exception("network error")
        reader._unrealized_ws = mock_ws
        with patch("src.infrastructure.persistence.google_sheets_reader.GoogleSheetsReader._unrealized_worksheet",
                   return_value=mock_ws):
            result = reader._read_unrealized_sheet()
        assert result is None

    def test_empty_sheet_returns_empty_list(self):
        reader = self._reader_with_records([])
        with patch("src.infrastructure.persistence.google_sheets_reader.GoogleSheetsReader._unrealized_worksheet",
                   return_value=reader._unrealized_ws):
            result = reader._read_unrealized_sheet()
        assert result == []

    def test_decimal_pct_format(self):
        """gspread may return percentage as decimal (0.1654 instead of '16.54%')"""
        records = [{
            "股票代號": "2330", "股票名稱": "台積電", "持倉股數": 12,
            "平均成本(元)": 1965.0, "即時股價": 2290.0,
            "未實現損益(元)": 3900, "報酬率": 0.1654,
        }]
        reader = self._reader_with_records(records)
        with patch("src.infrastructure.persistence.google_sheets_reader.GoogleSheetsReader._unrealized_worksheet",
                   return_value=reader._unrealized_ws):
            result = reader._read_unrealized_sheet()
        assert result[0].pnl_pct == pytest.approx(16.54)


# ---------------------------------------------------------------------------
# _read_realized_sheet
# ---------------------------------------------------------------------------

class TestReadRealizedSheet:
    def _reader_with_records(self, records):
        reader = _make_reader()
        mock_ws = MagicMock()
        mock_ws.get_all_records.return_value = records
        reader._realized_ws = mock_ws
        return reader

    def test_parses_trades(self):
        reader = self._reader_with_records(REALIZED_RECORDS)
        with patch("src.infrastructure.persistence.google_sheets_reader.GoogleSheetsReader._realized_worksheet",
                   return_value=reader._realized_ws):
            result = reader._read_realized_sheet()

        assert result is not None
        assert len(result) == 2  # empty row skipped

    def test_values_parsed_correctly(self):
        reader = self._reader_with_records(REALIZED_RECORDS)
        with patch("src.infrastructure.persistence.google_sheets_reader.GoogleSheetsReader._realized_worksheet",
                   return_value=reader._realized_ws):
            result = reader._read_realized_sheet()

        # Sorted by exit_date desc → 2026-05-08 first
        trade = next(t for t in result if t.stock_code == "6147")
        assert trade.stock_name == "頎邦"
        assert trade.quantity == 1000
        assert trade.entry_price == pytest.approx(129.58)
        assert trade.exit_price == pytest.approx(172.0)
        assert trade.exit_date == "2026-05-06"
        assert trade.realized_pnl == pytest.approx(42420.0)
        assert trade.pnl_pct == pytest.approx(32.74)

    def test_loss_trade_negative_pnl(self):
        reader = self._reader_with_records(REALIZED_RECORDS)
        with patch("src.infrastructure.persistence.google_sheets_reader.GoogleSheetsReader._realized_worksheet",
                   return_value=reader._realized_ws):
            result = reader._read_realized_sheet()

        trade = next(t for t in result if t.stock_code == "8064")
        assert trade.realized_pnl == pytest.approx(-15000.0)
        assert trade.pnl_pct == pytest.approx(-12.20)

    def test_sorted_by_exit_date_desc(self):
        reader = self._reader_with_records(REALIZED_RECORDS)
        with patch("src.infrastructure.persistence.google_sheets_reader.GoogleSheetsReader._realized_worksheet",
                   return_value=reader._realized_ws):
            result = reader._read_realized_sheet()

        dates = [t.exit_date for t in result]
        assert dates == sorted(dates, reverse=True)

    def test_returns_none_on_error(self):
        reader = _make_reader()
        mock_ws = MagicMock()
        mock_ws.get_all_records.side_effect = Exception("timeout")
        reader._realized_ws = mock_ws
        with patch("src.infrastructure.persistence.google_sheets_reader.GoogleSheetsReader._realized_worksheet",
                   return_value=mock_ws):
            result = reader._read_realized_sheet()
        assert result is None


# ---------------------------------------------------------------------------
# get_pnl_summary (integration)
# ---------------------------------------------------------------------------

class TestGetPnlSummary:
    def _make_reader_with_both(self, unrealized_records, realized_records):
        reader = _make_reader()
        mock_u = MagicMock()
        mock_u.get_all_records.return_value = unrealized_records
        reader._unrealized_ws = mock_u
        mock_r = MagicMock()
        mock_r.get_all_records.return_value = realized_records
        reader._realized_ws = mock_r
        return reader

    def test_summary_aggregates_totals(self):
        reader = self._make_reader_with_both(UNREALIZED_RECORDS, REALIZED_RECORDS)
        with patch.object(reader, "_unrealized_worksheet", return_value=reader._unrealized_ws), \
             patch.object(reader, "_realized_worksheet", return_value=reader._realized_ws):
            summary = reader.get_pnl_summary()

        assert summary is not None
        assert len(summary.unrealized) == 2
        assert len(summary.realized) == 2
        # -2040 + 3900 = 1860
        assert summary.total_unrealized_pnl == pytest.approx(1860.0)
        # 42420 + (-15000) = 27420
        assert summary.total_realized_pnl == pytest.approx(27420.0)

    def test_returns_none_when_both_sheets_fail(self):
        reader = _make_reader()
        mock_ws = MagicMock()
        mock_ws.get_all_records.side_effect = Exception("error")
        reader._unrealized_ws = mock_ws
        reader._realized_ws = mock_ws
        with patch.object(reader, "_unrealized_worksheet", return_value=mock_ws), \
             patch.object(reader, "_realized_worksheet", return_value=mock_ws):
            summary = reader.get_pnl_summary()
        assert summary is None

    def test_partial_failure_still_returns_summary(self):
        """If only one sheet fails, still return partial data."""
        reader = _make_reader()
        mock_ok = MagicMock()
        mock_ok.get_all_records.return_value = UNREALIZED_RECORDS
        reader._unrealized_ws = mock_ok
        mock_fail = MagicMock()
        mock_fail.get_all_records.side_effect = Exception("error")
        reader._realized_ws = mock_fail

        with patch.object(reader, "_unrealized_worksheet", return_value=mock_ok), \
             patch.object(reader, "_realized_worksheet", return_value=mock_fail):
            summary = reader.get_pnl_summary()

        assert summary is not None
        assert len(summary.unrealized) == 2
        assert summary.realized == []

    def test_fetch_time_is_set(self):
        reader = self._make_reader_with_both([], [])
        with patch.object(reader, "_unrealized_worksheet", return_value=reader._unrealized_ws), \
             patch.object(reader, "_realized_worksheet", return_value=reader._realized_ws):
            summary = reader.get_pnl_summary()
        assert summary.fetch_time != ""
