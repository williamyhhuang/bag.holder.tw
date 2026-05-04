"""
Utility for fetching and caching Taiwan stock names from TWSE/TPEX APIs
"""
import json
import requests
import urllib3
import pandas as pd
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Optional

import sys
project_root = Path(__file__).parent.parent.parent
sys.path.append(str(project_root))

from src.utils.logger import get_logger

logger = get_logger(__name__)

CACHE_FILE = project_root / "data" / "cache" / "stock_names.json"
CACHE_TTL_HOURS = 24


def _fetch_tse_names() -> Dict[str, str]:
    """Fetch stock names from TWSE API"""
    try:
        url = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, timeout=10, verify=False)
        resp.raise_for_status()
        data = resp.json()
        return {
            f"{item['Code']}.TW": item["Name"]
            for item in data
            if "Code" in item and "Name" in item and item["Code"].isdigit() and len(item["Code"]) == 4
        }
    except Exception as e:
        logger.warning(f"Failed to fetch TSE stock names: {e}")
        return {}


def _fetch_otc_names() -> Dict[str, str]:
    """Fetch stock names from TPEX API"""
    try:
        url = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes"
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, timeout=10, verify=False)
        resp.raise_for_status()
        data = resp.json()
        return {
            f"{item['SecuritiesCompanyCode']}.TWO": item["CompanyName"]
            for item in data
            if "SecuritiesCompanyCode" in item
            and "CompanyName" in item
            and item["SecuritiesCompanyCode"].isdigit()
            and len(item["SecuritiesCompanyCode"]) == 4
        }
    except Exception as e:
        logger.warning(f"Failed to fetch OTC stock names: {e}")
        return {}


def _load_cache() -> Optional[Dict[str, str]]:
    """Load cached stock names if still fresh"""
    if not CACHE_FILE.exists():
        return None
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            payload = json.load(f)
        cached_at = datetime.fromisoformat(payload["cached_at"])
        if datetime.now() - cached_at < timedelta(hours=CACHE_TTL_HOURS):
            return payload["names"]
    except Exception:
        pass
    return None


def _save_cache(names: Dict[str, str]) -> None:
    """Save stock names to cache file"""
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump({"cached_at": datetime.now().isoformat(), "names": names}, f, ensure_ascii=False)
    except Exception as e:
        logger.warning(f"Failed to save stock name cache: {e}")


def get_stock_names(use_cache: bool = True) -> Dict[str, str]:
    """
    Return a mapping of stock symbol → Chinese name.

    Keys use the format stored in data files, e.g. "2330_TW" (underscore).
    Falls back to empty dict if APIs are unreachable and no cache exists.
    """
    if use_cache:
        cached = _load_cache()
        if cached is not None:
            return cached

    logger.info("Fetching stock names from TWSE/TPEX APIs...")
    names = {}
    names.update(_fetch_tse_names())
    names.update(_fetch_otc_names())

    if names:
        _save_cache(names)
        logger.info(f"Fetched {len(names)} stock names")
    else:
        logger.warning("Could not fetch any stock names")

    return names


def lookup_name(symbol_stem: str, names: Optional[Dict[str, str]] = None) -> str:
    """
    Look up the Chinese name for a stock given its file stem (e.g. "2330_TW").

    Args:
        symbol_stem: filename stem like "2330_TW" or display symbol like "2330.TW"
        names: pre-loaded name dict (optional, will fetch if not provided)

    Returns:
        Chinese company name, or empty string if not found
    """
    if names is None:
        names = get_stock_names()

    # Normalise to dot format used as dict key
    dot_symbol = symbol_stem.replace("_", ".")
    return names.get(dot_symbol, "")
