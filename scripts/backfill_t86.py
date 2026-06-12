"""
T86 三大法人歷史資料回填工具
==============================
從 TWSE T86 API 批量下載歷史三大法人買賣超資料，
快取至 src/data/cache/institutional_history/YYYYMMDD.json（永久保存）。

回填後，回測即可使用真實的法人連續買超資料
（取代原本的 0.5 均等填充），參見 build_factor_whitelist。

使用方式:
    cd /Users/yhh/GitHub/bag.holder.tw
    source venv/bin/activate
    # 預設回填回測區間（settings.backtest.start_date − 45 天 → end_date）
    python scripts/backfill_t86.py
    # 自訂區間
    python scripts/backfill_t86.py --start 2024-07-01 --end 2026-06-12
    # 調整 API 請求間隔（預設 1.0 秒，避免被 TWSE 封鎖）
    python scripts/backfill_t86.py --delay 2.0
"""

import argparse
import os
import sys
import time
from datetime import date, datetime, timedelta

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.infrastructure.market_data.institutional_history import (
    InstitutionalHistoryLoader,
)
from config.settings import settings


def backfill(start_date: date, end_date: date, delay: float = 1.0) -> dict:
    """
    回填 [start_date, end_date] 區間的 T86 資料。

    跳過週末與已有快取的日期；非交易日（API 回傳無資料）不快取。

    Returns:
        {"fetched": int, "cached": int, "skipped_weekend": int, "no_data": int}
    """
    loader = InstitutionalHistoryLoader()
    stats = {"fetched": 0, "cached": 0, "skipped_weekend": 0, "no_data": 0}

    total_days = (end_date - start_date).days + 1
    current = start_date
    done = 0

    while current <= end_date:
        done += 1
        if current.weekday() >= 5:  # 週六/週日
            stats["skipped_weekend"] += 1
            current += timedelta(days=1)
            continue

        if loader._cache_path(current).exists():
            stats["cached"] += 1
            current += timedelta(days=1)
            continue

        data = loader.load_date(current)
        if data:
            stats["fetched"] += 1
            print(f"  [{done}/{total_days}] {current} ✓ {len(data)} 支", flush=True)
        else:
            stats["no_data"] += 1
            print(f"  [{done}/{total_days}] {current} — 非交易日/無資料", flush=True)
        time.sleep(delay)
        current += timedelta(days=1)

    return stats


def main():
    cfg = settings.backtest
    default_start = (cfg.start_date or date(2024, 9, 1)) - timedelta(days=45)
    default_end = cfg.end_date or date.today()

    parser = argparse.ArgumentParser(description="T86 法人歷史資料回填")
    parser.add_argument("--start", type=str, default=default_start.isoformat(),
                        help=f"起日 YYYY-MM-DD（預設 {default_start} = 回測起日−45天暖機）")
    parser.add_argument("--end", type=str, default=default_end.isoformat(),
                        help=f"迄日 YYYY-MM-DD（預設 {default_end}）")
    parser.add_argument("--delay", type=float, default=1.0,
                        help="API 請求間隔秒數（預設 1.0）")
    args = parser.parse_args()

    start_date = datetime.strptime(args.start, "%Y-%m-%d").date()
    end_date = datetime.strptime(args.end, "%Y-%m-%d").date()

    print(f"\nT86 法人歷史資料回填  {start_date} → {end_date}  (delay={args.delay}s)")
    print(f"快取目錄: {InstitutionalHistoryLoader().history_dir}\n")

    t0 = time.time()
    stats = backfill(start_date, end_date, delay=args.delay)
    elapsed = time.time() - t0

    print(f"\n完成（{elapsed/60:.1f} 分鐘）")
    print(f"  新抓取: {stats['fetched']} 日")
    print(f"  已有快取: {stats['cached']} 日")
    print(f"  週末跳過: {stats['skipped_weekend']} 日")
    print(f"  非交易日: {stats['no_data']} 日")


if __name__ == "__main__":
    main()
