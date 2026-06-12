"""
Per-Signal Attribution Analysis（逐訊號歸因分析）
=================================================
拆解 P1 生產策略中「每一種進場訊號」各自的貢獻：

Phase 1 — 基準回測逐訊號統計：
  對 P1 baseline 回測的每筆交易，按 entry_signal_name 分組，計算
  出手次數、勝率、平均報酬、平均賺/賠、期望值、獲利因子、累計貢獻。

Phase 2 — Leave-One-Out（LOO）影響分析：
  逐一停用每種訊號重跑完整回測，觀察總報酬/勝率/Sharpe 的變化。
  這能捕捉「個別勝率低但對組合有正貢獻」的情況
  （例如 Golden Cross 勝率僅 22-32% 但停用後報酬 -5.90%）。

策略/引擎參數完全鏡像 src/interfaces/cli/backtest_main.py BacktestRunner
（P1 生產設定），確保歸因結果可直接對應實際策略。

使用方式:
    cd /Users/yhh/GitHub/bag.holder.tw
    source venv/bin/activate
    python scripts/analyze_signal_attribution.py            # Phase 1 + 2
    python scripts/analyze_signal_attribution.py --skip-loo # 只跑 Phase 1（快）
"""

import argparse
import asyncio
import os
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.infrastructure.market_data.backtest_data_source import YFinanceDataSource
from src.application.services.backtest_engine import BacktestEngine
from src.application.services.backtest_strategy import TechnicalStrategy
from src.domain.models import Position
from config.settings import settings


# ─────────────────────────────────────────────
# Phase 1: 逐訊號統計（純函式，可單元測試）
# ─────────────────────────────────────────────

@dataclass
class SignalStats:
    name: str
    trades: int
    wins: int
    win_rate: float           # %
    avg_pnl_pct: float        # 平均每筆報酬 %
    avg_win_pct: float        # 獲利交易平均 %
    avg_loss_pct: float       # 虧損交易平均 %（負值）
    expectancy_pct: float     # 期望值 = win_rate*avg_win + (1-win_rate)*avg_loss
    profit_factor: float      # 總獲利金額 / 總虧損金額
    total_pnl: float          # 累計損益金額
    total_pnl_pct: float      # pnl_percent 加總（貢獻度 proxy）
    avg_holding: float        # 平均持倉天數


def compute_signal_stats(positions: List[Position]) -> Dict[str, SignalStats]:
    """按 entry_signal_name 分組計算完整績效統計"""
    grouped: Dict[str, List[Position]] = {}
    for p in positions:
        grouped.setdefault(p.entry_signal_name or "Unknown", []).append(p)

    stats: Dict[str, SignalStats] = {}
    for name, plist in grouped.items():
        pnl_pcts = [float(p.pnl_percent or 0) for p in plist]
        pnls = [float(p.pnl or 0) for p in plist]
        holdings = [float(p.holding_days or 0) for p in plist]

        win_pcts = [x for x in pnl_pcts if x > 0]
        loss_pcts = [x for x in pnl_pcts if x <= 0]
        gross_profit = sum(x for x in pnls if x > 0)
        gross_loss = abs(sum(x for x in pnls if x < 0))

        n = len(plist)
        wins = len(win_pcts)
        wr = wins / n if n else 0.0
        avg_win = sum(win_pcts) / len(win_pcts) if win_pcts else 0.0
        avg_loss = sum(loss_pcts) / len(loss_pcts) if loss_pcts else 0.0

        stats[name] = SignalStats(
            name=name,
            trades=n,
            wins=wins,
            win_rate=wr * 100,
            avg_pnl_pct=sum(pnl_pcts) / n if n else 0.0,
            avg_win_pct=avg_win,
            avg_loss_pct=avg_loss,
            expectancy_pct=wr * avg_win + (1 - wr) * avg_loss,
            profit_factor=(gross_profit / gross_loss) if gross_loss > 0 else float('inf'),
            total_pnl=sum(pnls),
            total_pnl_pct=sum(pnl_pcts),
            avg_holding=sum(holdings) / n if n else 0.0,
        )
    return stats


# ─────────────────────────────────────────────
# Phase 2: Leave-One-Out 結果
# ─────────────────────────────────────────────

@dataclass
class LooResult:
    disabled_signal: str
    total_trades: int
    win_rate: float
    total_return_pct: float
    sharpe: float
    max_drawdown: float
    # vs baseline
    d_return: float = 0.0
    d_win_rate: float = 0.0
    d_sharpe: float = 0.0


def classify_loo(loo: LooResult) -> str:
    """LOO 結論：停用後報酬上升 → 該訊號是負貢獻（建議停用）"""
    if loo.d_return > 1.0 and loo.d_sharpe >= 0:
        return "❌ 負貢獻（建議停用）"
    if loo.d_return < -1.0:
        return "✅ 正貢獻（保留）"
    return "─ 中性（影響 <1%）"


# ─────────────────────────────────────────────
# P1 生產設定建構（鏡像 backtest_main.py BacktestRunner）
# ─────────────────────────────────────────────

def build_p1_strategy(extra_disabled: Optional[List[str]] = None) -> TechnicalStrategy:
    cfg = settings.backtest
    disabled = [s.strip() for s in cfg.disabled_signals.split(",") if s.strip()]
    if extra_disabled:
        disabled = disabled + list(extra_disabled)
    return TechnicalStrategy(
        rsi_min_entry=cfg.rsi_min_entry,
        disabled_signals=disabled,
        require_ma60_uptrend=cfg.require_ma60_uptrend,
        require_volume_confirmation=cfg.require_volume_confirmation,
        volume_confirmation_multiplier=cfg.volume_confirmation_multiplier,
        rsi_overbought_threshold=cfg.rsi_overbought_threshold,
        donchian_period=cfg.donchian_period,
        min_volume_lots=cfg.min_volume_lots,
        signal_cooldown_days=cfg.signal_cooldown_days,
        require_weekly_trend=cfg.require_weekly_trend,
        require_52w_filter=cfg.require_52w_filter,
        above_52w_low_pct=cfg.above_52w_low_pct,
        near_52w_high_pct=cfg.near_52w_high_pct,
        enable_vcp=cfg.enable_vcp,
        vcp_lookback=cfg.vcp_lookback,
        pre_breakout_mode=cfg.pre_breakout_mode,
        enable_momentum_signal=cfg.enable_momentum_signal,
        momentum_signal_days=cfg.momentum_signal_days,
        momentum_signal_min_return=cfg.momentum_signal_min_return,
        require_weekly_rsi=cfg.require_weekly_rsi,
        weekly_rsi_min=cfg.weekly_rsi_min,
        require_revenue_growth=cfg.require_revenue_growth,
        revenue_yoy_min_pct=cfg.revenue_yoy_min_pct,
        finmind_api_token=settings.finmind.api_token or "",
        weekly_close_only=cfg.weekly_close_only,
        require_minervini_trend=cfg.require_minervini_trend,
        min_confirming_signals=cfg.min_confirming_signals,
        enable_weekly_signals=cfg.enable_weekly_signals,
        weekly_bb_period=cfg.weekly_bb_period,
        weekly_donchian_period=cfg.weekly_donchian_period,
        donchian_period_2=cfg.donchian_period_2,
        rsi_oversold_require_uptrend=cfg.rsi_oversold_require_uptrend,
    )


def _parse_signal_list(s: str):
    items = [x.strip() for x in s.split(",") if x.strip()]
    return items if items else None


def build_p1_engine(initial_capital: Decimal = Decimal("1000000")) -> BacktestEngine:
    cfg = settings.backtest
    engine = BacktestEngine(
        initial_capital=initial_capital,
        stop_loss_pct=Decimal(str(cfg.stop_loss_pct)),
        take_profit_pct=Decimal(str(cfg.take_profit_pct)),
        trailing_stop_pct=Decimal(str(cfg.trailing_stop_pct)),
        max_holding_days=cfg.max_holding_days,
        position_sizing=Decimal(str(cfg.position_sizing)),
        atr_stop_multiplier=cfg.atr_stop_multiplier,
        min_holding_days=cfg.min_holding_days,
        profit_threshold_pct=(
            Decimal(str(cfg.profit_threshold_pct))
            if cfg.enable_profit_protection else None
        ),
        profit_trailing_pct=(
            Decimal(str(cfg.profit_trailing_pct))
            if cfg.enable_profit_protection else None
        ),
        catastrophic_stop_pct=Decimal(str(cfg.catastrophic_stop_pct)),
        scale_out_trigger_pct=Decimal(str(cfg.scale_out_trigger_pct)),
        scale_out_ratio=Decimal(str(cfg.scale_out_ratio)),
        resonance_min_signals=cfg.resonance_min_signals,
        resonance_size_multiplier=cfg.resonance_size_multiplier,
        market_regime_strong_rsi=cfg.market_regime_strong_rsi,
        strong_regime_signals=_parse_signal_list(cfg.strong_regime_signals),
        neutral_regime_signals=_parse_signal_list(cfg.neutral_regime_signals),
        strong_trend_signals=_parse_signal_list(cfg.strong_trend_signals),
        strong_trend_multiplier=cfg.strong_trend_multiplier,
    )

    # P6 + P3-B: trend signal exit config
    trend_names = [s.strip() for s in cfg.trend_signal_names.split(",") if s.strip()]
    if trend_names:
        if cfg.trend_use_trailing_stop:
            eff_trailing = Decimal(str(cfg.trend_trailing_stop_pct))
            eff_exit_signals = None
        else:
            eff_trailing = Decimal('0')
            eff_exit_signals = _parse_signal_list(cfg.trend_exit_on_signals)
        trend_exit = {
            name: {
                "stop_loss_pct": Decimal(str(cfg.trend_stop_loss_pct)),
                "trailing_stop_pct": eff_trailing,
                "take_profit_pct": Decimal(str(cfg.trend_take_profit_pct)),
                "max_holding_days": cfg.trend_max_holding_days,
                "exit_on_signals": eff_exit_signals,
                "profit_threshold_pct": Decimal(str(cfg.trend_profit_threshold_pct)),
                "profit_trailing_pct": Decimal(str(cfg.trend_profit_trailing_pct)),
            }
            for name in trend_names
        }
        engine.set_signal_exit_config(trend_exit)
    return engine


def run_p1_backtest(
    stock_data: dict,
    benchmark_data,
    start_date: date,
    end_date: date,
    momentum_whitelist: Optional[dict] = None,
    extra_disabled: Optional[List[str]] = None,
):
    """執行一次 P1 生產設定回測，回傳 BacktestResult"""
    cfg = settings.backtest
    strategy = build_p1_strategy(extra_disabled)
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
    return engine.run_backtest(
        signals=signals,
        start_date=start_date,
        end_date=end_date,
        benchmark_data=benchmark_data,
        market_regime_rsi_threshold=cfg.market_regime_rsi_threshold,
        market_regime_check_ma5=cfg.market_regime_check_ma5,
    )


# ─────────────────────────────────────────────
# 報告輸出
# ─────────────────────────────────────────────

def print_signal_stats_report(stats: Dict[str, SignalStats], baseline_result):
    sep = "─" * 132
    print("\n" + "=" * 132)
    print("  Phase 1 — P1 基準回測逐訊號歸因")
    print("=" * 132)
    print(
        f"  Baseline: 交易 {baseline_result.total_trades} 筆, "
        f"勝率 {float(baseline_result.win_rate):.1f}%, "
        f"總報酬 {float(baseline_result.total_return_pct):+.2f}%, "
        f"Sharpe {float(baseline_result.sharpe_ratio):.2f}, "
        f"最大回撤 {float(baseline_result.max_drawdown):.2f}%\n"
    )
    print(
        f"  {'訊號':<26} {'交易數':>6} {'勝率':>7} {'平均每筆':>9} "
        f"{'平均賺':>8} {'平均賠':>8} {'期望值':>8} {'獲利因子':>8} "
        f"{'累計損益$':>11} {'平均持倉':>8}"
    )
    print(sep)
    for s in sorted(stats.values(), key=lambda x: -x.expectancy_pct):
        pf = f"{s.profit_factor:.2f}" if s.profit_factor != float('inf') else "∞"
        print(
            f"  {s.name:<26} {s.trades:>6} {s.win_rate:>6.1f}% "
            f"{s.avg_pnl_pct:>+8.2f}% {s.avg_win_pct:>+7.2f}% "
            f"{s.avg_loss_pct:>+7.2f}% {s.expectancy_pct:>+7.2f}% "
            f"{pf:>8} {s.total_pnl:>+11,.0f} {s.avg_holding:>7.1f}d"
        )
    print(sep)
    print("  期望值 = 勝率×平均賺 + 敗率×平均賠（每筆交易的期望報酬 %）")


def print_loo_report(baseline_result, loo_results: List[LooResult]):
    sep = "─" * 120
    print("\n" + "=" * 120)
    print("  Phase 2 — Leave-One-Out 訊號影響分析（停用單一訊號重跑回測）")
    print("=" * 120)
    print(
        f"  {'停用訊號':<26} {'交易數':>6} {'勝率':>7} {'報酬':>8} {'Sharpe':>7} "
        f"{'Δ報酬':>8} {'Δ勝率':>8} {'ΔSharpe':>8}  結論"
    )
    print(sep)
    base_label = (
        f"  {'(無停用 = baseline)':<26} {baseline_result.total_trades:>6} "
        f"{float(baseline_result.win_rate):>6.1f}% "
        f"{float(baseline_result.total_return_pct):>+7.2f}% "
        f"{float(baseline_result.sharpe_ratio):>7.2f}"
    )
    print(base_label)
    for loo in sorted(loo_results, key=lambda x: x.d_return):
        print(
            f"  {loo.disabled_signal:<26} {loo.total_trades:>6} "
            f"{loo.win_rate:>6.1f}% {loo.total_return_pct:>+7.2f}% "
            f"{loo.sharpe:>7.2f} {loo.d_return:>+7.2f}% "
            f"{loo.d_win_rate:>+7.2f}% {loo.d_sharpe:>+8.2f}  {classify_loo(loo)}"
        )
    print(sep)
    print("  Δ = 停用該訊號後 − baseline。Δ報酬為正 → 該訊號拖累組合。")
    print("  注意：訊號間有互動效應（多訊號確認），LOO 比單純分組統計更可信。")
    print("=" * 120 + "\n")


# ─────────────────────────────────────────────
# 主程式
# ─────────────────────────────────────────────

async def main():
    parser = argparse.ArgumentParser(description="P1 逐訊號歸因分析")
    parser.add_argument("--skip-loo", action="store_true",
                        help="跳過 Phase 2 Leave-One-Out（只跑基準逐訊號統計）")
    args = parser.parse_args()

    cfg = settings.backtest
    start_date = cfg.start_date or date(2024, 9, 1)
    end_date = cfg.end_date or date.today()

    print(f"\nP1 逐訊號歸因分析  {start_date} → {end_date}")

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

    # 動能白名單只需建一次（與 disabled_signals 無關）
    momentum_whitelist = None
    if cfg.momentum_top_n > 0:
        print(f"🏃 建立動能排名 top{cfg.momentum_top_n}...")
        momentum_whitelist = build_p1_strategy().build_momentum_rankings(
            stock_data_dict=filtered_data,
            lookback_days=cfg.momentum_lookback_days,
            top_n=cfg.momentum_top_n,
            start_date=start_date,
            end_date=end_date,
        )

    # Phase 1: baseline
    print("\n🚀 執行 P1 baseline 回測...")
    baseline = run_p1_backtest(
        filtered_data, benchmark_data, start_date, end_date, momentum_whitelist
    )
    stats = compute_signal_stats(baseline.trades)
    print_signal_stats_report(stats, baseline)

    if args.skip_loo:
        return

    # Phase 2: leave-one-out
    signal_names = sorted(stats.keys())
    print(f"\n🔁 Phase 2 — Leave-One-Out（{len(signal_names)} 種訊號各重跑一次）...")
    loo_results: List[LooResult] = []
    for sig in signal_names:
        if sig == "Unknown":
            continue
        print(f"   停用 [{sig}] ...", end="", flush=True)
        r = run_p1_backtest(
            filtered_data, benchmark_data, start_date, end_date,
            momentum_whitelist, extra_disabled=[sig],
        )
        loo = LooResult(
            disabled_signal=sig,
            total_trades=r.total_trades,
            win_rate=float(r.win_rate),
            total_return_pct=float(r.total_return_pct),
            sharpe=float(r.sharpe_ratio),
            max_drawdown=float(r.max_drawdown),
            d_return=float(r.total_return_pct) - float(baseline.total_return_pct),
            d_win_rate=float(r.win_rate) - float(baseline.win_rate),
            d_sharpe=float(r.sharpe_ratio) - float(baseline.sharpe_ratio),
        )
        loo_results.append(loo)
        print(f" 報酬 {loo.total_return_pct:+.2f}% (Δ {loo.d_return:+.2f}%)")

    print_loo_report(baseline, loo_results)


if __name__ == "__main__":
    asyncio.run(main())
