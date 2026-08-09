#!/usr/bin/env python
"""取得微台 60 分 K，符合均線條件時發送 Telegram。"""
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
    evaluate_ma_alert,
    format_alert,
    load_candle_state,
    mark_alert_sent,
    save_candle_state,
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


async def run(session: str, state_file: Path) -> int:
    symbol = get_near_month_symbol("MTX")
    api_session = "afterhours" if session == "night" else None

    async with _build_client() as client:
        candles = await client.get_futures_candles(symbol, "60", api_session)

    # 期貨 intraday API 只回傳當日資料；合併 VM 持久磁碟帶入的跨盤狀態，
    # 才有足夠的 21 根 60K 可計算 MA20 斜率。
    state = load_candle_state(state_file)
    rows = completed_candles(
        [*state, *candles],
        now=datetime.now(_TW),
        session=session,
    )
    save_candle_state(state_file, rows)
    result = evaluate_ma_alert(rows)
    if result is None:
        logger.warning("60K 資料不足：需要至少 21 根已完成 K 棒，目前 %d 根", len(rows))
        return 0
    if not result.matched:
        logger.info(
            "條件未成立 %s: MA %.2f/%.2f/%.2f slope %+.2f/%+.2f/%+.2f",
            result.bar_time,
            result.ma5,
            result.ma10,
            result.ma20,
            result.ma5_slope,
            result.ma10_slope,
            result.ma20_slope,
        )
        return 0

    alert_marker = state_file.with_suffix(state_file.suffix + ".last-alert")
    if was_alert_sent(alert_marker, result.bar_time):
        logger.info("此 60K 已通知，略過重複發送：%s", result.bar_time)
        return 0

    message = format_alert(symbol, session, result)
    if not TelegramNotifier().send_message(message, parse_mode=None):
        logger.error("Telegram 通知發送失敗")
        return 1
    mark_alert_sent(alert_marker, result.bar_time)
    logger.info("Telegram 通知發送成功：%s", result.bar_time)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="微台 60K 均線多頭排列通知")
    parser.add_argument("--session", choices=["day", "night"], required=True)
    parser.add_argument(
        "--state-file",
        type=Path,
        default=Path("/tmp/mtx-60m-bars.json"),
        help="跨排程 60K 狀態檔",
    )
    args = parser.parse_args()
    return asyncio.run(run(args.session, args.state_file))


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
