"""
ma-cross 細產業 top N 回測比較

用法：
    python scripts/backtest_ma_cross_topn.py
    python scripts/backtest_ma_cross_topn.py --top-n 5 10 20 --start 2023-01-01
    python scripts/backtest_ma_cross_topn.py --all-days      # 計入連續多天在榜的重複訊號
"""
import argparse
import os
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import settings
from src.application.services.ma_cross_backtest import build_panel, run_topn_backtest
from src.application.services.ma_cross_scanner import load_price_frames
from src.utils.sub_industry_mapper import get_sub_industries


def main() -> None:
    cfg = settings.ma_cross
    p = argparse.ArgumentParser(description="ma-cross 細產業 top N 回測比較")
    p.add_argument("--top-n", type=int, nargs="+", default=[5, 10, 15, 20, 30])
    p.add_argument("--start", help="訊號起始日 YYYY-MM-DD")
    p.add_argument("--end", help="訊號結束日 YYYY-MM-DD")
    p.add_argument("--all-days", action="store_true", help="計入連續在榜的每一天（預設只算新進榜）")
    p.add_argument("--by-year", action="store_true", help="另外輸出逐年結果")
    p.add_argument("--output", default=os.path.join(cfg.output_dir, "topn_backtest.csv"))
    args = p.parse_args()

    frames = load_price_frames(settings.data.stocks_path)
    panel = build_panel(frames)
    subs = get_sub_industries(ttl_hours=cfg.sub_industry_cache_ttl_hours)
    common = dict(
        top_ns=args.top_n,
        lookback_days=cfg.lookback_days,
        slope_days=cfg.ma60_slope_days,
        flat_tolerance=cfg.ma60_flat_tolerance,
        min_trade_value=cfg.sub_industry_min_trade_value,
        weighting=cfg.sub_industry_weighting,
        min_volume_lots=cfg.min_volume_lots,
        new_entries_only=not args.all_days,
    )
    start = pd.Timestamp(args.start) if args.start else None
    end = pd.Timestamp(args.end) if args.end else None

    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", 50)
    pd.set_option("display.float_format", lambda v: f"{v:,.2f}")

    print(f"資料期間：{panel.close.index[0].date()} ~ {panel.close.index[-1].date()}，"
          f"{panel.close.shape[1]} 檔，{len(subs)} 個細產業")
    result = run_topn_backtest(panel, subs, start=start, end=end, **common)
    print("\n=== 全期間 ===")
    print(result.to_string(index=False))

    frames_out = [result.assign(period="all")]
    if args.by_year:
        for year in sorted(set(panel.close.index.year)):
            ys, ye = pd.Timestamp(f"{year}-01-01"), pd.Timestamp(f"{year}-12-31")
            ys, ye = max(ys, start) if start else ys, min(ye, end) if end else ye
            r = run_topn_backtest(panel, subs, start=ys, end=ye, **common)
            print(f"\n=== {year} ===")
            print(r.to_string(index=False))
            frames_out.append(r.assign(period=str(year)))

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    pd.concat(frames_out).to_csv(args.output, index=False, encoding="utf-8-sig")
    print(f"\n💾 已輸出：{args.output}")


if __name__ == "__main__":
    main()
