"""
均線穿越下彎/走平 60MA 篩選
==========================
條件（皆以日K收盤價計算）：
  1. 60MA 下彎或走平：今日 60MA / slope_days 日前 60MA - 1 <= flat_tolerance
  2. 短均線（預設 5MA、10MA，見 short_periods）皆在 60MA 之上
  3. 最近 lookback_days 個交易日內，最慢的短均線（預設 10MA）由下往上穿越 60MA
     （最慢的穿越代表所有短均線都已站上 60MA）
20MA 不參與判斷，只作為參考數值輸出。
"""

from typing import Dict, Optional, Sequence

import pandas as pd

MA_PERIODS = (5, 10, 20, 60)
DEFAULT_SHORT_PERIODS = (5, 10)


def detect_ma_cross_flat60(
    df: pd.DataFrame,
    lookback_days: int = 5,
    slope_days: int = 5,
    flat_tolerance: float = 0.002,
    short_periods: Sequence[int] = DEFAULT_SHORT_PERIODS,
) -> Optional[Dict]:
    """檢查單一股票是否符合條件。

    Args:
        df: 依日期升冪排序、含 date / close 欄位的日K資料
    Returns:
        符合時回傳最新一日的均線數值與穿越日；不符合回傳 None
    """
    need = 60 + max(lookback_days, slope_days) + 1
    if len(df) < need:
        return None

    close = df["close"].astype(float)
    ma = {n: close.rolling(n).mean() for n in set(MA_PERIODS) | set(short_periods)}
    ma60 = ma[60]

    slope = ma60.iloc[-1] / ma60.iloc[-1 - slope_days] - 1
    if slope > flat_tolerance:
        return None

    if not all(ma[n].iloc[-1] > ma60.iloc[-1] for n in short_periods):
        return None

    # 視窗第一天最慢短均線需 <= 60MA，之後某天轉為 > 60MA（且最新一天仍在上方）
    slowest = max(short_periods)
    diff = (ma[slowest] - ma60).iloc[-lookback_days - 1:]
    if diff.iloc[0] > 0:
        return None
    above = (diff > 0).to_numpy()
    first_above = int(above.argmax())
    cross_date = df["date"].iloc[-lookback_days - 1 + first_above]

    return {
        "close": float(close.iloc[-1]),
        "ma5": float(ma[5].iloc[-1]),
        "ma10": float(ma[10].iloc[-1]),
        "ma20": float(ma[20].iloc[-1]),
        "ma60": float(ma60.iloc[-1]),
        "ma60_slope": float(slope),
        "cross_date": pd.Timestamp(cross_date).date(),
    }
