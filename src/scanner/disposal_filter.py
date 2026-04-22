"""
Disposal Stock Filter (處置股/注意股過濾器)
==========================================
排除目前處於「處置」或「注意」狀態的股票，避免進場難度高或流動性受限的標的。

資料來源（雙來源，優先序）：
  1. 富邦 API intraday.tickers(isDisposition=True / isAttention=True)
     ── 需已登入 SDK；回傳最即時、最準確的清單
  2. TWSE OpenAPI（fallback，無需登入）
     ── https://openapi.twse.com.tw/v1/announcement/punish  (處置股)
     ── https://openapi.twse.com.tw/v1/announcement/notetrans (注意股)

任一來源失敗時 fail-open（回空集合），不阻斷掃描流程。
"""

import json
import logging
from datetime import date
from pathlib import Path
from typing import Optional, Set

import requests

logger = logging.getLogger(__name__)

_TWSE_PUNISH_URL = "https://openapi.twse.com.tw/v1/announcement/punish"
_TWSE_NOTETRANS_URL = "https://openapi.twse.com.tw/v1/announcement/notetrans"

_DEFAULT_CACHE_PATH = (
    Path(__file__).parent.parent.parent / "data" / "cache" / "disposal_cache.json"
)


def _fetch_from_fubon(sdk) -> Optional[Set[str]]:
    """
    透過富邦 SDK 取得處置股與注意股清單。

    Args:
        sdk: 已登入的 FubonSDK 實例。

    Returns:
        股票代碼集合（如 {"2330", "4741"}），失敗時回傳 None。
    """
    try:
        reststock = sdk.marketdata.rest_client.stock
        symbols: Set[str] = set()

        for flag, label in [("isDisposition", "處置股"), ("isAttention", "注意股")]:
            try:
                result = reststock.intraday.tickers(type="EQUITY", **{flag: True})
                rows = result.get("data", []) if isinstance(result, dict) else []
                for row in rows:
                    code = str(row.get("symbol", "")).strip()
                    # 富邦 symbol 格式如 "2330"（上市）或 "4741"（上櫃）
                    if code:
                        symbols.add(code)
                logger.info(f"[disposal] 富邦 {label}: {len(rows)} 支")
            except Exception as exc:
                logger.warning(f"[disposal] 富邦 {label} 失敗: {exc}")

        return symbols if symbols is not None else set()

    except Exception as exc:
        logger.warning(f"[disposal] 富邦 SDK 呼叫失敗: {exc}")
        return None


def _fetch_from_twse() -> Set[str]:
    """
    透過 TWSE OpenAPI 取得目前處置股與注意股清單（fallback）。

    回傳格式：list of dict，每筆含 ``Code`` 欄位（股票代號）。

    Returns:
        股票代碼集合，失敗時回傳空集合。
    """
    symbols: Set[str] = set()

    for url, label in [
        (_TWSE_PUNISH_URL, "處置股"),
        (_TWSE_NOTETRANS_URL, "注意股"),
    ]:
        try:
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()

            text = resp.text.strip()
            if not text.startswith("[") and not text.startswith("{"):
                logger.warning(f"[disposal] TWSE {label} API 回傳非 JSON，略過")
                continue

            data = resp.json()
            rows = data if isinstance(data, list) else data.get("data", [])
            before = len(symbols)
            for row in rows:
                if isinstance(row, dict):
                    code = str(row.get("Code", row.get("code", row.get("symbol", "")))).strip()
                    if code:
                        symbols.add(code)
                elif isinstance(row, list) and row:
                    code = str(row[0]).strip()
                    if code and code.isdigit():
                        symbols.add(code)
            logger.info(f"[disposal] TWSE {label}: {len(symbols) - before} 支")

        except Exception as exc:
            logger.warning(f"[disposal] TWSE {label} API 失敗: {exc}")

    logger.info(f"[disposal] TWSE OpenAPI 合計取得 {len(symbols)} 支")
    return symbols


class DisposalStockFilter:
    """
    處置股/注意股過濾器（帶當日磁碟快取）。

    使用方式：
        # 有富邦 SDK 時（最準確）
        disposal_filter = DisposalStockFilter(sdk=fubon_sdk)
        disposal_set = disposal_filter.load()

        # 無富邦 SDK 時（fallback 至 TWSE API）
        disposal_filter = DisposalStockFilter()
        disposal_set = disposal_filter.load()
    """

    def __init__(
        self,
        sdk=None,
        cache_path: Path = _DEFAULT_CACHE_PATH,
        filter_attention: bool = False,
    ):
        """
        Args:
            sdk: 已登入的 FubonSDK 實例（可為 None）。
            cache_path: 快取檔路徑。
            filter_attention: 是否也包含注意股（預設 False，只過濾處置股）。
        """
        self.sdk = sdk
        self.cache_path = cache_path
        self.filter_attention = filter_attention

    def _load_cache(self) -> Optional[Set[str]]:
        if not self.cache_path.exists():
            return None
        try:
            with open(self.cache_path, encoding="utf-8") as f:
                payload = json.load(f)
            if payload.get("date") != date.today().isoformat():
                return None
            data = payload.get("data", [])
            return set(data) if isinstance(data, list) else None
        except Exception:
            return None

    def _save_cache(self, symbols: Set[str]) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.cache_path, "w", encoding="utf-8") as f:
            json.dump(
                {"date": date.today().isoformat(), "data": sorted(symbols)},
                f,
                ensure_ascii=False,
            )
        logger.info(f"[disposal] 快取已儲存：{len(symbols)} 支，路徑 {self.cache_path}")

    def load(self) -> Set[str]:
        """
        回傳應排除的股票代碼集合。
        優先讀取當日快取；無快取時從 API 抓取並存檔。
        全部失敗時 fail-open（回空集合，不阻斷掃描）。
        """
        cached = self._load_cache()
        if cached is not None:
            logger.info(f"[disposal] 使用快取（{len(cached)} 支）")
            return cached

        logger.info("[disposal] 快取不存在或已過期，重新抓取...")
        symbols: Set[str] = set()

        # 優先使用富邦 SDK
        if self.sdk is not None:
            result = _fetch_from_fubon(self.sdk)
            if result is not None:
                symbols = result
            else:
                logger.info("[disposal] 富邦 SDK 失敗，改用 TWSE fallback")
                symbols = _fetch_from_twse()
        else:
            symbols = _fetch_from_twse()

        if symbols:
            self._save_cache(symbols)
        else:
            logger.warning("[disposal] 未能取得任何處置股資料，過濾將略過（fail-open）")

        return symbols
