"""
FinMind Historical Data Client
================================
使用 FinMind API 取得台股歷史財務資料，供回測使用。

資料來源：
  - TaiwanStockMonthRevenue: 月營收歷史資料（含年增率計算）
  - TaiwanStockInstitutionalInvestorsBuySell: 三大法人買賣歷史資料

快取至 data/cache/finmind_{dataset}_{date}.json，當日有效。

設定：
  FINMIND_API_TOKEN: 在 settings.py 或 .env 設定
  （免費帳號：每小時 600 次請求，需先至 finmindtrade.com 註冊）
"""

import json
import logging
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_DEFAULT_CACHE_DIR = Path(__file__).parent.parent.parent / "data" / "cache"


class FinMindRevenueLoader:
    """
    從 FinMind 載入歷史月營收，計算每個日期對應的當月 YoY 成長率。

    回傳格式（rev_map）:
        { stock_id: { date: {"revenue": float, "yoy_pct": float} } }
    """

    def __init__(self, api_token: str = "", cache_dir: Path = _DEFAULT_CACHE_DIR):
        self.api_token = api_token
        self.cache_dir = cache_dir

    def _cache_path(self, stock_id: str) -> Path:
        return self.cache_dir / f"finmind_revenue_{stock_id}_{date.today().isoformat()}.json"

    def _load_cache(self, stock_id: str) -> Optional[Dict]:
        p = self._cache_path(stock_id)
        if not p.exists():
            return None
        try:
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def _save_cache(self, stock_id: str, data: Dict) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        with open(self._cache_path(stock_id), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)

    def load_stock_revenue_history(
        self,
        stock_id: str,
        start_date: str,
        end_date: str,
    ) -> Dict[str, dict]:
        """
        取得 stock_id 的月營收歷史，計算 YoY。

        Returns:
            Dict mapping date_str (YYYY-MM-DD, 報告發布日) -> {"revenue": float, "yoy_pct": float}
        """
        cached = self._load_cache(stock_id)
        if cached is not None:
            return cached

        try:
            from FinMind.data import DataLoader
            dl = DataLoader()
            if self.api_token:
                dl.login_by_token(api_token=self.api_token)

            # 需要比 start_date 早 13 個月才能算出 YoY
            from datetime import datetime
            sd = datetime.strptime(start_date, "%Y-%m-%d")
            fetch_start = (sd - timedelta(days=400)).strftime("%Y-%m-%d")

            df = dl.taiwan_stock_month_revenue(
                stock_id=stock_id,
                start_date=fetch_start,
                end_date=end_date,
            )

            if df is None or len(df) == 0:
                return {}

            # 建立 (revenue_year, revenue_month) -> revenue 的 lookup
            rev_lookup: Dict[Tuple[int, int], float] = {}
            for _, row in df.iterrows():
                rev_lookup[(int(row["revenue_year"]), int(row["revenue_month"]))] = float(row["revenue"])

            # 計算 YoY
            result: Dict[str, dict] = {}
            for _, row in df.iterrows():
                report_date = str(row["date"])[:10]
                yr = int(row["revenue_year"])
                mo = int(row["revenue_month"])
                cur_rev = float(row["revenue"])
                prev = rev_lookup.get((yr - 1, mo))
                yoy = ((cur_rev / prev) - 1.0) * 100.0 if prev and prev != 0 else 0.0
                result[report_date] = {
                    "revenue": cur_rev / 1_000_000.0,  # convert to million NTD
                    "yoy_pct": round(yoy, 2),
                }

            self._save_cache(stock_id, result)
            return result

        except Exception as exc:
            logger.warning(f"[FinMind] 月營收 {stock_id} 取得失敗: {exc}")
            return {}

    def get_revenue_on_date(
        self,
        stock_id: str,
        target_date: date,
        history: Dict[str, dict],
    ) -> Optional[dict]:
        """
        回傳 target_date 當日可知的最新月營收（取 <= target_date 的最新報告）。
        """
        valid = {d: v for d, v in history.items() if d <= target_date.isoformat()}
        if not valid:
            return None
        return valid[max(valid)]


class FinMindInstitutionalLoader:
    """
    從 FinMind 載入歷史三大法人資料，計算外資/投信連續買超天數。

    回傳格式（inst_map）:
        { stock_id: { date: {"foreign_net": float, "trust_net": float,
                              "foreign_consecutive": int, "trust_consecutive": int} } }
    """

    def __init__(self, api_token: str = "", cache_dir: Path = _DEFAULT_CACHE_DIR):
        self.api_token = api_token
        self.cache_dir = cache_dir

    def _cache_path(self, stock_id: str) -> Path:
        return self.cache_dir / f"finmind_inst_{stock_id}_{date.today().isoformat()}.json"

    def _load_cache(self, stock_id: str) -> Optional[Dict]:
        p = self._cache_path(stock_id)
        if not p.exists():
            return None
        try:
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def _save_cache(self, stock_id: str, data: Dict) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        with open(self._cache_path(stock_id), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)

    def load_stock_institutional_history(
        self,
        stock_id: str,
        start_date: str,
        end_date: str,
        lookback_extra_days: int = 60,
    ) -> Dict[str, dict]:
        """
        取得 stock_id 的三大法人歷史，計算每日外資/投信淨買超及連續買超天數。

        Args:
            lookback_extra_days: 取更早資料以計算連續買超（預設 60 天）

        Returns:
            Dict mapping date_str -> {"foreign_net": shares, "trust_net": shares,
                                       "foreign_consecutive": int, "trust_consecutive": int}
        """
        cached = self._load_cache(stock_id)
        if cached is not None:
            return cached

        try:
            from FinMind.data import DataLoader
            from datetime import datetime
            dl = DataLoader()
            if self.api_token:
                dl.login_by_token(api_token=self.api_token)

            sd = datetime.strptime(start_date, "%Y-%m-%d")
            fetch_start = (sd - timedelta(days=lookback_extra_days)).strftime("%Y-%m-%d")

            df = dl.taiwan_stock_institutional_investors(
                stock_id=stock_id,
                start_date=fetch_start,
                end_date=end_date,
            )

            if df is None or len(df) == 0:
                return {}

            # 彙整每日 Foreign_Investor 與 Investment_Trust 淨買超
            daily: Dict[str, Dict[str, float]] = {}
            for _, row in df.iterrows():
                d = str(row["date"])[:10]
                name = str(row["name"])
                net = float(row["buy"]) - float(row["sell"])
                if d not in daily:
                    daily[d] = {"foreign_net": 0.0, "trust_net": 0.0}
                if name == "Foreign_Investor":
                    daily[d]["foreign_net"] += net
                elif name == "Investment_Trust":
                    daily[d]["trust_net"] += net

            # 按日期排序，計算連續買超天數
            sorted_dates = sorted(daily.keys())
            result: Dict[str, dict] = {}
            f_streak = 0
            t_streak = 0

            for d in sorted_dates:
                f_net = daily[d]["foreign_net"]
                t_net = daily[d]["trust_net"]
                f_streak = f_streak + 1 if f_net > 0 else 0
                t_streak = t_streak + 1 if t_net > 0 else 0
                result[d] = {
                    "foreign_net": f_net,
                    "trust_net": t_net,
                    "foreign_consecutive": f_streak,
                    "trust_consecutive": t_streak,
                }

            self._save_cache(stock_id, result)
            return result

        except Exception as exc:
            logger.warning(f"[FinMind] 法人 {stock_id} 取得失敗: {exc}")
            return {}

    def get_institutional_on_date(
        self,
        stock_id: str,
        target_date: date,
        history: Dict[str, dict],
    ) -> Optional[dict]:
        """回傳 target_date 當日法人資料（精確日期匹配）。"""
        return history.get(target_date.isoformat())
