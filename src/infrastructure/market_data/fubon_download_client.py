"""
Fubon SDK client for downloading historical stock data (synchronous).
Uses the same interface as YFinanceClient so they can be swapped transparently.

Authentication: apikey_login(user_id, api_key, cert_path, cert_password)
or              login(user_id, password, cert_path, cert_password)
"""
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
from tqdm import tqdm

from ...utils.logger import get_logger
from config.settings import settings

logger = get_logger(__name__)


class FubonDownloadError(Exception):
    pass


def _to_fubon_symbol(symbol: str) -> str:
    """Strip yfinance suffix: '2330.TW' → '2330', '6277.TWO' → '6277'"""
    return symbol.split(".")[0]


class FubonDownloadClient:
    """
    Synchronous Fubon SDK client for bulk historical stock data download.

    Compatible with YFinanceClient – provides the same
    download_all_stocks() / download_recent_data() / get_last_trading_date() API
    so it can be swapped in without changing callers.

    Rate limit: 30 requests / 60 s (configurable via settings.fubon.rate_limit_per_minute).
    """

    def __init__(
        self,
        user_id: str = None,
        api_key: str = None,
        cert_path: str = None,
        cert_password: str = None,
        password: str = None,
    ):
        self.user_id = user_id or settings.fubon.user_id
        self.api_key = api_key or settings.fubon.api_key
        self.cert_path = cert_path or settings.fubon.cert_path
        self.cert_password = cert_password or settings.fubon.cert_password or self.user_id
        self.password = password or settings.fubon.password

        self._sdk = None
        self._reststock = None
        self._logged_in = False

        rpm = getattr(settings.fubon, "rate_limit_per_minute", 30) or 30
        # minimum seconds between requests to stay under rate limit
        self._min_interval = 60.0 / rpm

    # ─────────────────────────────────────────────────────────────────────────
    # Login
    # ─────────────────────────────────────────────────────────────────────────

    def login(self) -> None:
        """Login to Fubon SDK and initialise the REST market-data client."""
        # Validate credentials before attempting SDK import
        if self.api_key and self.user_id and self.cert_path:
            method = "API Key"
        elif self.user_id and self.password and self.cert_path:
            method = "Certificate"
        else:
            raise FubonDownloadError(
                "Fubon auth not configured. "
                "Set FUBON_USER_ID + FUBON_API_KEY + FUBON_CERT_PATH in .env, "
                "or FUBON_USER_ID + FUBON_PASSWORD + FUBON_CERT_PATH."
            )

        try:
            from fubon_neo.sdk import FubonSDK
        except ImportError:
            raise FubonDownloadError(
                "fubon_neo SDK not installed. "
                "Download from: https://www.fbs.com.tw/TradeAPI/docs/download.txt"
            )

        sdk = FubonSDK()

        if method == "API Key":
            result = sdk.apikey_login(
                self.user_id, self.api_key, self.cert_path, self.cert_password
            )
        else:
            result = sdk.login(
                self.user_id, self.password, self.cert_path, self.cert_password
            )

        if not result.is_success:
            raise FubonDownloadError(f"Fubon login ({method}) failed: {result.message}")

        sdk.init_realtime()
        self._sdk = sdk
        self._reststock = sdk.marketdata.rest_client.stock
        self._logged_in = True
        logger.info(f"Fubon SDK logged in ({method})")

    def logout(self) -> None:
        if self._sdk and self._logged_in:
            try:
                if hasattr(self._sdk, "logout"):
                    self._sdk.logout()
            except Exception:
                pass
            self._logged_in = False
            logger.info("Fubon SDK logged out")

    # ─────────────────────────────────────────────────────────────────────────
    # Stock list  (reuse TWSE / TPEX fetchers from YFinanceClient)
    # ─────────────────────────────────────────────────────────────────────────

    def get_tse_listed_stocks(self) -> List[str]:
        from .yfinance_client import YFinanceClient
        return YFinanceClient().get_tse_listed_stocks()

    def get_otc_listed_stocks(self) -> List[str]:
        from .yfinance_client import YFinanceClient
        return YFinanceClient().get_otc_listed_stocks()

    # ─────────────────────────────────────────────────────────────────────────
    # Historical data
    # ─────────────────────────────────────────────────────────────────────────

    def get_stock_data(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
    ) -> Optional[pd.DataFrame]:
        """
        Fetch daily OHLCV data for *symbol* (yfinance format, e.g. '2330.TW')
        from Fubon historical candles API.

        Returns a DataFrame with columns:
            date, open, high, low, close, volume, symbol
        or None if no data.
        """
        if not self._logged_in:
            self.login()

        fubon_sym = _to_fubon_symbol(symbol)
        from_str = start_date.strftime("%Y-%m-%d")
        to_str = end_date.strftime("%Y-%m-%d")

        try:
            result = self._reststock.historical.candles(
                **{"symbol": fubon_sym, "from": from_str, "to": to_str}
            )
        except Exception as e:
            logger.warning(f"Fubon candles error for {symbol}: {e}")
            return None

        if not result or not getattr(result, "data", None):
            return None

        raw = result.data if isinstance(result.data, list) else []
        rows = []
        for item in raw:
            d = item if isinstance(item, dict) else vars(item)
            rows.append(
                {
                    "date": d.get("date", ""),
                    "open": float(d.get("open", 0) or 0),
                    "high": float(d.get("high", 0) or 0),
                    "low": float(d.get("low", 0) or 0),
                    "close": float(d.get("close", 0) or 0),
                    "volume": int(d.get("volume", 0) or 0),
                    "symbol": symbol,
                }
            )

        if not rows:
            return None

        df = pd.DataFrame(rows)
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").reset_index(drop=True)
        return df

    # ─────────────────────────────────────────────────────────────────────────
    # Save (delegates to YFinanceClient so CSV format stays identical)
    # ─────────────────────────────────────────────────────────────────────────

    def save_stock_data(self, symbol: str, data: pd.DataFrame) -> bool:
        from .yfinance_client import YFinanceClient
        return YFinanceClient().save_stock_data(symbol, data)

    # ─────────────────────────────────────────────────────────────────────────
    # Bulk download  (same signature as YFinanceClient)
    # ─────────────────────────────────────────────────────────────────────────

    def get_last_trading_date(self) -> datetime:
        from .yfinance_client import YFinanceClient
        return YFinanceClient().get_last_trading_date()

    def download_all_stocks(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        markets: List[str] = None,
        limit: Optional[int] = None,
        batch_size: Optional[int] = None,  # ignored – Fubon API is per-symbol
    ) -> int:
        """
        Download historical OHLCV data for all listed stocks via Fubon API.

        Args:
            start_date: Start of the date range (defaults to last trading day).
            end_date:   End of the date range (defaults to today).
            markets:    ["TSE"], ["OTC"], or ["TSE", "OTC"] (default).
            limit:      Cap on number of stocks (useful for testing).
            batch_size: Ignored; Fubon API is called one symbol at a time.

        Returns:
            Number of symbols successfully saved.
        """
        if not self._logged_in:
            self.login()

        if markets is None:
            markets = ["TSE", "OTC"]

        all_symbols: List[str] = []
        if "TSE" in markets:
            all_symbols.extend(self.get_tse_listed_stocks())
        if "OTC" in markets:
            all_symbols.extend(self.get_otc_listed_stocks())

        if limit and limit > 0:
            all_symbols = all_symbols[:limit]
            logger.info(f"Limited to first {limit} stocks")

        if not all_symbols:
            logger.error("No stock symbols to download")
            return 0

        if start_date is None:
            start_date = self.get_last_trading_date()
        if end_date is None:
            import pytz
            taipei_tz = pytz.timezone("Asia/Taipei")
            end_date = datetime.now(taipei_tz).replace(tzinfo=None)

        total = len(all_symbols)
        logger.info(
            f"Starting Fubon download for {total} stocks "
            f"({start_date.date()} → {end_date.date()}, "
            f"rate limit: {int(60 / self._min_interval)} req/min)"
        )

        success = 0
        failed = 0
        _last_call = 0.0

        progress_bar = tqdm(
            all_symbols,
            desc="富邦下載",
            unit="支",
            bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} 支 [{elapsed}<{remaining}]",
        )

        for symbol in progress_bar:
            progress_bar.set_description(f"富邦下載 {symbol}")

            # Respect rate limit
            elapsed = time.monotonic() - _last_call
            if elapsed < self._min_interval:
                time.sleep(self._min_interval - elapsed)

            try:
                df = self.get_stock_data(symbol, start_date, end_date)
                _last_call = time.monotonic()

                if df is not None and not df.empty:
                    if self.save_stock_data(symbol, df):
                        success += 1
                    else:
                        failed += 1
                        progress_bar.write(f"⚠️ 儲存失敗: {symbol}")
                else:
                    failed += 1
                    progress_bar.write(f"⚠️ 無資料: {symbol}")

            except Exception as e:
                _last_call = time.monotonic()
                failed += 1
                progress_bar.write(f"❌ 下載失敗 {symbol}: {e}")

        progress_bar.close()

        rate = success / total * 100 if total > 0 else 0
        logger.info(f"下載完成: {success}/{total} 支成功 ({rate:.1f}%)")
        if failed:
            logger.info(f"失敗: {failed} 支")

        return success

    def download_recent_data(self, days_back: int = 2) -> int:
        """
        Download recent data (mirrors YFinanceClient.download_recent_data).

        Args:
            days_back: How many trading days back to cover.

        Returns:
            Number of stocks successfully saved.
        """
        import pytz

        taipei_tz = pytz.timezone("Asia/Taipei")
        today_taipei = datetime.now(taipei_tz)
        end_date = today_taipei.replace(tzinfo=None)
        start_date = self.get_last_trading_date()

        if days_back > 1:
            start_date = start_date - timedelta(days=days_back - 1)

        logger.info(
            f"Downloading recent Fubon data "
            f"from {start_date.date()} to {end_date.date()}"
        )
        return self.download_all_stocks(start_date, end_date)
