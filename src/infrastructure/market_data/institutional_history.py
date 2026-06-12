"""
Institutional History Loader — T86 歷史三大法人資料
=====================================================
從 TWSE T86 API 批量下載歷史法人資料，
快取至 data/cache/institutional_history/YYYYMMDD.json（永久保存）。

用途：提供 FactorEngine 計算外資/投信連續買超天數。

注意：T86 僅涵蓋上市（TSE）股票，上櫃以 fail-open 處理。
"""

import json
import logging
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

_T86_URL = (
    "https://www.twse.com.tw/rwd/zh/fund/T86"
    "?response=json&date={date}&selectType=ALLBUT0999"
)

_DEFAULT_HISTORY_DIR = (
    Path(__file__).parent.parent.parent / "data" / "cache" / "institutional_history"
)


def _parse_int(raw: str) -> int:
    try:
        return int(str(raw).replace(",", "").strip())
    except (ValueError, AttributeError):
        return 0


def _fetch_t86_for_date(target_date: date) -> Optional[Dict[str, dict]]:
    """
    從 T86 API 抓取單一交易日的法人資料。

    Returns:
        {symbol: {"foreign_net": int, "trust_net": int}} 或 None（非交易日）
    """
    date_str = target_date.strftime("%Y%m%d")
    url = _T86_URL.format(date=date_str)
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        if data.get("stat", "").startswith(("no", "很抱歉")):
            return None  # 非交易日

        result: Dict[str, dict] = {}
        for row in data.get("data", []):
            if not isinstance(row, list) or len(row) < 19:
                continue
            code = str(row[0]).strip()
            if not code or not code.isdigit():
                continue
            result[code] = {
                "foreign_net": _parse_int(row[4]),
                "trust_net": _parse_int(row[10]),
                "dealer_net": _parse_int(row[11]),
            }
        return result
    except Exception as exc:
        logger.warning(f"[inst_history] T86 {target_date} 失敗: {exc}")
        return None


class InstitutionalHistoryLoader:
    """
    歷史三大法人資料載入器。

    每個交易日的資料快取為獨立 JSON 檔，永久保存（不會因日期改變而失效）。
    這與 InstitutionalFlowLoader（只快取當日）的策略不同。

    快取格式（YYYYMMDD.json）：
        {
            "date": "YYYY-MM-DD",
            "data": {
                "2330": {"foreign_net": 1000000, "trust_net": 200000, "dealer_net": 50000},
                ...
            }
        }
    """

    def __init__(self, history_dir: Path = _DEFAULT_HISTORY_DIR):
        self.history_dir = history_dir
        self.history_dir.mkdir(parents=True, exist_ok=True)

    def _cache_path(self, target_date: date) -> Path:
        return self.history_dir / f"{target_date.strftime('%Y%m%d')}.json"

    def _load_from_cache(self, target_date: date) -> Optional[Dict[str, dict]]:
        path = self._cache_path(target_date)
        if not path.exists():
            return None
        try:
            with open(path, encoding="utf-8") as f:
                payload = json.load(f)
            return payload.get("data", {})
        except Exception:
            return None

    def _save_to_cache(self, target_date: date, data: Dict[str, dict]) -> None:
        path = self._cache_path(target_date)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(
                {"date": target_date.isoformat(), "data": data},
                f,
                ensure_ascii=False,
            )

    def load_date(self, target_date: date) -> Dict[str, dict]:
        """
        載入單一交易日的法人資料（優先使用快取）。

        Returns:
            {symbol: {"foreign_net": int, "trust_net": int, "dealer_net": int}}
            非交易日或失敗回傳空 dict
        """
        cached = self._load_from_cache(target_date)
        if cached is not None:
            return cached

        result = _fetch_t86_for_date(target_date)
        if result is None:
            return {}  # 非交易日，不快取

        self._save_to_cache(target_date, result)
        logger.info(f"[inst_history] {target_date} 已快取 {len(result)} 支")
        return result

    def load_range(
        self,
        end_date: date,
        n_days: int = 30,
        request_delay: float = 0.5,
    ) -> List[Dict]:
        """
        載入最近 n_days 個自然日內的所有交易日資料。

        Args:
            end_date: 結束日期（含）
            n_days: 往回查幾個自然日（預設 30）
            request_delay: 每次 API 請求間隔秒數（避免被封）

        Returns:
            [{"date": date, "data": {symbol: {...}}}] 只含有資料的交易日
        """
        results = []
        current = end_date

        for _ in range(n_days):
            if current < end_date - timedelta(days=n_days):
                break

            cached = self._load_from_cache(current)
            if cached is not None:
                if cached:  # 非空（真實交易日）
                    results.append({"date": current, "data": cached})
            else:
                fetched = _fetch_t86_for_date(current)
                if fetched is not None and fetched:
                    self._save_to_cache(current, fetched)
                    results.append({"date": current, "data": fetched})
                    time.sleep(request_delay)

            current -= timedelta(days=1)

        return sorted(results, key=lambda x: x["date"])

    def load_cached_range(
        self,
        start_date: date,
        end_date: date,
    ) -> List[Dict]:
        """
        只從本地快取載入日期區間內的法人資料（不打 API，供回測使用）。

        Returns:
            [{"date": date, "data": {symbol: {...}}}] 依日期升序，只含有快取的交易日
        """
        results = []
        current = start_date
        while current <= end_date:
            cached = self._load_from_cache(current)
            if cached:
                results.append({"date": current, "data": cached})
            current += timedelta(days=1)
        return results

    def build_consecutive_series(
        self,
        start_date: date,
        end_date: date,
        warmup_days: int = 30,
    ) -> Dict[date, Dict[str, dict]]:
        """
        一次掃描快取，計算區間內「每個交易日」每支股票的法人連續買超天數。
        供回測使用（無 lookahead：每日數值只依賴當日(含)以前的資料）。

        Args:
            start_date: 輸出區間起日
            end_date: 輸出區間迄日
            warmup_days: 起日前額外讀取的自然日數（讓首日 streak 正確）

        Returns:
            {date: {symbol: {"foreign_consecutive": int, "trust_consecutive": int}}}
            只包含 [start_date, end_date] 內有快取資料的交易日
        """
        history = self.load_cached_range(
            start_date - timedelta(days=warmup_days), end_date
        )
        if not history:
            return {}

        series: Dict[date, Dict[str, dict]] = {}
        # 滾動 streak 狀態
        f_streaks: Dict[str, int] = {}
        t_streaks: Dict[str, int] = {}

        for day in history:
            day_data = day["data"]
            # 當日無資料的股票 streak 重置
            for sym in list(f_streaks.keys()):
                if sym not in day_data:
                    f_streaks[sym] = 0
                    t_streaks[sym] = 0

            for sym, vals in day_data.items():
                f_net = vals.get("foreign_net", 0)
                t_net = vals.get("trust_net", 0)
                f_streaks[sym] = f_streaks.get(sym, 0) + 1 if f_net > 0 else 0
                t_streaks[sym] = t_streaks.get(sym, 0) + 1 if t_net > 0 else 0

            if day["date"] >= start_date:
                series[day["date"]] = {
                    sym: {
                        "foreign_consecutive": f_streaks.get(sym, 0),
                        "trust_consecutive": t_streaks.get(sym, 0),
                    }
                    for sym in day_data
                }

        return series

    def build_consecutive_days(
        self,
        end_date: date,
        n_days: int = 30,
    ) -> Dict[str, dict]:
        """
        計算每支股票截至 end_date 的外資/投信連續買超天數。

        Returns:
            {symbol: {"foreign_consecutive": int, "trust_consecutive": int,
                      "foreign_net_today": int, "trust_net_today": int}}
        """
        history = self.load_range(end_date=end_date, n_days=n_days)
        if not history:
            return {}

        # 蒐集所有出現過的股票
        all_symbols: set = set()
        for day in history:
            all_symbols.update(day["data"].keys())

        result: Dict[str, dict] = {}

        for sym in all_symbols:
            f_streak = 0
            t_streak = 0
            f_net_today = 0
            t_net_today = 0

            for day in history:
                day_data = day["data"].get(sym)
                if day_data is None:
                    # 該股當日無資料（可能上市日期較晚），重置連續天數
                    f_streak = 0
                    t_streak = 0
                    continue

                f_net = day_data.get("foreign_net", 0)
                t_net = day_data.get("trust_net", 0)
                f_streak = f_streak + 1 if f_net > 0 else 0
                t_streak = t_streak + 1 if t_net > 0 else 0
                f_net_today = f_net
                t_net_today = t_net

            result[sym] = {
                "foreign_consecutive": f_streak,
                "trust_consecutive": t_streak,
                "foreign_net_today": f_net_today,
                "trust_net_today": t_net_today,
            }

        return result
