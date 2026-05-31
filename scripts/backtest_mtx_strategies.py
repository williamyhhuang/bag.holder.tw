"""
MTX 策略回測比較腳本
從 TAIFEX 每筆成交 CSV 重建分鐘 K 棒，測試 4 種策略變體的勝率

策略變體:
  A (現況)  : 5m 剛好 KD 黃金交叉 + 日線方向 + 1m 剛好 KD 黃金交叉
  B (放寬5m): 5m K>D 持續區間 (非僅交叉瞬間)
  C (信號記憶): 5m 黃金交叉後保持 3 根 5mK 有效
  D (無5m)  : 僅日線方向 + 1m 訊號

用法:
  python scripts/backtest_mtx_strategies.py
  python scripts/backtest_mtx_strategies.py --data-dir data/taifex_tick --session all
"""
from __future__ import annotations

import argparse
import math
import zipfile
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, time, date, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DATA_DIR = Path(__file__).parent.parent / "data" / "taifex_tick"
MTX_PRODUCT = "MTX"

# 停損/獲利 (points)
STOP_LOSS_PTS = 50
TAKE_PROFIT_PTS = 150
MIN_PROFIT_KD_EXIT = 8

# 盤別時間 (TWN local time)
DAY_SESSION_START = time(8, 45)
DAY_SESSION_END = time(13, 45)
NIGHT_SESSION_START = time(15, 0)
# 夜盤跨日，結束時間用 < 05:00 隔天判斷


# ---------------------------------------------------------------------------
# Bar reconstruction
# ---------------------------------------------------------------------------

@dataclass
class Bar:
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int

    def update(self, price: float, vol: int):
        self.high = max(self.high, price)
        self.low = min(self.low, price)
        self.close = price
        self.volume += vol


def floor_to_tf(ts: datetime, minutes: int) -> datetime:
    total = ts.hour * 60 + ts.minute
    floored = (total // minutes) * minutes
    return ts.replace(hour=floored // 60, minute=floored % 60, second=0, microsecond=0)


def build_bars(ticks: List[Tuple[datetime, float, int]], tf_minutes: int) -> List[Bar]:
    """從 tick list 建立固定時間框架的 OHLCV bar list"""
    bars: List[Bar] = []
    current: Optional[Bar] = None

    for ts, price, vol in ticks:
        bar_ts = floor_to_tf(ts, tf_minutes)
        if current is None:
            current = Bar(bar_ts, price, price, price, price, vol)
        elif bar_ts > current.ts:
            bars.append(current)
            current = Bar(bar_ts, price, price, price, price, vol)
        else:
            current.update(price, vol)

    if current is not None:
        bars.append(current)
    return bars


# ---------------------------------------------------------------------------
# Indicators
# ---------------------------------------------------------------------------

def compute_stoch(bars: List[Bar], fastk=9, slowk=3, slowd=3) -> Tuple[List[float], List[float]]:
    n = len(bars)
    if n < fastk + slowk + slowd:
        return [float('nan')] * n, [float('nan')] * n

    raw_k = [float('nan')] * n
    for i in range(fastk - 1, n):
        h = max(b.high for b in bars[i - fastk + 1: i + 1])
        lo = min(b.low for b in bars[i - fastk + 1: i + 1])
        if h != lo:
            raw_k[i] = (bars[i].close - lo) / (h - lo) * 100
        else:
            raw_k[i] = 50.0

    k = [float('nan')] * n
    for i in range(fastk - 1 + slowk - 1, n):
        w = raw_k[i - slowk + 1: i + 1]
        if not any(math.isnan(x) for x in w):
            k[i] = sum(w) / len(w)

    d = [float('nan')] * n
    for i in range(fastk - 1 + slowk - 1 + slowd - 1, n):
        w = k[i - slowd + 1: i + 1]
        if not any(math.isnan(x) for x in w):
            d[i] = sum(w) / len(w)

    return k, d


def compute_ma(closes: List[float], period: int) -> List[float]:
    n = len(closes)
    ma = [float('nan')] * n
    for i in range(period - 1, n):
        ma[i] = sum(closes[i - period + 1: i + 1]) / period
    return ma


def golden_cross(k: List[float], d: List[float]) -> bool:
    if len(k) < 2:
        return False
    if any(math.isnan(x) for x in [k[-2], d[-2], k[-1], d[-1]]):
        return False
    return k[-2] < d[-2] and k[-1] >= d[-1]


def death_cross(k: List[float], d: List[float]) -> bool:
    if len(k) < 2:
        return False
    if any(math.isnan(x) for x in [k[-2], d[-2], k[-1], d[-1]]):
        return False
    return k[-2] > d[-2] and k[-1] <= d[-1]


# ---------------------------------------------------------------------------
# Session identification
# ---------------------------------------------------------------------------

def is_night_session(ts: datetime) -> bool:
    t = ts.time()
    return t >= NIGHT_SESSION_START or t < time(5, 0)


def is_day_session(ts: datetime) -> bool:
    return DAY_SESSION_START <= ts.time() <= DAY_SESSION_END


def session_key(ts: datetime) -> str:
    """每個交易 session 的唯一 key (夜盤跨日，以開始當天為準)"""
    t = ts.time()
    if t < time(5, 0):
        # 夜盤隔天早上，歸屬前一天
        d = ts.date() - timedelta(days=1)
    else:
        d = ts.date()
    if t >= NIGHT_SESSION_START or t < time(5, 0):
        return f"{d}_night"
    return f"{d}_day"


# ---------------------------------------------------------------------------
# Strategy variants
# ---------------------------------------------------------------------------

def daily_bias(daily_bars: List[Bar]) -> int:
    """+1 bullish / -1 bearish / 0 neutral"""
    if len(daily_bars) < 12:
        return 0
    closes = [b.close for b in daily_bars]
    highs = [b.high for b in daily_bars]
    lows = [b.low for b in daily_bars]
    ma5 = compute_ma(closes, 5)
    ma10 = compute_ma(closes, 10)
    k, d = compute_stoch(daily_bars)
    if any(math.isnan(x) for x in [ma5[-1], ma10[-1], k[-1], d[-1]]):
        return 0
    kv = k[-1]
    if kv > 80:
        return -1
    if kv < 20:
        return 1
    if closes[-1] > ma5[-1] > ma10[-1] and k[-1] > d[-1]:
        return 1
    if closes[-1] < ma5[-1] < ma10[-1] and k[-1] < d[-1]:
        return -1
    return 0


def signal_5m_A(bars_5m: List[Bar]) -> int:
    """策略A/C: 剛好 KD 黃金/死亡交叉"""
    if len(bars_5m) < 15:
        return 0
    k, d = compute_stoch(bars_5m)
    ma5 = compute_ma([b.close for b in bars_5m], 5)
    ma10 = compute_ma([b.close for b in bars_5m], 10)
    if any(math.isnan(x) for x in [k[-1], d[-1]]):
        return 0

    score = 0
    if golden_cross(k, d) and k[-1] < 60:
        score += 1
    elif death_cross(k, d) and k[-1] > 40:
        score -= 1

    if not any(math.isnan(x) for x in [ma5[-1], ma10[-1], ma5[-2], ma10[-2]]):
        if ma5[-2] < ma10[-2] and ma5[-1] >= ma10[-1]:
            score += 1
        elif ma5[-2] > ma10[-2] and ma5[-1] <= ma10[-1]:
            score -= 1

    return max(-1, min(1, score))


def signal_5m_B(bars_5m: List[Bar]) -> int:
    """策略B: K>D 持續區間 (不需剛好交叉)"""
    if len(bars_5m) < 15:
        return 0
    k, d = compute_stoch(bars_5m)
    if any(math.isnan(x) for x in [k[-1], d[-1]]):
        return 0

    if k[-1] > d[-1] and k[-1] < 70:
        return 1
    if k[-1] < d[-1] and k[-1] > 30:
        return -1
    return 0


def entry_1m(bars_1m: List[Bar]) -> int:
    """1m 進場觸發 +1/−1/0"""
    if len(bars_1m) < 15:
        return 0
    k, d = compute_stoch(bars_1m)
    closes = [b.close for b in bars_1m]
    ma5 = compute_ma(closes, 5)
    if any(math.isnan(x) for x in [k[-1], d[-1], ma5[-1]]):
        return 0
    if golden_cross(k, d) and closes[-1] > ma5[-1]:
        return 1
    if death_cross(k, d) and closes[-1] < ma5[-1]:
        return -1
    return 0


# ---------------------------------------------------------------------------
# Single-session simulation
# ---------------------------------------------------------------------------

@dataclass
class Trade:
    entry_ts: datetime
    entry_price: float      # 平均進場價
    direction: str          # LONG / SHORT
    lots: int = 1           # 出場時持倉口數
    exit_ts: Optional[datetime] = None
    exit_price: Optional[float] = None
    exit_reason: str = ""
    pnl: float = 0.0        # 總損益 pts（已乘口數）

    @property
    def won(self) -> bool:
        return self.pnl > 0


def simulate_session(
    ticks_1m: List[Bar],
    ticks_5m: List[Bar],
    daily_bars_before: List[Bar],  # 截至本 session 前的日 K
    variant: str,
    stop_loss: float = STOP_LOSS_PTS,
    take_profit: float = TAKE_PROFIT_PTS,
    min_profit_kd: float = MIN_PROFIT_KD_EXIT,
    signal_memory: int = 3,   # 策略C: 5m 訊號保持 N 根有效
    max_lots: int = 3,        # 最大持倉口數（加碼上限）
) -> List[Trade]:
    """在單一 session 的分鐘 K 棒序列上模擬交易（支援加碼至 max_lots 口）"""
    trades: List[Trade] = []
    position: Optional[str] = None
    avg_entry: Optional[float] = None   # 加權平均進場價
    entry_ts: Optional[datetime] = None
    lots: int = 0                        # 當前持倉口數

    # 策略C: 記憶 5m 訊號
    last_5m_signal: int = 0
    last_5m_signal_age: int = 0

    db = daily_bias(daily_bars_before)

    for i in range(15, len(ticks_1m)):
        bars_1m_now = ticks_1m[:i + 1]
        current_bar = bars_1m_now[-1]
        price = current_bar.close
        ts = current_bar.ts

        # 找對應 5m 截至此刻的 bars
        bars_5m_now = [b for b in ticks_5m if b.ts <= ts]

        # --- 出場邏輯 ---
        if position is not None and avg_entry is not None:
            pnl_per_lot = (price - avg_entry) if position == "LONG" else (avg_entry - price)
            pnl_total = pnl_per_lot * lots

            def _close(reason: str) -> None:
                nonlocal position, avg_entry, entry_ts, lots
                trades.append(Trade(
                    entry_ts=entry_ts, entry_price=avg_entry,
                    direction=position, lots=lots,
                    exit_ts=ts, exit_price=price,
                    exit_reason=reason, pnl=pnl_total,
                ))
                position = None
                avg_entry = None
                lots = 0

            # 停損（以每口計算）
            if pnl_per_lot <= -stop_loss:
                _close("停損")
                continue

            # 獲利了結（以每口計算）
            if pnl_per_lot >= take_profit:
                _close("獲利")
                continue

            # KD 反轉出場（需達最低獲利保護，以每口計算）
            if len(bars_1m_now) >= 15:
                k1m, d1m = compute_stoch(bars_1m_now)
                if pnl_per_lot >= min_profit_kd:
                    if position == "LONG" and death_cross(k1m, d1m):
                        _close("1mKD死叉")
                        continue
                    if position == "SHORT" and golden_cross(k1m, d1m):
                        _close("1mKD黃叉")
                        continue

        # --- 進場 / 加碼邏輯 ---
        s1m = entry_1m(bars_1m_now)

        if variant == "A":
            s5m = signal_5m_A(bars_5m_now)
        elif variant == "B":
            s5m = signal_5m_B(bars_5m_now)
        elif variant == "C":
            new_s5m = signal_5m_A(bars_5m_now)
            if new_s5m != 0:
                last_5m_signal = new_s5m
                last_5m_signal_age = 0
            else:
                last_5m_signal_age += 1
                if last_5m_signal_age > signal_memory:
                    last_5m_signal = 0
            s5m = last_5m_signal
        elif variant == "D":
            s5m = 1 if db >= 0 else -1

        want_long = (db >= 0 and s5m == 1 and s1m == 1)
        want_short = (db <= 0 and s5m == -1 and s1m == -1)

        # 方向反轉 → 先平倉
        if position == "LONG" and want_short:
            pnl_total = (price - avg_entry) * lots
            trades.append(Trade(
                entry_ts=entry_ts, entry_price=avg_entry,
                direction=position, lots=lots,
                exit_ts=ts, exit_price=price,
                exit_reason="多空反轉", pnl=pnl_total,
            ))
            position = None
            avg_entry = None
            lots = 0
        elif position == "SHORT" and want_long:
            pnl_total = (avg_entry - price) * lots
            trades.append(Trade(
                entry_ts=entry_ts, entry_price=avg_entry,
                direction=position, lots=lots,
                exit_ts=ts, exit_price=price,
                exit_reason="多空反轉", pnl=pnl_total,
            ))
            position = None
            avg_entry = None
            lots = 0

        # 新倉 / 加碼
        if want_long and (position is None or position == "LONG") and lots < max_lots:
            if position is None:
                position = "LONG"
                avg_entry = price
                entry_ts = ts
                lots = 1
            else:
                # 加碼：更新加權平均進場價
                avg_entry = (avg_entry * lots + price) / (lots + 1)
                lots += 1

        elif want_short and (position is None or position == "SHORT") and lots < max_lots:
            if position is None:
                position = "SHORT"
                avg_entry = price
                entry_ts = ts
                lots = 1
            else:
                avg_entry = (avg_entry * lots + price) / (lots + 1)
                lots += 1

    # session 結束強平
    if position is not None and avg_entry is not None and ticks_1m:
        last_price = ticks_1m[-1].close
        pnl_per_lot = (last_price - avg_entry) if position == "LONG" else (avg_entry - last_price)
        trades.append(Trade(
            entry_ts=entry_ts, entry_price=avg_entry,
            direction=position, lots=lots,
            exit_ts=ticks_1m[-1].ts, exit_price=last_price,
            exit_reason="收盤強平", pnl=pnl_per_lot * lots,
        ))

    return trades


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_mtx_ticks(data_dir: Path) -> Dict[str, List[Tuple[datetime, float, int]]]:
    """
    讀取所有 zip，解析 MTX 最近月 tick，
    回傳 {session_key: [(datetime, price, volume), ...]}
    """
    all_ticks: Dict[str, List] = defaultdict(list)

    for zpath in sorted(data_dir.glob("Daily_*.zip")):
        with zipfile.ZipFile(zpath) as zf:
            csv_name = [n for n in zf.namelist() if n.endswith(".csv")][0]
            with zf.open(csv_name) as f:
                raw = f.read()
            try:
                text = raw.decode("big5")
            except Exception:
                text = raw.decode("cp950", errors="replace")

        lines = text.splitlines()
        # 找最近月合約（月份數字最小者）
        near_month: Optional[str] = None

        # 先掃描找 MTX 最近月
        mtx_months: set = set()
        for line in lines[1:]:
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 5:
                continue
            if parts[1].strip() == MTX_PRODUCT:
                mtx_months.add(parts[2].strip())
        if not mtx_months:
            continue
        # 最近月 = 月份最小（以數字排序，排除週選 W）
        regular = sorted([m for m in mtx_months if "W" not in m])
        near_month = regular[0] if regular else sorted(mtx_months)[0]

        for line in lines[1:]:
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 5:
                continue
            if parts[1].strip() != MTX_PRODUCT:
                continue
            if parts[2].strip() != near_month:
                continue

            date_str = parts[0]   # YYYYMMDD
            time_str = parts[3]   # HHMMSS (6 digits)
            price_str = parts[4]
            vol_str = parts[5]

            try:
                dt = datetime.strptime(f"{date_str}{time_str.zfill(6)}", "%Y%m%d%H%M%S")
                price = float(price_str)
                vol = int(vol_str)
            except Exception:
                continue

            sk = session_key(dt)
            all_ticks[sk].append((dt, price, vol))

    # 每個 session 按時間排序
    for sk in all_ticks:
        all_ticks[sk].sort(key=lambda x: x[0])

    return dict(all_ticks)


def build_daily_bars(session_ticks: Dict[str, List]) -> List[Bar]:
    """從各 day session 的 tick 建立日 K bars"""
    daily: List[Bar] = []
    for sk in sorted(session_ticks.keys()):
        if "_day" not in sk:
            continue
        ticks = session_ticks[sk]
        if not ticks:
            continue
        o = ticks[0][1]
        h = max(t[1] for t in ticks)
        lo = min(t[1] for t in ticks)
        c = ticks[-1][1]
        v = sum(t[2] for t in ticks)
        dt = ticks[0][0].date()
        daily.append(Bar(datetime.combine(dt, time(0)), o, h, lo, c, v))
    return daily


# ---------------------------------------------------------------------------
# Main backtest runner
# ---------------------------------------------------------------------------

def run_backtest(
    data_dir: Path = DATA_DIR,
    session_filter: str = "all",  # "all" / "day" / "night"
    variants: List[str] = None,
) -> pd.DataFrame:
    if variants is None:
        variants = ["A", "B", "C", "D"]

    print(f"載入 TAIFEX tick 資料從 {data_dir} ...")
    session_ticks = load_mtx_ticks(data_dir)
    print(f"  → {len(session_ticks)} sessions 載入完成")

    daily_bars_all = build_daily_bars(session_ticks)
    print(f"  → {len(daily_bars_all)} 日 K bars")

    results: Dict[str, List[Trade]] = {v: [] for v in variants}

    sorted_sessions = sorted(session_ticks.keys())

    for sk in sorted_sessions:
        if session_filter == "day" and "_night" in sk:
            continue
        if session_filter == "night" and "_day" in sk:
            continue

        ticks = session_ticks[sk]
        if len(ticks) < 30:
            continue

        # 截至本 session 前的日 K
        sk_date = datetime.strptime(sk[:10], "%Y-%m-%d").date()
        daily_before = [b for b in daily_bars_all if b.ts.date() < sk_date]

        bars_1m = build_bars(ticks, 1)
        bars_5m = build_bars(ticks, 5)

        if len(bars_1m) < 20:
            continue

        for v in variants:
            trades = simulate_session(bars_1m, bars_5m, daily_before, variant=v)
            results[v].extend(trades)

    # 統計
    rows = []
    for v in variants:
        ts = results[v]
        total = len(ts)
        if total == 0:
            rows.append({
                "策略": v, "交易次數": 0, "勝率": "-",
                "平均獲利": "-", "平均虧損": "-",
                "獲利因子": "-", "總損益(pts)": 0,
            })
            continue

        wins = [t for t in ts if t.won]
        losses = [t for t in ts if not t.won]
        win_rate = len(wins) / total * 100
        avg_win = sum(t.pnl for t in wins) / len(wins) if wins else 0
        avg_loss = sum(t.pnl for t in losses) / len(losses) if losses else 0
        gross_profit = sum(t.pnl for t in wins)
        gross_loss = abs(sum(t.pnl for t in losses))
        pf = gross_profit / gross_loss if gross_loss > 0 else float("inf")
        total_pnl = sum(t.pnl for t in ts)
        total_lots_exited = sum(t.lots for t in ts)
        fee = total_lots_exited * 50          # 50元/口，出場時收
        net_ntd = int(total_pnl * 10 - fee)  # 微台每點10元

        rows.append({
            "策略": v,
            "說明": {"A": "嚴格(現況)", "B": "放寬5m區間", "C": "5m信號記憶", "D": "無5m確認"}[v],
            "交易次數": total,
            "勝率 %": f"{win_rate:.1f}",
            "平均獲利 pts": f"{avg_win:.1f}",
            "平均虧損 pts": f"{avg_loss:.1f}",
            "獲利因子": f"{pf:.2f}",
            "總損益 pts": f"{total_pnl:.0f}",
            "總損益 NTD": f"{int(total_pnl * 10):,}",
            "手續費 NTD": f"-{fee:,}",
            "淨損益 NTD": f"{net_ntd:,}",
        })

    df = pd.DataFrame(rows)

    # 出場原因統計
    print("\n=== 策略比較結果 ===")
    print(df.to_string(index=False))

    for v in variants:
        ts = results[v]
        if not ts:
            continue
        reasons = defaultdict(int)
        for t in ts:
            reasons[t.exit_reason] += 1
        print(f"\n[策略{v}] 出場原因分布:")
        for r, cnt in sorted(reasons.items(), key=lambda x: -x[1]):
            print(f"  {r}: {cnt}")

    return df


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MTX 策略回測比較")
    parser.add_argument("--data-dir", default=str(DATA_DIR), help="TAIFEX zip 資料目錄")
    parser.add_argument(
        "--session", default="all", choices=["all", "day", "night"],
        help="測試盤別 (all/day/night)"
    )
    parser.add_argument("--stop-loss", type=float, default=STOP_LOSS_PTS)
    parser.add_argument("--take-profit", type=float, default=TAKE_PROFIT_PTS)
    args = parser.parse_args()

    run_backtest(
        data_dir=Path(args.data_dir),
        session_filter=args.session,
    )
