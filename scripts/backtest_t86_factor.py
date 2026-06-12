"""
T86 法人資料回測 A/B 驗證
==========================
驗證「真實 T86 法人歷史資料」對策略績效的影響。

場景：
  A. P1 baseline（動能 top30，無因子排名）
  B. P1 + 因子排名 top15（法人 0.5 均等填充 = 舊行為）
  C. P1 + 因子排名 top15（真實 T86 法人連買資料）
  D. P1 + 法人連買過濾（外資或投信連買 ≥ N 日；上櫃無資料 fail-open）

前置：需先執行 scripts/backfill_t86.py 回填 T86 歷史快取，
      否則 C/D 場景自動跳過。

使用方式:
    cd /Users/yhh/GitHub/bag.holder.tw
    source venv/bin/activate
    python scripts/backtest_t86_factor.py
    python scripts/backtest_t86_factor.py --inst-min-days 3
"""

import argparse
import asyncio
import os
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, Optional, Set

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.infrastructure.market_data.backtest_data_source import YFinanceDataSource
from src.infrastructure.market_data.institutional_history import (
    InstitutionalHistoryLoader,
)
from config.settings import settings

from scripts.analyze_signal_attribution import (
    build_p1_strategy,
    build_p1_engine,
)


def build_inst_filter_whitelist(
    inst_series: Dict[date, Dict[str, dict]],
    all_symbols: Set[str],
    min_consecutive_days: int = 2,
) -> Dict[date, Set[str]]:
    """
    建立法人連買過濾白名單：
      外資連買 ≥ N 日 或 投信連買 ≥ N 日 → 允許交易。
    上櫃等無 T86 資料的股票 fail-open（保留可交易）。

    Returns:
        {date: set_of_allowed_symbols}
    """
    whitelist: Dict[date, Set[str]] = {}
    for d, day_data in inst_series.items():
        allowed = {
            sym for sym, vals in day_data.items()
            if vals.get("foreign_consecutive", 0) >= min_consecutive_days
            or vals.get("trust_consecutive", 0) >= min_consecutive_days
        }
        # fail-open: 無 T86 資料的股票（上櫃）不受過濾
        no_data = all_symbols - set(day_data.keys())
        whitelist[d] = allowed | no_data
    return whitelist


def run_scenario(
    name: str,
    stock_data: dict,
    benchmark_data,
    start_date: date,
    end_date: date,
    momentum_whitelist: Optional[dict],
    factor_whitelist: Optional[dict] = None,
):
    cfg = settings.backtest
    strategy = build_p1_strategy()
    signals = strategy.generate_signals_for_multiple_stocks(
        stock_data_dict=stock_data,
        start_date=start_date,
        end_date=end_date,
    )
    engine = build_p1_engine()
    for sym, d in stock_data.items():
        engine.add_price_data(sym, d)
    if momentum_whitelist is not None:
        engine.set_momentum_whitelist(momentum_whitelist)
    if factor_whitelist is not None:
        engine.set_factor_whitelist(factor_whitelist)

    result = engine.run_backtest(
        signals=signals,
        start_date=start_date,
        end_date=end_date,
        benchmark_data=benchmark_data,
        market_regime_rsi_threshold=cfg.market_regime_rsi_threshold,
        market_regime_check_ma5=cfg.market_regime_check_ma5,
    )
    print(
        f"   [{name}] 交易 {result.total_trades} 筆, "
        f"勝率 {float(result.win_rate):.1f}%, "
        f"報酬 {float(result.total_return_pct):+.2f}%, "
        f"Sharpe {float(result.sharpe_ratio):.2f}, "
        f"回撤 {float(result.max_drawdown):.2f}%"
    )
    return result


def print_comparison(results: Dict[str, object]):
    sep = "─" * 110
    print("\n" + "=" * 110)
    print("  T86 法人資料 A/B 驗證結果")
    print("=" * 110)
    print(f"  {'場景':<44} {'交易數':>6} {'勝率':>7} {'報酬':>8} {'Sharpe':>7} {'回撤':>7} {'Δ報酬 vs A':>11}")
    print(sep)
    names = list(results.keys())
    base = results[names[0]] if names else None
    for name, r in results.items():
        is_base = name == names[0]
        d_ret = (
            float(r.total_return_pct) - float(base.total_return_pct)
            if base and not is_base else 0.0
        )
        d_str = f"{d_ret:+.2f}%" if not is_base else "—"
        print(
            f"  {name:<44} {r.total_trades:>6} "
            f"{float(r.win_rate):>6.1f}% {float(r.total_return_pct):>+7.2f}% "
            f"{float(r.sharpe_ratio):>7.2f} {float(r.max_drawdown):>6.2f}% {d_str:>11}"
        )
    print(sep)
    print("=" * 110 + "\n")


async def main():
    parser = argparse.ArgumentParser(description="T86 法人資料回測 A/B 驗證")
    parser.add_argument("--inst-min-days", type=int, default=2,
                        help="場景 D 的法人連買最少天數（預設 2）")
    parser.add_argument("--factor-top-n", type=int, default=None,
                        help="因子排名 top N（預設用 settings.factor_ranking_top_n）")
    args = parser.parse_args()

    cfg = settings.backtest
    start_date = cfg.start_date or date(2024, 9, 1)
    end_date = cfg.end_date or date.today()
    top_n = args.factor_top_n or cfg.factor_ranking_top_n

    print(f"\nT86 法人資料 A/B 驗證  {start_date} → {end_date}")

    # 載入資料
    data_source = YFinanceDataSource()
    stocks_dir = os.path.normpath(
        os.path.join(os.path.dirname(__file__), '../data/stocks')
    )
    print("📂 載入歷史資料...")
    stock_data = data_source.load_from_stocks_dir(
        stocks_dir=stocks_dir,
        start_date=start_date - timedelta(days=120),
        end_date=end_date,
    )
    if not stock_data:
        print(f"❌ 找不到資料：{stocks_dir}")
        return
    benchmark_data = data_source.get_market_index_data(start_date, end_date)

    excluded = cfg.load_excluded_symbols(
        project_root=Path(os.path.normpath(os.path.join(os.path.dirname(__file__), '..')))
    )
    filtered_data = {s: d for s, d in stock_data.items() if s not in excluded}
    print(f"   {len(filtered_data)} 支股票（產業排除後）")

    # T86 歷史
    print("🏦 載入 T86 法人歷史快取...")
    inst_loader = InstitutionalHistoryLoader()
    inst_series = inst_loader.build_consecutive_series(
        start_date=start_date,
        end_date=end_date,
        warmup_days=cfg.factor_inst_history_days,
    )
    if inst_series:
        print(f"   T86 覆蓋 {len(inst_series)} 個交易日")
    else:
        print("   ⚠️ 無 T86 快取 — 場景 C/D 將跳過。請先執行 scripts/backfill_t86.py")

    # 動能白名單（所有場景共用）
    strategy = build_p1_strategy()
    momentum_whitelist = None
    if cfg.momentum_top_n > 0:
        momentum_whitelist = strategy.build_momentum_rankings(
            stock_data_dict=filtered_data,
            lookback_days=cfg.momentum_lookback_days,
            top_n=cfg.momentum_top_n,
            start_date=start_date,
            end_date=end_date,
        )

    results: Dict[str, object] = {}

    print("\n🚀 場景 A — P1 baseline（無因子排名）")
    results["A. P1 baseline（動能top30）"] = run_scenario(
        "A", filtered_data, benchmark_data, start_date, end_date, momentum_whitelist
    )

    print(f"\n🚀 場景 B — 因子排名 top{top_n}（法人 0.5 填充 = 舊行為）")
    fw_legacy = strategy.build_factor_whitelist(
        stock_data_dict=filtered_data,
        top_n=top_n,
        start_date=start_date,
        end_date=end_date,
    )
    results[f"B. 因子排名 top{top_n}（法人0.5填充）"] = run_scenario(
        "B", filtered_data, benchmark_data, start_date, end_date,
        momentum_whitelist, factor_whitelist=fw_legacy,
    )

    if inst_series:
        print(f"\n🚀 場景 C — 因子排名 top{top_n}（真實 T86）")
        fw_real = strategy.build_factor_whitelist(
            stock_data_dict=filtered_data,
            top_n=top_n,
            start_date=start_date,
            end_date=end_date,
            inst_consecutive_by_date=inst_series,
        )
        results[f"C. 因子排名 top{top_n}（真實 T86）"] = run_scenario(
            "C", filtered_data, benchmark_data, start_date, end_date,
            momentum_whitelist, factor_whitelist=fw_real,
        )

        print(f"\n🚀 場景 D — 法人連買過濾（連買 ≥ {args.inst_min_days} 日, fail-open）")
        inst_wl = build_inst_filter_whitelist(
            inst_series, set(filtered_data.keys()), args.inst_min_days
        )
        results[f"D. 法人連買 ≥{args.inst_min_days}日過濾"] = run_scenario(
            "D", filtered_data, benchmark_data, start_date, end_date,
            momentum_whitelist, factor_whitelist=inst_wl,
        )

    print_comparison(results)


if __name__ == "__main__":
    asyncio.run(main())
