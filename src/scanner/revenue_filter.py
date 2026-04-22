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

回傳格式（每支股票）：
  {
    "revenue_million": float,  # 當月營收（百萬元）
    "yoy_pct": float,          # 年增率（%）
    "mom_pct": float,          # 月增率（%）
  }
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

# 快取格式版本（舊版快取值為 float，新版為 dict）
_CACHE_SCHEMA_VERSION = 2

# 預設快取路徑
_DEFAULT_CACHE_PATH = Path(__file__).parent.parent.parent / "data" / "cache" / "revenue_cache.json"


def _safe_float(raw, default: float = 0.0) -> float:
    """安全轉換字串為 float，失敗時回傳 default。"""
    try:
        return float(str(raw).replace(",", "").strip())
    except (ValueError, TypeError):
        return default


def _fetch_revenue_from_api() -> Dict[str, dict]:
    """
    從 TWSE / TPEX API 抓取月營收（含年增率、月增率）。

    Returns:
        dict mapping 股票代號（如 "2330"）→ {revenue_million, yoy_pct, mom_pct}
        若 API 無法連線則回傳空 dict。
    """
    revenue: Dict[str, dict] = {}

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
                raw_rev = str(row.get("營業收入-當月營收", "")).strip().replace(",", "")
                if not code or not raw_rev:
                    continue
                try:
                    # API 單位：千元 → 轉換為百萬元
                    revenue_million = float(raw_rev) / 1_000.0
                    yoy_pct = _safe_float(row.get("營業收入-去年同月增減(%)"))
                    mom_pct = _safe_float(row.get("營業收入-上月比較增減(%)"))
                    revenue[code] = {
                        "revenue_million": revenue_million,
                        "yoy_pct": yoy_pct,
                        "mom_pct": mom_pct,
                    }
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

    def _load_cache(self) -> Optional[Dict[str, dict]]:
        """讀取快取；若快取日期非今天或格式版本不符則回傳 None。"""
        if not self.cache_path.exists():
            return None
        try:
            with open(self.cache_path, encoding="utf-8") as f:
                payload = json.load(f)
            if payload.get("date") != date.today().isoformat():
                return None
            # 舊版快取（schema_version 缺失或 < 2）以 float 儲存，視為過期
            if payload.get("schema_version", 1) < _CACHE_SCHEMA_VERSION:
                return None
            data = payload.get("data", {})
            if not isinstance(data, dict):
                return None
            # 確認第一個值為 dict（非 float）
            first = next(iter(data.values()), None)
            if first is not None and not isinstance(first, dict):
                return None
            return data
        except Exception:
            return None

    def _save_cache(self, data: Dict[str, dict]) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.cache_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "date": date.today().isoformat(),
                    "schema_version": _CACHE_SCHEMA_VERSION,
                    "data": data,
                },
                f,
                ensure_ascii=False,
            )
        logger.info(f"[revenue] 快取已儲存至 {self.cache_path}，共 {len(data)} 支")

    def load(self) -> Dict[str, dict]:
        """
        回傳月營收字典（每支股票含 revenue_million、yoy_pct、mom_pct）。
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


def get_revenue_million(revenue_map: Dict[str, dict], code: str) -> Optional[float]:
    """
    從 revenue_map 安全取得當月營收（百萬元）。
    相容舊版 float 格式（向後兼容）。
    """
    val = revenue_map.get(code)
    if val is None:
        return None
    if isinstance(val, dict):
        return val.get("revenue_million")
    if isinstance(val, (int, float)):
        return float(val)
    return None


def get_revenue_yoy(revenue_map: Dict[str, dict], code: str) -> float:
    """從 revenue_map 安全取得年增率（%）；無資料時回傳 0.0。"""
    val = revenue_map.get(code)
    if isinstance(val, dict):
        return val.get("yoy_pct", 0.0)
    return 0.0


def get_revenue_mom(revenue_map: Dict[str, dict], code: str) -> float:
    """從 revenue_map 安全取得月增率（%）；無資料時回傳 0.0。"""
    val = revenue_map.get(code)
    if isinstance(val, dict):
        return val.get("mom_pct", 0.0)
    return 0.0
