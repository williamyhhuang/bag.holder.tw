"""
Telegram Trade Recorder Bot — 獨立執行入口

啟動後以 polling 模式接收 Telegram 訊息，
使用者輸入買入/賣出指令後自動記錄至 CSV 及 Google Sheets。

使用方式:
    python -m src.interfaces.trade_bot_main

環境變數（必填）:
    TELEGRAM_BOT_TOKEN          Telegram Bot Token
    GOOGLE_SHEETS_ENABLED       true
    GOOGLE_SHEETS_SPREADSHEET_ID  Google 試算表 ID
    GOOGLE_CREDENTIALS_JSON     Service Account JSON 字串（或 GOOGLE_CREDENTIALS_FILE）

指令格式:
    買入 2330 150.5 1000    買入 1000 股 2330，成本 150.5
    賣出 2330 165           賣出 2330（預設 1000 股）
    /stats                  查看近 30 天交易統計
    /trades                 查看最近 10 筆記錄
    /help                   顯示說明
"""
import asyncio
import sys
from pathlib import Path

# 確保專案根目錄在 sys.path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from src.infrastructure.notification.telegram_trade_bot import TradingBot
from src.utils.logger import get_logger
from config.settings import settings

logger = get_logger(__name__)

_trade_bot = TradingBot()


async def _start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "👋 歡迎使用交易記錄 Bot！\n\n"
        "輸入 /help 查看指令說明。"
    )


async def _help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = _trade_bot.process_telegram_command("/help", str(update.effective_chat.id))
    await update.message.reply_text(msg, parse_mode="Markdown")


async def _stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = _trade_bot.process_telegram_command("/stats", str(update.effective_chat.id))
    await update.message.reply_text(msg, parse_mode="Markdown")


async def _trades(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = _trade_bot.process_telegram_command("/trades", str(update.effective_chat.id))
    await update.message.reply_text(msg, parse_mode="Markdown")


async def _message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = str(update.effective_chat.id)
    text = update.message.text or ""
    msg = _trade_bot.process_telegram_command(text, chat_id)
    await update.message.reply_text(msg, parse_mode="Markdown")


def main() -> None:
    token = settings.telegram.bot_token
    if not token or token == "dummy_token":
        logger.error("TELEGRAM_BOT_TOKEN 未設定，請在 .env 中設定")
        sys.exit(1)

    logger.info("Trade Recorder Bot 啟動中...")

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", _start))
    app.add_handler(CommandHandler("help", _help))
    app.add_handler(CommandHandler("stats", _stats))
    app.add_handler(CommandHandler("trades", _trades))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _message_handler))

    sheets_ok = _trade_bot.sheets_recorder.is_available()
    logger.info(f"Google Sheets 同步: {'啟用' if sheets_ok else '停用（未設定或 GOOGLE_SHEETS_ENABLED=false）'}")
    logger.info("Bot 已啟動，等待訊息（Ctrl+C 停止）...")

    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
