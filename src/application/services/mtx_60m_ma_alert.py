"""60 分 K 均線條件 Telegram 警示。"""
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
    """最近一根已完成 60 分 K 的均線判斷結果。"""

    bar_time: datetime
    close: float
    ma5: float
    ma10: float
    ma20: float
    ma5_slope: float
    ma10_slope: float
    ma20_slope: float
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
) -> list[tuple[datetime, float]]:
    """整理並排除尚未收完的最新 60 分 K。

    富邦 intraday API 的時間是 K 棒起始時間。日盤最後一根會在 13:30
    提早收完，因此另以日盤收盤時間判斷。
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

        closed = bar_time + timedelta(minutes=60) <= current
        if (
            not closed
            and session == "day"
            and bar_time.date() == current.date()
            and current.time() >= time(13, 30)
        ):
            closed = True
        if closed:
            by_time[bar_time] = close

    return sorted(by_time.items())


def evaluate_ma_alert(candles: Iterable[tuple[datetime, float]]) -> Optional[MAAlertResult]:
    """判斷 MA5/10/20 斜率皆正且 MA5 >= MA10 或 MA5 >= MA20。

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
    matched = (
        slope5 > 0
        and slope10 > 0
        and slope20 > 0
        and (ma5 >= ma10 or ma5 >= ma20)
    )
    return MAAlertResult(
        bar_time=rows[-1][0],
        close=float(closes[-1]),
        ma5=ma5,
        ma10=ma10,
        ma20=ma20,
        ma5_slope=slope5,
        ma10_slope=slope10,
        ma20_slope=slope20,
        matched=matched,
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


def format_alert(symbol: str, session: str, result: MAAlertResult) -> str:
    session_label = "日盤" if session == "day" else "夜盤"
    return (
        f"📈 微台 60K 均線條件通知\n"
        f"商品：{symbol}｜{session_label}\n"
        f"K棒：{result.bar_time.strftime('%Y-%m-%d %H:%M')}｜收盤：{result.close:.0f}\n"
        f"MA5：{result.ma5:.2f}（斜率 {result.ma5_slope:+.2f}）\n"
        f"MA10：{result.ma10:.2f}（斜率 {result.ma10_slope:+.2f}）\n"
        f"MA20：{result.ma20:.2f}（斜率 {result.ma20_slope:+.2f}）\n"
        "條件：MA5 ≥ MA10 或 MA5 ≥ MA20，且三條均線斜率皆為正"
    )
