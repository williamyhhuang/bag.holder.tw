"""
ma-cross 細產業 top N 回測
==========================
每個交易日 t 收盤後，依 ma-cross 的規則選股（與 MACrossScanner 同一套條件）：
  1. 均線條件（ma_cross_screener.detect_ma_cross_flat60 的向量化版本）＋ 當日成交量門檻
  2. 細產業指標（sub_industry_index 的向量化版本）：成交值 >= 門檻、漲幅前 N 名

進場：t+1 開盤價；出場：t+h 收盤價（h = 1, 5, 10, 20 個交易日）。
另以「同期間全市場等權平均報酬」計算超額報酬，排除大盤漲跌的影響。

一致性：tests/test_ma_cross_backtest.py 會比對向量化結果與生產端逐日函式完全一致。

限制：細產業成分股使用目前的對照表（存在倖存者／分類前視偏誤），
      價格資料可能為還原價，成交值為近似值。
"""

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence

import numpy as np
import pandas as pd

from src.utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_HORIZONS = (1, 5, 10, 20)


@dataclass
class Panel:
    """寬表：index = 交易日、columns = 股票代號"""
    open: pd.DataFrame
    close: pd.DataFrame
    volume: pd.DataFrame


def build_panel(price_frames: Dict[str, Dict], min_coverage: float = 0.5) -> Panel:
    """將 load_price_frames 的輸出轉成寬表。

    只保留「當天有資料的股票數 >= 全市場 min_coverage」的日期，
    避免少數髒資料（例如非交易日的 TEST 檔）產生假交易日。
    """
    opens, closes, vols = {}, {}, {}
    for code, item in price_frames.items():
        df = item["df"].set_index("date")
        closes[code] = df["close"].astype(float)
        vols[code] = df["volume"].astype(float)
        opens[code] = df["open"].astype(float) if "open" in df else df["close"].astype(float)
    close = pd.DataFrame(closes).sort_index()
    counts = close.notna().sum(axis=1)
    valid_days = counts[counts >= counts.max() * min_coverage].index
    close = close.loc[valid_days]
    return Panel(
        open=pd.DataFrame(opens).reindex(index=valid_days, columns=close.columns),
        close=close,
        volume=pd.DataFrame(vols).reindex(index=valid_days, columns=close.columns),
    )


def ma_cross_signals(
    close: pd.DataFrame,
    lookback_days: int = 5,
    slope_days: int = 5,
    flat_tolerance: float = 0.002,
) -> pd.DataFrame:
    """向量化均線條件（布林寬表），邏輯與 detect_ma_cross_flat60 相同。

    每檔股票以「自己有交易的日子」計算均線（與生產端逐檔計算一致），停牌日不視為交易日。
    """
    out = pd.DataFrame(False, index=close.index, columns=close.columns)
    need = 60 + max(lookback_days, slope_days) + 1
    for code in close.columns:
        s = close[code].dropna()
        if len(s) < need:
            continue
        ma5, ma10, ma20, ma60 = (s.rolling(n).mean() for n in (5, 10, 20, 60))
        slope = ma60 / ma60.shift(slope_days) - 1
        diff = ma20 - ma60
        cond = (
            (slope <= flat_tolerance)
            & (ma5 > ma60) & (ma10 > ma60) & (ma20 > ma60)
            & (diff.shift(lookback_days) <= 0)
        )
        # 前 need-1 根資料不足，生產端會直接回傳 None
        cond.iloc[: need - 1] = False
        out.loc[cond.index, code] = cond.to_numpy()
    return out


def sub_industry_daily_metrics(
    panel: Panel,
    sub_industries: Dict[str, Dict],
    weighting: str = "equal",
) -> Dict[str, pd.DataFrame]:
    """每日每個細產業的漲幅與成交值，邏輯與 compute_sub_industry_metrics 相同。

    Returns: {"change_pct": 寬表(日 × 細產業), "trade_value": 寬表(日 × 細產業)}
    """
    if weighting not in ("equal", "value"):
        raise ValueError(f"未知的加權方式: {weighting}")

    # 漲跌幅以「該股前一個有交易的日子」為基準（與 build_daily_snapshot 一致）
    change = pd.DataFrame(index=panel.close.index, columns=panel.close.columns, dtype=float)
    for code in panel.close.columns:
        s = panel.close[code].dropna()
        prev = s.shift(1)
        pct = (s / prev - 1) * 100
        pct[~(prev > 0)] = np.nan
        change.loc[pct.index, code] = pct.to_numpy()
    value = panel.close * panel.volume
    # 只計入「有漲跌幅」的成分股（停牌或第一天上市不計）
    value = value.where(change.notna())

    chg_cols, val_cols = {}, {}
    for sub_id, info in sub_industries.items():
        members = [c for c in info["codes"] if c in change.columns]
        if not members:
            continue
        c, v = change[members], value[members]
        total = v.sum(axis=1, min_count=1)
        if weighting == "value":
            weighted = (c * v).sum(axis=1, min_count=1) / total
            chg = weighted.where(total > 0, c.mean(axis=1))
        else:
            chg = c.mean(axis=1)
        chg_cols[sub_id] = chg
        val_cols[sub_id] = total
    return {"change_pct": pd.DataFrame(chg_cols), "trade_value": pd.DataFrame(val_cols)}


def hot_sub_industry_mask(
    metrics: Dict[str, pd.DataFrame],
    min_trade_value: float,
    top_n: int,
) -> pd.DataFrame:
    """每日入選的熱門細產業（布林寬表），邏輯與 select_hot_sub_industries 相同"""
    chg = metrics["change_pct"].where(metrics["trade_value"] >= min_trade_value)
    if top_n <= 0:
        return chg.notna()
    # method="first"：同分時依欄位順序，與 sort_values(稳定排序) 一致
    rank = chg.rank(axis=1, ascending=False, method="first")
    return rank <= top_n


def stock_hot_mask(
    hot: pd.DataFrame,
    sub_industries: Dict[str, Dict],
    columns: Sequence[str],
) -> pd.DataFrame:
    """股票任一所屬細產業入選 → True"""
    out = pd.DataFrame(False, index=hot.index, columns=list(columns))
    col_set = set(columns)
    for sub_id in hot.columns:
        members = [c for c in sub_industries[sub_id]["codes"] if c in col_set]
        if not members:
            continue
        flag = hot[sub_id].to_numpy()[:, None]
        out[members] = out[members].to_numpy() | flag
    return out


def forward_returns(panel: Panel, horizons: Iterable[int]) -> Dict[int, pd.DataFrame]:
    """t 日訊號 → t+1 開盤進場、t+h 收盤出場的報酬（%）"""
    entry = panel.open.shift(-1)
    entry = entry.where(entry > 0)
    return {h: (panel.close.shift(-h) / entry - 1) * 100 for h in horizons}


def summarize(
    signals: pd.DataFrame,
    fwd: Dict[int, pd.DataFrame],
    market: Dict[int, pd.Series],
    label: str,
) -> Dict:
    """彙整單一組合的訊號統計"""
    row: Dict = {"variant": label}
    stacked = signals.stack()
    picks = stacked[stacked].index
    row["signals"] = len(picks)
    row["days_with_signal"] = int(signals.any(axis=1).sum())
    for h, ret in fwd.items():
        r = ret.stack().reindex(picks).dropna()
        if r.empty:
            row.update({f"ret{h}d": np.nan, f"win{h}d": np.nan, f"excess{h}d": np.nan, f"med{h}d": np.nan})
            continue
        mkt = market[h].reindex(r.index.get_level_values(0)).to_numpy()
        excess = r.to_numpy() - mkt
        row[f"ret{h}d"] = r.mean()
        row[f"med{h}d"] = r.median()
        row[f"win{h}d"] = (r > 0).mean() * 100
        row[f"excess{h}d"] = np.nanmean(excess)
    return row


def first_entries(signals: pd.DataFrame) -> pd.DataFrame:
    """只保留「當天新進榜」的訊號（前一個交易日不在名單內）"""
    return signals & ~signals.shift(1, fill_value=False)


def run_topn_backtest(
    panel: Panel,
    sub_industries: Dict[str, Dict],
    top_ns: Sequence[int] = (5, 10, 15, 20, 30),
    horizons: Sequence[int] = DEFAULT_HORIZONS,
    lookback_days: int = 5,
    slope_days: int = 5,
    flat_tolerance: float = 0.002,
    min_trade_value: float = 1e10,
    weighting: str = "equal",
    min_volume_lots: int = 0,
    start: Optional[pd.Timestamp] = None,
    end: Optional[pd.Timestamp] = None,
    new_entries_only: bool = True,
) -> pd.DataFrame:
    """比較不同 top N（以及不過濾）的訊號績效。

    Returns: 每列一個組合（no_filter / top{N}）的統計表
    """
    base = ma_cross_signals(panel.close, lookback_days, slope_days, flat_tolerance)
    if min_volume_lots > 0:
        # 當日成交量門檻（與 MACrossScanner 相同，單位：張 → 股）
        base = base & (panel.volume >= min_volume_lots * 1000).fillna(False)
    metrics = sub_industry_daily_metrics(panel, sub_industries, weighting)
    fwd = forward_returns(panel, horizons)
    market = {h: r.mean(axis=1) for h, r in fwd.items()}

    def clip(df: pd.DataFrame) -> pd.DataFrame:
        if start is not None:
            df = df.loc[df.index >= start]
        if end is not None:
            df = df.loc[df.index <= end]
        return df

    variants: List[tuple] = [("no_filter", base)]
    for n in top_ns:
        hot = hot_sub_industry_mask(metrics, min_trade_value, n)
        mask = stock_hot_mask(hot.reindex(base.index, fill_value=False), sub_industries, base.columns)
        variants.append((f"top{n}", base & mask))

    rows = []
    for label, sig in variants:
        sig = first_entries(sig) if new_entries_only else sig
        rows.append(summarize(clip(sig), fwd, market, label))
    return pd.DataFrame(rows)
