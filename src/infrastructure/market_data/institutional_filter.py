"""
Institutional Flow Filter (三大法人籌碼過濾器)
===============================================
取得每日三大法人（外資、投信、自營商）買賣超資料，
作為技術訊號的早期驗證過濾器。

法人買超通常比散戶早 3-10 天，可過濾掉「散戶追高」而機構未跟進的假突破。

資料來源：TWSE T86（上市三大法人）
  https://www.twse.com.tw/rwd/zh/fund/T86?response=json&date=YYYYMMDD&selectType=ALLBUT0999

注意：T86 僅涵蓋上市（TSE）股票。上櫃（OTC）股票法人資料另需 TPEX API，
目前以 fail-open 處理（OTC 股票不受法人過濾限制）。

快取：data/cache/institutional_cache.json（每交易日刷新）
"""

import json
import logging
from dataclasses import dataclass, asdict
from datetime import date
from pathlib import Path
from typing import Dict, Optional

import requests

logger = logging.getLogger(__name__)

_T86_URL = (
    "https://www.twse.com.tw/rwd/zh/fund/T86"
    "?response=json&date={date}&selectType=ALLBUT0999"
)

_DEFAULT_CACHE_PATH = (
    Path(__file__).parent.parent.parent / "data" / "cache" / "institutional_cache.json"
)


@dataclass
class InstitutionalFlow:
    """單日三大法人買賣超資料（單位：股）"""
    foreign_net: int    # 外資（含外資自營）買賣超
    trust_net: int      # 投信買賣超
    dealer_net: int     # 自營商買賣超
    total_net: int      # 三大法人合計買賣超


def _parse_int(raw: str) -> int:
    """解析帶逗號的整數字串（如 '1,234,567' 或 '-500,000'）"""
    try:
        return int(str(raw).replace(",", "").strip())
    except (ValueError, AttributeError):
        return 0


def _fetch_institutional_from_api(target_date: date) -> Dict[str, InstitutionalFlow]:
    """
    從 TWSE T86 API 抓取指定交易日的三大法人資料。

    Args:
        target_date: 目標日期（需為交易日）。

    Returns:
        dict mapping 股票代號（如 "2330"）→ InstitutionalFlow
        非交易日或 API 失敗時回傳空 dict。
    """
    date_str = target_date.strftime("%Y%m%d")
    url = _T86_URL.format(date=date_str)

    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()

        data = resp.json()

        # 非交易日：{"stat": "no data"} 或 {"stat": "很抱歉，沒有符合..."}
        if data.get("stat", "").startswith(("no", "很抱歉")):
            logger.info(f"[institutional] {target_date} 非交易日或無資料")
            return {}

        rows = data.get("data", [])
        result: Dict[str, InstitutionalFlow] = {}

        for row in rows:
            if not isinstance(row, list) or len(row) < 19:
                continue

            code = str(row[0]).strip()
            if not code or not code.isdigit():
                continue

            # T86 欄位索引（以 selectType=ALLBUT0999 為準）：
            # [0]  證券代號
            # [1]  證券名稱
            # [2]  外陸資買進股數
            # [3]  外陸資賣出股數
            # [4]  外陸資買賣超股數   ← 外資合計
            # [5]  外資自營商買進股數
            # [6]  外資自營商賣出股數
            # [7]  外資自營商買賣超股數
            # [8]  投信買進股數
            # [9]  投信賣出股數
            # [10] 投信買賣超股數     ← 投信
            # [11] 自營商買賣超股數   ← 自營商合計
            # [12] 自營商買進股數(自行)
            # [13] 自營商賣出股數(自行)
            # [14] 自營商買賣超股數(自行)
            # [15] 自營商買進股數(避險)
            # [16] 自營商賣出股數(避險)
            # [17] 自營商買賣超股數(避險)
            # [18] 三大法人買賣超股數 ← 合計
            try:
                flow = InstitutionalFlow(
                    foreign_net=_parse_int(row[4]),
                    trust_net=_parse_int(row[10]),
                    dealer_net=_parse_int(row[11]),
                    total_net=_parse_int(row[18]),
                )
                result[code] = flow
            except (IndexError, Exception) as exc:
                logger.debug(f"[institutional] 解析 {code} 失敗: {exc}")
                continue

        logger.info(
            f"[institutional] {target_date} 取得 {len(result)} 支三大法人資料"
        )
        return result

    except Exception as exc:
        logger.warning(f"[institutional] T86 API 失敗: {exc}")
        return {}


class InstitutionalFlowLoader:
    """
    三大法人資料載入器（帶當日磁碟快取）。

    快取格式：
        {
            "date": "YYYY-MM-DD",
            "data": {
                "2330": {"foreign_net": 1000000, "trust_net": 200000, ...},
                ...
            }
        }
    """

    def __init__(self, cache_path: Path = _DEFAULT_CACHE_PATH):
        self.cache_path = cache_path

    def _load_cache(
        self, target_date: date
    ) -> Optional[Dict[str, InstitutionalFlow]]:
        if not self.cache_path.exists():
            return None
        try:
            with open(self.cache_path, encoding="utf-8") as f:
                payload = json.load(f)
            if payload.get("date") != target_date.isoformat():
                return None
            raw_data = payload.get("data", {})
            return {
                code: InstitutionalFlow(**v) for code, v in raw_data.items()
            }
        except Exception:
            return None

    def _save_cache(
        self, target_date: date, data: Dict[str, InstitutionalFlow]
    ) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        serializable = {code: asdict(flow) for code, flow in data.items()}
        with open(self.cache_path, "w", encoding="utf-8") as f:
            json.dump(
                {"date": target_date.isoformat(), "data": serializable},
                f,
                ensure_ascii=False,
            )
        logger.info(
            f"[institutional] 快取已儲存至 {self.cache_path}，共 {len(data)} 支"
        )

    def load(
        self, target_date: Optional[date] = None
    ) -> Dict[str, InstitutionalFlow]:
        """
        回傳三大法人買賣超字典。
        優先使用當日快取，無快取時從 T86 API 抓取並存檔。
        API 失敗或非交易日時回傳空 dict（fail-open，不阻斷掃描）。

        Args:
            target_date: 目標日期，預設為今天。
        """
        if target_date is None:
            target_date = date.today()

        cached = self._load_cache(target_date)
        if cached is not None:
            logger.info(f"[institutional] 使用快取（{len(cached)} 支）")
            return cached

        logger.info(f"[institutional] 快取不存在或已過期，從 T86 API 抓取 {target_date}...")
        data = _fetch_institutional_from_api(target_date)

        if data:
            self._save_cache(target_date, data)
        else:
            logger.warning(
                "[institutional] 未能取得三大法人資料，法人過濾將略過（fail-open）"
            )

        return data
