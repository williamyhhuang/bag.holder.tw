"""
Scan Type Trade Attribution Analysis
=====================================
執行 P1 完整回測，然後對每筆實際成交的交易，
查詢「進場當天這支股票是否符合動能股/超賣股/突破股掃描條件」，
按掃描類型分組統計績效。

核心問題：P1 策略實際交易的股票裡，
  動能股 / 超賣股 / 突破股 各自的勝率與報酬貢獻如何？

使用方式:
    cd /Users/yhh/GitHub/bag.holder.tw
    source venv/bin/activate
    python scripts/analyze_scan_attribution.py
"""

import asyncio
import os
import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional, Set

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.backtest import (
    YFinanceDataSource,
    BacktestEngine,
    TechnicalStrategy,
)
from src.backtest.models import Position, StockData
from config.settings import settings

# 複用白名單建立工具
from scripts.backtest_scan_types import build_scan_whitelist


# ─────────────────────────────────────────────
# 交易歸因
# ─────────────────────────────────────────────

SCAN_TYPES = ("momentum", "oversold", "breakout")
SCAN_LABELS = {
    "momentum": "動能股",
    "oversold": "超賣股",
    "breakout": "突破股",
}


def classify_trades(
    positions: List[Position],
    whitelists: Dict[str, Dict[date, Set[str]]],
) -> Dict[str, List[Position]]:
    """
    對每筆成交交易，依進場日的掃描白名單分類。
    一筆交易可同時屬於多個類型（例如同時符合動能股 + 突破股）。
    "none" 組：不屬於任何掃描類型的交易。

    回傳 {category: [Position, ...]}
    """
    groups: Dict[str, List[Position]] = {t: [] for t in SCAN_TYPES}
    groups["none"] = []

    for pos in positions:
        matched = []
        for scan_type in SCAN_TYPES:
            wl = whitelists[scan_type]
            # 用最近一個白名單日（與引擎邏輯一致）
            available = [d for d in wl if d <= pos.entry_date]
            if not available:
                continue
            latest = max(available)
            if pos.symbol in wl[latest]:
                matched.append(scan_type)
        if matched:
            for t in matched:
                groups[t].append(pos)
        else:
            groups["none"].append(pos)

    return groups


# ─────────────────────────────────────────────
# 統計計算
# ─────────────────────────────────────────────

@dataclass
class GroupStats:
    label: str
    trades: int
    wins: int
    total_pnl_pct: float      # 所有交易 pnl_percent 的加總（%）
    avg_pnl_pct: float        # 平均每筆報酬（%）
    win_rate: float           # 勝率（%）
    avg_holding: float        # 平均持倉天數
    signal_breakdown: Dict[str, Dict] = field(default_factory=dict)

    def summary(self) -> str:
        return (
            f"交易 {self.trades:4d} 筆  "
            f"勝率 {self.win_rate:5.1f}%  "
            f"平均每筆 {self.avg_pnl_pct:+6.2f}%  "
            f"累計貢獻 {self.total_pnl_pct:+7.2f}%  "
            f"平均持倉 {self.avg_holding:.1f}d"
        )


def compute_stats(label: str, positions: List[Position]) -> GroupStats:
    if not positions:
        return GroupStats(label=label, trades=0, wins=0,
                          total_pnl_pct=0, avg_pnl_pct=0,
                          win_rate=0, avg_holding=0)

    wins = sum(1 for p in positions if (p.pnl or Decimal(0)) > 0)
    pnl_pcts = [float(p.pnl_percent or 0) for p in positions]
    holdings = [float(p.holding_days or 0) for p in positions]

    breakdown: Dict[str, Dict] = {}
    for p in positions:
        sig = p.entry_signal_name or "Unknown"
        if sig not in breakdown:
            breakdown[sig] = {"trades": 0, "wins": 0}
        breakdown[sig]["trades"] += 1
        if (p.pnl or Decimal(0)) > 0:
            breakdown[sig]["wins"] += 1

    return GroupStats(
        label=label,
        trades=len(positions),
        wins=wins,
        total_pnl_pct=sum(pnl_pcts),
        avg_pnl_pct=sum(pnl_pcts) / len(pnl_pcts),
        win_rate=wins / len(positions) * 100,
        avg_holding=sum(holdings) / len(holdings),
        signal_breakdown=breakdown,
    )


# ─────────────────────────────────────────────
# 報告
# ─────────────────────────────────────────────

def print_attribution_report(
    stats_list: List[GroupStats],
    total_return_pct: float,
    taiex_return: float,
):
    sep = "─" * 100
    print("\n" + "=" * 100)
    print("  P1 交易歸因分析  ——  依進場日掃描類型分類")
    print("=" * 100)
    print(f"  P1 策略總報酬: {total_return_pct:+.2f}%   TAIEX 同期: {taiex_return:+.2f}%\n")

    print(f"  {'分類':<10}  {'交易數':>6}  {'勝率':>7}  {'平均每筆':>9}  {'累計貢獻':>9}  {'平均持倉':>8}")
    print(sep)

    all_group = next((s for s in stats_list if s.label == "全部"), None)
    for s in stats_list:
        pct_of_total = s.trades / all_group.trades * 100 if all_group and all_group.trades else 0
        print(
            f"  {s.label:<10}  "
            f"{s.trades:>6}筆({pct_of_total:4.0f}%)  "
            f"{s.win_rate:>6.1f}%  "
            f"{s.avg_pnl_pct:>+8.2f}%  "
            f"{s.total_pnl_pct:>+8.2f}%  "
            f"{s.avg_holding:>7.1f}d"
        )

    print(sep)
    print("  * 一筆交易可同時屬於多個類型（例如當天同時符合動能股 + 突破股）")
    print("  * 「無分類」= 進場日不在任何掃描白名單內")

    # 訊號明細
    all_sigs: Set[str] = set()
    for s in stats_list:
        all_sigs.update(s.signal_breakdown.keys())
    all_sigs_sorted = sorted(all_sigs)

    if all_sigs_sorted:
        print("\n" + "=" * 100)
        print("  各分類 × 各訊號  勝率明細")
        print("=" * 100)
        header = f"  {'訊號':<26}"
        for s in stats_list:
            header += f"  {s.label:>12}"
        print(header)
        print(sep)
        for sig in all_sigs_sorted:
            row = f"  {sig:<26}"
            for s in stats_list:
                entry = s.signal_breakdown.get(sig, {})
                t = entry.get("trades", 0)
                w = entry.get("wins", 0)
                cell = f"{w}/{t}={w/t*100:.0f}%" if t else "-"
                row += f"  {cell:>12}"
            print(row)

    print("=" * 100 + "\n")


# ─────────────────────────────────────────────
# 主程式
# ─────────────────────────────────────────────

async def main():
    cfg = settings.backtest
    start_date = cfg.start_date or date(2024, 9, 1)
    end_date = cfg.end_date or date.today()

    print(f"\nP1 交易歸因分析  {start_date} → {end_date}")

    # 載入資料
    data_source = YFinanceDataSource()
    stocks_dir = os.path.normpath(
        os.path.join(os.path.dirname(__file__), '../data/stocks')
    )
    needed_start = start_date - timedelta(days=120)

    print("📂 載入歷史資料...")
    stock_data = data_source.load_from_stocks_dir(
        stocks_dir=stocks_dir,
        start_date=needed_start,
        end_date=end_date,
    )
    if not stock_data:
        print(f"❌ 找不到資料：{stocks_dir}")
        return
    print(f"   載入 {len(stock_data)} 支股票")

    print("📊 載入大盤資料...")
    benchmark_data = data_source.get_market_index_data(start_date, end_date)

    excluded_symbols = cfg.load_excluded_symbols(
        project_root=Path(os.path.normpath(os.path.join(os.path.dirname(__file__), '..')))
    )
    filtered_data = {s: d for s, d in stock_data.items() if s not in excluded_symbols}
    print(f"   產業排除後剩 {len(filtered_data)} 支股票")

    # 建立三種掃描白名單
    print("\n🔍 建立掃描條件白名單...")
    whitelists = {
        t: build_scan_whitelist(filtered_data, t, start_date, end_date)
        for t in SCAN_TYPES
    }

    # 執行 P1 完整回測
    print("\n🚀 執行 P1 生產回測...")
    disabled = [s.strip() for s in cfg.disabled_signals.split(",") if s.strip()]
    strategy = TechnicalStrategy(
        disabled_signals=disabled,
        require_ma60_uptrend=cfg.require_ma60_uptrend,
        require_volume_confirmation=cfg.require_volume_confirmation,
        volume_confirmation_multiplier=cfg.volume_confirmation_multiplier,
        rsi_min_entry=cfg.rsi_min_entry,
        donchian_period=cfg.donchian_period,
    )

    signals = strategy.generate_signals_for_multiple_stocks(
        stock_data_dict=filtered_data,
        start_date=start_date,
        end_date=end_date,
    )

    def _parse_signals(s: str):
        items = [x.strip() for x in s.split(",") if x.strip()]
        return items if items else None

    engine = BacktestEngine(
        initial_capital=Decimal("1000000"),
        stop_loss_pct=Decimal(str(cfg.stop_loss_pct)),
        take_profit_pct=Decimal(str(cfg.take_profit_pct)),
        trailing_stop_pct=Decimal(str(cfg.trailing_stop_pct)),
        max_holding_days=cfg.max_holding_days,
        position_sizing=Decimal(str(cfg.position_sizing)),
        market_regime_strong_rsi=cfg.market_regime_strong_rsi,
        strong_regime_signals=_parse_signals(cfg.strong_regime_signals),
        neutral_regime_signals=_parse_signals(cfg.neutral_regime_signals),
        strong_trend_signals=_parse_signals(cfg.strong_trend_signals),
        strong_trend_multiplier=cfg.strong_trend_multiplier,
    )

    trend_names = [s.strip() for s in cfg.trend_signal_names.split(",") if s.strip()]
    if trend_names:
        eff_trailing = Decimal('0')
        eff_exit_signals = [
            s.strip() for s in cfg.trend_exit_on_signals.split(",") if s.strip()
        ] or None
        if cfg.trend_use_trailing_stop:
            eff_trailing = Decimal(str(cfg.trend_trailing_stop_pct))
            eff_exit_signals = None
        trend_exit = {
            tn: {
                "stop_loss_pct": Decimal(str(cfg.trend_stop_loss_pct)),
                "trailing_stop_pct": eff_trailing,
                "take_profit_pct": Decimal(str(cfg.trend_take_profit_pct)),
                "max_holding_days": cfg.trend_max_holding_days,
                "exit_on_signals": eff_exit_signals,
                "profit_threshold_pct": Decimal(str(cfg.trend_profit_threshold_pct)),
                "profit_trailing_pct": Decimal(str(cfg.trend_profit_trailing_pct)),
            }
            for tn in trend_names
        }
        engine.set_signal_exit_config(trend_exit)

    for sym, d in filtered_data.items():
        engine.add_price_data(sym, d)

    # 動能白名單（P1 top30）
    if cfg.momentum_top_n > 0:
        mw = strategy.build_momentum_rankings(
            stock_data_dict=filtered_data,
            lookback_days=cfg.momentum_lookback_days,
            top_n=cfg.momentum_top_n,
            start_date=start_date,
            end_date=end_date,
        )
        engine.set_momentum_whitelist(mw)

    result = engine.run_backtest(
        signals=signals,
        start_date=start_date,
        end_date=end_date,
        benchmark_data=benchmark_data,
        market_regime_rsi_threshold=cfg.market_regime_rsi_threshold,
        market_regime_check_ma5=cfg.market_regime_check_ma5,
    )

    print(
        f"   回測完成 → 交易 {result.total_trades} 筆, "
        f"勝率 {float(result.win_rate):.1f}%, "
        f"總報酬 {float(result.total_return_pct):+.2f}%, "
        f"Sharpe {float(result.sharpe_ratio):.2f}"
    )

    # 歸因分析
    print("\n📊 進行交易歸因分析...")
    groups = classify_trades(result.trades, whitelists)

    # 分組統計
    stats_list = []
    stats_list.append(compute_stats("全部", result.trades))
    for scan_type in SCAN_TYPES:
        stats_list.append(compute_stats(SCAN_LABELS[scan_type], groups[scan_type]))
    stats_list.append(compute_stats("無分類", groups["none"]))

    # TAIEX 報酬
    taiex_return = 0.0
    if benchmark_data and len(benchmark_data) >= 2:
        sorted_bm = sorted(benchmark_data, key=lambda x: x.date)
        taiex_return = float(
            (sorted_bm[-1].close_price - sorted_bm[0].close_price)
            / sorted_bm[0].close_price * 100
        )

    print_attribution_report(
        stats_list,
        total_return_pct=float(result.total_return_pct),
        taiex_return=taiex_return,
    )


if __name__ == "__main__":
    asyncio.run(main())
