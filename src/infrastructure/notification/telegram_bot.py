"""
Telegram bot for Taiwan stock monitoring notifications
"""
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from decimal import Decimal

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler,
    ContextTypes, filters
)
from sqlalchemy import and_, desc

from ...database.connection import db_manager
from ...database.models import (
    TelegramUser, Stock, Alert, Watchlist, Portfolio, PortfolioHolding,
    StockRealtime, TechnicalIndicator
)
from ..market_data.market_filters import MarketScreener, FilterCriteria, FilterOperator
from ...utils.logger import get_logger
from ...utils.error_handler import handle_errors
from ...utils.rate_limiter import rate_limit_manager

logger = get_logger(__name__)

class TelegramBot:
    """Telegram bot for stock monitoring"""

    def __init__(self, token: str):
        self.token = token
        self.application = Application.builder().token(token).build()
        self.market_screener = MarketScreener()
        self.logger = get_logger(self.__class__.__name__)

        # Setup handlers
        self._setup_handlers()

    def _setup_handlers(self):
        """Setup bot command and message handlers"""
        # Command handlers
        self.application.add_handler(CommandHandler("start", self._start_command))
        self.application.add_handler(CommandHandler("help", self._help_command))
        self.application.add_handler(CommandHandler("status", self._status_command))
        self.application.add_handler(CommandHandler("watch", self._watch_command))
        self.application.add_handler(CommandHandler("unwatch", self._unwatch_command))
        self.application.add_handler(CommandHandler("watchlist", self._watchlist_command))
        self.application.add_handler(CommandHandler("quote", self._quote_command))
        self.application.add_handler(CommandHandler("screen", self._screen_command))
        self.application.add_handler(CommandHandler("alerts", self._alerts_command))
        self.application.add_handler(CommandHandler("portfolio", self._portfolio_command))
        self.application.add_handler(CommandHandler("settings", self._settings_command))

        # Callback query handler for inline keyboards
        self.application.add_handler(CallbackQueryHandler(self._button_callback))

        # Message handler for stock symbols
        self.application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self._message_handler)
        )

    async def start_bot(self):
        """Start the telegram bot"""
        self.logger.info("Starting Telegram bot...")
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling()

    async def stop_bot(self):
        """Stop the telegram bot"""
        self.logger.info("Stopping Telegram bot...")
        await self.application.updater.stop()
        await self.application.stop()
        await self.application.shutdown()

    @handle_errors()
    async def _start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        user = update.effective_user
        chat_id = str(update.effective_chat.id)

        # Register user
        await self._register_user(chat_id, user.username, user.first_name)

        welcome_text = """
🎯 *台股監控機器人* 歡迎您！

我可以幫您：
📊 監控股票價格與技術指標
🔔 發送買賣信號通知
📈 追蹤投資組合
🔍 市場篩選功能

*常用指令：*
/help - 查看所有指令
/watch 2330 - 加入關注股票
/quote 2330 - 查看即時報價
/screen momentum - 篩選動能股
/portfolio - 查看投資組合
/alerts - 查看最新警報

開始使用吧！💪
        """

        await update.message.reply_text(
            welcome_text,
            parse_mode='Markdown'
        )

    @handle_errors()
    async def _help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        help_text = """
🤖 *台股監控機器人指令說明*

*基本功能：*
/start - 開始使用機器人
/help - 顯示此說明
/status - 系統狀態

*股票查詢：*
/quote <股票代號> - 查看即時報價
例：/quote 2330

*關注清單：*
/watch <股票代號> - 加入關注
/unwatch <股票代號> - 移除關注
/watchlist - 查看關注清單

*市場篩選：*
/screen <類型> - 篩選股票
類型：momentum, oversold, breakout, value, tech

*投資組合：*
/portfolio - 查看投資組合

*警報系統：*
/alerts - 查看最新警報

*設定：*
/settings - 個人設定

直接輸入股票代號也可以查看報價！
例：直接輸入 "2330"
        """

        await update.message.reply_text(
            help_text,
            parse_mode='Markdown'
        )

    @handle_errors()
    async def _status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command"""
        try:
            # Get system status
            with db_manager.get_session() as session:
                total_stocks = session.query(Stock).filter(Stock.is_active == True).count()
                total_alerts = session.query(Alert).filter(
                    Alert.triggered_at >= datetime.now() - timedelta(days=1)
                ).count()
                total_users = session.query(TelegramUser).filter(TelegramUser.is_active == True).count()

            status_text = f"""
📊 *系統狀態*

🎯 監控股票數量：{total_stocks:,} 檔
🔔 今日警報數量：{total_alerts} 個
👥 活躍用戶數量：{total_users} 人

🟢 系統運行正常
⏰ 最後更新：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            """

            await update.message.reply_text(
                status_text,
                parse_mode='Markdown'
            )

        except Exception as e:
            await update.message.reply_text(f"❌ 獲取系統狀態失敗：{e}")

    @handle_errors()
    async def _watch_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /watch command"""
        if not context.args:
            await update.message.reply_text("請提供股票代號，例：/watch 2330")
            return

        symbol = context.args[0].upper()
        user_id = str(update.effective_user.id)

        try:
            with db_manager.get_session() as session:
                # Find stock
                stock = session.query(Stock).filter(Stock.symbol == symbol).first()
                if not stock:
                    await update.message.reply_text(f"❌ 找不到股票代號：{symbol}")
                    return

                # Check if already watching
                existing = session.query(Watchlist).filter(
                    and_(
                        Watchlist.user_id == user_id,
                        Watchlist.stock_id == stock.id
                    )
                ).first()

                if existing:
                    await update.message.reply_text(f"📌 您已經在關注 {symbol} {stock.name}")
                    return

                # Add to watchlist
                watchlist = Watchlist(user_id=user_id, stock_id=stock.id)
                session.add(watchlist)
                session.commit()

                await update.message.reply_text(
                    f"✅ 已加入關注：{symbol} {stock.name}\n"
                    f"您將收到相關的交易信號通知"
                )

        except Exception as e:
            await update.message.reply_text(f"❌ 加入關注失敗：{e}")

    @handle_errors()
    async def _unwatch_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /unwatch command"""
        if not context.args:
            await update.message.reply_text("請提供股票代號，例：/unwatch 2330")
            return

        symbol = context.args[0].upper()
        user_id = str(update.effective_user.id)

        try:
            with db_manager.get_session() as session:
                # Find stock
                stock = session.query(Stock).filter(Stock.symbol == symbol).first()
                if not stock:
                    await update.message.reply_text(f"❌ 找不到股票代號：{symbol}")
                    return

                # Remove from watchlist
                deleted = session.query(Watchlist).filter(
                    and_(
                        Watchlist.user_id == user_id,
                        Watchlist.stock_id == stock.id
                    )
                ).delete()

                session.commit()

                if deleted:
                    await update.message.reply_text(f"✅ 已移除關注：{symbol} {stock.name}")
                else:
                    await update.message.reply_text(f"❌ 您尚未關注：{symbol}")

        except Exception as e:
            await update.message.reply_text(f"❌ 移除關注失敗：{e}")

    @handle_errors()
    async def _watchlist_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /watchlist command"""
        user_id = str(update.effective_user.id)

        try:
            with db_manager.get_session() as session:
                watchlists = session.query(Watchlist, Stock).join(
                    Stock, Watchlist.stock_id == Stock.id
                ).filter(Watchlist.user_id == user_id).all()

                if not watchlists:
                    await update.message.reply_text(
                        "📋 您的關注清單是空的\n使用 /watch <股票代號> 來添加股票"
                    )
                    return

                watchlist_text = "📋 *您的關注清單：*\n\n"

                for watchlist, stock in watchlists:
                    # Get current price
                    realtime = session.query(StockRealtime).filter(
                        StockRealtime.stock_id == stock.id
                    ).first()

                    if realtime:
                        price_text = f"{realtime.current_price}"
                        change_text = f"{realtime.change_amount:+.2f} ({realtime.change_percent:+.2f}%)"
                        emoji = "📈" if realtime.change_amount >= 0 else "📉"
                    else:
                        price_text = "N/A"
                        change_text = "N/A"
                        emoji = "📊"

                    watchlist_text += (
                        f"{emoji} *{stock.symbol}* {stock.name}\n"
                        f"💰 {price_text} ({change_text})\n\n"
                    )

                await update.message.reply_text(watchlist_text, parse_mode='Markdown')

        except Exception as e:
            await update.message.reply_text(f"❌ 獲取關注清單失敗：{e}")

    @handle_errors()
    async def _quote_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /quote command"""
        if not context.args:
            await update.message.reply_text("請提供股票代號，例：/quote 2330")
            return

        symbol = context.args[0].upper()
        await self._send_stock_quote(update, symbol)

    @handle_errors()
    async def _screen_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /screen command"""
        if not context.args:
            presets = self.market_screener.get_available_presets()
            await update.message.reply_text(
                f"請提供篩選類型，例：/screen momentum\n\n可用類型：{', '.join(presets)}"
            )
            return

        screen_type = context.args[0].lower()

        try:
            results = self.market_screener.screen_market(
                preset_name=screen_type,
                limit=10
            )

            if not results:
                await update.message.reply_text(f"❌ 篩選類型 '{screen_type}' 沒有找到符合條件的股票")
                return

            screen_text = f"🔍 *{screen_type.upper()} 篩選結果：*\n\n"

            for i, result in enumerate(results, 1):
                stock = result.stock
                values = result.matched_values

                # Get current price info
                current_price = values.get('price_current', 'N/A')
                change_pct = values.get('price_change_pct', 0)

                emoji = "📈" if change_pct >= 0 else "📉"
                screen_text += (
                    f"{i}. {emoji} *{stock.symbol}* {stock.name}\n"
                    f"💰 {current_price} ({change_pct:+.2f}%)\n"
                    f"📊 評分：{result.score:.1f}\n\n"
                )

            # Add keyboard for actions
            keyboard = [
                [InlineKeyboardButton("📊 更多資訊", callback_data=f"more_info_{results[0].stock.symbol}")],
                [InlineKeyboardButton("🔄 重新篩選", callback_data=f"rescreen_{screen_type}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(
                screen_text,
                parse_mode='Markdown',
                reply_markup=reply_markup
            )

        except Exception as e:
            await update.message.reply_text(f"❌ 篩選失敗：{e}")

    @handle_errors()
    async def _alerts_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /alerts command"""
        user_id = str(update.effective_user.id)

        try:
            with db_manager.get_session() as session:
                # Get user's watchlist stocks
                watchlist_stocks = session.query(Watchlist.stock_id).filter(
                    Watchlist.user_id == user_id
                ).subquery()

                # Get recent alerts for watched stocks
                alerts = session.query(Alert, Stock).join(
                    Stock, Alert.stock_id == Stock.id
                ).filter(
                    and_(
                        Alert.stock_id.in_(watchlist_stocks),
                        Alert.triggered_at >= datetime.now() - timedelta(days=7)
                    )
                ).order_by(desc(Alert.triggered_at)).limit(20).all()

                if not alerts:
                    await update.message.reply_text(
                        "🔔 您關注的股票最近沒有警報\n"
                        "使用 /watch <股票代號> 來添加更多關注股票"
                    )
                    return

                alert_text = "🔔 *最近警報 (7天內)：*\n\n"

                for alert, stock in alerts:
                    alert_type_emoji = {
                        'BUY': '🟢',
                        'SELL': '🔴',
                        'WATCH': '🟡'
                    }.get(alert.alert_type, '📊')

                    time_str = alert.triggered_at.strftime('%m/%d %H:%M')

                    alert_text += (
                        f"{alert_type_emoji} *{stock.symbol}* {stock.name}\n"
                        f"📍 {alert.signal_name}\n"
                        f"💰 {alert.price}\n"
                        f"📝 {alert.description}\n"
                        f"⏰ {time_str}\n\n"
                    )

                await update.message.reply_text(alert_text, parse_mode='Markdown')

        except Exception as e:
            await update.message.reply_text(f"❌ 獲取警報失敗：{e}")

    @handle_errors()
    async def _portfolio_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /portfolio command"""
        await update.message.reply_text(
            "💼 投資組合功能開發中...\n"
            "敬請期待！"
        )

    @handle_errors()
    async def _settings_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /settings command"""
        keyboard = [
            [InlineKeyboardButton("🔔 通知設定", callback_data="settings_notifications")],
            [InlineKeyboardButton("📊 顯示偏好", callback_data="settings_display")],
            [InlineKeyboardButton("🔙 返回", callback_data="settings_back")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            "⚙️ *個人設定*\n\n請選擇要調整的項目：",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )

    @handle_errors()
    async def _message_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle text messages (stock symbols)"""
        message = update.message.text.strip().upper()

        # Check if it's a stock symbol (digits only, 4-6 characters)
        if message.isdigit() and 4 <= len(message) <= 6:
            await self._send_stock_quote(update, message)
        else:
            await update.message.reply_text(
                "💡 輸入股票代號可查看報價，或使用 /help 查看所有指令"
            )

    @handle_errors()
    async def _button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle inline keyboard callbacks"""
        query = update.callback_query
        await query.answer()

        data = query.data
        if data.startswith("more_info_"):
            symbol = data.split("_")[-1]
            await self._send_detailed_info(query, symbol)
        elif data.startswith("rescreen_"):
            screen_type = data.split("_")[-1]
            await query.edit_message_text(f"🔄 重新篩選 {screen_type} 中...")
            # Implement rescreen logic here

    async def _send_stock_quote(self, update: Update, symbol: str):
        """Send stock quote information"""
        try:
            with db_manager.get_session() as session:
                # Get stock info
                stock = session.query(Stock).filter(Stock.symbol == symbol).first()
                if not stock:
                    await update.message.reply_text(f"❌ 找不到股票代號：{symbol}")
                    return

                # Get real-time data
                realtime = session.query(StockRealtime).filter(
                    StockRealtime.stock_id == stock.id
                ).first()

                # Get technical indicators
                indicator = session.query(TechnicalIndicator).filter(
                    TechnicalIndicator.stock_id == stock.id
                ).order_by(desc(TechnicalIndicator.date)).first()

                # Format quote message
                quote_text = f"📊 *{symbol} {stock.name}*\n"
                quote_text += f"🏢 {stock.market} - {stock.industry or 'N/A'}\n\n"

                if realtime:
                    emoji = "📈" if realtime.change_amount >= 0 else "📉"
                    quote_text += f"{emoji} *價格：{realtime.current_price}*\n"
                    quote_text += f"📊 漲跌：{realtime.change_amount:+.2f} ({realtime.change_percent:+.2f}%)\n"
                    quote_text += f"📦 成交量：{realtime.volume:,}\n\n"

                    if indicator:
                        quote_text += "📈 *技術指標：*\n"
                        if indicator.ma5 and indicator.ma20:
                            quote_text += f"MA5/MA20: {indicator.ma5:.2f} / {indicator.ma20:.2f}\n"
                        if indicator.rsi14:
                            rsi_emoji = "🔴" if indicator.rsi14 > 70 else "🟢" if indicator.rsi14 < 30 else "🟡"
                            quote_text += f"RSI(14): {rsi_emoji} {indicator.rsi14:.2f}\n"

                    update_time = realtime.timestamp.strftime('%H:%M:%S')
                    quote_text += f"\n⏰ 更新時間：{update_time}"
                else:
                    quote_text += "❌ 暫無即時報價資料"

                # Add action buttons
                keyboard = [
                    [
                        InlineKeyboardButton("➕ 加入關注", callback_data=f"watch_{symbol}"),
                        InlineKeyboardButton("📊 詳細資訊", callback_data=f"more_info_{symbol}")
                    ]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)

                await update.message.reply_text(
                    quote_text,
                    parse_mode='Markdown',
                    reply_markup=reply_markup
                )

        except Exception as e:
            await update.message.reply_text(f"❌ 獲取報價失敗：{e}")

    async def _send_detailed_info(self, query, symbol: str):
        """Send detailed stock information"""
        # Implement detailed info display
        await query.edit_message_text(f"📊 {symbol} 詳細資訊功能開發中...")

    async def _register_user(self, telegram_id: str, username: str, first_name: str):
        """Register or update user"""
        try:
            with db_manager.get_session() as session:
                user = session.query(TelegramUser).filter(
                    TelegramUser.telegram_id == telegram_id
                ).first()

                if user:
                    # Update existing user
                    user.username = username
                    user.first_name = first_name
                    user.is_active = True
                else:
                    # Create new user
                    user = TelegramUser(
                        telegram_id=telegram_id,
                        username=username,
                        first_name=first_name
                    )
                    session.add(user)

                session.commit()
                self.logger.info(f"User registered/updated: {telegram_id}")

        except Exception as e:
            self.logger.error(f"Error registering user: {e}")

    async def send_alert_notification(self, alert: Alert, stock: Stock):
        """Send alert notification to relevant users"""
        try:
            with db_manager.get_session() as session:
                # Get users watching this stock
                watchers = session.query(TelegramUser).join(
                    Watchlist, TelegramUser.telegram_id == Watchlist.user_id
                ).filter(
                    and_(
                        Watchlist.stock_id == stock.id,
                        TelegramUser.is_active == True,
                        TelegramUser.alert_enabled == True,
                        alert.alert_type.in_(TelegramUser.alert_types)
                    )
                ).all()

                alert_emoji = {
                    'BUY': '🟢',
                    'SELL': '🔴',
                    'WATCH': '🟡'
                }.get(alert.alert_type, '📊')

                message = (
                    f"{alert_emoji} *交易信號*\n\n"
                    f"📈 *{stock.symbol} {stock.name}*\n"
                    f"🎯 {alert.signal_name}\n"
                    f"💰 價格：{alert.price}\n"
                    f"📝 {alert.description}\n"
                    f"⏰ {alert.triggered_at.strftime('%Y-%m-%d %H:%M:%S')}"
                )

                # Send to each watcher
                for user in watchers:
                    try:
                        await self.application.bot.send_message(
                            chat_id=user.telegram_id,
                            text=message,
                            parse_mode='Markdown'
                        )
                    except Exception as e:
                        self.logger.error(f"Failed to send alert to {user.telegram_id}: {e}")

                self.logger.info(f"Alert sent to {len(watchers)} users")

        except Exception as e:
            self.logger.error(f"Error sending alert notification: {e}")