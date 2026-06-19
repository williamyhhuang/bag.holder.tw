"""
Win-Rate Optimization Harness
==============================
逐項驗證「提升選股勝率」的各個改動（A 出場 / B 進場 / C 品質過濾），
與 baseline 做 apples-to-apples 比較，輸出勝率 / 報酬率 / 獲利因子 / 回撤 / 交易數。

設計重點：
  * 直接重用生產用 BacktestRunner（與 strategy.py / signals_scanner 共用同一條 wiring），
    每個場景只覆寫 config.settings.backtest 的欄位 → 確保回測＝實盤，無策略漂移。
  * 歷史資料與大盤資料只載入一次，跨場景快取重用。
  * 每個場景跑完自動還原被覆寫的欄位。

採納準則（與使用者確認的目標一致：勝率優先但守住報酬）：
  win_rate↑  且  total_return_pct >= baseline*0.95  且  profit_factor >= baseline

使用方式:
    cd /Users/yhh/GitHub/bag.holder.tw
    source venv/bin/activate
    python scripts/optimize_winrate.py
"""

import asyncio
import os
import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Dict, List, Optional

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from config.settings import settings
from src.interfaces.cli.backtest_main import BacktestRunner
from src.infrastructure.market_data.backtest_data_source import YFinanceDataSource


# ─────────────────────────────────────────────
# 場景定義：每個場景是一組 settings.backtest 覆寫
# ─────────────────────────────────────────────

@dataclass
class Scenario:
    name: str
    description: str
    overrides: Dict[str, object] = field(default_factory=dict)


# baseline = 本次改動「之前」的生產行為（關閉三個新槓桿），用來量測提升幅度
BASELINE_OVERRIDES: Dict[str, object] = {
    "enable_profit_protection": False,      # A1 off（基礎部位無獲利保護）
    "catastrophic_stop_pct": 0.0,           # A2 off
    "rsi_oversold_require_uptrend": False,   # B1 off
}

# 每個全期回測約 3-4 分鐘，故預設只跑必要場景。
# 第一輪結論：A1（+5%鎖6% 獲利保護）、A2（-15% 鎖倉災難停損）皆讓勝率/報酬下降，已棄用為預設。
# 第二輪：改測「提早停利」這個最可靠的勝率槓桿 —— 降低 take_profit_pct 讓更多單在獲利時出場。
SCENARIOS: List[Scenario] = [
    Scenario("0_baseline", "現行生產（TP=10%，三新槓桿關）", dict(BASELINE_OVERRIDES)),
    Scenario("tp_08", "提早停利 TP=8%",
             {**BASELINE_OVERRIDES, "take_profit_pct": 0.08}),
    Scenario("tp_06", "提早停利 TP=6%",
             {**BASELINE_OVERRIDES, "take_profit_pct": 0.06}),
    Scenario("pp_loose", "獲利保護（寬版：+10%後鎖4%）",
             {**BASELINE_OVERRIDES, "enable_profit_protection": True,
              "profit_threshold_pct": 0.10, "profit_trailing_pct": 0.04}),
]


@dataclass
class Result:
    name: str
    description: str
    total_trades: int
    win_rate: float
    total_return_pct: float
    profit_factor: float
    max_drawdown: float
    sharpe: float
    avg_holding: float
    signal_breakdown: Dict[str, Dict] = field(default_factory=dict)


def _breakdown(positions) -> Dict[str, Dict]:
    out: Dict[str, Dict] = {}
    for pos in positions:
        sig = pos.entry_signal_name or "Unknown"
        out.setdefault(sig, {"trades": 0, "wins": 0})
        out[sig]["trades"] += 1
        if (pos.pnl or Decimal("0")) > 0:
            out[sig]["wins"] += 1
    return out


# ─────────────────────────────────────────────
# 資料快取：跨場景只載入一次
# ─────────────────────────────────────────────

class _DataCache:
    stock_data = None
    benchmark = None

    @classmethod
    def load(cls, start_date: date, end_date: date):
        if cls.stock_data is not None:
            return
        ds = YFinanceDataSource()
        stocks_dir = os.path.normpath(
            os.path.join(os.path.dirname(__file__), '../data/stocks')
        )
        print("📂 載入歷史資料（只載一次）...")
        cls.stock_data = ds.load_from_stocks_dir(
            stocks_dir=stocks_dir,
            start_date=start_date - timedelta(days=100),
            end_date=end_date,
        )
        print(f"   載入 {len(cls.stock_data)} 支股票")
        print("📊 載入大盤資料...")
        cls.benchmark = ds.get_market_index_data(start_date, end_date)
        print(f"   TAIEX {len(cls.benchmark) if cls.benchmark else 0} 筆")


def _patch_runner(runner: BacktestRunner):
    """讓 runner 使用快取資料、停用報告檔輸出，加速跨場景比較。"""
    runner.data_source.load_from_stocks_dir = lambda **kw: _DataCache.stock_data  # type: ignore
    runner.data_source.get_market_index_data = lambda *a, **kw: _DataCache.benchmark  # type: ignore
    if getattr(runner, "reporter", None) is not None:
        runner.reporter.export_all_results = lambda **kw: {}  # type: ignore


async def run_scenario(scenario: Scenario, start_date: date, end_date: date) -> Result:
    cfg = settings.backtest
    saved = {k: getattr(cfg, k) for k in scenario.overrides}
    try:
        for k, v in scenario.overrides.items():
            setattr(cfg, k, v)
        # 覆寫後才建立 runner（strategy 在 __init__ 依 settings 建構）
        runner = BacktestRunner()
        _patch_runner(runner)
        result, _ = await runner.run_full_backtest(
            start_date=start_date, end_date=end_date, skip_download=True,
        )
    finally:
        for k, v in saved.items():
            setattr(cfg, k, v)

    return Result(
        name=scenario.name,
        description=scenario.description,
        total_trades=result.total_trades,
        win_rate=float(result.win_rate),
        total_return_pct=float(result.total_return_pct),
        profit_factor=float(result.profit_factor),
        max_drawdown=float(result.max_drawdown),
        sharpe=float(result.sharpe_ratio),
        avg_holding=float(result.avg_holding_period),
        signal_breakdown=_breakdown(result.trades),
    )


def print_report(results: List[Result]):
    sep = "─" * 104
    base = results[0]
    print("\n" + "=" * 104)
    print(" 🎯  Win-Rate 優化對照表  |  baseline = 改動前生產行為")
    print("=" * 104)
    print(f"{'場景':<24}{'交易數':>7}{'勝率':>8}{'報酬率':>9}{'獲利因子':>9}{'最大回撤':>9}{'Sharpe':>8}{'持倉':>7}")
    print(sep)
    for r in results:
        tag = "▶" if r.name == "ALL_candidate" else " "
        print(f"{tag}{r.name:<23}{r.total_trades:>7}{r.win_rate:>7.1f}%"
              f"{r.total_return_pct:>+8.2f}%{r.profit_factor:>9.2f}"
              f"{r.max_drawdown:>8.2f}%{r.sharpe:>8.2f}{r.avg_holding:>6.1f}d")
    print(sep)

    # 採納判定
    print("\n 採納判定（勝率↑ 且 報酬>=baseline*0.95 且 獲利因子>=baseline）：")
    ret_floor = base.total_return_pct * 0.95 if base.total_return_pct >= 0 else base.total_return_pct * 1.05
    for r in results[1:]:
        wr = r.win_rate - base.win_rate
        ok = (r.win_rate > base.win_rate
              and r.total_return_pct >= ret_floor
              and r.profit_factor >= base.profit_factor)
        verdict = "✅ 採納" if ok else "❌ 不採納"
        print(f"   {r.name:<24} 勝率 {wr:+.1f}pp, "
              f"報酬 {r.total_return_pct - base.total_return_pct:+.2f}pp, "
              f"獲利因子 {r.profit_factor - base.profit_factor:+.2f}  → {verdict}")
    print("=" * 104 + "\n")


def _build_tp_sweep(values: List[float]) -> List[Scenario]:
    """從一組 take_profit_pct 值建立掃描場景（其餘維持 baseline，三新槓桿關）。"""
    scs = []
    for v in values:
        scs.append(Scenario(f"tp_{int(round(v*100)):02d}", f"停利 TP={v*100:.0f}%",
                            {**BASELINE_OVERRIDES, "take_profit_pct": v}))
    return scs


async def main():
    cfg = settings.backtest
    start_date = cfg.start_date or date(2024, 9, 1)
    end_date = cfg.end_date or date.today()

    # 支援 `--tp-sweep 0.05,0.07,...` 對 take_profit_pct 做細掃描
    scenarios = SCENARIOS
    for arg in sys.argv[1:]:
        if arg.startswith("--tp-sweep="):
            vals = [float(x) for x in arg.split("=", 1)[1].split(",") if x.strip()]
            scenarios = _build_tp_sweep(vals)
        elif arg == "--tp-sweep" and len(sys.argv) > sys.argv.index(arg) + 1:
            vals = [float(x) for x in sys.argv[sys.argv.index(arg) + 1].split(",") if x.strip()]
            scenarios = _build_tp_sweep(vals)

    print(f"\n🔬 Win-Rate 優化回測  {start_date} → {end_date}  |  {len(scenarios)} 場景\n")

    _DataCache.load(start_date, end_date)

    results: List[Result] = []
    for i, sc in enumerate(scenarios):
        print(f"[{i+1}/{len(scenarios)}] {sc.name}: {sc.description}")
        r = await run_scenario(sc, start_date, end_date)
        print(f"   → 交易 {r.total_trades}, 勝率 {r.win_rate:.1f}%, "
              f"報酬 {r.total_return_pct:+.2f}%, 獲利因子 {r.profit_factor:.2f}, "
              f"回撤 {r.max_drawdown:.2f}%")
        results.append(r)

    print_report(results)


if __name__ == "__main__":
    asyncio.run(main())
