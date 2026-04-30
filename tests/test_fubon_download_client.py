"""
Unit tests for FubonDownloadClient
"""
import os
import tempfile
import time
from datetime import datetime
from unittest.mock import MagicMock, patch, PropertyMock

import pandas as pd
import pytest

from src.infrastructure.market_data.fubon_download_client import (
    FubonDownloadClient,
    FubonDownloadError,
    _SlidingWindowRateLimiter,
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

class TestDownloadSnapshot:
    SNAPSHOT_TSE = [
        {"type": "EQUITY", "symbol": "2330", "name": "台積電",
         "openPrice": 900, "highPrice": 910, "lowPrice": 895,
         "closePrice": 908, "tradeVolume": 39000},   # 張
        {"type": "EQUITY", "symbol": "2317", "name": "鴻海",
         "openPrice": 150, "highPrice": 152, "lowPrice": 149,
         "closePrice": 151, "tradeVolume": 20000},   # 張
        # Should be filtered out – not 4-digit numeric
        {"type": "EQUITY", "symbol": "00679B", "name": "元大美債20年",
         "openPrice": 30, "highPrice": 30, "lowPrice": 30,
         "closePrice": 30, "tradeVolume": 100},
    ]
    SNAPSHOT_TIB = [
        {"type": "EQUITY", "symbol": "8162", "name": "微矽電子-創",
         "openPrice": 50, "highPrice": 53, "lowPrice": 49,
         "closePrice": 52, "tradeVolume": 1409},     # 張
    ]

    def test_saves_tse_stocks_with_tw_suffix(self):
        client = _make_client()
        client._reststock.snapshot.quotes.return_value = {"data": self.SNAPSHOT_TSE}

        with patch.object(client, "save_stock_data", return_value=True) as mock_save:
            count = client.download_snapshot(markets=["TSE"])

        saved_symbols = [call.args[0] for call in mock_save.call_args_list]
        assert "2330.TW" in saved_symbols
        assert "2317.TW" in saved_symbols

    def test_filters_non_4digit_symbols(self):
        client = _make_client()
        client._reststock.snapshot.quotes.return_value = {"data": self.SNAPSHOT_TSE}

        with patch.object(client, "save_stock_data", return_value=True) as mock_save:
            client.download_snapshot(markets=["TSE"])

        saved_symbols = [call.args[0] for call in mock_save.call_args_list]
        assert "00679B.TW" not in saved_symbols

    def test_volume_converted_from_zhang_to_shares(self):
        """tradeVolume (張) must be multiplied by 1000 to match yfinance (股)."""
        client = _make_client()
        client._reststock.snapshot.quotes.return_value = {"data": self.SNAPSHOT_TSE[:1]}

        captured = {}
        def fake_save(symbol, df):
            captured[symbol] = df
            return True

        with patch.object(client, "save_stock_data", side_effect=fake_save):
            client.download_snapshot(markets=["TSE"])

        saved_vol = int(captured["2330.TW"]["volume"].iloc[0])
        assert saved_vol == 39_000 * 1000  # 張 → 股

    def test_tib_fetched_when_tse_requested(self):
        """Requesting TSE should also query TIB (臺灣創新板) with same .TW suffix."""
        client = _make_client()

        def fake_quotes(market):
            if market == "TSE":
                return {"data": self.SNAPSHOT_TSE}
            if market == "TIB":
                return {"data": self.SNAPSHOT_TIB}
            return {"data": []}

        client._reststock.snapshot.quotes.side_effect = fake_quotes

        with patch.object(client, "save_stock_data", return_value=True) as mock_save:
            count = client.download_snapshot(markets=["TSE"])

        saved_symbols = [call.args[0] for call in mock_save.call_args_list]
        assert "8162.TW" in saved_symbols   # TIB stock got .TW suffix
        assert count == 3  # 2330, 2317, 8162 (00679B filtered)

    def test_otc_uses_two_suffix(self):
        otc_data = [{"type": "EQUITY", "symbol": "6277", "name": "宏正",
                     "openPrice": 50, "highPrice": 51, "lowPrice": 49,
                     "closePrice": 50, "tradeVolume": 500}]
        client = _make_client()
        client._reststock.snapshot.quotes.return_value = {"data": otc_data}

        with patch.object(client, "save_stock_data", return_value=True) as mock_save:
            client.download_snapshot(markets=["OTC"])

        saved_symbols = [call.args[0] for call in mock_save.call_args_list]
        assert "6277.TWO" in saved_symbols

    def test_snapshot_df_has_correct_columns(self):
        client = _make_client()
        client._reststock.snapshot.quotes.return_value = {"data": self.SNAPSHOT_TSE[:1]}

        captured = {}
        def fake_save(symbol, df):
            captured[symbol] = df
            return True

        with patch.object(client, "save_stock_data", side_effect=fake_save):
            client.download_snapshot(markets=["TSE"])

        df = captured["2330.TW"]
        for col in ("date", "open", "high", "low", "close", "volume", "symbol"):
            assert col in df.columns

    def test_returns_success_count(self):
        client = _make_client()

        def fake_quotes(market):
            if market == "TSE":
                return {"data": self.SNAPSHOT_TSE}
            return {"data": []}

        client._reststock.snapshot.quotes.side_effect = fake_quotes

        with patch.object(client, "save_stock_data", return_value=True):
            count = client.download_snapshot(markets=["TSE"])

        assert count == 2  # 00679B filtered out, TIB returns empty


class TestSlidingWindowRateLimiter:
    def test_allows_up_to_max_requests_immediately(self):
        limiter = _SlidingWindowRateLimiter(max_requests=5, window=60.0)
        start = time.monotonic()
        for _ in range(5):
            limiter.acquire()
        elapsed = time.monotonic() - start
        assert elapsed < 1.0, "First 5 requests should be immediate"

    def test_blocks_when_limit_reached(self):
        limiter = _SlidingWindowRateLimiter(max_requests=2, window=1.0)
        limiter.acquire()
        limiter.acquire()
        start = time.monotonic()
        limiter.acquire()  # 3rd request should wait ~1s
        elapsed = time.monotonic() - start
        assert elapsed >= 0.8, f"Should have waited ~1s, waited {elapsed:.2f}s"

    def test_concurrent_threads_respect_limit(self):
        """N concurrent threads should never exceed max_requests in any window."""
        import threading

        max_req = 5
        window = 1.0
        limiter = _SlidingWindowRateLimiter(max_requests=max_req, window=window)
        timestamps = []
        lock = threading.Lock()

        def worker():
            limiter.acquire()
            with lock:
                timestamps.append(time.monotonic())

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        timestamps.sort()
        # Sliding check: no window of *window* seconds should contain more than max_req
        for i in range(len(timestamps)):
            count = sum(1 for ts in timestamps if timestamps[i] <= ts < timestamps[i] + window)
            assert count <= max_req, f"Rate limit exceeded: {count} requests in {window}s"


class TestDownloadRecentData:
    def test_single_day_uses_snapshot(self):
        """days_back=1 should call download_snapshot, not download_all_stocks."""
        client = _make_client()
        with patch.object(client, "download_snapshot", return_value=1943) as mock_snap, \
             patch.object(client, "download_all_stocks") as mock_hist:
            result = client.download_recent_data(days_back=1)

        assert result == 1943
        mock_snap.assert_called_once()
        mock_hist.assert_not_called()

    def test_multi_day_uses_historical(self):
        """days_back>1 should call download_all_stocks, not download_snapshot."""
        client = _make_client()
        with patch.object(client, "get_last_trading_date", return_value=datetime(2024, 1, 2)), \
             patch.object(client, "download_snapshot") as mock_snap, \
             patch.object(client, "download_all_stocks", return_value=5) as mock_hist:
            result = client.download_recent_data(days_back=3)

        assert result == 5
        mock_hist.assert_called_once()
        mock_snap.assert_not_called()
