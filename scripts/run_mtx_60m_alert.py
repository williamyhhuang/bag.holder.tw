#!/usr/bin/env python
"""取得微台分 K（60K / 5K），符合均線多空排列條件時發送 Telegram。"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import settings
from src.application.services.mtx_60m_ma_alert import (
    completed_candles,
    detect_ma5_cross,
    evaluate_ma_alert,
    format_alert,
    format_ma5_cross_alert,
    held_positions,
    load_candle_state,
    load_last_signal,
    mark_alert_sent,
    save_candle_state,
    save_last_signal,
    select_near_month_symbol,
    signal_changed,
    was_alert_sent,
)
from src.infrastructure.market_data.fubon_client import FubonClient, get_near_month_symbol
from src.infrastructure.notification.telegram_notifier import TelegramNotifier


logger = logging.getLogger(__name__)
_TW = ZoneInfo("Asia/Taipei")


def _build_client() -> FubonClient:
    fubon = settings.fubon
    return FubonClient(
        user_id=fubon.user_id,
        password=fubon.password,
        cert_path=fubon.cert_path,
        cert_password=fubon.cert_password or fubon.user_id,
        api_key=fubon.api_key,
        is_simulation=fubon.is_simulation,
    )


async def run(session: str, state_file: Path, interval: int = 60) -> int:
    now = datetime.now(_TW)
    api_session = "afterhours" if session == "night" else None
    ticker_session = "AFTERHOURS" if session == "night" else "REGULAR"

    async with _build_client() as client:
        tickers = await client.get_futures_tickers(
            product=None,
            session=ticker_session,
            contract_type="I",
        )
        symbol = select_near_month_symbol(
            tickers,
            product="TMF",
            as_of=now.date(),
        )
        if symbol:
            logger.info("富邦有效合約清單選出微台近月：%s", symbol)
        else:
            symbol = get_near_month_symbol("TMF", as_of=now.date())
            logger.warning("有效合約清單無可用資料，改用日期推算微台近月：%s", symbol)
        candles = await client.get_futures_candles(symbol, str(interval), api_session)

        positions = []
        check_position_cross = interval == 5 and settings.mtx_ma_alert.position_ma5_cross_enabled
        if check_position_cross:
            try:
                await client.ensure_futopt_account(settings.mtx_ma_alert.futopt_login_retries)
                raw_positions = await client.get_futures_positions()
                positions = held_positions(
                    raw_positions,
                    settings.mtx_ma_alert.position_symbol_keywords,
                )
                logger.info(
                    "期貨部位 %d 筆 %s，符合微台持倉 %d 筆",
                    len(raw_positions),
                    _summarize_positions(raw_positions),
                    len(positions),
                )
            except Exception as exc:  # 部位查詢失敗不影響均線排列通知
                logger.warning("查詢期貨部位失敗，略過持倉 MA5 通知：%s", exc)

    # 期貨 intraday API 只回傳當日資料；合併 VM 持久磁碟帶入的跨盤狀態，
    # 才有足夠的 21 根 K 棒可計算 MA20 斜率。
    state = load_candle_state(state_file)
    rows = completed_candles(
        [*state, *candles],
        now=now,
        session=session,
        interval_minutes=interval,
    )
    save_candle_state(state_file, rows)

    if positions:
        _notify_ma5_cross(symbol, session, interval, rows, positions, state_file)

    result = evaluate_ma_alert(rows)
    if result is None:
        logger.warning("%dK 資料不足：需要至少 21 根已完成 K 棒，目前 %d 根", interval, len(rows))
        return 0

    alert_marker = state_file.with_suffix(state_file.suffix + ".last-alert")
    if was_alert_sent(alert_marker, result.bar_time):
        logger.info("此 %dK 已處理，略過重複發送：%s", interval, result.bar_time)
        return 0

    on_change_only = interval in settings.mtx_ma_alert.notify_on_change_intervals
    signal_marker = state_file.with_suffix(state_file.suffix + ".last-signal")
    previous = load_last_signal(signal_marker)
    if on_change_only:
        save_last_signal(signal_marker, result.signal)

    if not result.matched:
        logger.info(
            "%dK 條件未成立 %s: MA %.2f/%.2f/%.2f slope %+.2f/%+.2f/%+.2f",
            interval,
            result.bar_time,
            result.ma5,
            result.ma10,
            result.ma20,
            result.ma5_slope,
            result.ma10_slope,
            result.ma20_slope,
        )
        return 0

    signal_label = "多排" if result.signal == "long" else "空排"
    if on_change_only and not signal_changed(previous, result.signal):
        logger.info("%dK %s延續中（上一根已是%s），不重複通知：%s", interval, signal_label, signal_label, result.bar_time)
        return 0

    logger.info("%dK %s條件成立：%s", interval, signal_label, result.bar_time)
    message = format_alert(symbol, session, result, interval_minutes=interval)
    if not TelegramNotifier().send_message(message, parse_mode=None):
        logger.error("Telegram 通知發送失敗")
        if on_change_only:
            # 發送失敗時還原訊號，下次排程重試
            save_last_signal(signal_marker, previous)
        return 1
    mark_alert_sent(alert_marker, result.bar_time)
    logger.info("Telegram 通知發送成功：%s", result.bar_time)
    return 0


def _summarize_positions(positions) -> str:
    """部位摘要（商品/買賣/口數），供 log 確認持倉篩選結果。"""
    return "[" + ", ".join(
        f"{p.get('symbol')}/{p.get('buy_sell')}/{p.get('tradable_lot')}/{p.get('orig_lots')}"
        for p in positions
    ) + "]"


def _notify_ma5_cross(symbol, session, interval, rows, positions, state_file: Path) -> None:
    """持有微台時，K 棒收盤站上／跌破 MA5 發送通知（同一根 K 只發一次）。"""
    cross = detect_ma5_cross(rows)
    if cross is None:
        logger.info("持倉中，%dK 未穿越 MA5", interval)
        return
    marker = state_file.with_suffix(state_file.suffix + ".last-ma5-cross")
    if was_alert_sent(marker, cross.bar_time):
        logger.info("此 %dK MA5 穿越已通知，略過：%s", interval, cross.bar_time)
        return
    message = format_ma5_cross_alert(symbol, session, cross, positions, interval_minutes=interval)
    if TelegramNotifier().send_message(message, parse_mode=None):
        mark_alert_sent(marker, cross.bar_time)
        logger.info("持倉 MA5 %s 通知發送成功：%s", cross.direction, cross.bar_time)
    else:
        logger.error("持倉 MA5 通知發送失敗")


def main() -> int:
    parser = argparse.ArgumentParser(description="微台分 K 均線多空排列通知")
    parser.add_argument("--session", choices=["day", "night"], required=True)
    parser.add_argument(
        "--interval",
        type=int,
        choices=[5, 60],
        default=60,
        help="K 棒週期（分鐘）：60 = 60K（預設），5 = 5K",
    )
    parser.add_argument(
        "--state-file",
        type=Path,
        default=None,
        help="跨排程 K 棒狀態檔（預設 /tmp/mtx-<interval>m-bars.json）",
    )
    args = parser.parse_args()
    state_file = args.state_file or Path(f"/tmp/mtx-{args.interval}m-bars.json")
    return asyncio.run(run(args.session, state_file, args.interval))


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
    )
    exit_code = main()
    # Fubon native SDK may segfault during CPython interpreter finalization even
    # after a successful disconnect. Flush all output, then bypass native object
    # destructors so systemd receives the real application exit code.
    logging.shutdown()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(exit_code)
