"""
CLI entry point for holdings sell check
"""
import argparse
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.parent))

from src.application.services.holdings_checker import HoldingsChecker
from src.infrastructure.notification.telegram_notifier import TelegramNotifier
from src.utils.logger import get_logger
from config.settings import settings

logger = get_logger(__name__)

TELEGRAM_MAX_LENGTH = 4096


def _split_chunks(text: str, max_length: int = TELEGRAM_MAX_LENGTH) -> list[str]:
    if len(text) <= max_length:
        return [text]
    chunks, current, current_len = [], [], 0
    for line in text.split("\n"):
        needed = len(line) + 1
        if current and current_len + needed > max_length:
            chunks.append("\n".join(current))
            current, current_len = [], 0
        current.append(line)
        current_len += needed
    if current:
        chunks.append("\n".join(current))
    return chunks


def _short_symbol(symbol: str) -> str:
    return symbol.split(".")[0] if "." in symbol else symbol


def display_result(result: dict):
    """終端顯示持倉檢查結果"""
    today = result['target_date']
    open_positions = result['open_positions']
    sell_alerts = result['sell_alerts']
    ai_result = result.get('ai_result', {})

    print(f"\n{'='*60}")
    print(f"  📋 持倉賣出檢查  {today}")
    print(f"  持倉 {len(open_positions)} 支，出現賣出訊號 {len(sell_alerts)} 支")
    print(f"{'='*60}")

    if not open_positions:
        print("\n  （Google Sheets 無未平倉持倉記錄）")
        print(f"{'='*60}\n")
        return

    if not sell_alerts:
        print(f"\n✅ 持倉 {len(open_positions)} 支，今日無賣出訊號")
        print(f"   持倉：{', '.join(sorted(open_positions))}")
        print(f"{'='*60}\n")
        return

    # P1 賣出訊號清單
    print(f"\n⚠️  P1 賣出訊號（持倉中）{len(sell_alerts)} 支：")
    print(f"  {'代號':<12} {'名稱':<10} {'訊號':<24} {'現價':>8} {'RSI':>6} {'損益%':>7} {'持有'}天")
    print("  " + "-" * 80)
    for s in sell_alerts:
        sym = _short_symbol(s['symbol'])
        name = (s.get('name') or '')[:8]
        signal = (s.get('signal') or '')[:22]
        price = s.get('price', 0)
        rsi_str = f"{s['rsi']:.1f}" if s.get('rsi') else '-'
        pnl = s.get('pnl_pct')
        pnl_str = f"{pnl:+.1f}%" if pnl is not None else '-'
        days = s.get('holding_days', '-')
        print(f"  {sym:<12} {name:<10} {signal:<24} {price:>8.2f} {rsi_str:>6} {pnl_str:>7} {days}")

    # AI 分析結果
    sell_ai = ai_result.get('sell', [])
    watch_ai = ai_result.get('watch', [])
    hold_ai = ai_result.get('hold', [])

    if sell_ai or watch_ai or hold_ai:
        print(f"\n{'─'*60}")
        print("🤖 AI 出場決策：")

        sections = [
            ("🔴 建議出場", sell_ai),
            ("👀 設停損觀察", watch_ai),
            ("✅ 繼續持有", hold_ai),
        ]
        for title, stocks in sections:
            if not stocks:
                continue
            print(f"\n{title} ({len(stocks)} 支)")
            for s in stocks:
                sym = _short_symbol(s.get('symbol', ''))
                name = s.get('name', '')
                reason = s.get('reason', '')
                print(f"  【{sym} {name}】")
                if reason:
                    print(f"    └ {reason}")

    print(f"\n{'='*60}\n")


def format_for_telegram(result: dict) -> list[str]:
    """格式化為 Telegram 訊息"""
    today = result['target_date']
    open_positions = result['open_positions']
    sell_alerts = result['sell_alerts']
    ai_result = result.get('ai_result', {})

    lines = [f"📋 持倉賣出檢查 {today}\n持倉 {len(open_positions)} 支，賣出訊號 {len(sell_alerts)} 支\n"]

    if not open_positions:
        lines.append("（Google Sheets 無未平倉持倉記錄）")
        return _split_chunks("\n".join(lines))

    if not sell_alerts:
        lines.append(f"✅ 持倉 {len(open_positions)} 支，今日無賣出訊號")
        return _split_chunks("\n".join(lines))

    # P1 賣出訊號
    lines.append(f"⚠️ P1 賣出訊號（持倉中）{len(sell_alerts)} 支")
    for s in sell_alerts:
        sym = _short_symbol(s['symbol'])
        name = s.get('name', '')
        signal = s.get('signal', '')
        pnl = s.get('pnl_pct')
        pnl_str = f" {pnl:+.1f}%" if pnl is not None else ""
        days = s.get('holding_days')
        days_str = f" 持有{days}天" if days is not None else ""
        lines.append(f"  {sym} {name} [{signal}]{pnl_str}{days_str}")
    lines.append("")

    # AI 分析
    sell_ai = ai_result.get('sell', [])
    watch_ai = ai_result.get('watch', [])
    hold_ai = ai_result.get('hold', [])

    if sell_ai or watch_ai or hold_ai:
        try:
            from config.settings import settings
            cfg = settings.ai_analyzer
            model_tag = f" ({cfg.model})" if cfg.model else ""
        except Exception:
            model_tag = ""
        lines.append(f"🤖 AI 持倉分析{model_tag}")

        ai_sections = [
            ("🔴 建議出場", sell_ai),
            ("👀 設停損觀察", watch_ai),
            ("✅ 繼續持有", hold_ai),
        ]
        for title, stocks in ai_sections:
            if not stocks:
                continue
            lines.append(f"\n{title} ({len(stocks)} 支)")
            for s in stocks:
                sym = _short_symbol(s.get('symbol', ''))
                name = s.get('name', '')
                reason = s.get('reason', '')
                lines.append(f"【{sym} {name}】")
                if reason:
                    lines.append(f"└ {reason}")

    return _split_chunks("\n".join(lines))


def run_check_holdings(args):
    """執行持倉賣出檢查"""
    try:
        checker = HoldingsChecker()
        result = checker.check()
        display_result(result)

        send_telegram = getattr(args, 'send_telegram', False)
        if send_telegram:
            notifier = TelegramNotifier()
            chunks = format_for_telegram(result)
            ok = all(notifier.send_message(chunk, parse_mode=None) for chunk in chunks)
            if ok:
                sent = f"（共 {len(chunks)} 則）" if len(chunks) > 1 else ""
                print(f"Telegram 訊息發送成功{sent}")
            else:
                print("Telegram 發送失敗")
                sys.exit(1)

    except Exception as e:
        logger.error(f"持倉檢查失敗: {e}")
        print(f"❌ 持倉檢查失敗: {e}")
        sys.exit(1)


def create_parser():
    parser = argparse.ArgumentParser(description="持倉賣出檢查")
    subparsers = parser.add_subparsers(dest="command")
    check_parser = subparsers.add_parser("check-holdings", help="持倉賣出檢查")
    check_parser.add_argument(
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
    if args.command == "check-holdings":
        run_check_holdings(args)


if __name__ == "__main__":
    main()
