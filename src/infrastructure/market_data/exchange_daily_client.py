"""
證交所 / 櫃買中心「每日收盤行情」（全市場單日 OHLCV）
====================================================
一次請求取得當日所有上市（或上櫃）股票的行情，用於補齊歷史缺口：
  - 富邦快照 API 只能抓今天；富邦歷史 K 線逐檔且限速，2000 檔無法在工作逾時內完成
  - yfinance 從 GCP 對外 IP 下載會被 Yahoo 限流

資料為未還原的原始價格（與富邦快照一致），成交量單位為「股」。

  TWSE: https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?date=YYYYMMDD&type=ALLBUT0999&response=json
  TPEx: https://www.tpex.org.tw/www/zh-tw/afterTrading/dailyQuotes?date=YYYY/MM/DD&response=json

非交易日兩者都回傳空資料。
"""

import time
from datetime import date
from typing import Dict, List, Optional

import pandas as pd
import requests
import urllib3

from src.utils.logger import get_logger

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = get_logger(__name__)

TWSE_URL = "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX"
TPEX_URL = "https://www.tpex.org.tw/www/zh-tw/afterTrading/dailyQuotes"
_HEADERS = {"User-Agent": "Mozilla/5.0"}

COLUMNS = ["code", "open", "high", "low", "close", "volume"]


def _num(value) -> Optional[float]:
    """'1,234.5' → 1234.5；'--'、'---'、'' 等無成交 → None"""
    text = str(value).replace(",", "").strip()
    try:
        return float(text)
    except ValueError:
        return None


def _rows_to_frame(rows: List[Dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows, columns=COLUMNS)
    # 當日無成交（價格為 '--'）的股票不寫入，避免以 0 或空值污染均線
    return df.dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)


def parse_twse(payload: Dict) -> pd.DataFrame:
    """解析 MI_INDEX 回應中的「每日收盤行情」表"""
    for table in payload.get("tables") or []:
        if "每日收盤行情" not in (table.get("title") or ""):
            continue
        idx = {name: i for i, name in enumerate(table.get("fields") or [])}
        rows = []
        for r in table.get("data") or []:
            rows.append({
                "code": str(r[idx["證券代號"]]).strip(),
                "open": _num(r[idx["開盤價"]]),
                "high": _num(r[idx["最高價"]]),
                "low": _num(r[idx["最低價"]]),
                "close": _num(r[idx["收盤價"]]),
                "volume": _num(r[idx["成交股數"]]) or 0.0,
            })
        return _rows_to_frame(rows)
    return pd.DataFrame(columns=COLUMNS)


def parse_tpex(payload: Dict) -> pd.DataFrame:
    """解析 dailyQuotes 回應中的「上櫃股票行情」表"""
    for table in payload.get("tables") or []:
        if "上櫃股票行情" not in (table.get("title") or ""):
            continue
        idx = {name: i for i, name in enumerate(table.get("fields") or [])}
        rows = []
        for r in table.get("data") or []:
            rows.append({
                "code": str(r[idx["代號"]]).strip(),
                "open": _num(r[idx["開盤"]]),
                "high": _num(r[idx["最高"]]),
                "low": _num(r[idx["最低"]]),
                "close": _num(r[idx["收盤"]]),
                "volume": _num(r[idx["成交股數"]]) or 0.0,
            })
        return _rows_to_frame(rows)
    return pd.DataFrame(columns=COLUMNS)


class ExchangeDailyClient:
    def __init__(self, request_interval: float = 2.0, timeout: float = 30.0, max_retries: int = 3):
        # 證交所對高頻請求會暫時封鎖 IP，每次請求間隔 2 秒
        self.request_interval = request_interval
        self.timeout = timeout
        self.max_retries = max_retries

    def _get_json(self, url: str, params: Dict) -> Dict:
        last_error: Optional[Exception] = None
        for attempt in range(self.max_retries):
            try:
                resp = requests.get(url, params=params, headers=_HEADERS, timeout=self.timeout, verify=False)
                resp.raise_for_status()
                return resp.json()
            except Exception as e:  # 網路錯誤或被暫時封鎖時回傳 HTML
                last_error = e
                time.sleep(self.request_interval * (attempt + 2))
            finally:
                time.sleep(self.request_interval)
        raise RuntimeError(f"{url} 請求失敗: {last_error}")

    def fetch_twse(self, day: date) -> pd.DataFrame:
        payload = self._get_json(TWSE_URL, {"date": day.strftime("%Y%m%d"), "type": "ALLBUT0999", "response": "json"})
        return parse_twse(payload)

    def fetch_tpex(self, day: date) -> pd.DataFrame:
        payload = self._get_json(TPEX_URL, {"date": day.strftime("%Y/%m/%d"), "id": "", "response": "json"})
        return parse_tpex(payload)

    def fetch_day(self, day: date) -> Dict[str, pd.DataFrame]:
        """回傳 {"TW": 上市行情, "TWO": 上櫃行情}；非交易日兩者皆為空"""
        return {"TW": self.fetch_twse(day), "TWO": self.fetch_tpex(day)}
