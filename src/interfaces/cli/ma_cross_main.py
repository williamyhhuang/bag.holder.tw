"""
均線穿越 60MA 篩選 CLI

用法：
    python -m src.interfaces.cli.ma_cross_main            # 套用細產業指標過濾
    python -m src.interfaces.cli.ma_cross_main --no-sub-industry-filter
    python -m src.interfaces.cli.ma_cross_main --refresh-sub-industries
    python -m src.interfaces.cli.ma_cross_main --send-telegram --require-today   # 排程用
"""
import argparse
import sys
from datetime import date, datetime
from pathlib import Path
from typing import List, Optional
from zoneinfo import ZoneInfo

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
        f"\n📈 5/10/20MA 穿越下彎或走平 60MA：{len(result.candidates)} 檔"
        + (f"，細產業過濾後 {len(result.stocks)} 檔" if show_filter else "")
    )
    for _, r in result.stocks.iterrows():
        subs = r["hot_sub_industries"] if show_filter else r["sub_industries"]
        print(
            f"  {r['cross_date']}  {r['code']:<6} {r['name']:<8} {r['sector']:<6} "
            f"收 {r['close']:>8.2f}  60MA {r['ma60']:>8.2f} ({r['ma60_slope_pct']:+.2f}%)  {subs}"
        )


def format_for_telegram(result: MACrossScanResult, show_filter: bool, max_stocks: int = 30) -> List[str]:
    """組成 Telegram 純文字訊息（不使用 Markdown，避免股票名稱中的符號造成解析錯誤），依長度切段"""
    cfg = settings.ma_cross
    lines = [f"📈 均線穿越 60MA 選股｜{result.as_of}", ""]

    if show_filter:
        lines.append(
            f"🔥 熱門細產業（成交值≥{_fmt_value(cfg.sub_industry_min_trade_value)}，"
            f"漲幅前{cfg.sub_industry_top_n}）"
        )
        if result.hot_sub_industries.empty:
            lines.append("（無細產業達成交值門檻）")
        for i, r in result.hot_sub_industries.iterrows():
            lines.append(
                f"{i + 1}. {r['chain']}/{r['name']} {r['change_pct']:+.2f}%  {_fmt_value(r['trade_value'])}"
            )
        lines.append("")

    header = f"5/10/20MA 穿越下彎或走平 60MA：{len(result.candidates)} 檔"
    if show_filter:
        header += f"，細產業過濾後 {len(result.stocks)} 檔"
    lines.append(f"🎯 {header}")

    if result.stocks.empty:
        lines.append("今日無符合條件的股票")
    shown = result.stocks.head(max_stocks) if max_stocks > 0 else result.stocks
    for _, r in shown.iterrows():
        subs = r["hot_sub_industries"] if show_filter else r["sub_industries"]
        cross = r["cross_date"].strftime("%m/%d") if hasattr(r["cross_date"], "strftime") else r["cross_date"]
        lines.append(
            f"• {r['code']} {r['name']}  收{r['close']:g}  60MA {r['ma60']:g}({r['ma60_slope_pct']:+.2f}%)"
            f"  穿越{cross}" + (f"\n   {subs}" if subs else "")
        )
    if len(shown) < len(result.stocks):
        lines.append(f"…另有 {len(result.stocks) - len(shown)} 檔，完整清單見 CSV")

    chunks: List[str] = []
    current = ""
    for line in lines:
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) > TELEGRAM_CHUNK_LIMIT and current:
            chunks.append(current)
            current = line
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def send_telegram(chunks: List[str], chat_id: Optional[str] = None) -> bool:
    notifier = TelegramNotifier()
    target = chat_id or settings.ma_cross.telegram_chat_id
    return all(notifier.send_message(chunk, chat_id=target, parse_mode=None) for chunk in chunks)


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
