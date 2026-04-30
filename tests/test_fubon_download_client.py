"""
Unit tests for FubonDownloadClient
"""
import os
import tempfile
from datetime import datetime
from unittest.mock import MagicMock, patch, PropertyMock

import pandas as pd
import pytest

from src.infrastructure.market_data.fubon_download_client import (
    FubonDownloadClient,
    FubonDownloadError,
    _to_fubon_symbol,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_candle_result(rows: list):
    """Build a mock SDK candles response."""
    result = MagicMock()
    result.data = rows
    return result


def _make_client(logged_in=True) -> FubonDownloadClient:
    """Return a FubonDownloadClient with mocked internals (no real SDK needed)."""
    client = FubonDownloadClient(
        user_id="TEST_USER",
        api_key="TEST_KEY",
        cert_path="/fake/cert.p12",
        cert_password="TEST_PASS",
    )
    if logged_in:
        client._logged_in = True
        client._reststock = MagicMock()
    return client


# ─────────────────────────────────────────────────────────────────────────────
# Symbol conversion
# ─────────────────────────────────────────────────────────────────────────────

class TestToFubonSymbol:
    def test_tse_symbol(self):
        assert _to_fubon_symbol("2330.TW") == "2330"

    def test_otc_symbol(self):
        assert _to_fubon_symbol("6277.TWO") == "6277"

    def test_plain_symbol(self):
        assert _to_fubon_symbol("0050") == "0050"


# ─────────────────────────────────────────────────────────────────────────────
# Login
# ─────────────────────────────────────────────────────────────────────────────

class TestFubonDownloadClientLogin:
    def test_login_with_api_key_success(self):
        client = FubonDownloadClient(
            user_id="U1", api_key="K1", cert_path="/c.p12", cert_password="P1"
        )
        mock_sdk = MagicMock()
        mock_sdk.apikey_login.return_value = MagicMock(is_success=True)

        with patch("src.infrastructure.market_data.fubon_download_client.FubonSDK", mock_sdk, create=True):
            with patch("builtins.__import__", side_effect=_import_fubon_neo(mock_sdk)):
                pass  # sdk import is tested below via direct patch

        # Patch the SDK import inside login()
        with patch.dict("sys.modules", {"fubon_neo": MagicMock(), "fubon_neo.sdk": MagicMock()}):
            import fubon_neo.sdk as sdk_mod
            sdk_mod.FubonSDK = MagicMock(return_value=mock_sdk)
            mock_sdk.apikey_login.return_value = MagicMock(is_success=True)
            mock_sdk.init_realtime = MagicMock()
            mock_sdk.marketdata.rest_client.stock = MagicMock()

            client.login()

        assert client._logged_in

    def test_login_raises_without_credentials(self):
        client = FubonDownloadClient()
        # Override any values that may have been pulled from settings
        client.user_id = None
        client.api_key = None
        client.password = None
        client.cert_path = None
        with pytest.raises(FubonDownloadError, match="auth not configured"):
            client.login()

    def test_login_raises_on_sdk_not_installed(self):
        client = FubonDownloadClient(
            user_id="U", api_key="K", cert_path="/c.p12"
        )
        with patch.dict("sys.modules", {"fubon_neo": None, "fubon_neo.sdk": None}):
            with pytest.raises((FubonDownloadError, ImportError)):
                client.login()


def _import_fubon_neo(mock_sdk):
    """Helper – not actually used."""
    pass


# ─────────────────────────────────────────────────────────────────────────────
# get_stock_data
# ─────────────────────────────────────────────────────────────────────────────

class TestGetStockData:
    CANDLES = [
        {"date": "2024-01-02", "open": 100.0, "high": 102.0, "low": 99.0, "close": 101.0, "volume": 1_000_000},
        {"date": "2024-01-03", "open": 101.0, "high": 103.0, "low": 100.0, "close": 102.0, "volume": 1_200_000},
    ]

    def test_returns_dataframe(self):
        client = _make_client()
        client._reststock.historical.candles.return_value = _make_candle_result(self.CANDLES)

        df = client.get_stock_data(
            "2330.TW",
            datetime(2024, 1, 2),
            datetime(2024, 1, 3),
        )

        assert df is not None
        assert len(df) == 2
        assert list(df.columns) >= ["date", "open", "high", "low", "close", "volume", "symbol"]

    def test_symbol_column_uses_yfinance_format(self):
        client = _make_client()
        client._reststock.historical.candles.return_value = _make_candle_result(self.CANDLES)

        df = client.get_stock_data("2330.TW", datetime(2024, 1, 2), datetime(2024, 1, 3))

        assert (df["symbol"] == "2330.TW").all()

    def test_api_called_with_fubon_symbol(self):
        client = _make_client()
        client._reststock.historical.candles.return_value = _make_candle_result(self.CANDLES)

        client.get_stock_data("2330.TW", datetime(2024, 1, 2), datetime(2024, 1, 3))

        call_kwargs = client._reststock.historical.candles.call_args[1]
        assert call_kwargs["symbol"] == "2330"

    def test_returns_none_when_no_data(self):
        client = _make_client()
        client._reststock.historical.candles.return_value = _make_candle_result([])

        result = client.get_stock_data("2330.TW", datetime(2024, 1, 2), datetime(2024, 1, 3))
        assert result is None

    def test_returns_none_on_api_error(self):
        client = _make_client()
        client._reststock.historical.candles.side_effect = Exception("API error")

        result = client.get_stock_data("2330.TW", datetime(2024, 1, 2), datetime(2024, 1, 3))
        assert result is None

    def test_sorted_by_date_ascending(self):
        candles_desc = list(reversed(self.CANDLES))
        client = _make_client()
        client._reststock.historical.candles.return_value = _make_candle_result(candles_desc)

        df = client.get_stock_data("2330.TW", datetime(2024, 1, 2), datetime(2024, 1, 3))

        assert df["date"].is_monotonic_increasing

    def test_otc_symbol_stripped_correctly(self):
        client = _make_client()
        client._reststock.historical.candles.return_value = _make_candle_result(self.CANDLES)

        client.get_stock_data("6277.TWO", datetime(2024, 1, 2), datetime(2024, 1, 3))

        call_kwargs = client._reststock.historical.candles.call_args[1]
        assert call_kwargs["symbol"] == "6277"


# ─────────────────────────────────────────────────────────────────────────────
# download_all_stocks
# ─────────────────────────────────────────────────────────────────────────────

class TestDownloadAllStocks:
    CANDLES = [
        {"date": "2024-01-02", "open": 100.0, "high": 102.0, "low": 99.0, "close": 101.0, "volume": 1_000_000},
    ]

    def test_returns_success_count(self):
        client = _make_client()
        symbols = ["2330.TW", "2317.TW"]

        with patch.object(client, "get_tse_listed_stocks", return_value=symbols), \
             patch.object(client, "get_otc_listed_stocks", return_value=[]), \
             patch.object(client, "get_stock_data", return_value=pd.DataFrame(self.CANDLES)), \
             patch.object(client, "save_stock_data", return_value=True), \
             patch.object(client, "get_last_trading_date", return_value=datetime(2024, 1, 1)):

            count = client.download_all_stocks(
                start_date=datetime(2024, 1, 2),
                end_date=datetime(2024, 1, 2),
                markets=["TSE"],
            )

        assert count == 2

    def test_limit_respected(self):
        client = _make_client()
        symbols = [f"{i:04d}.TW" for i in range(1, 11)]

        with patch.object(client, "get_tse_listed_stocks", return_value=symbols), \
             patch.object(client, "get_otc_listed_stocks", return_value=[]), \
             patch.object(client, "get_stock_data", return_value=pd.DataFrame(self.CANDLES)), \
             patch.object(client, "save_stock_data", return_value=True), \
             patch.object(client, "get_last_trading_date", return_value=datetime(2024, 1, 1)):

            count = client.download_all_stocks(
                start_date=datetime(2024, 1, 2),
                end_date=datetime(2024, 1, 2),
                limit=3,
            )

        assert count == 3

    def test_failed_symbol_not_counted(self):
        client = _make_client()
        symbols = ["2330.TW", "FAIL.TW"]

        def fake_get_stock_data(symbol, *args, **kwargs):
            if symbol == "FAIL.TW":
                return None
            return pd.DataFrame(self.CANDLES)

        with patch.object(client, "get_tse_listed_stocks", return_value=symbols), \
             patch.object(client, "get_otc_listed_stocks", return_value=[]), \
             patch.object(client, "get_stock_data", side_effect=fake_get_stock_data), \
             patch.object(client, "save_stock_data", return_value=True), \
             patch.object(client, "get_last_trading_date", return_value=datetime(2024, 1, 1)):

            count = client.download_all_stocks(
                start_date=datetime(2024, 1, 2),
                end_date=datetime(2024, 1, 2),
            )

        assert count == 1

    def test_no_symbols_returns_zero(self):
        client = _make_client()
        with patch.object(client, "get_tse_listed_stocks", return_value=[]), \
             patch.object(client, "get_otc_listed_stocks", return_value=[]):
            count = client.download_all_stocks()
        assert count == 0


# ─────────────────────────────────────────────────────────────────────────────
# download_recent_data
# ─────────────────────────────────────────────────────────────────────────────

class TestDownloadRecentData:
    def test_calls_download_all_stocks(self):
        client = _make_client()
        with patch.object(client, "get_last_trading_date", return_value=datetime(2024, 1, 2)), \
             patch.object(client, "download_all_stocks", return_value=5) as mock_dl:
            result = client.download_recent_data(days_back=1)

        assert result == 5
        mock_dl.assert_called_once()
