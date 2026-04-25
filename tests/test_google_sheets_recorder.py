"""
Unit tests for GoogleSheetsRecorder
"""
import pytest
from unittest.mock import MagicMock, patch, PropertyMock


class TestGoogleSheetsRecorderAvailability:
    """Test is_available() logic without real GCP credentials"""

    def test_not_available_when_disabled(self):
        from src.infrastructure.persistence.google_sheets_recorder import GoogleSheetsRecorder

        with patch("src.infrastructure.persistence.google_sheets_recorder.logger"):
            recorder = GoogleSheetsRecorder()

        # settings.google_sheets.enabled = False by default
        assert recorder.is_available() is False

    def test_not_available_missing_spreadsheet_id(self):
        from src.infrastructure.persistence.google_sheets_recorder import GoogleSheetsRecorder

        recorder = GoogleSheetsRecorder()

        mock_cfg = MagicMock()
        mock_cfg.enabled = True
        mock_cfg.spreadsheet_id = None
        mock_cfg.credentials_json = '{"type":"service_account"}'
        mock_cfg.credentials_file = None

        with patch("config.settings.settings") as mock_settings:
            mock_settings.google_sheets = mock_cfg
            assert recorder.is_available() is False

    def test_not_available_missing_credentials(self):
        from src.infrastructure.persistence.google_sheets_recorder import GoogleSheetsRecorder

        recorder = GoogleSheetsRecorder()

        mock_cfg = MagicMock()
        mock_cfg.enabled = True
        mock_cfg.spreadsheet_id = "fake_id"
        mock_cfg.credentials_json = None
        mock_cfg.credentials_file = None

        with patch("config.settings.settings") as mock_settings:
            mock_settings.google_sheets = mock_cfg
            assert recorder.is_available() is False

    def test_available_with_json_credentials(self):
        from src.infrastructure.persistence.google_sheets_recorder import GoogleSheetsRecorder

        recorder = GoogleSheetsRecorder()

        mock_cfg = MagicMock()
        mock_cfg.enabled = True
        mock_cfg.spreadsheet_id = "fake_spreadsheet_id"
        mock_cfg.credentials_json = '{"type":"service_account"}'
        mock_cfg.credentials_file = None

        with patch("config.settings.settings") as mock_settings:
            mock_settings.google_sheets = mock_cfg
            assert recorder.is_available() is True

    def test_available_with_credentials_file(self):
        from src.infrastructure.persistence.google_sheets_recorder import GoogleSheetsRecorder

        recorder = GoogleSheetsRecorder()

        mock_cfg = MagicMock()
        mock_cfg.enabled = True
        mock_cfg.spreadsheet_id = "fake_id"
        mock_cfg.credentials_json = None
        mock_cfg.credentials_file = "/path/to/creds.json"

        with patch("config.settings.settings") as mock_settings:
            mock_settings.google_sheets = mock_cfg
            assert recorder.is_available() is True


class TestGoogleSheetsRecorderWrite:
    """Test record_trade() with mocked gspread"""

    def _make_recorder_with_mock_ws(self):
        from src.infrastructure.persistence.google_sheets_recorder import GoogleSheetsRecorder

        recorder = GoogleSheetsRecorder()
        mock_ws = MagicMock()
        recorder._worksheet = mock_ws
        return recorder, mock_ws

    def test_record_trade_appends_row(self):
        recorder, mock_ws = self._make_recorder_with_mock_ws()
        mock_ws.append_row.return_value = None

        result = recorder.record_trade(
            stock_code="2330",
            action="買入",
            price=150.5,
            quantity=1000,
            notes="test",
        )

        assert result is True
        mock_ws.append_row.assert_called_once()
        row = mock_ws.append_row.call_args[0][0]
        assert row[3] == "2330"
        assert row[4] == "買入"
        assert row[5] == 150.5
        assert row[6] == 1000
        assert row[7] == pytest.approx(150500.0)

    def test_record_trade_returns_false_on_exception(self):
        recorder, mock_ws = self._make_recorder_with_mock_ws()
        mock_ws.append_row.side_effect = Exception("network error")

        result = recorder.record_trade(
            stock_code="2330",
            action="賣出",
            price=160.0,
        )

        assert result is False

    def test_record_trade_default_quantity(self):
        recorder, mock_ws = self._make_recorder_with_mock_ws()
        mock_ws.append_row.return_value = None

        recorder.record_trade(stock_code="2454", action="買入", price=200.0)

        row = mock_ws.append_row.call_args[0][0]
        assert row[6] == 1000  # default quantity
