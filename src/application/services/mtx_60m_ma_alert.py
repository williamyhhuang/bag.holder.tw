"""微台分 K（60K / 5K）均線多空排列 Telegram 警示。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
import json
from pathlib import Path
from typing import Iterable, Mapping, Optional
from zoneinfo import ZoneInfo

import numpy as np


_TW = ZoneInfo("Asia/Taipei")


@dataclass(frozen=True)
class MAAlertResult:
    """最近一根已完成分 K 的均線判斷結果。"""

    bar_time: datetime
    close: float
    ma5: float
    ma10: float
    ma20: float
    ma5_slope: float
    ma10_slope: float
    ma20_slope: float
    signal: Optional[str]
    matched: bool


def _parse_contract_date(value: object) -> Optional[date]:
    """解析富邦 tickers API 回傳的合約日期。"""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or not value:
        return None

    text = value.strip()
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        try:
            return datetime.strptime(text[:8], "%Y%m%d").date()
        except ValueError:
            return None


def select_near_month_symbol(
    tickers: Iterable[Mapping[str, object]],
    *,
    product: str = "TMF",
    as_of: Optional[date] = None,
) -> Optional[str]:
    """從有效合約清單選出最近到期的指定期貨商品。"""
    current_date = as_of or datetime.now(_TW).date()
    candidates: list[tuple[date, str]] = []
    for ticker in tickers:
        symbol = str(ticker.get("symbol") or "").upper()
        if not symbol.startswith(product.upper()):
            continue
        expiry = _parse_contract_date(
            ticker.get("end_date") or ticker.get("settlement_date")
        )
        if expiry is None or expiry < current_date:
            continue
        candidates.append((expiry, symbol))

    if not candidates:
        return None
    return min(candidates)[1]


def _parse_time(value: object) -> Optional[datetime]:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            try:
                parsed = datetime.fromisoformat(value[:19])
            except ValueError:
                return None
    else:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=_TW)
    return parsed.astimezone(_TW)


def completed_candles(
    candles: Iterable[Mapping[str, object]],
    *,
    now: Optional[datetime] = None,
    session: str,
    interval_minutes: int = 60,
) -> list[tuple[datetime, float]]:
    """整理並排除尚未收完的最新分 K。

    富邦 intraday API 的時間是 K 棒起始時間。60K 日盤最後一根會在 13:30
    提早收完，因此另以日盤收盤時間判斷；5K 每根長度固定，不需特例。
    """
    current = now or datetime.now(_TW)
    if current.tzinfo is None:
        current = current.replace(tzinfo=_TW)
    else:
        current = current.astimezone(_TW)

    by_time: dict[datetime, float] = {}
    for candle in candles:
        bar_time = _parse_time(candle.get("time") or candle.get("ts"))
        try:
            close = float(candle.get("close", 0) or 0)
        except (TypeError, ValueError):
            continue
        if bar_time is None or close <= 0 or bar_time > current:
            continue

        closed = bar_time + timedelta(minutes=interval_minutes) <= current
        if (
            not closed
            and interval_minutes == 60
            and session == "day"
            and bar_time.date() == current.date()
            and current.time() >= time(13, 30)
        ):
            closed = True
        if closed:
            by_time[bar_time] = close

    return sorted(by_time.items())


def evaluate_ma_alert(candles: Iterable[tuple[datetime, float]]) -> Optional[MAAlertResult]:
    """判斷分 K（60K / 5K）多排或其鏡像空排條件。

    多排：三條均線斜率皆正，且 MA5 >= MA10 >= MA20。
    空排：三條均線斜率皆負，且 MA5 <= MA10 <= MA20。

    斜率定義為「本根 K 的 MA 減去前一根 K 的 MA」，因此至少需要
    21 根已完成 K 棒才能判斷 MA20 斜率。
    """
    rows = list(candles)
    if len(rows) < 21:
        return None

    closes = np.asarray([close for _, close in rows], dtype=float)

    def latest_and_slope(period: int) -> tuple[float, float]:
        current_ma = float(closes[-period:].mean())
        previous_ma = float(closes[-period - 1 : -1].mean())
        return current_ma, current_ma - previous_ma

    ma5, slope5 = latest_and_slope(5)
    ma10, slope10 = latest_and_slope(10)
    ma20, slope20 = latest_and_slope(20)
    long_matched = slope5 > 0 and slope10 > 0 and slope20 > 0 and ma5 >= ma10 >= ma20
    short_matched = slope5 < 0 and slope10 < 0 and slope20 < 0 and ma5 <= ma10 <= ma20
    signal = "long" if long_matched else "short" if short_matched else None
    return MAAlertResult(
        bar_time=rows[-1][0],
        close=float(closes[-1]),
        ma5=ma5,
        ma10=ma10,
        ma20=ma20,
        ma5_slope=slope5,
        ma10_slope=slope10,
        ma20_slope=slope20,
        signal=signal,
        matched=signal is not None,
    )


@dataclass(frozen=True)
class MA5CrossResult:
    """最近一根已完成 K 棒收盤價相對 MA5 的穿越結果。"""

    bar_time: datetime
    close: float
    ma5: float
    direction: str  # "up" 站上 / "down" 跌破


def detect_ma5_cross(candles: Iterable[tuple[datetime, float]]) -> Optional[MA5CrossResult]:
    """K 棒收盤站上或跌破 MA5。

    站上：上一根收盤 <= 上一根 MA5，且本根收盤 > 本根 MA5。
    跌破：上一根收盤 >= 上一根 MA5，且本根收盤 < 本根 MA5。
    至少需要 6 根已完成 K 棒；未穿越回傳 None。
    """
    rows = list(candles)
    if len(rows) < 6:
        return None
    closes = np.asarray([close for _, close in rows], dtype=float)
    ma5 = float(closes[-5:].mean())
    prev_ma5 = float(closes[-6:-1].mean())
    close, prev_close = float(closes[-1]), float(closes[-2])

    if prev_close <= prev_ma5 and close > ma5:
        direction = "up"
    elif prev_close >= prev_ma5 and close < ma5:
        direction = "down"
    else:
        return None
    return MA5CrossResult(bar_time=rows[-1][0], close=close, ma5=ma5, direction=direction)


def held_positions(
    positions: Iterable[Mapping[str, object]],
    keywords: Iterable[str],
) -> list[Mapping[str, object]]:
    """篩出商品代號含任一關鍵字（如 TMF）且仍有口數的期貨部位。"""
    keys = [k.upper() for k in keywords if k]
    held = []
    for pos in positions:
        symbol = str(pos.get("symbol") or "").upper()
        lots = int(pos.get("tradable_lot") or 0) or int(pos.get("orig_lots") or 0)
        if lots > 0 and any(k in symbol for k in keys):
            held.append(pos)
    return held


def _position_side(pos: Mapping[str, object]) -> str:
    text = str(pos.get("buy_sell") or "").lower()
    if "buy" in text or text == "b":
        return "多單"
    if "sell" in text or text == "s":
        return "空單"
    return "部位"


def format_ma5_cross_alert(
    symbol: str,
    session: str,
    result: MA5CrossResult,
    positions: Iterable[Mapping[str, object]],
    interval_minutes: int = 5,
) -> str:
    session_label = "日盤" if session == "day" else "夜盤"
    is_up = result.direction == "up"
    icon = "🔼" if is_up else "🔽"
    action = "站上" if is_up else "跌破"
    holdings = "、".join(
        f"{pos.get('symbol')} {pos.get('expiry_date')} {_position_side(pos)} "
        f"{int(pos.get('tradable_lot') or 0) or int(pos.get('orig_lots') or 0)} 口 @ {float(pos.get('price') or 0):.0f}"
        for pos in positions
    )
    return (
        f"{icon} 微台 {interval_minutes}K {action} MA5（持倉通知）\n"
        f"商品：{symbol}｜{session_label}\n"
        f"K棒：{result.bar_time.strftime('%Y-%m-%d %H:%M')}｜收盤：{result.close:.0f}\n"
        f"MA5：{result.ma5:.2f}\n"
        f"持倉：{holdings}"
    )


def load_candle_state(path: Path) -> list[dict[str, object]]:
    """讀取跨排程保存的 60K 收盤資料；不存在或損壞時安全地從空狀態開始。"""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return []
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


def save_candle_state(
    path: Path,
    candles: Iterable[tuple[datetime, float]],
    *,
    keep: int = 200,
) -> None:
    """以原子替換寫入最近的已完成 60K，供下次 VM timer 延續計算。"""
    rows = list(candles)[-keep:]
    payload = [{"time": ts.isoformat(), "close": close} for ts, close in rows]
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def was_alert_sent(path: Path, bar_time: datetime) -> bool:
    """檢查同一根 60K 是否已成功通知，避免 timer catch-up 造成重複訊息。"""
    try:
        return path.read_text(encoding="utf-8").strip() == bar_time.isoformat()
    except OSError:
        return False


def mark_alert_sent(path: Path, bar_time: datetime) -> None:
    """原子記錄最後一根已成功通知的 K 棒。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(bar_time.isoformat(), encoding="utf-8")
    temporary.replace(path)


def load_last_signal(path: Path) -> Optional[str]:
    """讀取上次記錄的訊號（long / short / none）；不存在時回傳 None。"""
    try:
        value = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return value or None


def save_last_signal(path: Path, signal: Optional[str]) -> None:
    """原子記錄最新一根 K 棒的訊號，供「排列轉變才通知」模式比較。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(signal or "none", encoding="utf-8")
    temporary.replace(path)


def signal_changed(previous: Optional[str], current: Optional[str]) -> bool:
    """排列轉變才通知：本根成立多排／空排，且與上一根記錄的訊號不同。"""
    return current is not None and current != (previous or "none")


def format_alert(
    symbol: str,
    session: str,
    result: MAAlertResult,
    interval_minutes: int = 60,
) -> str:
    session_label = "日盤" if session == "day" else "夜盤"
    is_long = result.signal == "long"
    signal_label = "多排" if is_long else "空排"
    icon = "📈" if is_long else "📉"
    order = "MA5 ≥ MA10 ≥ MA20" if is_long else "MA5 ≤ MA10 ≤ MA20"
    condition = f"{order}，且三條均線斜率皆為{'正' if is_long else '負'}"
    return (
        f"{icon} 微台 {interval_minutes}K {signal_label}通知\n"
        f"商品：{symbol}｜{session_label}\n"
        f"K棒：{result.bar_time.strftime('%Y-%m-%d %H:%M')}｜收盤：{result.close:.0f}\n"
        f"MA5：{result.ma5:.2f}（斜率 {result.ma5_slope:+.2f}）\n"
        f"MA10：{result.ma10:.2f}（斜率 {result.ma10_slope:+.2f}）\n"
        f"MA20：{result.ma20:.2f}（斜率 {result.ma20_slope:+.2f}）\n"
        f"條件：{condition}"
    )
