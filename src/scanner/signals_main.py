"""
CLI entry point for today's trading signals
"""
import argparse
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.parent))

from src.scanner.signals_scanner import SignalsScanner
from src.telegram.simple_notifier import TelegramNotifier
from src.utils.logger import get_logger

logger = get_logger(__name__)


def display_signals(result: dict, show_watch: bool = False):
    """格式化輸出今日訊號"""
    target_date = result["target_date"]
    buy_list = result["buy"]
    sell_list = result["sell"]
    watch_list = result["watch"]
    total = result["total_scanned"]

    print(f"\n{'='*60}")
    print(f"  📊 今日交易訊號  {target_date}  (共分析 {total} 支)")
    print(f"{'='*60}")

    # ── 建議買入 ──
    print(f"\n✅ 建議買入 ({len(buy_list)} 支)  [P1 策略完整過濾通過]")
    if buy_list:
        print(f"  {'代號':<16} {'名稱':<10} {'觸發訊號':<40} {'價格':>9} {'RSI':>6}")
        print("  " + "-" * 85)
        for s in buy_list:
            name = (s["name"] or "")[:8]
            signal = s["signal"][:40]
            rsi_str = f"{s['rsi']:.1f}" if s["rsi"] else "-"
            print(f"  {s['symbol']:<16} {name:<10} {signal:<40} {s['price']:>9.2f} {rsi_str:>6}")
    else:
        print("  （今日無 P1 買入訊號）")

    # ── 賣出警示 ──
    SELL_DISPLAY_LIMIT = 30
    print(f"\n⚠️  賣出警示 ({len(sell_list)} 支)  [若持有以下個股，請留意出場]")
    if sell_list:
        shown = sell_list[:SELL_DISPLAY_LIMIT]
        print(f"  {'代號':<16} {'名稱':<10} {'訊號':<26} {'價格':>8} {'RSI':>6}")
        print("  " + "-" * 70)
        for s in shown:
            name = (s["name"] or "")[:8]
            signal = s["signal"][:24]
            rsi_str = f"{s['rsi']:.1f}" if s["rsi"] else "-"
            print(f"  {s['symbol']:<16} {name:<10} {signal:<26} {s['price']:>8.2f} {rsi_str:>6}")
        if len(sell_list) > SELL_DISPLAY_LIMIT:
            print(f"  ... 另有 {len(sell_list) - SELL_DISPLAY_LIMIT} 支（使用 --watch 查看觀察清單）")
    else:
        print("  （今日無賣出訊號）")

    # ── 觀察清單（選用） ──
    if show_watch:
        print(f"\n👁️  觀察清單 ({len(watch_list)} 支)  [訊號觸發但未達進場條件]")
        if watch_list:
            print(f"  {'代號':<16} {'名稱':<10} {'訊號':<22} {'RSI':>6}  未達原因")
            print("  " + "-" * 80)
            for s in watch_list[:30]:  # 最多顯示 30 筆
                name = (s["name"] or "")[:8]
                signal = s["signal"][:20]
                rsi_str = f"{s['rsi']:.1f}" if s["rsi"] else "-"
                reason = s.get("reason", "")[:30]
                print(f"  {s['symbol']:<16} {name:<10} {signal:<22} {rsi_str:>6}  {reason}")

    print(f"\n{'='*60}")
    print("  說明：")
    print("  • 買入訊號需同時通過：MA60上方、均線排列(MA5>MA10>MA20)、")
    print("    RSI≥50、動能排名前30、成交量≥1000張（P1生產策略設定）")
    print("  • 賣出警示為參考，不代表強制出場")
    print(f"{'='*60}\n")


def format_for_telegram(result: dict) -> str:
    """格式化為 Telegram 訊息"""
    target_date = result["target_date"]
    buy_list = result["buy"]
    sell_list = result["sell"]

    lines = [f"📊 今日交易訊號 {target_date}\n"]

    if buy_list:
        lines.append(f"✅ *建議買入* ({len(buy_list)} 支)")
        for s in buy_list[:10]:
            name = s["name"] or ""
            rsi_str = f"RSI:{s['rsi']:.0f}" if s["rsi"] else ""
            lines.append(f"  {s['symbol']} {name} | {s['signal']} | {s['price']:.2f} {rsi_str}")
        lines.append("")

    if sell_list:
        lines.append(f"⚠️ *賣出警示* ({len(sell_list)} 支)")
        for s in sell_list[:10]:
            name = s["name"] or ""
            rsi_str = f"RSI:{s['rsi']:.0f}" if s["rsi"] else ""
            lines.append(f"  {s['symbol']} {name} | {s['signal']} | {s['price']:.2f} {rsi_str}")

    if not buy_list and not sell_list:
        lines.append("今日無買賣訊號")

    return "\n".join(lines)


def run_signals(args):
    """執行今日訊號掃描"""
    try:
        scanner = SignalsScanner()
        result = scanner.scan_today()
        display_signals(result, show_watch=getattr(args, "watch", False))

        if getattr(args, "send_telegram", False):
            notifier = TelegramNotifier()
            msg = format_for_telegram(result)
            ok = notifier.send_message(msg)
            if ok:
                print("Telegram 訊息發送成功")
            else:
                print("Telegram 發送失敗")

    except Exception as e:
        logger.error(f"訊號掃描失敗: {e}")
        print(f"❌ 訊號掃描失敗: {e}")
        sys.exit(1)


def create_parser():
    parser = argparse.ArgumentParser(description="今日 P1 策略買賣訊號")
    subparsers = parser.add_subparsers(dest="command")

    signals_parser = subparsers.add_parser("signals", help="今日買賣訊號")
    signals_parser.add_argument(
        "--watch",
        action="store_true",
        help="同時顯示觀察清單（訊號觸發但未達條件）",
    )
    signals_parser.add_argument(
        "--send-telegram",
        action="store_true",
        help="發送結果到 Telegram",
    )
    return parser


def main():
    parser = create_parser()
    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)
    if args.command == "signals":
        run_signals(args)


if __name__ == "__main__":
    main()
