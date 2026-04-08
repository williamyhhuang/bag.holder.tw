"""
Filter Diagnostic Script
========================
逐一啟用每個進場過濾器，找出哪個過濾器對績效影響最大。

使用方式:
    cd /Users/yhh/GitHub/bag.holder.tw
    source venv/bin/activate
    python scripts/diagnose_filters.py

輸出：
    1. 每個場景的整體績效比較表
    2. 每個場景的個訊號勝率分析
    3. 結論摘要（哪個 filter 影響最大）
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
from src.backtest.models import Position
from config.settings import settings

# ─────────────────────────────────────────────
# 場景定義
# ─────────────────────────────────────────────

@dataclass
class Scenario:
    """單個回測場景的過濾器設定"""
    name: str
    description: str
    # TechnicalStrategy kwargs
    disabled_signals: List[str] = field(default_factory=list)
    require_ma60_uptrend: bool = False
    require_volume_confirmation: bool = False
    volume_confirmation_multiplier: float = 1.5
    rsi_min_entry: float = 0.0
    # BacktestEngine / run_backtest kwargs
    use_market_regime: bool = False
    market_regime_check_ma5: bool = False
    market_regime_rsi_threshold: float = 45.0
    # Momentum whitelist
    momentum_top_n: int = 0
    momentum_lookback_days: int = 20


SCENARIOS: List[Scenario] = [
    Scenario(
        name="0_baseline",
        description="無任何過濾器（基準線）",
    ),
    Scenario(
        name="1_disabled_signals",
        description="+停用 MACD Golden Cross / Golden Cross",
        disabled_signals=["MACD Golden Cross", "Golden Cross"],
    ),
    Scenario(
        name="2_market_regime",
        description="+大盤環境過濾（TAIEX >= MA20）",
        disabled_signals=["MACD Golden Cross", "Golden Cross"],
        use_market_regime=True,
        market_regime_check_ma5=False,
        market_regime_rsi_threshold=0.0,
    ),
    Scenario(
        name="3_market_regime_full",
        description="+大盤環境過濾（MA5>MA20 + RSI>=45）",
        disabled_signals=["MACD Golden Cross", "Golden Cross"],
        use_market_regime=True,
        market_regime_check_ma5=True,
        market_regime_rsi_threshold=45.0,
    ),
    Scenario(
        name="4_ma60_uptrend",
        description="+個股 MA60 上升趨勢",
        disabled_signals=["MACD Golden Cross", "Golden Cross"],
        use_market_regime=True,
        market_regime_check_ma5=True,
        market_regime_rsi_threshold=45.0,
        require_ma60_uptrend=True,
    ),
    Scenario(
        name="5_volume_confirm",
        description="+量能確認（成交量 > 1.5× MA20 量）",
        disabled_signals=["MACD Golden Cross", "Golden Cross"],
        use_market_regime=True,
        market_regime_check_ma5=True,
        market_regime_rsi_threshold=45.0,
        require_ma60_uptrend=True,
        require_volume_confirmation=True,
        volume_confirmation_multiplier=1.5,
    ),
    Scenario(
        name="6_ma_alignment",
        description="+MA 排列（MA5>MA10>MA20）",
        disabled_signals=["MACD Golden Cross", "Golden Cross"],
        use_market_regime=True,
        market_regime_check_ma5=True,
        market_regime_rsi_threshold=45.0,
        require_ma60_uptrend=True,
        require_volume_confirmation=True,
        volume_confirmation_multiplier=1.5,
        # MA alignment is hardcoded in strategy._apply_buy_filters (Filter 4)
        # 這個場景無法直接關閉它；用 rsi_min_entry=0 作為前一步基準
    ),
    Scenario(
        name="7_rsi_min",
        description="+RSI 進場門檻（RSI >= 50）",
        disabled_signals=["MACD Golden Cross", "Golden Cross"],
        use_market_regime=True,
        market_regime_check_ma5=True,
        market_regime_rsi_threshold=45.0,
        require_ma60_uptrend=True,
        require_volume_confirmation=True,
        volume_confirmation_multiplier=1.5,
        rsi_min_entry=50.0,
    ),
    Scenario(
        name="8_momentum_top50",
        description="+動能排名前 50（full = 目前生產設定）",
        disabled_signals=["MACD Golden Cross", "Golden Cross"],
        use_market_regime=True,
        market_regime_check_ma5=True,
        market_regime_rsi_threshold=45.0,
        require_ma60_uptrend=True,
        require_volume_confirmation=True,
        volume_confirmation_multiplier=1.5,
        rsi_min_entry=50.0,
        momentum_top_n=50,
        momentum_lookback_days=20,
    ),
]

# ─────────────────────────────────────────────
# 結果分析
# ─────────────────────────────────────────────

@dataclass
class ScenarioResult:
    name: str
    description: str
    total_trades: int
    win_rate: float          # %
    total_return_pct: float  # %
    profit_factor: float
    max_drawdown: float      # %
    sharpe: float
    avg_holding: float       # days
    # {signal_name: {"trades": int, "wins": int}}
    signal_breakdown: Dict[str, Dict] = field(default_factory=dict)

    def win_rate_by_signal(self, name: str) -> str:
        entry = self.signal_breakdown.get(name, {})
        t = entry.get("trades", 0)
        w = entry.get("wins", 0)
        if t == 0:
            return "  0 trades"
        return f"{w:3d}/{t:3d} = {w/t*100:.1f}%"


def _analyze_signal_breakdown(positions: List[Position]) -> Dict[str, Dict]:
    breakdown: Dict[str, Dict] = {}
    for pos in positions:
        sig = pos.entry_signal_name or "Unknown"
        if sig not in breakdown:
            breakdown[sig] = {"trades": 0, "wins": 0}
        breakdown[sig]["trades"] += 1
        if (pos.pnl or Decimal("0")) > 0:
            breakdown[sig]["wins"] += 1
    return breakdown


# ─────────────────────────────────────────────
# 回測執行
# ─────────────────────────────────────────────

async def run_scenario(
    scenario: Scenario,
    stock_data: dict,
    benchmark_data,
    start_date: date,
    end_date: date,
    excluded_symbols: Set[str],
    initial_capital: Decimal = Decimal("1000000"),
) -> ScenarioResult:
    """單一場景的完整回測流程"""

    # 過濾產業
    data = {s: d for s, d in stock_data.items() if s not in excluded_symbols}

    # 建立策略（MA alignment Filter 4 在 strategy.py 是硬編碼的，無法從外部關閉）
    strategy = TechnicalStrategy(
        disabled_signals=scenario.disabled_signals,
        require_ma60_uptrend=scenario.require_ma60_uptrend,
        require_volume_confirmation=scenario.require_volume_confirmation,
        volume_confirmation_multiplier=scenario.volume_confirmation_multiplier,
        rsi_min_entry=scenario.rsi_min_entry,
    )

    # 產生訊號
    signals = strategy.generate_signals_for_multiple_stocks(
        stock_data_dict=data,
        start_date=start_date,
        end_date=end_date,
    )

    # 回測引擎（使用目前 config 的停損停利，不改變以隔離訊號品質的影響）
    cfg = settings.backtest
    engine = BacktestEngine(
        initial_capital=initial_capital,
        stop_loss_pct=Decimal(str(cfg.stop_loss_pct)),
        take_profit_pct=Decimal(str(cfg.take_profit_pct)),
        trailing_stop_pct=Decimal(str(cfg.trailing_stop_pct)),
        max_holding_days=cfg.max_holding_days,
    )
    for sym, d in data.items():
        engine.add_price_data(sym, d)

    # 動能白名單
    if scenario.momentum_top_n > 0:
        whitelist = strategy.build_momentum_rankings(
            stock_data_dict=data,
            lookback_days=scenario.momentum_lookback_days,
            top_n=scenario.momentum_top_n,
            start_date=start_date,
            end_date=end_date,
        )
        engine.set_momentum_whitelist(whitelist)

    # 執行回測
    result = engine.run_backtest(
        signals=signals,
        start_date=start_date,
        end_date=end_date,
        benchmark_data=benchmark_data if scenario.use_market_regime else None,
        market_regime_rsi_threshold=scenario.market_regime_rsi_threshold,
        market_regime_check_ma5=scenario.market_regime_check_ma5,
    )

    breakdown = _analyze_signal_breakdown(result.trades)

    return ScenarioResult(
        name=scenario.name,
        description=scenario.description,
        total_trades=result.total_trades,
        win_rate=float(result.win_rate),
        total_return_pct=float(result.total_return_pct),
        profit_factor=float(result.profit_factor),
        max_drawdown=float(result.max_drawdown),
        sharpe=float(result.sharpe_ratio),
        avg_holding=float(result.avg_holding_period),
        signal_breakdown=breakdown,
    )


# ─────────────────────────────────────────────
# 報告輸出
# ─────────────────────────────────────────────

def _bar(value: float, max_val: float = 100.0, width: int = 20) -> str:
    filled = int(width * min(abs(value), max_val) / max_val)
    char = "█" if value >= 0 else "░"
    return char * filled + " " * (width - filled)


def print_report(results: List[ScenarioResult], taiex_return: float = 56.34):
    """印出完整的診斷報告"""

    # 收集所有出現過的訊號名稱
    all_signals: Set[str] = set()
    for r in results:
        all_signals.update(r.signal_breakdown.keys())
    all_signals_sorted = sorted(all_signals)

    separator = "─" * 120

    print("\n" + "=" * 120)
    print(" 🔍  過濾器診斷報告  |  逐步累加 Filter 分析")
    print("=" * 120)
    print(f"  大盤 TAIEX 同期報酬: {taiex_return:+.2f}%")
    print()

    # ── 整體績效比較表 ──
    print(f"{'場景':<30} {'交易數':>6} {'勝率':>7} {'報酬率':>8} {'超額':>8} {'獲利因子':>8} {'最大回撤':>8} {'Sharpe':>7} {'平均持倉':>7}")
    print(separator)

    for r in results:
        excess = r.total_return_pct - taiex_return
        tag = "★" if r.name == results[-1].name else " "
        print(
            f"{tag}{r.name:<29} "
            f"{r.total_trades:>6} "
            f"{r.win_rate:>6.1f}% "
            f"{r.total_return_pct:>+7.2f}% "
            f"{excess:>+7.2f}% "
            f"{r.profit_factor:>8.2f} "
            f"{r.max_drawdown:>7.2f}% "
            f"{r.sharpe:>7.2f} "
            f"{r.avg_holding:>6.1f}d"
        )

    print(separator)
    print(f"  ★ = 目前生產設定  |  超額 = 策略報酬 - TAIEX {taiex_return:+.2f}%")

    # ── 每加一個 filter 對交易次數的影響 ──
    print("\n" + "=" * 120)
    print(" 📉  各 Filter 對交易次數的削減影響")
    print("=" * 120)
    baseline_trades = results[0].total_trades if results else 1
    for i, r in enumerate(results):
        if i == 0:
            print(f"  {r.name:<30}  {r.total_trades:>5} 筆  (基準線)")
        else:
            prev = results[i-1].total_trades
            delta = r.total_trades - prev
            pct = delta / prev * 100 if prev else 0
            print(f"  {r.name:<30}  {r.total_trades:>5} 筆  ({delta:+d}, {pct:+.1f}% vs 上一步)")

    # ── 每個訊號的勝率分析 ──
    if all_signals_sorted:
        print("\n" + "=" * 120)
        print(" 🎯  各場景 × 各訊號  勝率明細")
        print("=" * 120)

        # Header
        header = f"{'訊號名稱':<26}"
        for r in results:
            short = r.name[:14]
            header += f"  {short:>14}"
        print(header)
        print(separator)

        for sig in all_signals_sorted:
            row = f"  {sig:<24}"
            for r in results:
                entry = r.signal_breakdown.get(sig, {})
                t = entry.get("trades", 0)
                w = entry.get("wins", 0)
                if t == 0:
                    cell = "      -"
                else:
                    cell = f"{w}/{t}={w/t*100:.0f}%"
                row += f"  {cell:>14}"
            print(row)

    # ── 結論 ──
    print("\n" + "=" * 120)
    print(" 💡  自動診斷結論")
    print("=" * 120)

    if len(results) >= 2:
        # 找出最大削減交易次數的步驟
        max_cut_step = None
        max_cut_abs = 0
        for i in range(1, len(results)):
            delta = results[i-1].total_trades - results[i].total_trades
            if delta > max_cut_abs:
                max_cut_abs = delta
                max_cut_step = results[i]

        if max_cut_step:
            print(f"  → 削減交易次數最多的步驟: [{max_cut_step.name}] 減少了 {max_cut_abs} 筆")

        # 找出加入後「報酬率改善最多」的步驟
        best_improvement = None
        best_gain = -999
        for i in range(1, len(results)):
            gain = results[i].total_return_pct - results[i-1].total_return_pct
            if gain > best_gain:
                best_gain = gain
                best_improvement = results[i]

        if best_improvement and best_gain > 0:
            print(f"  → 加入後報酬率改善最多: [{best_improvement.name}] +{best_gain:.2f}%")
        elif best_improvement:
            print(f"  → 所有過濾器都讓報酬率下降，改善最少的: [{best_improvement.name}] {best_gain:+.2f}%")

        # 找出加入後「報酬率下滑最多」的步驟
        worst_step = None
        worst_loss = 999
        for i in range(1, len(results)):
            gain = results[i].total_return_pct - results[i-1].total_return_pct
            if gain < worst_loss:
                worst_loss = gain
                worst_step = results[i]

        if worst_step and worst_loss < 0:
            print(f"  → 加入後報酬率下滑最多: [{worst_step.name}] {worst_loss:+.2f}%")

    # 檢查是否有訊號完全無交易
    last = results[-1] if results else None
    if last:
        dead_signals = [s for s in all_signals_sorted if last.signal_breakdown.get(s, {}).get("trades", 0) == 0]
        alive_signals = [s for s in all_signals_sorted if last.signal_breakdown.get(s, {}).get("trades", 0) > 0]
        if dead_signals:
            print(f"  → 在 full 設定下完全無交易的訊號: {dead_signals}")
        if alive_signals:
            for sig in alive_signals:
                entry = last.signal_breakdown.get(sig, {})
                t = entry.get("trades", 0)
                w = entry.get("wins", 0)
                wr = w / t * 100 if t else 0
                print(f"  → 實際交易訊號: [{sig}] {t} 筆, 勝率 {wr:.1f}%")

    print("=" * 120 + "\n")


# ─────────────────────────────────────────────
# 主程式
# ─────────────────────────────────────────────

async def main():
    cfg = settings.backtest
    start_date = cfg.start_date or date(2024, 9, 1)
    end_date = cfg.end_date or date.today()

    print(f"\n🔍 過濾器診斷回測  {start_date} → {end_date}")
    print(f"   場景數: {len(SCENARIOS)}")
    print(f"   注意：MA alignment（MA5>MA10>MA20）為 strategy.py 硬編碼，全場景均啟用\n")

    # ── 載入資料（只載一次）──
    data_source = YFinanceDataSource()
    stocks_dir = os.path.normpath(
        os.path.join(os.path.dirname(__file__), '../data/stocks')
    )
    needed_start = start_date - timedelta(days=100)

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

    # ── 載入大盤資料（只載一次）──
    print("📊 載入大盤資料...")
    benchmark_data = data_source.get_market_index_data(start_date, end_date)
    print(f"   TAIEX {len(benchmark_data) if benchmark_data else 0} 筆")

    # ── 產業排除清單 ──
    excluded_symbols = cfg.load_excluded_symbols(
        project_root=Path(os.path.normpath(os.path.join(os.path.dirname(__file__), '..')))
    )

    # ── 逐一執行場景 ──
    results: List[ScenarioResult] = []
    for i, scenario in enumerate(SCENARIOS):
        print(f"\n[{i+1}/{len(SCENARIOS)}] {scenario.name}: {scenario.description}")
        result = await run_scenario(
            scenario=scenario,
            stock_data=stock_data,
            benchmark_data=benchmark_data,
            start_date=start_date,
            end_date=end_date,
            excluded_symbols=excluded_symbols,
        )
        print(
            f"   → 交易: {result.total_trades}, 勝率: {result.win_rate:.1f}%, "
            f"報酬: {result.total_return_pct:+.2f}%, 最大回撤: {result.max_drawdown:.2f}%"
        )
        results.append(result)

    # ── 計算 TAIEX 期間報酬 ──
    taiex_return = 56.34  # 從 report_20260408_163607.md
    if benchmark_data and len(benchmark_data) >= 2:
        sorted_bm = sorted(benchmark_data, key=lambda x: x.date)
        first, last = sorted_bm[0].close_price, sorted_bm[-1].close_price
        taiex_return = float((last - first) / first * 100)

    # ── 輸出報告 ──
    print_report(results, taiex_return=taiex_return)


if __name__ == "__main__":
    asyncio.run(main())
