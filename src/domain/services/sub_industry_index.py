"""
細產業指標計算
==============
以成分股日K自行合成細產業指標（交易所 / 富邦 API 只有官方大分類指數，沒有細產業）。

  - 成交值 = Σ 成分股當日 收盤價 × 成交股數
  - 漲幅   = 成分股當日漲跌幅的平均
             equal：等權平均（預設，避免單一權值股主導）
             value：以當日成交值加權
  - 只計入當日有交易資料、且有前一日收盤價的成分股
"""

from datetime import date
from typing import Dict, List, Optional

import pandas as pd

METRIC_COLUMNS = ["sub_id", "chain", "name", "members", "trade_value", "change_pct"]


def build_daily_snapshot(price_frames: Dict[str, pd.DataFrame], as_of: date) -> pd.DataFrame:
    """取出每檔股票在 as_of 當日的漲跌幅與成交值。

    Args:
        price_frames: {股票代號: 依日期升冪排序、含 date/close/volume 的 DataFrame}
    Returns:
        index 為股票代號，欄位 change_pct（%）、trade_value（元）
    """
    target = pd.Timestamp(as_of)
    rows = {}
    for code, df in price_frames.items():
        hit = df.index[df["date"] == target]
        if len(hit) == 0:
            continue
        pos = df.index.get_loc(hit[-1])
        if pos == 0:
            continue
        prev_close = float(df["close"].iloc[pos - 1])
        close = float(df["close"].iloc[pos])
        if prev_close <= 0:
            continue
        rows[code] = {
            "change_pct": (close / prev_close - 1) * 100,
            "trade_value": close * float(df["volume"].iloc[pos]),
        }
    return pd.DataFrame.from_dict(rows, orient="index", columns=["change_pct", "trade_value"])


def compute_sub_industry_metrics(
    snapshot: pd.DataFrame,
    sub_industries: Dict[str, Dict],
    weighting: str = "equal",
) -> pd.DataFrame:
    """依細產業成分股合成當日指標。

    Args:
        snapshot: build_daily_snapshot 的輸出
        sub_industries: {sub_id: {"name", "chain", "codes"}}
        weighting: "equal" 或 "value"
    """
    if weighting not in ("equal", "value"):
        raise ValueError(f"未知的加權方式: {weighting}")

    records: List[Dict] = []
    for sub_id, info in sub_industries.items():
        members = snapshot.reindex([c for c in info["codes"] if c in snapshot.index])
        if members.empty:
            continue
        trade_value = float(members["trade_value"].sum())
        if weighting == "value" and trade_value > 0:
            change = float((members["change_pct"] * members["trade_value"]).sum() / trade_value)
        else:
            change = float(members["change_pct"].mean())
        records.append({
            "sub_id": sub_id,
            "chain": info["chain"],
            "name": info["name"],
            "members": len(members),
            "trade_value": trade_value,
            "change_pct": change,
        })
    return pd.DataFrame(records, columns=METRIC_COLUMNS)


def select_hot_sub_industries(
    metrics: pd.DataFrame,
    min_trade_value: float,
    top_n: int,
) -> pd.DataFrame:
    """成交值 >= min_trade_value 的細產業中，取漲幅前 top_n 名（top_n <= 0 表示不限）"""
    eligible = metrics[metrics["trade_value"] >= min_trade_value]
    ranked = eligible.sort_values("change_pct", ascending=False)
    if top_n > 0:
        ranked = ranked.head(top_n)
    return ranked.reset_index(drop=True)


def latest_trading_date(price_frames: Dict[str, pd.DataFrame]) -> Optional[date]:
    """以「最多股票共有的最後交易日」作為基準日，避免單一髒資料把日期拉到非交易日"""
    last_dates = pd.Series([df["date"].iloc[-1] for df in price_frames.values() if len(df)])
    if last_dates.empty:
        return None
    return pd.Timestamp(last_dates.mode().iloc[0]).date()
