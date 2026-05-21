"""
MTX Auto Trader — 微台指 (MTX) 自動下單交易系統

執行時間：
  日盤  08:45–13:30 台灣時間
  夜盤  15:00–05:00 台灣時間

使用 Fubon SDK WebSocket 訂閱 aggregates 頻道取得即時報價，
結合 MTXSignalEngine 的多重時間框架策略（日K + 5分K + 1分K）
自動進出場，最多持倉 3 口。

Feature Toggle (settings.mtx_trader.live_order)
  False（預設）→ 模擬模式：不呼叫富邦 API，交易紀錄寫入 Google Sheets「微台交易紀錄」
  True         → 實單模式：透過富邦 e01 SDK 下單
"""
from __future__ import annotations

import asyncio
import json
import signal as _sys_signal
from dataclasses import dataclass, field
from datetime import datetime, time
from enum import Enum
from typing import List, Optional

from ...infrastructure.market_data.fubon_client import FubonClient, get_near_month_symbol
from ...infrastructure.notification.telegram_notifier import TelegramNotifier
from ...infrastructure.persistence.mtx_sheets_recorder import MTXSheetsRecorder
from ...utils.logger import get_logger
from .mtx_signal_engine import MTXSignalEngine, SignalDirection, TradeSignal

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Session detection
# ---------------------------------------------------------------------------

class SessionType(Enum):
    DAY = "day"       # 08:45–13:30 台灣時間
    NIGHT = "night"   # 15:00–05:00 台灣時間（含跨日）
    CLOSED = "closed"


def get_session(now: Optional[datetime] = None) -> SessionType:
    """Determine the current Taiwan-time trading session."""
    t = (now or datetime.now()).time()
    if time(8, 45) <= t < time(13, 31):
        return SessionType.DAY
    if t >= time(15, 0) or t < time(5, 1):
        return SessionType.NIGHT
    return SessionType.CLOSED


# ---------------------------------------------------------------------------
# Domain types
# ---------------------------------------------------------------------------

@dataclass
class Position:
    symbol: str
    direction: str      # 'LONG' | 'SHORT'
    entry_price: float
    lots: int
    entry_time: datetime
    order_no: str = ""


@dataclass
class TradeRecord:
    symbol: str
    direction: str
    entry_price: float
    exit_price: float
    lots: int
    pnl_pts: float
    entry_time: datetime
    exit_time: datetime
    exit_reason: str


# ---------------------------------------------------------------------------
# Trader
# ---------------------------------------------------------------------------

class MTXAutoTrader:
    """
    Automated MTX (微台指) futures trader.

    Parameters
    ----------
    fubon_client : :class:`FubonClient`
        Already-initialised SDK client.
    notifier : :class:`TelegramNotifier`, optional
        Send Telegram alerts on orders and errors.
    dry_run : bool
        When ``True``, log signals but do **not** place real orders.
    stop_loss_pts : float
        Stop-loss distance in index points (default 30).
    take_profit_pts : float
        Take-profit target in index points (default 50).
    max_lots : int
        Maximum position size (default 3).
    """

    SYMBOL_ROOT = "TMF"  # 微型臺指期貨，Fugle product code (非 FIMTX)

    def __init__(
        self,
        fubon_client: FubonClient,
        notifier: Optional[TelegramNotifier] = None,
        dry_run: bool = False,
        stop_loss_pts: float = 15.0,
        take_profit_pts: float = 50.0,
        max_lots: int = 3,
        live_order: Optional[bool] = None,
        sheets_recorder: Optional[MTXSheetsRecorder] = None,
        min_profit_before_kd_exit_pts: float = 8.0,
        late_session_no_entry_minutes: int = 30,
    ) -> None:
        self.client = fubon_client
        self.notifier = notifier
        self.dry_run = dry_run
        self.max_lots = max_lots
        self.late_session_no_entry_minutes = late_session_no_entry_minutes

        # Feature toggle: live_order 明確傳入時使用傳入值，否則從 settings 讀取
        if live_order is not None:
            self.live_order = live_order
        else:
            try:
                from config.settings import settings
                self.live_order = settings.mtx_trader.live_order
            except Exception:
                self.live_order = False  # 安全預設：模擬模式

        # Google Sheets recorder（模擬模式使用）
        self._sheets_recorder = sheets_recorder or MTXSheetsRecorder()

        self.signal_engine = MTXSignalEngine(
            stop_loss_pts=stop_loss_pts,
            take_profit_pts=take_profit_pts,
            min_profit_before_kd_exit_pts=min_profit_before_kd_exit_pts,
        )
        self.position: Optional[Position] = None
        self.trades: List[TradeRecord] = []
        self.running = False
        self._symbol: Optional[str] = None

        # IOC unfilled cooldown: block re-entry until the current 1m bar closes
        # Stores the floored 1-minute timestamp of the bar where IOC failed
        self._ioc_failed_bar_ts: Optional[datetime] = None

        # Graceful shutdown on SIGTERM / SIGINT
        for sig in (_sys_signal.SIGTERM, _sys_signal.SIGINT):
            try:
                _sys_signal.signal(sig, self._handle_shutdown)
            except (ValueError, OSError):
                pass  # Not in main thread — ignore

    # ------------------------------------------------------------------
    # Lifecycle

    def _handle_shutdown(self, signum, _frame) -> None:
        logger.info(f"Signal {signum} received — stopping MTX trader…")
        self.running = False

    @property
    def symbol(self) -> str:
        if self._symbol is None:
            self._symbol = get_near_month_symbol(self.SYMBOL_ROOT)
        return self._symbol

    async def initialize(self) -> None:
        """Login (if needed) and seed historical bar data."""
        if not self.client.is_logged_in:
            await self.client._initialize_sdk()

        self._symbol = get_near_month_symbol(self.SYMBOL_ROOT)
        logger.info(f"MTX symbol: {self._symbol}")

        await self._seed_bars()

    async def _seed_bars(self) -> None:
        """Fetch intraday 1-min / 5-min / daily candles and pre-load the signal engine."""
        session = get_session()
        api_session = "afterhours" if session == SessionType.NIGHT else None

        try:
            c1m = await self.client.get_futures_candles(self.symbol, "1", api_session)
            # Fall back to regular session if afterhours returns no data (e.g. roll day)
            if not c1m and api_session:
                c1m = await self.client.get_futures_candles(self.symbol, "1", None)
            if c1m:
                self.signal_engine.seed_1m(c1m)
                logger.info(f"Seeded {len(c1m)} × 1-min bars")
        except Exception as exc:
            logger.warning(f"1-min seed failed: {exc}")

        try:
            c5m = await self.client.get_futures_candles(self.symbol, "5", api_session)
            # Fall back to regular session if afterhours returns no data (e.g. roll day)
            if not c5m and api_session:
                c5m = await self.client.get_futures_candles(self.symbol, "5", None)
            if c5m:
                self.signal_engine.seed_5m(c5m)
                logger.info(f"Seeded {len(c5m)} × 5-min bars")
        except Exception as exc:
            logger.warning(f"5-min seed failed: {exc}")

        try:
            cd = await self.client.get_futures_candles(self.symbol, "D", None)
            if cd:
                self.signal_engine.seed_daily(cd)
                logger.info(f"Seeded {len(cd)} × daily bars")
        except Exception as exc:
            logger.warning(f"Daily seed failed: {exc}")

    # ------------------------------------------------------------------
    # Main run loop

    async def run(self, session: Optional[SessionType] = None) -> None:
        """
        Start the auto trader.

        Parameters
        ----------
        session : SessionType, optional
            Force a specific session; auto-detect if ``None``.
        """
        self.running = True

        if session is None:
            session = get_session()

        if session == SessionType.CLOSED:
            logger.info("Market currently closed — waiting for next session…")
            await self._wait_for_open()
            session = get_session()

        logger.info(f"Starting MTX trader — session={session.value}")
        is_night = session == SessionType.NIGHT

        try:
            await self._run_session(is_night)
        except Exception as exc:
            logger.exception(f"Unhandled error in trading session: {exc}")
            await self._notify(f"❌ MTX Trader 錯誤：{exc}")
        finally:
            await self._close_all("Session ended")
            self._log_summary()

    async def _wait_for_open(self) -> None:
        while self.running:
            if get_session() != SessionType.CLOSED:
                return
            await asyncio.sleep(30)

    # ------------------------------------------------------------------
    # Session loop

    async def _run_session(self, is_night: bool) -> None:
        if self.dry_run:
            mode_label = "⚠️  DRY RUN（不下單、不記錄）"
        elif not self.live_order:
            mode_label = "📋 模擬模式（記錄至 Google Sheets 微台交易紀錄）"
        else:
            mode_label = "✅ 實單模式（富邦 API 下單）"

        await self._notify(
            f"🟢 MTX 自動交易 啟動 — {'夜盤' if is_night else '日盤'}\n"
            f"商品：{self.symbol} | 最大口數：{self.max_lots}\n"
            f"{mode_label}"
        )

        message_queue: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_event_loop()

        # ------ WebSocket setup ------
        futopt_ws = self.client.sdk.marketdata.websocket_client.futopt
        sub_params: dict = {"channel": "aggregates", "symbol": self.symbol}
        if is_night:
            sub_params["afterHours"] = True

        ws_connected = [False]  # mutable flag accessible from callbacks

        def _on_message(raw_msg) -> None:
            try:
                data = json.loads(raw_msg) if isinstance(raw_msg, str) else raw_msg
                loop.call_soon_threadsafe(message_queue.put_nowait, data)
            except Exception as exc:
                logger.debug(f"WS message parse error: {exc}")

        def _on_authenticated(*_args) -> None:
            """Called after WebSocket auth completes — safe to subscribe."""
            ws_connected[0] = True
            try:
                futopt_ws.subscribe(sub_params)
            except Exception as exc:
                logger.warning(f"訂閱失敗：{exc}")
            logger.warning(
                f"✅ WebSocket 已訂閱 {self.symbol} "
                f"{'[夜盤]' if is_night else '[日盤]'} — 等待行情..."
            )

        def _on_disconnect(*_args) -> None:
            if ws_connected[0]:
                ws_connected[0] = False
                logger.warning("⚠️  WebSocket 斷線，等待重連...")

        # Correct fugle SDK event names: "connect"/"disconnect"/"authenticated"
        futopt_ws.on("authenticated", _on_authenticated)
        futopt_ws.on("message", _on_message)
        futopt_ws.on("error", _on_disconnect)
        futopt_ws.on("disconnect", _on_disconnect)

        def _ws_connect(reconnect: bool = False) -> None:
            """Connect (or reconnect) WebSocket; subscribe is handled by _on_authenticated."""
            import time
            if reconnect:
                try:
                    futopt_ws.disconnect()
                except Exception:
                    pass
                time.sleep(1)  # let old run_forever thread exit before re-connecting
            try:
                futopt_ws.connect()
            except Exception as exc:
                logger.warning(f"WebSocket 重連失敗：{exc}")

        _ws_connect()

        # ------ Session end condition ------
        # Use expected session boundary instead of get_session() to avoid
        # exiting immediately when forced session starts before official open.
        session_end: time = time(13, 31) if not is_night else time(5, 1)

        def _session_should_end() -> bool:
            t = datetime.now().time()
            if not is_night:
                return t >= session_end
            # Night session crosses midnight: end when 05:01 reached from above
            return time(5, 1) <= t < time(8, 45)

        # ------ Main loop ------
        last_seed = datetime.now()
        last_reconnect = datetime.now()

        while self.running:
            # Check if session ended
            if _session_should_end():
                logger.info("Session window closed — exiting loop")
                break

            # Reconnect if WebSocket dropped (throttle: max once per 10s)
            now = datetime.now()
            if not ws_connected[0] and (now - last_reconnect).seconds >= 10:
                last_reconnect = now
                logger.info("🔄 WebSocket 重連中...")
                _ws_connect(reconnect=True)

            # Periodic bar refresh (every 5 min) to stay in sync with REST API
            if (now - last_seed).seconds >= 300:
                await self._seed_bars()
                last_seed = now

            # Drain WebSocket queue
            processed = 0
            while not message_queue.empty() and processed < 50:
                try:
                    msg = message_queue.get_nowait()
                    await self._on_ws_data(msg, is_night)
                    processed += 1
                except asyncio.QueueEmpty:
                    break
                except Exception as exc:
                    logger.warning(f"WS processing error: {exc}")

            await asyncio.sleep(0.2)

        # ------ Cleanup ------
        try:
            futopt_ws.unsubscribe({"channel": "aggregates", "symbol": self.symbol})
        except Exception:
            pass

    # ------------------------------------------------------------------
    # WebSocket message handler

    async def _on_ws_data(self, msg: dict, is_night: bool) -> None:
        if msg.get("event") != "data":
            logger.debug(f"WS non-data event: {msg.get('event')} — {msg}")
            return

        data = msg.get("data") or {}
        price_raw = data.get("lastPrice") or data.get("closePrice")
        if price_raw is None:
            logger.debug(f"WS data without price: {data}")
            return

        price = float(price_raw)
        volume = int(data.get("lastSize") or 0)
        ts = datetime.now()

        logger.debug(f"Tick  {price:.0f}  vol={volume}  {ts.strftime('%H:%M:%S')}")
        self.signal_engine.add_tick(price, volume, ts)

        pos_dir = self.position.direction if self.position else None
        entry_p = self.position.entry_price if self.position else None
        signal = self.signal_engine.evaluate(pos_dir, entry_p)

        await self._handle_signal(signal, is_night)

    # ------------------------------------------------------------------
    # Signal → order execution

    async def _handle_signal(self, signal: TradeSignal, is_night: bool) -> None:
        direction = signal.direction

        if direction == SignalDirection.HOLD:
            return

        price = signal.price

        # ---- Close signals ----
        if direction in (SignalDirection.CLOSE_LONG, SignalDirection.CLOSE_SHORT):
            if self.position:
                await self._close_position(signal.reason, price, is_night)
            return

        # ---- Late session entry guard ----
        if self._is_late_session(is_night):
            logger.debug(f"Late session guard: skip new entry {direction.value}")
            return

        # ---- IOC cooldown: skip entry if last IOC failed in the current 1m bar ----
        current_bar_ts = datetime.now().replace(second=0, microsecond=0)
        if self._ioc_failed_bar_ts is not None and self._ioc_failed_bar_ts >= current_bar_ts:
            logger.debug("IOC cooldown active — skip entry until next 1m bar")
            return

        # ---- Entry signals ----
        if direction == SignalDirection.LONG:
            if self.position and self.position.direction == "SHORT":
                # Reverse: close short first
                await self._close_position("多空反轉", price, is_night)
            if self.position is None and self._open_slots() > 0:
                await self._open_position("LONG", price, 1, signal.reason, is_night)

        elif direction == SignalDirection.SHORT:
            if self.position and self.position.direction == "LONG":
                await self._close_position("多空反轉", price, is_night)
            if self.position is None and self._open_slots() > 0:
                await self._open_position("SHORT", price, 1, signal.reason, is_night)

    def _open_slots(self) -> int:
        used = self.position.lots if self.position else 0
        return max(0, self.max_lots - used)

    def _is_late_session(self, is_night: bool) -> bool:
        """True if within late_session_no_entry_minutes of session end."""
        if self.late_session_no_entry_minutes <= 0:
            return False
        from datetime import timedelta
        now = datetime.now()
        now_t = now.time()
        if not is_night:
            session_end = now.replace(hour=13, minute=31, second=0, microsecond=0)
            if now_t >= time(13, 31):
                return True
            minutes_left = (session_end - now).total_seconds() / 60
        else:
            session_end = now.replace(hour=5, minute=1, second=0, microsecond=0)
            if now_t >= time(5, 1):
                return True
            if now_t >= time(15, 0):
                session_end += timedelta(days=1)
            minutes_left = (session_end - now).total_seconds() / 60
        return minutes_left < self.late_session_no_entry_minutes

    # ------------------------------------------------------------------
    # Order helpers

    async def _open_position(
        self,
        direction: str,
        price: float,
        lots: int,
        reason: str,
        is_night: bool,
    ) -> None:
        logger.info(f"→ OPEN {direction} {lots}L @ {price:.0f} — {reason}")
        session_label = "夜盤" if is_night else "日盤"

        # ── DRY RUN ──
        if self.dry_run:
            self.position = Position(
                symbol=self.symbol, direction=direction,
                entry_price=price, lots=lots,
                entry_time=datetime.now(), order_no="DRY",
            )
            await self._notify(
                f"📋 [DRY RUN] {'🟢 做多' if direction == 'LONG' else '🔴 做空'} {lots}口\n"
                f"進場：{price:.0f}　原因：{reason}"
            )
            return

        # ── 模擬模式 → Google Sheets ──
        if not self.live_order:
            self._sheets_recorder.record_open(
                symbol=self.symbol,
                direction=direction,
                price=price,
                lots=lots,
                reason=reason,
                session=session_label,
            )
            self.position = Position(
                symbol=self.symbol, direction=direction,
                entry_price=price, lots=lots,
                entry_time=datetime.now(), order_no="SIM",
            )
            await self._notify(
                f"📋 [模擬] {'🟢 做多' if direction == 'LONG' else '🔴 做空'} {lots}口\n"
                f"進場：{price:.0f}　原因：{reason}\n"
                f"目標：+{self.signal_engine.take_profit_pts:.0f}pt　"
                f"停損：-{self.signal_engine.stop_loss_pts:.0f}pt"
            )
            return

        # ── 實單模式 → 富邦 API ──
        try:
            buy_sell = "Buy" if direction == "LONG" else "Sell"
            result = await self.client.place_futures_order(
                symbol=self.symbol,
                buy_sell=buy_sell,
                price=str(int(price)),
                lot=lots,
                price_type="Market",
                time_in_force="IOC",
                order_type="New",
                is_night_session=is_night,
            )

            filled_lot = int(result.get("filled_lot") or 0)
            filled_money = float(result.get("filled_money") or 0)

            # IOC 完全未成交 → 不建立倉位，鎖定本根 1m K 棒不再重試
            if filled_lot == 0:
                self._ioc_failed_bar_ts = datetime.now().replace(second=0, microsecond=0)
                logger.warning(f"Open position IOC unfilled (0/{lots}L) — cooldown until next 1m bar")
                await self._notify(
                    f"⚠️ 開倉未成交（IOC 0/{lots}口）\n"
                    f"方向：{direction}　信號價：{price:.0f}\n"
                    f"原因：{reason}　本根K棒不再重試"
                )
                return

            # 用實際成交均價；若券商沒回 filled_money 則退用 signal 報價
            actual_entry = filled_money / filled_lot if filled_money > 0 else price

            if filled_lot < lots:
                logger.warning(f"Open position partially filled: {filled_lot}/{lots}L @ {actual_entry:.0f}")
                await self._notify(
                    f"⚠️ 部分成交 {filled_lot}/{lots}口\n"
                    f"實際進場：{actual_entry:.0f}　原因：{reason}"
                )

            self.position = Position(
                symbol=self.symbol, direction=direction,
                entry_price=actual_entry, lots=filled_lot,
                entry_time=datetime.now(),
                order_no=result.get("order_no", ""),
            )
            await self._notify(
                f"{'🟢 做多' if direction == 'LONG' else '🔴 做空'} {filled_lot}口 進場\n"
                f"進場：{actual_entry:.0f}　原因：{reason}\n"
                f"目標：+{self.signal_engine.take_profit_pts:.0f}pt　"
                f"停損：-{self.signal_engine.stop_loss_pts:.0f}pt"
            )
        except Exception as exc:
            logger.error(f"Open position failed: {exc}")
            await self._notify(f"❌ 開倉失敗：{exc}")

    async def _close_position(self, reason: str, price: float, is_night: bool) -> None:
        if not self.position:
            return

        pos = self.position
        pnl = (
            price - pos.entry_price
            if pos.direction == "LONG"
            else pos.entry_price - price
        )
        logger.info(f"→ CLOSE {pos.direction} @ {price:.0f} | PnL={pnl:+.0f}pts — {reason}")
        session_label = "夜盤" if is_night else "日盤"

        # ── DRY RUN ── （不下單、不寫 Sheets）
        if self.dry_run:
            pass  # fall through to trade record

        # ── 模擬模式 → Google Sheets ──
        elif not self.live_order:
            self._sheets_recorder.record_close(
                symbol=pos.symbol,
                direction=pos.direction,
                price=price,
                lots=pos.lots,
                pnl_pts=pnl,
                reason=reason,
                session=session_label,
            )

        # ── 實單模式 → 富邦 API ──
        else:
            buy_sell = "Sell" if pos.direction == "LONG" else "Buy"
            try:
                await self.client.place_futures_order(
                    symbol=self.symbol,
                    buy_sell=buy_sell,
                    price=str(int(price)),
                    lot=pos.lots,
                    price_type="Market",
                    time_in_force="IOC",
                    order_type="Close",
                    is_night_session=is_night,
                )
            except Exception as exc:
                logger.error(f"Close position failed: {exc}")
                await self._notify(f"❌ 平倉失敗：{exc}")
                return

        self.trades.append(
            TradeRecord(
                symbol=pos.symbol,
                direction=pos.direction,
                entry_price=pos.entry_price,
                exit_price=price,
                lots=pos.lots,
                pnl_pts=pnl * pos.lots,
                entry_time=pos.entry_time,
                exit_time=datetime.now(),
                exit_reason=reason,
            )
        )
        self.position = None

        mode_tag = "[DRY RUN] " if self.dry_run else ("[模擬] " if not self.live_order else "")
        emoji = "✅" if pnl >= 0 else "🛑"
        await self._notify(
            f"{mode_tag}{emoji} {'平多' if pos.direction == 'LONG' else '平空'} {pos.lots}口\n"
            f"出場：{price:.0f}　損益：{pnl * pos.lots:+.0f}pt\n"
            f"原因：{reason}"
        )

    async def _close_all(self, reason: str) -> None:
        if self.position:
            session = get_session()
            is_night = session == SessionType.NIGHT
            price = self.signal_engine.last_price or self.position.entry_price
            await self._close_position(reason, price, is_night)

    # ------------------------------------------------------------------
    # Utilities

    def _log_summary(self) -> None:
        total_pnl = sum(t.pnl_pts for t in self.trades)
        wins = sum(1 for t in self.trades if t.pnl_pts > 0)
        logger.info(
            f"=== 交易結果 ===  共 {len(self.trades)} 筆  "
            f"勝 {wins}  總損益 {total_pnl:+.0f}pts"
        )
        for t in self.trades:
            logger.info(
                f"  {t.direction} {t.lots}L  "
                f"{t.entry_price:.0f}→{t.exit_price:.0f}  "
                f"{t.pnl_pts:+.0f}pts  [{t.exit_reason}]"
            )

    async def _notify(self, msg: str) -> None:
        logger.info(f"[NOTIFY] {msg}")
        if self.notifier:
            try:
                self.notifier.send_message(msg)
            except Exception as exc:
                logger.warning(f"Telegram notify failed: {exc}")
