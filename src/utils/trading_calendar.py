"""
台股交易日判斷
==============
資料來源：證交所 OpenAPI 休市日程表
  https://openapi.twse.com.tw/v1/holidaySchedule/holidaySchedule

表中除了休市日，也列出「開始交易日」「最後交易日」等提示，這些日子照常交易，須排除。
颱風等臨時休市不在表中，另由富邦快照的行情日期檢查把關（fubon_download_client.download_snapshot）。

快取：data/cache/twse_holidays.json（7 天）。抓取失敗時退回過期快取，再不行只判斷週末。
"""

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional, Set

import requests
import urllib3

from src.utils.logger import get_logger

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = get_logger(__name__)

HOLIDAY_URL = "https://openapi.twse.com.tw/v1/holidaySchedule/holidaySchedule"
CACHE_FILE = Path(__file__).parent.parent.parent / "data" / "cache" / "twse_holidays.json"
CACHE_TTL = timedelta(days=7)

# 名稱含這些字的是「照常交易」的提示日，不是休市日
_TRADING_MARKERS = ("開始交易", "最後交易")


def _roc_to_date(text: str) -> Optional[date]:
    """民國日期 '1151009' → date(2026, 10, 9)"""
    text = str(text).strip()
    if len(text) < 7 or not text.isdigit():
        return None
    try:
        return date(int(text[:-4]) + 1911, int(text[-4:-2]), int(text[-2:]))
    except ValueError:
        return None


def parse_holidays(payload) -> Set[date]:
    holidays: Set[date] = set()
    for item in payload or []:
        name = str(item.get("Name", ""))
        if any(marker in name for marker in _TRADING_MARKERS):
            continue
        d = _roc_to_date(item.get("Date", ""))
        if d:
            holidays.add(d)
    return holidays


def _load_cache(max_age: Optional[timedelta]) -> Optional[Set[date]]:
    try:
        payload = json.loads(CACHE_FILE.read_text())
        if max_age is not None and datetime.now() - datetime.fromisoformat(payload["cached_at"]) > max_age:
            return None
        return {date.fromisoformat(d) for d in payload["holidays"]}
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _save_cache(holidays: Set[date]) -> None:
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(json.dumps({
            "cached_at": datetime.now().isoformat(),
            "holidays": sorted(d.isoformat() for d in holidays),
        }))
    except OSError as e:
        logger.warning(f"寫入休市日快取失敗: {e}")


def get_holidays(use_cache: bool = True) -> Set[date]:
    if use_cache:
        cached = _load_cache(CACHE_TTL)
        if cached is not None:
            return cached
    try:
        resp = requests.get(HOLIDAY_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=20, verify=False)
        resp.raise_for_status()
        holidays = parse_holidays(resp.json())
        if holidays:
            _save_cache(holidays)
            return holidays
    except Exception as e:
        logger.warning(f"證交所休市日程表抓取失敗: {e}")
    stale = _load_cache(None)
    if stale is not None:
        logger.warning("改用過期的休市日快取")
        return stale
    logger.warning("無休市日資料，只判斷週末")
    return set()


def is_trading_day(day: date, holidays: Optional[Set[date]] = None) -> bool:
    """週一至週五且不在證交所休市日程表中"""
    if day.weekday() >= 5:
        return False
    if holidays is None:
        holidays = get_holidays()
    return day not in holidays
