"""
均線穿越 60MA 掃描 + 細產業指標過濾
====================================
1. 讀取 data/stocks/*.csv 日K
2. 篩出「5/10/20MA 穿越下彎或走平的 60MA」且當日成交量 >= min_volume_lots 張的股票（ma_cross_screener）
3. 以產業價值鏈平台的細產業成分股合成細產業指標（sub_industry_index），
   保留「所屬細產業指標成交值 >= 門檻，且漲幅排名前 N」的股票
4. 附上股票名稱、官方產業別、所屬細產業
"""

import glob
import os
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional

import pandas as pd

from config.settings import settings
from src.domain.services.ma_cross_screener import detect_ma_cross_flat60
from src.domain.services.sub_industry_index import (
    build_daily_snapshot,
    compute_sub_industry_metrics,
    latest_trading_date,
    select_hot_sub_industries,
)
from src.utils.logger import get_logger
from src.utils.stock_industry_mapper import get_sector_name, get_stock_industries
from src.utils.stock_name_mapper import get_stock_names
from src.utils.sub_industry_mapper import (
    build_stock_to_sub_industries,
    format_sub_industry,
    get_sub_industries,
)

logger = get_logger(__name__)

RESULT_COLUMNS = [
    "cross_date", "code", "name", "market", "sector", "sub_industries", "hot_sub_industries",
    "main_sub_industry",
    "close", "change_pct", "ma5", "ma10", "ma20", "ma60", "ma60_slope_pct", "volume",
]


@dataclass
class MACrossScanResult:
    as_of: Optional[date]
    candidates: pd.DataFrame                 # 只通過均線條件的股票
    stocks: pd.DataFrame                     # 再通過細產業過濾的股票（未啟用過濾時 = candidates）
    sub_industry_metrics: pd.DataFrame = field(default_factory=pd.DataFrame)
    hot_sub_industries: pd.DataFrame = field(default_factory=pd.DataFrame)


def load_price_frames(stocks_dir: str) -> Dict[str, Dict]:
    """讀取每檔 CSV。回傳 {代號: {"market": "TW"/"TWO", "df": DataFrame}}"""
    frames: Dict[str, Dict] = {}
    for path in glob.glob(os.path.join(stocks_dir, "*.csv")):
        stem = os.path.splitext(os.path.basename(path))[0]
        if stem.upper().startswith("TEST") or "_" not in stem:
            continue
        code, market = stem.split("_", 1)
        try:
            df = pd.read_csv(path, usecols=lambda c: c in ("date", "open", "close", "volume"))
        except Exception as e:
            logger.warning(f"讀取 {path} 失敗: {e}")
            continue
        # 日期可能帶時區字串（"2026-03-30 00:00:00+08:00"），只取日期部分
        df["date"] = pd.to_datetime(df["date"].astype(str).str[:10], errors="coerce")
        df = (
            df.dropna(subset=["date", "close", "volume"])
            .sort_values("date")
            .drop_duplicates("date", keep="last")
            .reset_index(drop=True)
        )
        if not df.empty:
            frames[code] = {"market": market, "df": df}
    return frames


class MACrossScanner:
    def __init__(self, cfg=None, stocks_dir: Optional[str] = None):
        self.cfg = cfg or settings.ma_cross
        self.stocks_dir = stocks_dir or settings.data.stocks_path

    def scan(
        self,
        price_frames: Optional[Dict[str, Dict]] = None,
        sub_industries: Optional[Dict[str, Dict]] = None,
        names: Optional[Dict[str, str]] = None,
        industries: Optional[Dict[str, str]] = None,
        apply_sub_industry_filter: Optional[bool] = None,
    ) -> MACrossScanResult:
        cfg = self.cfg
        if apply_sub_industry_filter is None:
            apply_sub_industry_filter = cfg.enable_sub_industry_filter

        if price_frames is None:
            price_frames = load_price_frames(self.stocks_dir)
        dfs = {code: item["df"] for code, item in price_frames.items()}
        as_of = latest_trading_date(dfs)
        if as_of is None:
            empty = pd.DataFrame(columns=RESULT_COLUMNS)
            return MACrossScanResult(None, empty, empty)
        as_of_ts = pd.Timestamp(as_of)

        if sub_industries is None:
            sub_industries = get_sub_industries(ttl_hours=cfg.sub_industry_cache_ttl_hours)
        if names is None:
            names = get_stock_names()
        if industries is None:
            industries = get_stock_industries()
        stock_subs = build_stock_to_sub_industries(sub_industries)

        # ── 細產業指標 ───────────────────────────────────────────────
        snapshot = build_daily_snapshot(dfs, as_of)
        metrics = compute_sub_industry_metrics(snapshot, sub_industries, cfg.sub_industry_weighting)
        hot = select_hot_sub_industries(metrics, cfg.sub_industry_min_trade_value, cfg.sub_industry_top_n)
        hot_rank = {sub_id: i for i, sub_id in enumerate(hot["sub_id"])}  # 漲幅排名，0 = 第一名

        # ── 均線條件 ─────────────────────────────────────────────────
        rows: List[Dict] = []
        for code, item in price_frames.items():
            df = item["df"]
            if df["date"].iloc[-1] != as_of_ts:  # 停牌或資料未更新
                continue
            hit = detect_ma_cross_flat60(
                df,
                lookback_days=cfg.lookback_days,
                slope_days=cfg.ma60_slope_days,
                flat_tolerance=cfg.ma60_flat_tolerance,
            )
            if hit is None:
                continue
            # 成交量門檻（CSV 成交量單位為股）
            if df["volume"].iloc[-1] < cfg.min_volume_lots * 1000:
                continue
            market = item["market"]
            subs = stock_subs.get(code, [])
            rows.append({
                "cross_date": hit["cross_date"],
                "code": code,
                "name": names.get(f"{code}.{market}", ""),
                "market": {"TW": "上市", "TWO": "上櫃"}.get(market, market),
                "sector": get_sector_name(industries[code]) if code in industries else "",
                "sub_industries": "、".join(format_sub_industry(sub_industries[s]) for s in subs),
                "hot_sub_industries": "、".join(
                    format_sub_industry(sub_industries[s]) for s in subs if s in hot_rank
                ),
                # 代表細產業：所屬熱門細產業中排名最前者；無熱門細產業時取第一個所屬細產業
                "main_sub_industry": self._main_sub_industry(subs, hot_rank, sub_industries),
                "close": round(hit["close"], 2),
                # 當日漲跌幅（%）：相對該股前一個有交易的日子
                "change_pct": round((df["close"].iloc[-1] / df["close"].iloc[-2] - 1) * 100, 2),
                "ma5": round(hit["ma5"], 2),
                "ma10": round(hit["ma10"], 2),
                "ma20": round(hit["ma20"], 2),
                "ma60": round(hit["ma60"], 2),
                "ma60_slope_pct": round(hit["ma60_slope"] * 100, 2),
                "volume": int(df["volume"].iloc[-1]),
            })

        candidates = pd.DataFrame(rows, columns=RESULT_COLUMNS)
        if not candidates.empty:
            candidates = candidates.sort_values(
                ["cross_date", "volume"], ascending=[False, False]
            ).reset_index(drop=True)

        stocks = candidates
        if apply_sub_industry_filter:
            stocks = candidates[candidates["hot_sub_industries"] != ""].reset_index(drop=True)

        logger.info(
            f"{as_of}: 均線條件 {len(candidates)} 檔，熱門細產業 {len(hot)} 個，"
            f"過濾後 {len(stocks)} 檔"
        )
        return MACrossScanResult(as_of, candidates, stocks, metrics, hot)

    @staticmethod
    def _main_sub_industry(subs: List[str], hot_rank: Dict[str, int], sub_industries: Dict[str, Dict]) -> str:
        hot_subs = [s for s in subs if s in hot_rank]
        if hot_subs:
            return format_sub_industry(sub_industries[min(hot_subs, key=hot_rank.get)])
        return format_sub_industry(sub_industries[subs[0]]) if subs else ""

    def save(self, result: MACrossScanResult, output_dir: Optional[str] = None) -> str:
        out_dir = output_dir or self.cfg.output_dir
        os.makedirs(out_dir, exist_ok=True)
        stamp = result.as_of.strftime("%Y%m%d") if result.as_of else "unknown"
        path = os.path.join(out_dir, f"ma_cross_{stamp}.csv")
        result.stocks.to_csv(path, index=False, encoding="utf-8-sig")
        metrics_path = os.path.join(out_dir, f"sub_industry_metrics_{stamp}.csv")
        result.sub_industry_metrics.sort_values("change_pct", ascending=False).to_csv(
            metrics_path, index=False, encoding="utf-8-sig"
        )
        return path
