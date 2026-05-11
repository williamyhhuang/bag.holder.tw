"""
Fubon SDK client for downloading historical stock data (synchronous).
Uses the same interface as YFinanceClient so they can be swapped transparently.

Authentication: apikey_login(user_id, api_key, cert_path, cert_password)
or              login(user_id, password, cert_path, cert_password)
"""
import base64
import tempfile
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import List, Optional

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


class _SlidingWindowRateLimiter:
    """
    Thread-safe sliding window rate limiter.

    Allows at most *max_requests* in any rolling *window* second interval.
    Multiple threads can call acquire() concurrently; each call blocks until
    a slot is available, then records its timestamp and returns.
    """

    def __init__(self, max_requests: int, window: float = 60.0):
        self._max = max_requests
        self._window = window
        self._times: deque = deque()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        while True:
            with self._lock:
                now = time.monotonic()
                # Evict timestamps that have left the window
                while self._times and now - self._times[0] >= self._window:
                    self._times.popleft()

                if len(self._times) < self._max:
                    self._times.append(now)
                    return  # slot claimed; proceed with the request

                # Wait until the oldest slot expires, then retry
                wait = self._window - (now - self._times[0]) + 0.05
            time.sleep(max(0.05, wait))


class FubonDownloadClient:
    """
    Fubon SDK client for bulk historical stock data download.

    Compatible with YFinanceClient – provides the same
    download_all_stocks() / download_recent_data() / get_last_trading_date() API
    so it can be swapped in without changing callers.

    Downloads run concurrently (ThreadPoolExecutor) while a shared sliding-window
    rate limiter keeps total requests within the API limit.

    Rate limit:  settings.fubon.rate_limit_per_minute  (default 30 req/min)
    Concurrency: settings.download.fubon_max_workers    (default 5 threads)
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
        self.cert_password = cert_password or settings.fubon.cert_password or self.user_id
        self.password = password or settings.fubon.password

        # Resolve cert path: explicit path → env FUBON_CERT_PATH → decode FUBON_CERT_BASE64 to tmp file
        self.cert_path = cert_path or settings.fubon.cert_path
        self._cert_tmpfile = None  # keep reference so it isn't GC'd during login
        if not self.cert_path and settings.fubon.cert_base64:
            self._cert_tmpfile = tempfile.NamedTemporaryFile(suffix=".p12", delete=False)
            self._cert_tmpfile.write(base64.b64decode(settings.fubon.cert_base64))
            self._cert_tmpfile.flush()
            self.cert_path = self._cert_tmpfile.name
            logger.debug("Decoded FUBON_CERT_BASE64 to temp file: %s", self.cert_path)

        self._sdk = None
        self._reststock = None
        self._logged_in = False

        self._rpm: int = settings.fubon.rate_limit_per_minute   # FUBON_RATE_LIMIT_PER_MINUTE
        self._max_workers: int = settings.download.fubon_max_workers  # DOWNLOAD_FUBON_MAX_WORKERS

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

        # Clean up temp cert file after successful login (cert is loaded into SDK memory)
        if self._cert_tmpfile:
            try:
                import os
                os.unlink(self._cert_tmpfile.name)
            except OSError:
                pass
            self._cert_tmpfile = None

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

        max_retries = 3
        for attempt in range(max_retries):
            try:
                result = self._reststock.historical.candles(
                    **{"symbol": fubon_sym, "from": from_str, "to": to_str}
                )
                break
            except Exception as e:
                err_str = str(e)
                if "429" in err_str or "Rate limit" in err_str:
                    wait = 60 * (attempt + 1)
                    logger.warning(f"Rate limit hit for {symbol}, retrying in {wait}s ({attempt+1}/{max_retries})")
                    time.sleep(wait)
                    if attempt == max_retries - 1:
                        logger.warning(f"Fubon candles error for {symbol}: {e}")
                        return None
                else:
                    logger.warning(f"Fubon candles error for {symbol}: {e}")
                    return None

        if not result:
            return None

        # SDK returns a plain dict: {"symbol": ..., "data": [...], ...}
        if isinstance(result, dict):
            raw = result.get("data") or []
        else:
            raw = getattr(result, "data", None) or []

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
        batch_size: Optional[int] = None,  # unused – kept for interface compat
    ) -> int:
        """
        Download historical OHLCV data for all listed stocks via Fubon API.

        Requests run concurrently in a thread pool.  A shared sliding-window
        rate limiter ensures the total request rate never exceeds the API limit.

        Args:
            start_date:  Start of the date range (defaults to last trading day).
            end_date:    End of the date range (defaults to today).
            markets:     ["TSE"], ["OTC"], or ["TSE", "OTC"] (default).
            limit:       Cap on number of stocks (useful for testing).
            batch_size:  Unused; kept for interface compatibility with YFinanceClient.

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
            now_tw = datetime.now(taipei_tz)
            # 週末不開盤：end_date 對齊最後交易日，避免傳入週末日期給 API
            if now_tw.weekday() >= 5:
                end_date = self.get_last_trading_date()
            else:
                end_date = now_tw.replace(tzinfo=None)

        max_workers = self._max_workers
        rate_limiter = _SlidingWindowRateLimiter(max_requests=self._rpm, window=60.0)

        total = len(all_symbols)
        logger.info(
            f"Starting Fubon concurrent download: {total} stocks, "
            f"{max_workers} workers, {self._rpm} req/min "
            f"({start_date.date()} → {end_date.date()})"
        )

        success = 0
        failed = 0
        counter_lock = threading.Lock()

        progress_bar = tqdm(
            total=total,
            desc="富邦批次下載",
            unit="支",
            bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} 支 [{elapsed}<{remaining}]",
        )

        def _download_one(symbol: str):
            """Fetch + save one symbol; returns (symbol, ok, error_msg)."""
            rate_limiter.acquire()
            try:
                df = self.get_stock_data(symbol, start_date, end_date)
                if df is not None and not df.empty:
                    saved = self.save_stock_data(symbol, df)
                    return symbol, saved, None
                else:
                    return symbol, False, "無資料"
            except Exception as e:
                return symbol, False, str(e)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_download_one, sym): sym for sym in all_symbols}
            for future in as_completed(futures):
                sym = futures[future]
                try:
                    symbol, ok, err = future.result()
                    with counter_lock:
                        if ok:
                            success += 1
                        else:
                            failed += 1
                            if err:
                                progress_bar.write(f"⚠️ {symbol}: {err}")
                        progress_bar.update(1)
                except Exception as e:
                    with counter_lock:
                        failed += 1
                        progress_bar.write(f"❌ {sym}: {e}")
                        progress_bar.update(1)

        progress_bar.close()

        rate = success / total * 100 if total > 0 else 0
        logger.info(f"下載完成: {success}/{total} 支成功 ({rate:.1f}%)")
        if failed:
            logger.info(f"失敗: {failed} 支")

        return success

    # ─────────────────────────────────────────────────────────────────────────
    # Snapshot bulk download (today's data only – 2 API calls for all stocks)
    # ─────────────────────────────────────────────────────────────────────────

    def download_snapshot(self, markets: List[str] = None) -> int:
        """
        Download today's OHLCV for ALL stocks using the snapshot API.

        One request per market (TSE / OTC) → entire market in a single call.
        Much faster than per-symbol historical queries for today-only data.

        Args:
            markets: ["TSE"], ["OTC"], or ["TSE", "OTC"] (default).

        Returns:
            Number of stocks successfully saved.
        """
        if not self._logged_in:
            self.login()

        if markets is None:
            markets = ["TSE", "OTC"]

        import pytz
        today_str = datetime.now(pytz.timezone("Asia/Taipei")).strftime("%Y-%m-%d")
        today_dt = pd.Timestamp(today_str)

        # 台股週末不開盤，不執行 snapshot 避免寫入無效資料
        if today_dt.weekday() >= 5:
            logger.info(
                f"Snapshot skipped: {today_str} is a weekend (weekday={today_dt.weekday()})"
            )
            self.logout()
            return 0

        # Fubon market codes → yfinance suffix
        # TIB (臺灣創新板) stocks appear in TWSE's TSE list but as a separate
        # market in Fubon.  We fetch TIB alongside TSE and use the same .TW suffix.
        suffix_map = {"TSE": ".TW", "TIB": ".TW", "OTC": ".TWO"}

        # Expand TSE to also include TIB (mirrors the TWSE API which bundles them)
        fubon_markets = []
        for m in markets:
            fubon_markets.append(m)
            if m == "TSE":
                fubon_markets.append("TIB")

        success = 0
        for market in fubon_markets:
            suffix = suffix_map.get(market, ".TW")
            try:
                result = self._reststock.snapshot.quotes(market=market)
                raw = result.get("data", []) if isinstance(result, dict) else []
            except Exception as e:
                logger.error(f"Snapshot failed for {market}: {e}")
                continue

            # Filter to plain 4-digit numeric symbols only (same as yfinance)
            # Fubon tradeVolume is in 張 (1 張 = 1000 shares); multiply to match
            # yfinance's shares-based volume.
            rows_by_symbol: dict = {}
            for item in raw:
                d = item if isinstance(item, dict) else vars(item)
                sym_code = str(d.get("symbol", ""))
                if not (sym_code.isdigit() and len(sym_code) == 4):
                    continue
                yf_symbol = f"{sym_code}{suffix}"
                rows_by_symbol[yf_symbol] = {
                    "date": today_dt,
                    "open": float(d.get("openPrice", 0) or 0),
                    "high": float(d.get("highPrice", 0) or 0),
                    "low": float(d.get("lowPrice", 0) or 0),
                    "close": float(d.get("closePrice", 0) or 0),
                    "volume": int(d.get("tradeVolume", 0) or 0) * 1000,  # 張→股
                    "symbol": yf_symbol,
                }

            logger.info(f"Snapshot {market}: {len(rows_by_symbol)} stocks fetched")

            for yf_symbol, row in rows_by_symbol.items():
                df = pd.DataFrame([row])
                if self.save_stock_data(yf_symbol, df):
                    success += 1

        self.logout()
        logger.info(f"Snapshot download done: {success} stocks saved")
        return success

    def download_recent_data(self, days_back: int = 1) -> int:
        """
        Download recent trading data.

        When days_back == 1 (today only): uses the snapshot API
        (2 requests for all stocks, extremely fast).
        When days_back > 1: falls back to concurrent per-symbol historical queries.

        Args:
            days_back: Number of trading days back to cover. Defaults to 1 (snapshot).

        Returns:
            Number of stocks successfully saved.
        """
        if days_back <= 1:
            logger.info("days_back=1 → using Fubon snapshot API (2 requests for all stocks)")
            return self.download_snapshot()

        import pytz
        taipei_tz = pytz.timezone("Asia/Taipei")
        today_taipei = datetime.now(taipei_tz)
        # 週末不開盤：end_date 對齊最後交易日
        if today_taipei.weekday() >= 5:
            end_date = self.get_last_trading_date()
        else:
            end_date = today_taipei.replace(tzinfo=None)
        start_date = self.get_last_trading_date()

        if days_back > 1:
            start_date = start_date - timedelta(days=days_back - 1)

        logger.info(
            f"Downloading recent Fubon data "
            f"from {start_date.date()} to {end_date.date()}"
        )
        return self.download_all_stocks(start_date, end_date)
