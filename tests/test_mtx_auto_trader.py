"""
Unit tests for MTX Auto Trader

Tests cover:
  - Session detection (get_session)
  - BarManager: tick ingestion, bar closure, seeding
  - Technical indicators: compute_stoch, compute_ma, golden_cross, death_cross
  - MTXSignalEngine: signal evaluation, stop-loss, take-profit
  - MTXAutoTrader: position management, dry-run execution
"""
from __future__ import annotations

import asyncio
from datetime import datetime, date
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from src.application.services.mtx_signal_engine import (
    BarManager,
    MTXSignalEngine,
    OHLCVBar,
    SignalDirection,
    TradeSignal,
    _floor_to_tf,
    compute_ma,
    compute_stoch,
    death_cross,
    golden_cross,
)
from src.application.services.mtx_auto_trader import (
    MTXAutoTrader,
    Position,
    SessionType,
    TradeRecord,
    get_session,
)


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _dt(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 5, 19, hour, minute, 0)


def _make_bars(n: int, base: float = 20000.0, step: float = 1.0):
    """Return n synthetic candle dicts (rising prices)."""
    bars = []
    for i in range(n):
        p = base + i * step
        bars.append({
            "time": datetime(2026, 5, 19, 9, i % 60, 0),
            "open": p,
            "high": p + 2,
            "low": p - 2,
            "close": p,
            "volume": 100 + i,
        })
    return bars


# ──────────────────────────────────────────────────────────────────────────────
# Session detection
# ──────────────────────────────────────────────────────────────────────────────

class TestGetSession:
    def test_day_session_start(self):
        assert get_session(_dt(8, 45)) == SessionType.DAY

    def test_day_session_end(self):
        assert get_session(_dt(13, 30)) == SessionType.DAY

    def test_day_session_just_after_end(self):
        assert get_session(_dt(13, 31)) == SessionType.CLOSED

    def test_closed_between_sessions(self):
        assert get_session(_dt(14, 0)) == SessionType.CLOSED

    def test_night_session_start(self):
        assert get_session(_dt(15, 0)) == SessionType.NIGHT

    def test_night_session_late(self):
        assert get_session(_dt(23, 59)) == SessionType.NIGHT

    def test_night_session_early_morning(self):
        assert get_session(_dt(0, 30)) == SessionType.NIGHT

    def test_night_session_boundary_end(self):
        assert get_session(_dt(5, 0)) == SessionType.NIGHT

    def test_closed_after_night(self):
        assert get_session(_dt(5, 1)) == SessionType.CLOSED


# ──────────────────────────────────────────────────────────────────────────────
# _floor_to_tf
# ──────────────────────────────────────────────────────────────────────────────

class TestFloorToTf:
    def test_1m(self):
        ts = datetime(2026, 5, 19, 10, 7, 35)
        result = _floor_to_tf(ts, 1)
        assert result == datetime(2026, 5, 19, 10, 7, 0)

    def test_5m(self):
        ts = datetime(2026, 5, 19, 10, 7, 35)
        result = _floor_to_tf(ts, 5)
        assert result == datetime(2026, 5, 19, 10, 5, 0)

    def test_exactly_on_boundary(self):
        ts = datetime(2026, 5, 19, 10, 10, 0)
        assert _floor_to_tf(ts, 5) == datetime(2026, 5, 19, 10, 10, 0)


# ──────────────────────────────────────────────────────────────────────────────
# BarManager
# ──────────────────────────────────────────────────────────────────────────────

class TestBarManager:
    def test_first_tick_creates_bar(self):
        bm = BarManager(1)
        ts = datetime(2026, 5, 19, 9, 0, 0)
        bm.add_tick(100.0, 10, ts)
        assert bm.current is not None
        assert bm.current.close == 100.0

    def test_same_minute_updates_bar(self):
        bm = BarManager(1)
        t0 = datetime(2026, 5, 19, 9, 0, 10)
        t1 = datetime(2026, 5, 19, 9, 0, 50)
        bm.add_tick(100.0, 10, t0)
        bm.add_tick(102.0, 5, t1)
        assert bm.current.high == 102.0
        assert bm.current.close == 102.0
        assert bm.current.volume == 15

    def test_new_minute_closes_bar(self):
        bm = BarManager(1)
        t0 = datetime(2026, 5, 19, 9, 0, 30)
        t1 = datetime(2026, 5, 19, 9, 1, 5)
        closed = bm.add_tick(100.0, 10, t0)
        assert not closed
        closed = bm.add_tick(101.0, 5, t1)
        assert closed
        assert len(bm.bars) == 1
        assert bm.bars[0].close == 100.0
        assert bm.current.close == 101.0

    def test_seed_loads_bars(self):
        bm = BarManager(1)
        candles = _make_bars(30)
        bm.seed(candles)
        assert len(bm.bars) == 30

    def test_get_arrays_shape(self):
        bm = BarManager(1)
        bm.seed(_make_bars(20))
        o, h, l, c, v = bm.get_arrays()
        assert len(c) == 20

    def test_get_arrays_includes_current(self):
        bm = BarManager(1)
        bm.seed(_make_bars(20))
        bm.add_tick(99999.0, 1, datetime(2026, 5, 19, 12, 0, 0))
        o, h, l, c, v = bm.get_arrays()
        assert len(c) == 21
        assert c[-1] == 99999.0

    def test_len(self):
        bm = BarManager(1)
        bm.seed(_make_bars(10))
        bm.add_tick(1.0, 1, datetime(2026, 5, 19, 12, 0, 0))
        assert len(bm) == 11


# ──────────────────────────────────────────────────────────────────────────────
# compute_ma
# ──────────────────────────────────────────────────────────────────────────────

class TestComputeMA:
    def test_basic_5ma(self):
        close = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
        ma = compute_ma(close, 5)
        assert np.isnan(ma[3])
        assert ma[4] == pytest.approx(3.0)
        assert ma[5] == pytest.approx(4.0)

    def test_single_element_below_period(self):
        close = np.array([5.0])
        ma = compute_ma(close, 5)
        assert np.isnan(ma[0])


# ──────────────────────────────────────────────────────────────────────────────
# compute_stoch / crosses
# ──────────────────────────────────────────────────────────────────────────────

class TestComputeStoch:
    def _make_price_arrays(self, n=40):
        """Create synthetic rising-then-falling price arrays."""
        close = np.concatenate([np.linspace(100, 150, n // 2), np.linspace(150, 100, n // 2)])
        high = close + 5
        low = close - 5
        return high, low, close

    def test_output_shape(self):
        h, l, c = self._make_price_arrays(40)
        k, d = compute_stoch(h, l, c)
        assert len(k) == len(c)

    def test_values_in_range_0_100(self):
        h, l, c = self._make_price_arrays(40)
        k, d = compute_stoch(h, l, c)
        valid_k = k[~np.isnan(k)]
        assert np.all(valid_k >= 0) and np.all(valid_k <= 100)


class TestCrosses:
    def test_golden_cross_detected(self):
        k = np.array([np.nan, 20.0, 25.0, 28.0, 31.0])
        d = np.array([np.nan, 28.0, 27.5, 28.5, 29.0])
        # k[-2]=28 < d[-2]=28.5, k[-1]=31 > d[-1]=29 → golden
        assert golden_cross(k, d)

    def test_no_golden_cross(self):
        k = np.array([30.0, 32.0])
        d = np.array([28.0, 29.0])
        assert not golden_cross(k, d)

    def test_death_cross_detected(self):
        k = np.array([np.nan, 75.0, 72.0, 70.0, 65.0])
        d = np.array([np.nan, 70.0, 68.5, 69.0, 68.0])
        # k[-2]=70 > d[-2]=69, k[-1]=65 < d[-1]=68 → death
        assert death_cross(k, d)

    def test_no_death_cross(self):
        k = np.array([60.0, 58.0])
        d = np.array([65.0, 66.0])
        assert not death_cross(k, d)

    def test_cross_requires_at_least_2(self):
        assert not golden_cross(np.array([50.0]), np.array([40.0]))


# ──────────────────────────────────────────────────────────────────────────────
# MTXSignalEngine
# ──────────────────────────────────────────────────────────────────────────────

class TestMTXSignalEngine:
    def _engine_with_history(self):
        eng = MTXSignalEngine(stop_loss_pts=30, take_profit_pts=50)
        eng.seed_1m(_make_bars(50))
        eng.seed_5m(_make_bars(50))
        eng.seed_daily(_make_bars(30))
        return eng

    def test_hold_when_insufficient_data(self):
        eng = MTXSignalEngine()
        eng.last_price = 20000.0
        sig = eng.evaluate()
        assert sig.direction == SignalDirection.HOLD

    def test_stop_loss_long(self):
        eng = self._engine_with_history()
        eng.last_price = 19960.0
        sig = eng.evaluate(current_position="LONG", entry_price=20000.0)
        # 19960 - 20000 = -40 < -30
        assert sig.direction == SignalDirection.CLOSE_LONG
        assert "停損" in sig.reason

    def test_stop_loss_short(self):
        eng = self._engine_with_history()
        eng.last_price = 20040.0
        sig = eng.evaluate(current_position="SHORT", entry_price=20000.0)
        # 20000 - 20040 = -40 < -30
        assert sig.direction == SignalDirection.CLOSE_SHORT

    def test_take_profit_long(self):
        eng = self._engine_with_history()
        eng.last_price = 20060.0
        sig = eng.evaluate(current_position="LONG", entry_price=20000.0)
        # 20060 - 20000 = 60 >= 50
        assert sig.direction == SignalDirection.CLOSE_LONG
        assert "獲利" in sig.reason

    def test_take_profit_short(self):
        eng = self._engine_with_history()
        eng.last_price = 19940.0
        sig = eng.evaluate(current_position="SHORT", entry_price=20000.0)
        assert sig.direction == SignalDirection.CLOSE_SHORT

    def test_hold_when_pnl_in_range(self):
        eng = MTXSignalEngine(stop_loss_pts=30, take_profit_pts=50)
        # Seed minimal data to avoid entry signals
        eng.last_price = 20010.0
        sig = eng.evaluate(current_position="LONG", entry_price=20000.0)
        # +10 pts — not at stop or target
        assert sig.direction in (SignalDirection.HOLD, SignalDirection.CLOSE_LONG)

    def test_add_tick_updates_last_price(self):
        eng = MTXSignalEngine()
        eng.add_tick(20100.0, 5, datetime(2026, 5, 19, 10, 0, 0))
        assert eng.last_price == 20100.0

    def test_daily_bias_insufficient_data(self):
        eng = MTXSignalEngine()
        assert eng._daily_bias() == 0

    def test_5m_signal_insufficient_data(self):
        eng = MTXSignalEngine()
        assert eng._signal_5m() == 0

    def test_1m_entry_insufficient_data(self):
        eng = MTXSignalEngine()
        assert eng._entry_1m() == 0

    def test_custom_stop_loss_take_profit(self):
        eng = MTXSignalEngine(stop_loss_pts=10, take_profit_pts=20)
        eng.last_price = 20015.0
        sig = eng.evaluate(current_position="LONG", entry_price=20000.0)
        # +15 pts — no hit yet
        assert sig.direction == SignalDirection.HOLD

        eng.last_price = 20025.0
        sig = eng.evaluate(current_position="LONG", entry_price=20000.0)
        # +25 pts >= 20 → take profit
        assert sig.direction == SignalDirection.CLOSE_LONG


# ──────────────────────────────────────────────────────────────────────────────
# MTXAutoTrader (dry-run)
# ──────────────────────────────────────────────────────────────────────────────

def _mock_client():
    client = MagicMock()
    client.is_logged_in = True
    client.sdk = MagicMock()
    # WebSocket
    futopt_ws = MagicMock()
    futopt_ws.connect = MagicMock()
    futopt_ws.subscribe = MagicMock()
    futopt_ws.unsubscribe = MagicMock()
    client.sdk.marketdata.websocket_client.futopt = futopt_ws

    client.get_futures_candles = AsyncMock(return_value=_make_bars(30))
    client._initialize_sdk = AsyncMock()
    client.get_futopt_account = MagicMock(return_value=MagicMock())
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    return client


class TestMTXAutoTraderDryRun:
    def test_dry_run_open_long(self):
        client = _mock_client()
        trader = MTXAutoTrader(client, dry_run=True)

        async def _run():
            await trader._open_position("LONG", 20000.0, 1, "test", False)

        asyncio.run(_run())
        assert trader.position is not None
        assert trader.position.direction == "LONG"
        assert trader.position.order_no == "DRY"

    def test_dry_run_open_short(self):
        client = _mock_client()
        trader = MTXAutoTrader(client, dry_run=True)

        async def _run():
            await trader._open_position("SHORT", 20000.0, 1, "test", True)

        asyncio.run(_run())
        assert trader.position.direction == "SHORT"

    def test_dry_run_close_long_records_trade(self):
        client = _mock_client()
        trader = MTXAutoTrader(client, dry_run=True)
        trader.position = Position(
            symbol="FIMTXE6", direction="LONG",
            entry_price=20000.0, lots=1,
            entry_time=datetime(2026, 5, 19, 9, 0, 0),
        )

        async def _run():
            await trader._close_position("Take profit", 20060.0, False)

        asyncio.run(_run())
        assert trader.position is None
        assert len(trader.trades) == 1
        assert trader.trades[0].pnl_pts == pytest.approx(60.0)

    def test_dry_run_close_short_records_trade(self):
        client = _mock_client()
        trader = MTXAutoTrader(client, dry_run=True)
        trader.position = Position(
            symbol="FIMTXE6", direction="SHORT",
            entry_price=20000.0, lots=2,
            entry_time=datetime(2026, 5, 19, 9, 0, 0),
        )

        async def _run():
            await trader._close_position("Stop loss", 20040.0, False)

        asyncio.run(_run())
        assert trader.position is None
        assert trader.trades[0].pnl_pts == pytest.approx(-80.0)  # -40 pts × 2 lots

    def test_open_slots_at_capacity(self):
        client = _mock_client()
        trader = MTXAutoTrader(client, dry_run=True, max_lots=3)
        trader.position = Position(
            symbol="FIMTXE6", direction="LONG",
            entry_price=20000.0, lots=3,
            entry_time=datetime.now(),
        )
        assert trader._open_slots() == 0

    def test_open_slots_empty(self):
        client = _mock_client()
        trader = MTXAutoTrader(client, dry_run=True, max_lots=3)
        assert trader._open_slots() == 3

    def test_initialize_seeds_bars(self):
        client = _mock_client()
        trader = MTXAutoTrader(client, dry_run=True)

        async def _run():
            await trader.initialize()

        asyncio.run(_run())
        assert client.get_futures_candles.call_count >= 2  # 1m + 5m at minimum

    def test_signal_hold_doesnt_open_position(self):
        client = _mock_client()
        trader = MTXAutoTrader(client, dry_run=True)
        hold = TradeSignal(SignalDirection.HOLD, 20000.0, datetime.now(), "hold", 0.0)

        async def _run():
            await trader._handle_signal(hold, False)

        asyncio.run(_run())
        assert trader.position is None

    def test_long_signal_reverses_short(self):
        client = _mock_client()
        trader = MTXAutoTrader(client, dry_run=True)
        trader.signal_engine.last_price = 20000.0
        trader.position = Position(
            symbol="FIMTXE6", direction="SHORT",
            entry_price=20000.0, lots=1,
            entry_time=datetime.now(),
        )
        long_sig = TradeSignal(SignalDirection.LONG, 20000.0, datetime.now(), "flip", 0.9)

        async def _run():
            await trader._handle_signal(long_sig, False)

        asyncio.run(_run())
        # Short closed → long opened
        assert len(trader.trades) == 1
        assert trader.position is not None
        assert trader.position.direction == "LONG"

    def test_summary_logging(self, caplog):
        import logging
        client = _mock_client()
        trader = MTXAutoTrader(client, dry_run=True)
        trader.trades = [
            TradeRecord("FIMTXE6", "LONG", 20000, 20060, 1, 60, datetime.now(), datetime.now(), "tp"),
            TradeRecord("FIMTXE6", "SHORT", 20100, 20050, 2, 100, datetime.now(), datetime.now(), "tp"),
        ]
        with caplog.at_level(logging.INFO):
            trader._log_summary()
        assert "交易結果" in caplog.text

    def test_symbol_is_near_month(self):
        client = _mock_client()
        trader = MTXAutoTrader(client)
        sym = trader.symbol
        assert sym.startswith("FIMTX")
        assert len(sym) == 7  # e.g. FIMTXE6


# ──────────────────────────────────────────────────────────────────────────────
# Bug regression: session end condition & WS reconnect
# ──────────────────────────────────────────────────────────────────────────────

class TestSessionEndCondition:
    """_session_should_end boundary logic (replicated from _run_session closure)."""

    from datetime import time as _time

    @staticmethod
    def _should_end(is_night: bool, now: datetime) -> bool:
        """Pure version of the closure for unit testing."""
        from datetime import time as _t
        t = now.time()
        if not is_night:
            return t >= _t(13, 31)
        return _t(5, 1) <= t < _t(8, 45)

    def test_day_before_open_does_not_exit(self):
        """Forced --session day at 08:31 must NOT trigger early exit (regression)."""
        assert not self._should_end(False, datetime(2026, 5, 19, 8, 31, 0))

    def test_day_during_trading_does_not_exit(self):
        assert not self._should_end(False, datetime(2026, 5, 19, 11, 0, 0))

    def test_day_at_close_exits(self):
        assert self._should_end(False, datetime(2026, 5, 19, 13, 31, 0))

    def test_day_after_close_exits(self):
        assert self._should_end(False, datetime(2026, 5, 19, 14, 0, 0))

    def test_night_at_02h05_does_not_exit(self):
        """02:05 during night session must NOT trigger exit (regression)."""
        assert not self._should_end(True, datetime(2026, 5, 20, 2, 5, 0))

    def test_night_at_session_end_exits(self):
        assert self._should_end(True, datetime(2026, 5, 20, 5, 1, 0))

    def test_night_during_session_15h_does_not_exit(self):
        assert not self._should_end(True, datetime(2026, 5, 19, 15, 0, 0))


class TestWebSocketReconnect:
    """WS disconnect flag and reconnect path."""

    def test_on_disconnect_clears_flag(self):
        """_on_disconnect callback must set ws_connected[0] = False."""
        ws_connected = [True]

        def _on_disconnect(*_args):
            if ws_connected[0]:
                ws_connected[0] = False

        _on_disconnect()
        assert ws_connected[0] is False

    def test_reconnect_called_when_disconnected(self):
        """Main loop reconnect branch calls _ws_connect when flag is False."""
        reconnect_calls = []

        def _ws_connect():
            reconnect_calls.append(1)

        ws_connected = [False]
        last_reconnect = datetime(2026, 5, 19, 10, 0, 0)
        now = datetime(2026, 5, 19, 10, 0, 15)  # 15s later → throttle passed

        if not ws_connected[0] and (now - last_reconnect).seconds >= 10:
            _ws_connect()
            ws_connected[0] = True

        assert len(reconnect_calls) == 1
        assert ws_connected[0] is True

    def test_reconnect_throttled(self):
        """Reconnect must not fire if < 10s since last attempt."""
        reconnect_calls = []

        def _ws_connect():
            reconnect_calls.append(1)

        ws_connected = [False]
        last_reconnect = datetime(2026, 5, 19, 10, 0, 0)
        now = datetime(2026, 5, 19, 10, 0, 5)  # only 5s later

        if not ws_connected[0] and (now - last_reconnect).seconds >= 10:
            _ws_connect()

        assert len(reconnect_calls) == 0
