"""
CLI entry point for today's trading signals
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.parent))

from src.scanner.signals_scanner import SignalsScanner
from src.telegram.simple_notifier import TelegramNotifier
from src.utils.logger import get_logger
from config.settings import settings

logger = get_logger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.parent
SIGNALS_LOG_DIR = PROJECT_ROOT / "data" / "signals_log"


def save_signals_history(result: dict) -> Path:
    """將訊號結果存成 JSON，路徑：data/signals_log/YYYYMMDD_HHMMSS.json"""
    SIGNALS_LOG_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = SIGNALS_LOG_DIR / f"signals_{timestamp}.json"

    # date 物件需轉為字串才能 JSON 序列化
    payload = dict(result)
    if hasattr(payload.get("target_date"), "isoformat"):
        payload["target_date"] = payload["target_date"].isoformat()

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    return filepath


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
        print(f"  {'代號':<16} {'名稱':<10} {'族群':<10} {'觸發訊號':<30} {'價格':>9} {'RSI':>6}  備註")
        print("  " + "-" * 106)
        for s in buy_list:
            name = (s["name"] or "")[:8]
            sector = (s.get("sector") or "")[:8]
            signal = s["signal"][:30]
            rsi_str = f"{s['rsi']:.1f}" if s["rsi"] else "-"
            note = s.get("note", "")
            note_str = f"⚠️{note}" if note else ""
            print(f"  {s['symbol']:<16} {name:<10} {sector:<10} {signal:<30} {s['price']:>9.2f} {rsi_str:>6}  {note_str}")
    else:
        print("  （今日無 P1 買入訊號）")

    # ── 賣出警示 ──
    if settings.scanner.show_sell_signals:
        SELL_DISPLAY_LIMIT = 30
        print(f"\n⚠️  賣出警示 ({len(sell_list)} 支)  [若持有以下個股，請留意出場]")
        if sell_list:
            shown = sell_list[:SELL_DISPLAY_LIMIT]
            print(f"  {'代號':<16} {'名稱':<10} {'訊號':<26} {'價格':>8} {'RSI':>6}  備註")
            print("  " + "-" * 80)
            for s in shown:
                name = (s["name"] or "")[:8]
                signal = s["signal"][:24]
                rsi_str = f"{s['rsi']:.1f}" if s["rsi"] else "-"
                note = "⚠️處置股" if s.get("disposal") else ""
                print(f"  {s['symbol']:<16} {name:<10} {signal:<26} {s['price']:>8.2f} {rsi_str:>6}  {note}")
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

    # ── 族群強弱摘要 ──
    sector_summary = result.get("sector_summary", [])
    if sector_summary:
        strong_rows = [r for r in sector_summary if r["is_strong"]]
        weak_rows = [r for r in sector_summary if not r["is_strong"]]
        print(f"\n🏭 族群趨勢摘要（強勢 {len(strong_rows)} / 弱勢 {len(weak_rows)}）")
        if strong_rows:
            strong_str = "  強勢：" + "、".join(
                f"{r['sector']}({r['strength_pct']:.0f}%)" for r in strong_rows
            )
            print(strong_str)
        if weak_rows:
            weak_str = "  弱勢：" + "、".join(
                f"{r['sector']}({r['strength_pct']:.0f}%)" for r in weak_rows
            )
            print(weak_str)

    print(f"\n{'='*60}")
    print("  說明：")
    print("  • 買入訊號需同時通過（P1生產策略）：")
    print("    ① 技術面：MA60上方、均線排列(MA5>MA10>MA20)、RSI≥50")
    print("    ② 動能：成交量≥1000張、動能排名前30")
    print("    ③ 基本面：月營收≥門檻（可設年增率門檻）")
    print("    ④ 籌碼面：三大法人買超≥門檻（預設停用）")
    print("    ⑤ 處置/注意股：不排除，備註欄標記「⚠️處置股」或「⚠️注意股」供參考")
    print("    ⑥ 排除：族群偏弱（排入觀察清單）")
    if settings.scanner.show_sell_signals:
        print("  • 賣出警示：持有股出場訊號，不受買入過濾限制")
        print("    （處置/注意股賣出警示標記「⚠️處置股」或「⚠️注意股」）")
    else:
        print("  • 賣出警示：已關閉（可在 settings.py 設定 SIGNALS_SHOW_SELL=true 開啟）")
    print(f"{'='*60}\n")


TELEGRAM_MAX_LENGTH = 4096


def _escape_md(text: str) -> str:
    """Escape Telegram Markdown special characters in dynamic content"""
    return text.replace('*', '').replace('_', '\\_').replace('[', '\\[').replace('`', '\\`')


def format_for_telegram(result: dict) -> list[str]:
    """格式化為 Telegram 訊息，超過 4096 字元時自動切割為多則"""
    target_date = result["target_date"]
    buy_list = result["buy"]
    sell_list = result["sell"]

    lines = [f"📊 今日交易訊號 {target_date}\n"]

    if buy_list:
        lines.append(f"✅ *建議買入* ({len(buy_list)} 支)")
        for s in buy_list:
            name = _escape_md(s["name"] or "")
            sector = _escape_md(s.get("sector") or "")
            sector_tag = f" [{sector}]" if sector else ""
            note = _escape_md(s.get("note", ""))
            note_tag = f" ⚠️{note}" if note else ""
            lines.append(f"  {s['symbol']} {name}{sector_tag}{note_tag}")
        lines.append("")

    if sell_list and settings.scanner.show_sell_signals:
        lines.append(f"⚠️ *賣出警示* ({len(sell_list)} 支)")
        for s in sell_list:
            name = _escape_md(s["name"] or "")
            sector = _escape_md(s.get("sector") or "")
            sector_tag = f" [{sector}]" if sector else ""
            note = _escape_md(s.get("note", ""))
            note_tag = f" ⚠️{note}" if note else ""
            lines.append(f"  {s['symbol']} {name}{sector_tag}{note_tag}")

    if not buy_list and not (sell_list and settings.scanner.show_sell_signals):
        lines.append("今日無買賣訊號")

    return _split_into_chunks("\n".join(lines))


def _split_into_chunks(text: str, max_length: int = TELEGRAM_MAX_LENGTH) -> list[str]:
    """將長文字按行切割為不超過 max_length 的多則訊息"""
    if len(text) <= max_length:
        return [text]

    chunks = []
    current_lines = []
    current_len = 0

    for line in text.split("\n"):
        # +1 for the newline character
        needed = len(line) + 1
        if current_lines and current_len + needed > max_length:
            chunks.append("\n".join(current_lines))
            current_lines = []
            current_len = 0
        current_lines.append(line)
        current_len += needed

    if current_lines:
        chunks.append("\n".join(current_lines))

    return chunks


def run_ai_analysis(result: dict, send_telegram: bool = False) -> None:
    """執行 AI 二次過濾分析（provider 由 settings.ai_analyzer.provider 決定）"""
    cfg = settings.ai_analyzer
    api_key = cfg.get_api_key()
    provider = cfg.provider

    if not api_key:
        key_var = {"claude": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY", "gemini": "GEMINI_API_KEY", "openrouter": "OPENROUTER_API_KEY"}.get(
            provider.lower(), f"{provider.upper()}_API_KEY"
        )
        print(f"❌ AI 分析失敗：未設定 {key_var} 環境變數")
        return

    try:
        from src.ai_analyzer import create_analyzer
    except ImportError as e:
        print(f"❌ 無法載入 AI 分析器：{e}")
        return

    print(f"\n🤖 正在呼叫 {provider} 進行二次過濾分析...")
    try:
        analyzer = create_analyzer(provider=provider, api_key=api_key, model=cfg.model)
        ai_result = analyzer.analyze_signals(
            result, max_stocks_per_batch=cfg.max_stocks_per_batch
        )
    except Exception as e:
        logger.error(f"AI 分析失敗: {e}")
        print(f"❌ AI 分析失敗: {e}")
        return

    # ── 終端顯示 ──
    target_date = ai_result.get("target_date", "")
    strong_buy = ai_result.get("strong_buy", [])
    buy = ai_result.get("buy", [])
    watch = ai_result.get("watch", [])
    avoid = ai_result.get("avoid", [])

    print(f"\n{'='*60}")
    print(f"  🤖 AI 二次過濾分析（{provider}）  {target_date}")
    print(f"{'='*60}")

    sections = [
        ("🔥 強烈建議買入", strong_buy),
        ("✅ 建議買入", buy),
        ("👀 觀察", watch),
        ("⛔ 不建議", avoid),
    ]
    for title, stocks in sections:
        if not stocks:
            continue
        print(f"\n{title} ({len(stocks)} 支)")
        for s in stocks:
            symbol = s.get("symbol", "").split(".")[0]
            name = s.get("name", "")
            reason = s.get("reason", "")
            note = s.get("note", "")
            note_tag = f" ⚠️{note}" if note else ""
            print(f"  {symbol} {name}{note_tag}")
            if reason:
                print(f"    └ {reason}")

    total = len(strong_buy) + len(buy) + len(watch) + len(avoid)
    print(f"\n共分析 {total} 支（強買{len(strong_buy)} 買{len(buy)} 觀察{len(watch)} 不建議{len(avoid)}）")
    print(f"{'='*60}\n")

    # ── Telegram 發送 ──
    if send_telegram:
        notifier = TelegramNotifier()
        chunks = analyzer.format_for_telegram(ai_result)
        ok = all(notifier.send_message(chunk) for chunk in chunks)
        if ok:
            sent = f"（共 {len(chunks)} 則）" if len(chunks) > 1 else ""
            print(f"AI 分析 Telegram 發送成功{sent}")
        else:
            print("AI 分析 Telegram 發送失敗")


def run_signals(args):
    """執行今日訊號掃描"""
    try:
        scanner = SignalsScanner()
        result = scanner.scan_today()
        display_signals(result, show_watch=getattr(args, "watch", False))

        saved_path = save_signals_history(result)
        print(f"📁 訊號記錄已儲存：{saved_path.relative_to(PROJECT_ROOT)}")

        send_telegram = getattr(args, "send_telegram", False)

        if send_telegram:
            notifier = TelegramNotifier()
            chunks = format_for_telegram(result)
            ok = all(notifier.send_message(chunk) for chunk in chunks)
            if ok:
                sent = f"（共 {len(chunks)} 則）" if len(chunks) > 1 else ""
                print(f"Telegram 訊息發送成功{sent}")
            else:
                print("Telegram 發送失敗")

        if getattr(args, "ai_filter", False):
            run_ai_analysis(result, send_telegram=send_telegram)

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
    signals_parser.add_argument(
        "--ai-filter",
        action="store_true",
        dest="ai_filter",
        help="使用 AI 對訊號清單進行二次過濾分析（provider 由 AI_PROVIDER 設定，預設 claude）",
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
