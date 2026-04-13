"""
Monthly Revenue Filter
======================
從證交所 / 櫃買中心 OpenAPI 取得最新月營收，
快取至 data/revenue_cache.json，供 signals_scanner 過濾低營收股票。

API 來源：
  TSE（上市）: https://openapi.twse.com.tw/v1/opendata/t187ap05_L
  OTC（上櫃）: https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap05_O

回傳單位：千元（NTD thousands）
config 設定單位：百萬元（million NTD），1 億 = 100 百萬元
"""

import json
import logging
from datetime import date
from pathlib import Path
from typing import Dict, Optional

import requests

logger = logging.getLogger(__name__)

_TSE_URL = "https://openapi.twse.com.tw/v1/opendata/t187ap05_L"
_OTC_URL = "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap05_O"

# 預設快取路徑
_DEFAULT_CACHE_PATH = Path(__file__).parent.parent.parent / "data" / "revenue_cache.json"


def _fetch_revenue_from_api() -> Dict[str, float]:
    """
    從 TWSE / TPEX API 抓取月營收。

    Returns:
        dict mapping 股票代號（如 "2330"）→ 當月營收（百萬元）
        若 API 無法連線則回傳空 dict。
    """
    revenue: Dict[str, float] = {}

    for url, market in [(_TSE_URL, "TSE"), (_OTC_URL, "OTC")]:
        try:
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()

            # 部分端點在無資料時回傳 HTML
            text = resp.text.strip()
            if not text.startswith("["):
                logger.warning(f"[revenue] {market} API 回傳非 JSON 內容，略過")
                continue

            rows = resp.json()
            for row in rows:
                code = str(row.get("公司代號", "")).strip()
                raw = str(row.get("營業收入-當月營收", "")).strip().replace(",", "")
                if not code or not raw:
                    continue
                try:
                    # API 單位：千元 → 轉換為百萬元
                    revenue_million = float(raw) / 1_000.0
                    revenue[code] = revenue_million
                except ValueError:
                    continue

            logger.info(f"[revenue] {market} 取得 {len(rows)} 筆，累計 {len(revenue)} 支")

        except Exception as exc:
            logger.warning(f"[revenue] {market} API 失敗: {exc}")

    return revenue


class MonthlyRevenueLoader:
    """月營收載入器（帶當日磁碟快取）"""

    def __init__(self, cache_path: Path = _DEFAULT_CACHE_PATH):
        self.cache_path = cache_path

    def _load_cache(self) -> Optional[Dict[str, float]]:
        """讀取快取；若快取日期非今天則回傳 None。"""
        if not self.cache_path.exists():
            return None
        try:
            with open(self.cache_path, encoding="utf-8") as f:
                payload = json.load(f)
            if payload.get("date") != date.today().isoformat():
                return None
            data = payload.get("data", {})
            if not isinstance(data, dict):
                return None
            return data
        except Exception:
            return None

    def _save_cache(self, data: Dict[str, float]) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.cache_path, "w", encoding="utf-8") as f:
            json.dump({"date": date.today().isoformat(), "data": data}, f, ensure_ascii=False)
        logger.info(f"[revenue] 快取已儲存至 {self.cache_path}，共 {len(data)} 支")

    def load(self) -> Dict[str, float]:
        """
        回傳月營收字典（百萬元）。
        優先使用當日快取，無快取時從 API 抓取並存檔。
        若 API 失敗且無快取，回傳空 dict（不阻斷掃描流程）。
        """
        cached = self._load_cache()
        if cached is not None:
            logger.info(f"[revenue] 使用快取（{len(cached)} 支）")
            return cached

        logger.info("[revenue] 快取不存在或已過期，重新從 API 抓取...")
        data = _fetch_revenue_from_api()

        if data:
            self._save_cache(data)
        else:
            logger.warning("[revenue] API 未能取得資料，月營收過濾將略過")

        return data
