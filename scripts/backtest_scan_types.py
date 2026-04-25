"""
Scan Type Backtest Comparison
==============================
比較三種掃描類型（動能股、超賣股、突破股）各自的歷史回測績效。

做法：
  對每個交易日，根據掃描條件篩選當日符合資格的股票，建立每日白名單，
  然後用 P1 生產設定的策略，只對白名單內的股票進行交易。

掃描條件（與 csv_scanner.py 一致）：
  動能股: price_change_pct > 3%, volume > 500k, RSI14 > 50
  超賣股: RSI14 < 30, price_change_pct < -2%, volume > 300k
  突破股: volume > 1M, close > MA20, close > 10

使用方式:
    cd /Users/yhh/GitHub/bag.holder.tw
    source venv/bin/activate
    python scripts/backtest_scan_types.py
"""

import asyncio
import os
import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional, Set

import numpy as np

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.infrastructure.market_data.backtest_data_source import YFinanceDataSource
from src.application.services.backtest_engine import BacktestEngine
from src.application.services.backtest_strategy import TechnicalStrategy
from src.domain.models import Position, StockData
from config.settings import settings


# ─────────────────────────────────────────────
# 技術指標計算工具
# ─────────────────────────────────────────────

def _compute_rsi(closes: List[float], period: int = 14) -> List[float]:
    """計算 RSI，回傳與 closes 等長的 list（前 period 個為 nan）"""
    n = len(closes)
    rsi = [float('nan')] * n
    if n <= period:
        return rsi

    deltas = [closes[i] - closes[i - 1] for i in range(1, n)]
    gains = [max(d, 0.0) for d in deltas]
    losses = [max(-d, 0.0) for d in deltas]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, n):
        if i > period:
            avg_gain = (avg_gain * (period - 1) + gains[i - 1]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i - 1]) / period
        if avg_loss == 0:
            rsi[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi[i] = 100.0 - (100.0 / (1.0 + rs))

    return rsi


def _compute_ma(closes: List[float], period: int) -> List[float]:
    """計算移動平均，前 period-1 個為 nan"""
    ma = [float('nan')] * len(closes)
    for i in range(period - 1, len(closes)):
        ma[i] = sum(closes[i - period + 1:i + 1]) / period
    return ma


# ─────────────────────────────────────────────
# 每日白名單建立
# ─────────────────────────────────────────────

def build_scan_whitelist(
    stock_data_dict: Dict[str, List[StockData]],
    scan_type: str,
    start_date: date,
    end_date: date,
) -> Dict[date, Set[str]]:
    """
    依掃描條件，建立每個交易日的股票白名單。

    scan_type: "momentum" | "oversold" | "breakout"
    回傳 {date: set_of_symbols}，只包含 [start_date, end_date] 內的日期。
    """
    # scan type → scanner criteria thresholds
    cfg_strat = settings.strategy

    whitelist: Dict[date, Set[str]] = {}

    for symbol, records in stock_data_dict.items():
        if len(records) < 25:
            continue

        closes = [float(r.close_price) for r in records]
        volumes = [r.volume for r in records]
        dates = [r.date for r in records]

        # 計算技術指標
        rsi_vals = _compute_rsi(closes, 14)
        ma20_vals = _compute_ma(closes, 20)

        for i, d in enumerate(dates):
            if d < start_date or d > end_date:
                continue

            close = closes[i]
            volume = volumes[i]
            rsi = rsi_vals[i]
            ma20 = ma20_vals[i]

            # 前一天收盤（price_change_pct）
            if i == 0 or closes[i - 1] == 0:
                continue
            price_chg = (close - closes[i - 1]) / closes[i - 1] * 100

            if np.isnan(rsi) or np.isnan(ma20):
                continue

            eligible = False
            if scan_type == "momentum":
                eligible = (
                    price_chg > cfg_strat.momentum_price_change  # default 3.0%
                    and volume > cfg_strat.min_volume_momentum   # default 500_000
                    and rsi > 50
                )
            elif scan_type == "oversold":
                eligible = (
                    rsi < cfg_strat.rsi_oversold_threshold       # default 30.0
                    and price_chg < cfg_strat.oversold_price_change  # default -2.0%
                    and volume > cfg_strat.min_volume_oversold   # default 300_000
                )
            elif scan_type == "breakout":
                eligible = (
                    volume > cfg_strat.min_volume_breakout       # default 1_000_000
                    and close > ma20
                    and close > cfg_strat.min_price              # default 10.0
                )

            if eligible:
                whitelist.setdefault(d, set()).add(symbol)

    total_entries = sum(len(v) for v in whitelist.values())
    print(f"   [{scan_type}] 白名單建立完成：{len(whitelist)} 個交易日，"
          f"共 {total_entries} 筆符合")
    return whitelist


# ─────────────────────────────────────────────
# 結果資料結構
# ─────────────────────────────────────────────

@dataclass
class ScanResult:
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
    whitelist_dates: int = 0
    whitelist_avg_stocks: float = 0.0

    def win_rate_str(self) -> str:
        return f"{self.win_rate:.1f}%"


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
# 單一場景回測
# ─────────────────────────────────────────────

async def run_scan_backtest(
    name: str,
    description: str,
    stock_data: Dict[str, List[StockData]],
    benchmark_data,
    start_date: date,
    end_date: date,
    excluded_symbols: Set[str],
    whitelist: Optional[Dict[date, Set[str]]] = None,
    rsi_min_entry: float = 50.0,
    initial_capital: Decimal = Decimal("1000000"),
) -> ScanResult:
    """執行單一掃描類型的回測"""

    data = {s: d for s, d in stock_data.items() if s not in excluded_symbols}
    cfg = settings.backtest

    # P1 生產策略設定（與 main.py BacktestRunner 一致）
    disabled = [s.strip() for s in cfg.disabled_signals.split(",") if s.strip()]
    strategy = TechnicalStrategy(
        disabled_signals=disabled,
        require_ma60_uptrend=cfg.require_ma60_uptrend,
        require_volume_confirmation=cfg.require_volume_confirmation,
        volume_confirmation_multiplier=cfg.volume_confirmation_multiplier,
        rsi_min_entry=rsi_min_entry,
        donchian_period=cfg.donchian_period,
    )

    signals = strategy.generate_signals_for_multiple_stocks(
        stock_data_dict=data,
        start_date=start_date,
        end_date=end_date,
    )

    # 建立回測引擎（P1 停損停利設定）
    import src.backtest.engine as engine_mod
    from src.backtest.engine import BacktestEngine as BE

    # Parse regime signal lists
    def _parse_signals(s: str):
        items = [x.strip() for x in s.split(",") if x.strip()]
        return items if items else None

    engine = BE(
        initial_capital=initial_capital,
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

    # 趨勢訊號出場設定
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

    for sym, d in data.items():
        engine.add_price_data(sym, d)

    # 設定掃描白名單（取代 momentum whitelist）
    if whitelist is not None:
        engine.set_momentum_whitelist(whitelist)
    elif cfg.momentum_top_n > 0:
        # 無白名單時，使用 P1 動能排名（baseline）
        mw = strategy.build_momentum_rankings(
            stock_data_dict=data,
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

    breakdown = _analyze_signal_breakdown(result.trades)

    wl_dates = len(whitelist) if whitelist else 0
    wl_avg = (
        sum(len(v) for v in whitelist.values()) / wl_dates
        if whitelist and wl_dates > 0 else 0.0
    )

    return ScanResult(
        name=name,
        description=description,
        total_trades=result.total_trades,
        win_rate=float(result.win_rate),
        total_return_pct=float(result.total_return_pct),
        profit_factor=float(result.profit_factor),
        max_drawdown=float(result.max_drawdown),
        sharpe=float(result.sharpe_ratio),
        avg_holding=float(result.avg_holding_period),
        signal_breakdown=breakdown,
        whitelist_dates=wl_dates,
        whitelist_avg_stocks=wl_avg,
    )


# ─────────────────────────────────────────────
# 報告輸出
# ─────────────────────────────────────────────

def print_report(results: List[ScanResult], taiex_return: float):
    sep = "─" * 130

    print("\n" + "=" * 130)
    print("  掃描類型回測比較報告")
    print("=" * 130)
    print(f"  大盤 TAIEX 同期報酬: {taiex_return:+.2f}%")
    print()

    # 整體績效表
    print(f"{'名稱':<28} {'交易數':>6} {'勝率':>7} {'報酬率':>8} {'超額':>8} "
          f"{'獲利因子':>8} {'最大回撤':>8} {'Sharpe':>7} {'平均持倉':>8} "
          f"{'白名單日':>8} {'均白名單支':>10}")
    print(sep)

    for r in results:
        excess = r.total_return_pct - taiex_return
        print(
            f"  {r.name:<26} "
            f"{r.total_trades:>6} "
            f"{r.win_rate:>6.1f}% "
            f"{r.total_return_pct:>+7.2f}% "
            f"{excess:>+7.2f}% "
            f"{r.profit_factor:>8.2f} "
            f"{r.max_drawdown:>7.2f}% "
            f"{r.sharpe:>7.2f} "
            f"{r.avg_holding:>7.1f}d "
            f"{r.whitelist_dates:>8} "
            f"{r.whitelist_avg_stocks:>10.1f}"
        )

    print(sep)
    print(f"  超額 = 策略報酬 - TAIEX {taiex_return:+.2f}%")

    # 訊號明細
    all_signals: Set[str] = set()
    for r in results:
        all_signals.update(r.signal_breakdown.keys())
    all_sigs = sorted(all_signals)

    if all_sigs:
        print("\n" + "=" * 130)
        print("  各掃描類型 × 各訊號  勝率明細")
        print("=" * 130)
        header = f"  {'訊號名稱':<26}"
        for r in results:
            header += f"  {r.name[:16]:>16}"
        print(header)
        print(sep)
        for sig in all_sigs:
            row = f"  {sig:<26}"
            for r in results:
                entry = r.signal_breakdown.get(sig, {})
                t = entry.get("trades", 0)
                w = entry.get("wins", 0)
                if t == 0:
                    cell = "-"
                else:
                    cell = f"{w}/{t}={w/t*100:.0f}%"
                row += f"  {cell:>16}"
            print(row)

    # 結論
    print("\n" + "=" * 130)
    print("  結論")
    print("=" * 130)
    baseline = next((r for r in results if r.name == "baseline"), results[0])
    for r in results:
        if r.name == "baseline":
            continue
        delta = r.total_return_pct - baseline.total_return_pct
        sign = "+" if delta >= 0 else ""
        tag = "↑ 優於基準" if delta > 0 else "↓ 遜於基準"
        print(f"  {r.name:<28}  vs 基準: {sign}{delta:.2f}%  [{tag}]  "
              f"白名單平均每日 {r.whitelist_avg_stocks:.1f} 支股票可交易")
    print("=" * 130 + "\n")


# ─────────────────────────────────────────────
# 主程式
# ─────────────────────────────────────────────

async def main():
    cfg = settings.backtest
    start_date = cfg.start_date or date(2024, 9, 1)
    end_date = cfg.end_date or date.today()

    print(f"\n掃描類型回測  {start_date} → {end_date}")

    # 載入資料
    data_source = YFinanceDataSource()
    stocks_dir = os.path.normpath(
        os.path.join(os.path.dirname(__file__), '../data/stocks')
    )
    needed_start = start_date - timedelta(days=120)  # 多抓 120 天暖機

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
    print(f"   TAIEX {len(benchmark_data) if benchmark_data else 0} 筆")

    excluded_symbols = cfg.load_excluded_symbols(
        project_root=Path(os.path.normpath(os.path.join(os.path.dirname(__file__), '..')))
    )
    filtered_data = {s: d for s, d in stock_data.items() if s not in excluded_symbols}
    print(f"   產業排除後剩 {len(filtered_data)} 支股票")

    # 建立掃描白名單
    print("\n🔍 建立掃描條件白名單...")
    wl_momentum = build_scan_whitelist(filtered_data, "momentum", start_date, end_date)
    wl_oversold = build_scan_whitelist(filtered_data, "oversold", start_date, end_date)
    wl_breakout = build_scan_whitelist(filtered_data, "breakout", start_date, end_date)

    # 定義場景
    scenarios = [
        # (name, description, whitelist, rsi_min_entry)
        ("baseline",   "P1 生產設定（全股票 + 動能 top30）", None,          50.0),
        ("動能股 P1",  "動能掃描白名單 + P1 設定",           wl_momentum,   50.0),
        ("突破股 P1",  "突破掃描白名單 + P1 設定",           wl_breakout,   50.0),
        ("超賣股 P1",  "超賣掃描白名單 + P1 設定 (RSI≥50)",  wl_oversold,   50.0),
        ("超賣股 noRSI", "超賣掃描白名單 + 停用 RSI 進場過濾", wl_oversold, 0.0),
    ]

    results: List[ScanResult] = []
    for name, desc, wl, rsi_entry in scenarios:
        wl_info = f"{len(wl)} 個白名單日" if wl is not None else "無（使用動能 top30）"
        print(f"\n[{name}] {desc}  ({wl_info})")
        result = await run_scan_backtest(
            name=name,
            description=desc,
            stock_data=filtered_data,
            benchmark_data=benchmark_data,
            start_date=start_date,
            end_date=end_date,
            excluded_symbols=set(),  # already filtered above
            whitelist=wl,
            rsi_min_entry=rsi_entry,
        )
        print(
            f"   → 交易: {result.total_trades}, 勝率: {result.win_rate:.1f}%, "
            f"報酬: {result.total_return_pct:+.2f}%, Sharpe: {result.sharpe:.2f}, "
            f"最大回撤: {result.max_drawdown:.2f}%"
        )
        results.append(result)

    # TAIEX 期間報酬
    taiex_return = 0.0
    if benchmark_data and len(benchmark_data) >= 2:
        sorted_bm = sorted(benchmark_data, key=lambda x: x.date)
        first, last = sorted_bm[0].close_price, sorted_bm[-1].close_price
        taiex_return = float((last - first) / first * 100)

    print_report(results, taiex_return)


if __name__ == "__main__":
    asyncio.run(main())
