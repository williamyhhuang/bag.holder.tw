"""
均線穿越 60MA 篩選 CLI

用法：
    python -m src.interfaces.cli.ma_cross_main            # 套用細產業指標過濾
    python -m src.interfaces.cli.ma_cross_main --no-sub-industry-filter
    python -m src.interfaces.cli.ma_cross_main --refresh-sub-industries
    python -m src.interfaces.cli.ma_cross_main --send-telegram --require-today   # 排程用
"""
import argparse
import html
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo

import pandas as pd

project_root = Path(__file__).parent.parent.parent.parent
sys.path.append(str(project_root))

from config.settings import settings
from src.application.services.ma_cross_scanner import MACrossScanner, MACrossScanResult
from src.infrastructure.notification.telegram_notifier import TelegramNotifier
from src.utils.logger import get_logger
from src.utils.sub_industry_mapper import get_sub_industries

logger = get_logger(__name__)

TAIPEI = ZoneInfo("Asia/Taipei")
TELEGRAM_CHUNK_LIMIT = 3900  # Telegram 單則上限 4096 字元，保留緩衝


def _fmt_value(v: float) -> str:
    return f"{v / 1e8:,.1f}億"


def print_result(result: MACrossScanResult, show_filter: bool) -> None:
    cfg = settings.ma_cross
    print(f"\n📅 基準日：{result.as_of}")

    if show_filter:
        print(
            f"\n🔥 熱門細產業（成交值 ≥ {_fmt_value(cfg.sub_industry_min_trade_value)}，"
            f"漲幅前 {cfg.sub_industry_top_n} 名，{cfg.sub_industry_weighting} 加權）"
        )
        for i, r in result.hot_sub_industries.iterrows():
            print(
                f"  {i + 1:>2}. {r['chain']}/{r['name']:<20} 漲幅 {r['change_pct']:+.2f}%  "
                f"成交值 {_fmt_value(r['trade_value'])}  成分股 {r['members']}"
            )

    print(
        f"\n📈 5/10/20MA 穿越下彎或走平 60MA、成交量 ≥ {cfg.min_volume_lots:,} 張：{len(result.candidates)} 檔"
        + (f"，細產業過濾後 {len(result.stocks)} 檔" if show_filter else "")
    )
    for _, r in result.stocks.iterrows():
        subs = r["hot_sub_industries"] if show_filter else r["sub_industries"]
        print(
            f"  {r['cross_date']}  {r['code']:<6} {r['name']:<8} {r['sector']:<6} "
            f"收 {r['close']:>8.2f}  60MA {r['ma60']:>8.2f} ({r['ma60_slope_pct']:+.2f}%)  {subs}"
        )


WEEKDAYS = "一二三四五六日"


def format_for_telegram(result: MACrossScanResult, show_filter: bool, max_stocks: int = 30) -> List[str]:
    """組成 Telegram HTML 訊息（parse_mode=HTML）。

    手機版面：標題兩行短句；股票依代表細產業分組（熱門細產業依漲幅排名排序），
    每組一行細產業名稱，其下每檔一行「代號(粗體) 名稱 收盤價 漲跌幅」。
    不用 <pre> 等寬區塊：手機上右上角的複製按鈕會遮住內容，中文字寬也對不齊。
    超過長度時依行切段。
    """
    as_of = result.as_of
    day = f"{as_of:%Y-%m-%d}（{WEEKDAYS[as_of.weekday()]}）" if as_of else "-"
    label = "細產業過濾後" if show_filter else "符合"
    header = f"<b>📈 均線穿越 60MA</b>\n{day}・{label} <b>{len(result.stocks)}</b> 檔"

    if result.stocks.empty:
        return [f"{header}\n\n今日無符合條件的股票"]

    shown = result.stocks.head(max_stocks) if max_stocks > 0 else result.stocks
    order = {}
    if not result.hot_sub_industries.empty:
        for i, r in result.hot_sub_industries.reset_index(drop=True).iterrows():
            order[f"{r['chain']}/{r['name']}"] = i
    groups: Dict[str, List[str]] = {}
    for _, r in shown.iterrows():
        group = r.get("main_sub_industry") or "其他"
        groups.setdefault(group, []).append(
            f"<b>{html.escape(str(r['code']))}</b>  {html.escape(str(r['name']))}  {r['close']:.2f}"
            + (f"  {r['change_pct']:+.2f}%" if pd.notna(r.get("change_pct")) else "")
        )

    lines: List[str] = []
    for group in sorted(groups, key=lambda g: (order.get(g, len(order)), g == "其他")):
        lines.append("")
        lines.append(f"🏷 <b>{html.escape(group)}</b>")
        lines.extend(groups[group])
    if len(shown) < len(result.stocks):
        lines.append("")
        lines.append(f"…另有 {len(result.stocks) - len(shown)} 檔")

    chunks: List[str] = []
    current = header
    for line in lines:
        candidate = f"{current}\n{line}"
        if len(candidate) > TELEGRAM_CHUNK_LIMIT and current.strip():
            chunks.append(current.strip())
            current = line
        else:
            current = candidate
    chunks.append(current.strip())
    return chunks


def send_telegram(chunks: List[str], chat_id: Optional[str] = None) -> bool:
    notifier = TelegramNotifier()
    target = chat_id or settings.ma_cross.telegram_chat_id
    return all(notifier.send_message(chunk, chat_id=target, parse_mode="HTML") for chunk in chunks)


def today_taipei() -> date:
    return datetime.now(TAIPEI).date()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="5/10/20MA 穿越下彎或走平 60MA 篩選 + 細產業指標過濾")
    parser.add_argument("--no-sub-industry-filter", action="store_true", help="不套用細產業指標過濾")
    parser.add_argument("--refresh-sub-industries", action="store_true", help="強制重新抓取細產業對照")
    parser.add_argument("--output-dir", help=f"輸出目錄（預設 {settings.ma_cross.output_dir}）")
    parser.add_argument("--send-telegram", action="store_true", help="將結果發送到 Telegram")
    parser.add_argument(
        "--require-today",
        action="store_true",
        help="最新資料日不是今天（台北時間）時不執行（休市日或資料未更新），供排程使用",
    )
    args = parser.parse_args(argv)

    sub_industries = None
    if args.refresh_sub_industries:
        sub_industries = get_sub_industries(use_cache=False)

    scanner = MACrossScanner()
    show_filter = not args.no_sub_industry_filter
    result = scanner.scan(sub_industries=sub_industries, apply_sub_industry_filter=show_filter)
    if result.as_of is None:
        logger.error(f"{scanner.stocks_dir} 沒有可用的日K資料")
        return 1

    if args.require_today and result.as_of != today_taipei():
        print(f"⏭️ 最新資料日 {result.as_of} 不是今天 {today_taipei()}（休市或資料未更新），略過")
        return 0

    print_result(result, show_filter)
    path = scanner.save(result, args.output_dir)
    print(f"\n💾 已輸出：{path}")

    if args.send_telegram:
        chunks = format_for_telegram(result, show_filter, settings.ma_cross.telegram_max_stocks)
        if not send_telegram(chunks):
            logger.error("Telegram 發送失敗")
            return 1
        print(f"📨 已發送 Telegram（{len(chunks)} 則）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
