"""
MTX 微台策略參數最佳化 — 全面參數掃描 + Walk-forward LOO/OOS 驗證

動機（見一個月模擬結果分析）:
  現行策略淨虧損 (PF≈0.5)，三大根因：
    1. 報酬:風險不對稱 — KD 閘門 (min_profit=8) 讓贏單 +8~10 被砍，輸單跑到 -50/-80。
    2. 日K趨勢濾網形同虛設 (Day 一直 =0)。
    3. 盤整追打 / 停損後立即重進場 (無冷卻)。

本工具用一個月 tick 對下列槓桿做網格掃描，並以 walk-forward leave-one-day-out
做樣本外 (OOS) 驗證，避免單月過擬合：
  - 停損 (日/夜分開)、停利
  - 出場機制：KD 閘門 vs 保本停損 + 移動停利
  - 停損後冷卻 (cooldown bars)
  - 盤整濾網 (5m ADX 門檻)
  - 方向：日盤多空 vs 只做多 (夜盤一律只做多，與生產一致)

注意：本掃描器為「快速參數搜尋」工具，5m 訊號採「最近已收盤 5m K」(因果、無未來函數)，
與生產引擎 (forming-bar) 略有差異。勝出參數會再用 backtest_mtx_strategies.simulate_session
(與生產引擎逐行對齊) 做最終驗證後才採用。

用法:
  python scripts/optimize_mtx.py --data-dir data/taifex_tick
  python scripts/optimize_mtx.py --data-dir data/taifex_tick --metric sharpe --min-trades 20
"""
from __future__ import annotations

import argparse
import itertools
import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, date
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

# 重用既有回測模組的資料載入與指標 (確保與生產邏輯同源)
from backtest_mtx_strategies import (  # noqa: E402
    Bar,
    Trade,
    build_bars,
    build_daily_bars,
    daily_bias,
    floor_to_tf,
    load_mtx_ticks,
    signal_5m_A,
)

try:
    import talib as _talib  # type: ignore

    _TALIB = True
except ImportError:  # pragma: no cover
    _TALIB = False

POINT_VALUE = 10          # 1 pt = 10 NTD / 口 (微台)
FEE_PER_LOT = 50          # 單邊手續費+稅估計 (NTD/口)


# ---------------------------------------------------------------------------
# Parameter set
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Params:
    day_stop: float
    night_stop: float
    take_profit: float          # 0 = 停用
    kd_gate: float              # <0 = 停用 KD 出場；>=0 = 達此獲利後 KD 反交叉出場
    breakeven_trigger: float    # 0 = 停用；>0 = 浮盈達此值後鎖保本
    breakeven_buffer: float     # 保本觸發後，回落到此 pnl 即出場 (通常 0)
    trail_activate: float       # 0 = 停用；浮盈峰值達此值才啟動移動停利
    trail_distance: float       # 自峰值回落此值出場
    cooldown_bars: int          # 停損後封鎖進場的 1m bar 數
    adx_min: float              # 0 = 停用；5m ADX 低於此值不進場 (濾盤整)
    long_only_day: bool         # 日盤只做多
    name: str = ""

    def label(self) -> str:
        ex = []
        if self.kd_gate >= 0:
            ex.append(f"KD{self.kd_gate:.0f}")
        if self.breakeven_trigger > 0:
            ex.append(f"BE{self.breakeven_trigger:.0f}")
        if self.trail_activate > 0:
            ex.append(f"TR{self.trail_activate:.0f}/{self.trail_distance:.0f}")
        tp = f"TP{self.take_profit:.0f}" if self.take_profit > 0 else "TP-"
        return (
            f"SL{self.day_stop:.0f}/{self.night_stop:.0f} {tp} {'+'.join(ex) or 'none'} "
            f"cd{self.cooldown_bars} adx{self.adx_min:.0f} {'多' if self.long_only_day else '多空'}"
        )


def production_params() -> Params:
    """現行生產 (baseline) 參數。"""
    return Params(
        day_stop=50, night_stop=80, take_profit=150,
        kd_gate=8, breakeven_trigger=0, breakeven_buffer=0,
        trail_activate=0, trail_distance=0,
        cooldown_bars=0, adx_min=0, long_only_day=False, name="BASELINE",
    )


# ---------------------------------------------------------------------------
# Per-session precompute (參數無關，一次算好)
# ---------------------------------------------------------------------------

@dataclass
class SessionPre:
    sk: str
    sdate: date
    is_night: bool
    prices: List[float]
    ts: List[datetime]
    long_trig: List[bool]
    short_trig: List[bool]
    gc1m: List[bool]
    dc1m: List[bool]
    s5m: List[int]            # 最近已收盤 5m K 的 A 訊號 (+1/-1/0)
    adx5m: List[float]        # 對應 1m bar 的 5m ADX (最近已收盤值)
    db: int                   # 日K bias (session 內固定)


def _stoch_arrays(bars: List[Bar], fastk=9, slowk=3, slowd=3):
    n = len(bars)
    high = np.array([b.high for b in bars], dtype=float)
    low = np.array([b.low for b in bars], dtype=float)
    close = np.array([b.close for b in bars], dtype=float)
    if _TALIB and n >= fastk + slowk + slowd:
        k, d = _talib.STOCH(high, low, close, fastk, slowk, 0, slowd, 0)
        return k, d, close
    # fallback: NaN arrays (precompute will yield 0 signals — acceptable for tiny data)
    nan = np.full(n, np.nan)
    return nan.copy(), nan.copy(), close


def _sma(close: np.ndarray, period: int) -> np.ndarray:
    if _TALIB and len(close) >= period:
        return _talib.SMA(close, period)
    n = len(close)
    out = np.full(n, np.nan)
    for i in range(period - 1, n):
        out[i] = close[i - period + 1:i + 1].mean()
    return out


def _cross_arrays(k: np.ndarray, d: np.ndarray):
    n = len(k)
    gc = [False] * n
    dc = [False] * n
    for i in range(1, n):
        if any(math.isnan(x) for x in (k[i - 1], d[i - 1], k[i], d[i])):
            continue
        if k[i - 1] < d[i - 1] and k[i] >= d[i]:
            gc[i] = True
        elif k[i - 1] > d[i - 1] and k[i] <= d[i]:
            dc[i] = True
    return gc, dc


def precompute_session(sk: str, ticks, daily_before: List[Bar]) -> Optional[SessionPre]:
    bars_1m = build_bars(ticks, 1)
    bars_5m = build_bars(ticks, 5)
    if len(bars_1m) < 20:
        return None

    is_night = "_night" in sk
    sdate = datetime.strptime(sk[:10], "%Y-%m-%d").date()
    prices = [b.close for b in bars_1m]
    ts = [b.ts for b in bars_1m]

    # 1m 指標
    k1, d1, close1 = _stoch_arrays(bars_1m)
    ma5_1 = _sma(close1, 5)
    gc1m, dc1m = _cross_arrays(k1, d1)
    n = len(bars_1m)
    long_trig = [gc1m[i] and not math.isnan(ma5_1[i]) and close1[i] > ma5_1[i] for i in range(n)]
    short_trig = [dc1m[i] and not math.isnan(ma5_1[i]) and close1[i] < ma5_1[i] for i in range(n)]

    # 5m A 訊號 (每根已收盤 5m K 算一次)，再映射到 1m
    s5m_bar = [0] * len(bars_5m)
    for j in range(len(bars_5m)):
        s5m_bar[j] = signal_5m_A(bars_5m[:j + 1])

    # 5m ADX
    adx_bar = [0.0] * len(bars_5m)
    if _TALIB and len(bars_5m) >= 30:
        h5 = np.array([b.high for b in bars_5m], dtype=float)
        l5 = np.array([b.low for b in bars_5m], dtype=float)
        c5 = np.array([b.close for b in bars_5m], dtype=float)
        adx = _talib.ADX(h5, l5, c5, 14)
        adx_bar = [0.0 if math.isnan(x) else float(x) for x in adx]

    # 映射到 1m：用「最近已收盤」5m K (避免未來函數)
    five_ts = [b.ts for b in bars_5m]
    ts_to_idx = {t: i for i, t in enumerate(five_ts)}
    s5m = [0] * n
    adx5m = [0.0] * n
    for i in range(n):
        cur5 = floor_to_tf(ts[i], 5)
        j = ts_to_idx.get(cur5)
        closed_j = (j - 1) if j is not None else _last_closed(five_ts, cur5)
        if closed_j is not None and closed_j >= 0:
            s5m[i] = s5m_bar[closed_j]
            adx5m[i] = adx_bar[closed_j]

    db = daily_bias(daily_before)

    return SessionPre(sk, sdate, is_night, prices, ts, long_trig, short_trig,
                      gc1m, dc1m, s5m, adx5m, db)


def _last_closed(five_ts: List[datetime], cur5: datetime) -> Optional[int]:
    idx = None
    for i, t in enumerate(five_ts):
        if t < cur5:
            idx = i
        else:
            break
    return idx


# ---------------------------------------------------------------------------
# Fast parametric simulation (參數相關，每組合跑一次)
# ---------------------------------------------------------------------------

def simulate(pre: SessionPre, p: Params, max_lots: int = 3) -> List[Trade]:
    trades: List[Trade] = []
    n = len(pre.prices)
    stop = p.night_stop if pre.is_night else p.day_stop
    allow_short = (not pre.is_night) and (not p.long_only_day)  # 夜盤一律只做多

    position: Optional[str] = None
    avg_entry: Optional[float] = None
    entry_ts: Optional[datetime] = None
    lots = 0
    peak_pnl = 0.0
    be_armed = False
    last_stop_idx = -10 ** 9
    db = pre.db

    def close(i: int, reason: str):
        nonlocal position, avg_entry, entry_ts, lots, peak_pnl, be_armed
        price = pre.prices[i]
        ppl = (price - avg_entry) if position == "LONG" else (avg_entry - price)
        trades.append(Trade(
            entry_ts=entry_ts, entry_price=avg_entry, direction=position, lots=lots,
            exit_ts=pre.ts[i], exit_price=price, exit_reason=reason, pnl=ppl * lots,
        ))
        position = None
        avg_entry = None
        lots = 0
        peak_pnl = 0.0
        be_armed = False

    for i in range(15, n):
        price = pre.prices[i]

        if position is not None and avg_entry is not None:
            ppl = (price - avg_entry) if position == "LONG" else (avg_entry - price)
            peak_pnl = max(peak_pnl, ppl)

            if ppl <= -stop:
                close(i, "停損")
                last_stop_idx = i
                continue
            if p.take_profit > 0 and ppl >= p.take_profit:
                close(i, "獲利")
                continue
            if p.breakeven_trigger > 0:
                if ppl >= p.breakeven_trigger:
                    be_armed = True
                if be_armed and ppl <= p.breakeven_buffer:
                    close(i, "保本")
                    continue
            if p.trail_activate > 0 and peak_pnl >= p.trail_activate and (peak_pnl - ppl) >= p.trail_distance:
                close(i, "移動停利")
                continue
            if p.kd_gate >= 0 and ppl >= p.kd_gate:
                if position == "LONG" and pre.dc1m[i]:
                    close(i, "1mKD死叉")
                    continue
                if position == "SHORT" and pre.gc1m[i]:
                    close(i, "1mKD黃叉")
                    continue

        # ---- 進場 ----
        s5 = pre.s5m[i]
        want_long = (db >= 0 and s5 == 1 and pre.long_trig[i])
        want_short = (db <= 0 and s5 == -1 and pre.short_trig[i] and allow_short)

        if p.adx_min > 0 and pre.adx5m[i] < p.adx_min:
            want_long = want_short = False
        if i - last_stop_idx < p.cooldown_bars:
            want_long = want_short = False

        # 方向反轉先平倉
        if position == "LONG" and want_short:
            close(i, "多空反轉")
        elif position == "SHORT" and want_long:
            close(i, "多空反轉")

        if want_long and (position is None or position == "LONG") and lots < max_lots:
            if position is None:
                position, avg_entry, entry_ts, lots, peak_pnl, be_armed = "LONG", price, pre.ts[i], 1, 0.0, False
            else:
                avg_entry = (avg_entry * lots + price) / (lots + 1)
                lots += 1
        elif want_short and (position is None or position == "SHORT") and lots < max_lots:
            if position is None:
                position, avg_entry, entry_ts, lots, peak_pnl, be_armed = "SHORT", price, pre.ts[i], 1, 0.0, False
            else:
                avg_entry = (avg_entry * lots + price) / (lots + 1)
                lots += 1

    # 收盤強平
    if position is not None and avg_entry is not None:
        last = pre.prices[-1]
        ppl = (last - avg_entry) if position == "LONG" else (avg_entry - last)
        trades.append(Trade(
            entry_ts=entry_ts, entry_price=avg_entry, direction=position, lots=lots,
            exit_ts=pre.ts[-1], exit_price=last, exit_reason="收盤強平", pnl=ppl * lots,
        ))
    return trades


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

@dataclass
class Metrics:
    trades: int
    win_rate: float
    avg_win: float
    avg_loss: float
    profit_factor: float
    total_pnl: float
    max_drawdown: float
    sharpe: float
    net_ntd: int

    def as_row(self, label: str) -> dict:
        return {
            "策略": label,
            "交易": self.trades,
            "勝率%": f"{self.win_rate:.1f}",
            "均盈": f"{self.avg_win:.1f}",
            "均虧": f"{self.avg_loss:.1f}",
            "PF": f"{self.profit_factor:.2f}",
            "總pts": f"{self.total_pnl:.0f}",
            "maxDD": f"{self.max_drawdown:.0f}",
            "Sharpe": f"{self.sharpe:.2f}",
            "淨NTD": f"{self.net_ntd:,}",
        }


def compute_metrics(trades: List[Trade]) -> Metrics:
    total = len(trades)
    if total == 0:
        return Metrics(0, 0, 0, 0, 0, 0, 0, 0, 0)
    pnls = [t.pnl for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    win_rate = len(wins) / total * 100
    avg_win = sum(wins) / len(wins) if wins else 0.0
    avg_loss = sum(losses) / len(losses) if losses else 0.0
    gp = sum(wins)
    gl = abs(sum(losses))
    pf = gp / gl if gl > 0 else float("inf")
    total_pnl = sum(pnls)
    # max drawdown on cumulative equity (按出場時間排序)
    ordered = sorted(trades, key=lambda t: t.exit_ts or t.entry_ts)
    eq = 0.0
    peak = 0.0
    maxdd = 0.0
    for t in ordered:
        eq += t.pnl
        peak = max(peak, eq)
        maxdd = max(maxdd, peak - eq)
    arr = np.array(pnls, dtype=float)
    sharpe = float(arr.mean() / arr.std()) if arr.std() > 0 else 0.0
    lots = sum(t.lots for t in trades)
    net_ntd = int(total_pnl * POINT_VALUE - lots * FEE_PER_LOT)
    return Metrics(total, win_rate, avg_win, avg_loss, pf, total_pnl, maxdd, sharpe, net_ntd)


def score(m: Metrics, metric: str, min_trades: int) -> float:
    if m.trades < min_trades:
        return -1e9
    if metric == "sharpe":
        return m.sharpe
    if metric == "pnl":
        return m.total_pnl
    if metric == "winrate":
        return m.win_rate
    # default: profit factor (cap inf)
    return min(m.profit_factor, 99.0)


# ---------------------------------------------------------------------------
# Grid
# ---------------------------------------------------------------------------

def build_grid() -> List[Params]:
    day_stops = [30, 50]
    night_stops = [60, 90]
    cooldowns = [0, 10]
    adx_mins = [0, 22]
    long_only_days = [False, True]
    exits = [
        dict(kd_gate=8, take_profit=150, breakeven_trigger=0, trail_activate=0, trail_distance=0),
        dict(kd_gate=25, take_profit=200, breakeven_trigger=0, trail_activate=0, trail_distance=0),
        dict(kd_gate=-1, take_profit=200, breakeven_trigger=20, trail_activate=25, trail_distance=18),
        dict(kd_gate=-1, take_profit=0, breakeven_trigger=30, trail_activate=40, trail_distance=25),
    ]
    grid: List[Params] = []
    for ds, ns, cd, adx, lo, ex in itertools.product(
        day_stops, night_stops, cooldowns, adx_mins, long_only_days, exits
    ):
        grid.append(Params(
            day_stop=ds, night_stop=ns, take_profit=ex["take_profit"],
            kd_gate=ex["kd_gate"], breakeven_trigger=ex["breakeven_trigger"],
            breakeven_buffer=0, trail_activate=ex["trail_activate"],
            trail_distance=ex["trail_distance"], cooldown_bars=cd, adx_min=adx,
            long_only_day=lo,
        ))
    return grid


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run(data_dir: Path, metric: str, min_trades: int, session_filter: str = "all") -> None:
    print(f"載入 tick 資料 {data_dir} ...")
    session_ticks = load_mtx_ticks(data_dir)
    daily_all = build_daily_bars(session_ticks)
    print(f"  → {len(session_ticks)} sessions, {len(daily_all)} 日K bars")

    # precompute 每個 session
    pres: List[SessionPre] = []
    for sk in sorted(session_ticks.keys()):
        if session_filter == "day" and "_night" in sk:
            continue
        if session_filter == "night" and "_day" in sk:
            continue
        ticks = session_ticks[sk]
        if len(ticks) < 30:
            continue
        sk_date = datetime.strptime(sk[:10], "%Y-%m-%d").date()
        daily_before = [b for b in daily_all if b.ts.date() < sk_date]
        pre = precompute_session(sk, ticks, daily_before)
        if pre is not None:
            pres.append(pre)
    print(f"  → {len(pres)} sessions 預運算完成 (talib={_TALIB})")

    grid = build_grid()
    print(f"  → 掃描 {len(grid)} 組參數")

    # 每 (session, combo) 跑一次，存 trades
    by_combo_session: Dict[int, Dict[str, List[Trade]]] = defaultdict(dict)
    for ci, p in enumerate(grid):
        for pre in pres:
            by_combo_session[ci][pre.sk] = simulate(pre, p)

    dates = sorted({pre.sdate for pre in pres})
    sk_by_date: Dict[date, List[str]] = defaultdict(list)
    for pre in pres:
        sk_by_date[pre.sdate].append(pre.sk)

    # ---- Baseline (現行生產參數，日K濾網 active) ----
    base = production_params()
    base_trades: List[Trade] = []
    for pre in pres:
        base_trades.extend(simulate(pre, base))
    base_m = compute_metrics(base_trades)

    # ---- 生產實況模擬：日K濾網 DEAD (db=0)，重現線上虧損 ----
    base_trades_db0: List[Trade] = []
    for pre in pres:
        saved = pre.db
        pre.db = 0
        base_trades_db0.extend(simulate(pre, base))
        pre.db = saved
    base_m_db0 = compute_metrics(base_trades_db0)

    # ---- 全樣本最佳 (in-sample，會過擬合) ----
    is_best_ci, is_best_score = None, -1e18
    combo_metrics: Dict[int, Metrics] = {}
    for ci in range(len(grid)):
        allt: List[Trade] = []
        for sk_map in by_combo_session[ci].values():
            allt.extend(sk_map)
        m = compute_metrics(allt)
        combo_metrics[ci] = m
        s = score(m, metric, min_trades)
        if s > is_best_score:
            is_best_score, is_best_ci = s, ci

    # ---- Walk-forward leave-one-day-out ----
    oos_trades: List[Trade] = []
    chosen_counter: Dict[int, int] = defaultdict(int)
    for h in dates:
        # in-sample = 其他所有日期
        best_ci, best_s = None, -1e18
        for ci in range(len(grid)):
            ist: List[Trade] = []
            for d2 in dates:
                if d2 == h:
                    continue
                for sk in sk_by_date[d2]:
                    ist.extend(by_combo_session[ci].get(sk, []))
            s = score(compute_metrics(ist), metric, min_trades)
            if s > best_s:
                best_s, best_ci = s, ci
        chosen_counter[best_ci] += 1
        for sk in sk_by_date[h]:
            oos_trades.extend(by_combo_session[best_ci].get(sk, []))
    oos_m = compute_metrics(oos_trades)

    # ---- 報告 ----
    import pandas as pd
    print("\n=== Baseline vs In-sample best vs Walk-forward OOS ===")
    rows = [
        base_m_db0.as_row("生產實況 (日K濾網DEAD db=0)"),
        base_m.as_row(f"Baseline 濾網active [{base.label()}]"),
        combo_metrics[is_best_ci].as_row(f"IS-best [{grid[is_best_ci].label()}]"),
        oos_m.as_row(f"Walk-forward OOS (metric={metric})"),
    ]
    print(pd.DataFrame(rows).to_string(index=False))

    print(f"\nWalk-forward 各 fold 選中的參數 (共 {len(dates)} folds):")
    for ci, cnt in sorted(chosen_counter.items(), key=lambda x: -x[1]):
        print(f"  {cnt:>2}× [{grid[ci].label()}]")

    print(f"\nTop 8 全樣本參數 (by {metric}, 僅供參考，會過擬合):")
    ranked = sorted(combo_metrics.items(), key=lambda kv: score(kv[1], metric, min_trades), reverse=True)[:8]
    rows2 = [combo_metrics[ci].as_row(grid[ci].label()) for ci, _ in ranked]
    print(pd.DataFrame(rows2).to_string(index=False))

    # baseline 出場原因
    reasons = defaultdict(int)
    for t in base_trades:
        reasons[t.exit_reason] += 1
    print("\nBaseline 出場原因分布:")
    for r, c in sorted(reasons.items(), key=lambda x: -x[1]):
        print(f"  {r}: {c}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="MTX 參數最佳化 + walk-forward OOS")
    ap.add_argument("--data-dir", default=str(Path(__file__).parent.parent / "data" / "taifex_tick"))
    ap.add_argument("--metric", default="pf", choices=["pf", "sharpe", "pnl", "winrate"],
                    help="選參指標 (預設 pf)")
    ap.add_argument("--min-trades", type=int, default=15, help="參數組合最少交易數門檻")
    ap.add_argument("--session", default="all", choices=["all", "day", "night"])
    args = ap.parse_args()
    run(Path(args.data_dir), args.metric, args.min_trades, args.session)
