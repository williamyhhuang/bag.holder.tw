#!/usr/bin/env python3
"""
分析排除生技股對選股策略勝率的影響。

台灣生技醫療類股 (生技醫療) 主要代碼範圍：4100-4499
（包含藥品、生技、醫療器材等公司）
"""
import sys
import os
import asyncio
from datetime import date, timedelta
from decimal import Decimal

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.backtest import (
    YFinanceDataSource,
    BacktestEngine,
    TechnicalStrategy,
    PerformanceAnalyzer,
    BacktestReporter,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)

# 生技醫療類股代碼範圍 (4100-4499)
BIOTECH_CODE_MIN = 4100
BIOTECH_CODE_MAX = 4499


def is_biotech(symbol: str) -> bool:
    """判斷股票是否為生技醫療類股（代碼 4100-4499）"""
    try:
        code = int(symbol[:4])
        return BIOTECH_CODE_MIN <= code <= BIOTECH_CODE_MAX
    except (ValueError, IndexError):
        return False


def classify_stocks(stock_data: dict) -> tuple[dict, dict]:
    """將股票分為生技股和非生技股兩組"""
    biotech = {sym: data for sym, data in stock_data.items() if is_biotech(sym)}
    non_biotech = {sym: data for sym, data in stock_data.items() if not is_biotech(sym)}
    return biotech, non_biotech


async def run_backtest_group(
    label: str,
    stock_data: dict,
    start_date: date,
    end_date: date,
    benchmark_data: list,
    initial_capital: Decimal = Decimal('1000000'),
):
    """對指定股票群組執行回測並返回結果"""
    print(f"\n{'='*60}")
    print(f"  回測群組: {label}  ({len(stock_data)} 支股票)")
    print(f"{'='*60}")

    if not stock_data:
        print("  ⚠️  無股票資料，跳過此群組")
        return None

    strategy = TechnicalStrategy()
    engine = BacktestEngine(initial_capital=initial_capital)

    # 加入價格資料
    for symbol, data in stock_data.items():
        engine.add_price_data(symbol, data)

    # 產生訊號
    signals = strategy.generate_signals_for_multiple_stocks(
        stock_data_dict=stock_data,
        start_date=start_date,
        end_date=end_date,
    )

    buy_signals = [s for s in signals if s.signal_type.value == 'BUY']
    print(f"  買進訊號數: {len(buy_signals)}")
    print(f"  訊號總數:   {len(signals)}")

    # 執行回測
    result = engine.run_backtest(signals, start_date, end_date, benchmark_data=benchmark_data)

    return result


def print_comparison(all_result, no_bio_result, biotech_result):
    """印出三組結果的對比表"""
    print("\n" + "=" * 70)
    print("  📊  生技股影響分析報告")
    print("=" * 70)

    rows = [
        ("指標",            "全部股票",           "排除生技股",        "僅生技股"),
        ("-" * 14,          "-" * 18,             "-" * 18,            "-" * 18),
        ("總交易次數",
         str(all_result.total_trades if all_result else "N/A"),
         str(no_bio_result.total_trades if no_bio_result else "N/A"),
         str(biotech_result.total_trades if biotech_result else "N/A")),
        ("獲利次數",
         str(all_result.winning_trades if all_result else "N/A"),
         str(no_bio_result.winning_trades if no_bio_result else "N/A"),
         str(biotech_result.winning_trades if biotech_result else "N/A")),
        ("虧損次數",
         str(all_result.losing_trades if all_result else "N/A"),
         str(no_bio_result.losing_trades if no_bio_result else "N/A"),
         str(biotech_result.losing_trades if biotech_result else "N/A")),
        ("勝率",
         f"{all_result.win_rate}%" if all_result else "N/A",
         f"{no_bio_result.win_rate}%" if no_bio_result else "N/A",
         f"{biotech_result.win_rate}%" if biotech_result else "N/A"),
        ("總報酬率",
         f"{all_result.total_return_pct}%" if all_result else "N/A",
         f"{no_bio_result.total_return_pct}%" if no_bio_result else "N/A",
         f"{biotech_result.total_return_pct}%" if biotech_result else "N/A"),
        ("最大回撤",
         f"{all_result.max_drawdown}%" if all_result else "N/A",
         f"{no_bio_result.max_drawdown}%" if no_bio_result else "N/A",
         f"{biotech_result.max_drawdown}%" if biotech_result else "N/A"),
        ("夏普比率",
         str(all_result.sharpe_ratio) if all_result else "N/A",
         str(no_bio_result.sharpe_ratio) if no_bio_result else "N/A",
         str(biotech_result.sharpe_ratio) if biotech_result else "N/A"),
    ]

    for row in rows:
        print(f"  {row[0]:<14} {row[1]:<18} {row[2]:<18} {row[3]:<18}")

    # 勝率變化
    if all_result and no_bio_result:
        diff = float(no_bio_result.win_rate) - float(all_result.win_rate)
        direction = "↑ 提升" if diff > 0 else "↓ 下降"
        print(f"\n  🎯  排除生技股後勝率變化: {direction} {abs(diff):.2f}%")
        print(f"       全部股票: {all_result.win_rate}%  →  排除生技股: {no_bio_result.win_rate}%")

    if biotech_result and biotech_result.total_trades > 0:
        print(f"\n  🧬  生技股單獨勝率: {biotech_result.win_rate}%  (共 {biotech_result.total_trades} 筆交易)")


async def main():
    print("🔬  生技股影響分析 — 台股選股策略勝率比較")
    print()

    # 設定回測期間 (最近 90 天)
    end_date = date(2026, 4, 7)
    start_date = end_date - timedelta(days=90)

    stocks_dir = os.path.join(os.path.dirname(__file__), '../data/stocks')
    stocks_dir = os.path.normpath(stocks_dir)

    data_source = YFinanceDataSource()

    print(f"📅 回測期間: {start_date} ~ {end_date}")
    print(f"📂 載入股票資料中... ({stocks_dir})")

    # 載入全部股票資料（extra history for indicator warm-up）
    needed_start = start_date - timedelta(days=100)
    all_stock_data = data_source.load_from_stocks_dir(
        stocks_dir=stocks_dir,
        start_date=needed_start,
        end_date=end_date,
    )
    print(f"✅ 共載入 {len(all_stock_data)} 支股票")

    # 分類生技 / 非生技
    biotech_data, non_biotech_data = classify_stocks(all_stock_data)
    print(f"   🧬 生技醫療類股 (4100-4499): {len(biotech_data)} 支")
    print(f"   📈 非生技類股:               {len(non_biotech_data)} 支")

    # 取得大盤資料（TAIEX benchmark）
    print("\n📡 取得大盤基準資料...")
    benchmark_data = data_source.get_market_index_data(start_date, end_date)

    # 執行三組回測
    all_result = await run_backtest_group(
        "全部股票", all_stock_data, start_date, end_date, benchmark_data)

    no_bio_result = await run_backtest_group(
        "排除生技股 (非 4100-4499)", non_biotech_data, start_date, end_date, benchmark_data)

    biotech_result = await run_backtest_group(
        "僅生技股 (4100-4499)", biotech_data, start_date, end_date, benchmark_data)

    # 輸出對比報告
    print_comparison(all_result, no_bio_result, biotech_result)

    print("\n✅  分析完成")


if __name__ == "__main__":
    asyncio.run(main())
