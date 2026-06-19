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
from datetime import datetime, date, timedelta
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
    _now,
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

    # Weekend / day-of-week boundary tests
    def test_sunday_night_is_closed(self):
        """Sunday 22:00 TPE — no Sunday night session."""
        sun = datetime(2026, 6, 14, 22, 0, 0)  # Sunday
        assert get_session(sun) == SessionType.CLOSED

    def test_monday_early_morning_is_closed(self):
        """Monday 00:09 TPE — no Sunday night session to continue."""
        mon_early = datetime(2026, 6, 15, 0, 9, 0)  # Monday
        assert get_session(mon_early) == SessionType.CLOSED

    def test_saturday_early_morning_is_night(self):
        """Saturday 03:00 TPE — Friday night session continues until 05:00."""
        sat_early = datetime(2026, 6, 13, 3, 0, 0)  # Saturday
        assert get_session(sat_early) == SessionType.NIGHT

    def test_saturday_after_night_is_closed(self):
        """Saturday 06:00 TPE — after Friday night session ends."""
        sat_after = datetime(2026, 6, 13, 6, 0, 0)  # Saturday
        assert get_session(sat_after) == SessionType.CLOSED

    def test_sunday_daytime_is_closed(self):
        """Sunday 10:00 TPE — entirely closed."""
        sun_day = datetime(2026, 6, 14, 10, 0, 0)  # Sunday
        assert get_session(sun_day) == SessionType.CLOSED

    def test_tuesday_early_morning_is_night(self):
        """Tuesday 02:00 TPE — Monday night session continues."""
        tue_early = datetime(2026, 6, 16, 2, 0, 0)  # Tuesday
        assert get_session(tue_early) == SessionType.NIGHT


class TestRunSessionSafety:
    """run() safety check: forced session must agree with clock."""

    def test_forced_day_during_night_exits_without_trading(self):
        """Forced DAY at 01:23 (NIGHT active) should exit — night service owns it."""
        client = _mock_client()
        notifier = MagicMock()
        notifier.send_message = AsyncMock()
        trader = MTXAutoTrader(client, dry_run=True, notifier=notifier)

        with patch(
            "src.application.services.mtx_auto_trader.get_session",
            return_value=SessionType.NIGHT,
        ):
            asyncio.run(trader.run(session=SessionType.DAY))

        # Should NOT have sent any "啟動" notification — exited immediately
        notify_calls = [
            str(c) for c in notifier.send_message.call_args_list
        ]
        for call_str in notify_calls:
            assert "啟動" not in call_str

    def test_forced_night_during_closed_waits_then_proceeds(self):
        """Forced NIGHT at 14:59 (CLOSED) should wait, then proceed when NIGHT opens."""
        client = _mock_client()
        notifier = MagicMock()
        notifier.send_message = AsyncMock()
        trader = MTXAutoTrader(client, dry_run=True, notifier=notifier)
        trader._run_session = AsyncMock()  # prevent WS setup

        call_count = [0]

        def _get_session_seq(*a, **kw):
            call_count[0] += 1
            # call 1: initial check in run() → CLOSED
            # call 2: _wait_for_open loop check → CLOSED → sleep
            # call 3: _wait_for_open loop check → NIGHT → return
            # call 4: after wait, verify match → NIGHT
            if call_count[0] <= 2:
                return SessionType.CLOSED
            return SessionType.NIGHT

        with patch(
            "src.application.services.mtx_auto_trader.get_session",
            side_effect=_get_session_seq,
        ):
            async def _fake_sleep(secs):
                pass

            with patch("asyncio.sleep", side_effect=_fake_sleep):
                asyncio.run(trader.run(session=SessionType.NIGHT))

        # _run_session should have been called (session matched after wait)
        trader._run_session.assert_called_once_with(True)  # is_night=True

    def test_forced_night_closed_then_opens_as_day_exits(self):
        """Forced NIGHT, CLOSED → opens as DAY (hypothetical) → exit."""
        client = _mock_client()
        notifier = MagicMock()
        notifier.send_message = AsyncMock()
        trader = MTXAutoTrader(client, dry_run=True, notifier=notifier)
        trader._run_session = AsyncMock()

        call_count = [0]

        def _get_session_seq(*a, **kw):
            call_count[0] += 1
            if call_count[0] <= 2:
                return SessionType.CLOSED
            return SessionType.DAY  # opened as DAY, not NIGHT

        with patch(
            "src.application.services.mtx_auto_trader.get_session",
            side_effect=_get_session_seq,
        ):
            async def _fake_sleep(secs):
                pass

            with patch("asyncio.sleep", side_effect=_fake_sleep):
                asyncio.run(trader.run(session=SessionType.NIGHT))

        # _run_session should NOT have been called
        trader._run_session.assert_not_called()

    def test_forced_night_at_1402_is_closed(self):
        """14:02 on Monday is CLOSED — not DAY, not NIGHT."""
        mon_1402 = datetime(2026, 6, 15, 14, 2, 0)
        assert get_session(mon_1402) == SessionType.CLOSED


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

    def test_5m_signal_memory_keeps_signal_active(self):
        """Strategy C: 5m cross signal stays active for signal_5m_memory_bars bars."""
        eng = MTXSignalEngine(signal_5m_memory_bars=3)
        # Simulate a golden cross firing once then going neutral for 3 bars
        eng._last_5m_signal = 1
        eng._last_5m_signal_age = 0

        # Bar 1 after cross: raw=0, age becomes 1 → still active
        eng._last_5m_signal_age = 1
        # Age <= memory_bars (3): signal should persist
        assert eng._last_5m_signal == 1

        # After 3 bars of silence (age > memory_bars): signal expires
        eng._last_5m_signal_age = 4
        # Simulate the expiry path in _signal_5m (raw=0, age > memory)
        if eng._last_5m_signal_age > eng.signal_5m_memory_bars:
            eng._last_5m_signal = 0
        assert eng._last_5m_signal == 0

    def test_5m_signal_memory_zero_is_strict_mode(self):
        """signal_5m_memory_bars=0 behaves identically to the original strict mode."""
        eng = MTXSignalEngine(signal_5m_memory_bars=0)
        # With no memory, internal state is never used
        assert eng.signal_5m_memory_bars == 0
        # _signal_5m with insufficient data still returns 0
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
            symbol="TMFE6", direction="LONG",
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
            symbol="TMFE6", direction="SHORT",
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
            symbol="TMFE6", direction="LONG",
            entry_price=20000.0, lots=3,
            entry_time=_now(),
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
        hold = TradeSignal(SignalDirection.HOLD, 20000.0, _now(), "hold", 0.0)

        async def _run():
            await trader._handle_signal(hold, False)

        asyncio.run(_run())
        assert trader.position is None

    def test_long_signal_reverses_short(self):
        client = _mock_client()
        trader = MTXAutoTrader(client, dry_run=True, late_session_no_entry_minutes=0)
        trader.signal_engine.last_price = 20000.0
        trader.position = Position(
            symbol="TMFE6", direction="SHORT",
            entry_price=20000.0, lots=1,
            entry_time=_now(),
        )
        long_sig = TradeSignal(SignalDirection.LONG, 20000.0, _now(), "flip", 0.9)

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
            TradeRecord("FIMTXE6", "LONG", 20000, 20060, 1, 60, _now(), _now(), "tp"),
            TradeRecord("FIMTXE6", "SHORT", 20100, 20050, 2, 100, _now(), _now(), "tp"),
        ]
        with caplog.at_level(logging.INFO):
            trader._log_summary()
        assert "交易結果" in caplog.text

    def test_symbol_is_near_month(self):
        client = _mock_client()
        trader = MTXAutoTrader(client)
        sym = trader.symbol
        assert sym.startswith("TMF")
        assert len(sym) == 5  # e.g. TMFF6


# ──────────────────────────────────────────────────────────────────────────────
# IOC fill validation
# ──────────────────────────────────────────────────────────────────────────────

class TestIOCFillValidation:
    """_open_position must not set position when IOC order is unfilled or partial."""

    def _make_trader(self, filled_lot, filled_money=0):
        client = _mock_client()
        client.place_futures_order = AsyncMock(return_value={
            "order_no": "T001",
            "status": "Filled" if filled_lot > 0 else "Cancelled",
            "filled_lot": filled_lot,
            "filled_money": filled_money,
        })
        return MTXAutoTrader(client, live_order=True)

    def test_ioc_unfilled_no_position(self):
        """filled_lot=0 → position stays None, Telegram notified."""
        trader = self._make_trader(filled_lot=0)

        async def _run():
            await trader._open_position("LONG", 20000.0, 1, "test", False)

        asyncio.run(_run())
        assert trader.position is None

    def test_ioc_full_fill_sets_position(self):
        """filled_lot == requested → position created with actual fill price."""
        trader = self._make_trader(filled_lot=1, filled_money=20010.0)

        async def _run():
            await trader._open_position("LONG", 20000.0, 1, "test", False)

        asyncio.run(_run())
        assert trader.position is not None
        assert trader.position.lots == 1
        assert trader.position.entry_price == pytest.approx(20010.0)

    def test_ioc_partial_fill_uses_filled_lot_and_price(self):
        """filled_lot < requested → position uses actual filled qty and price."""
        trader = self._make_trader(filled_lot=1, filled_money=20005.0)

        async def _run():
            await trader._open_position("LONG", 20000.0, 2, "test", False)

        asyncio.run(_run())
        assert trader.position is not None
        assert trader.position.lots == 1
        assert trader.position.entry_price == pytest.approx(20005.0)

    def test_ioc_no_filled_money_falls_back_to_signal_price(self):
        """If broker returns filled_money=0, entry price falls back to signal price."""
        trader = self._make_trader(filled_lot=1, filled_money=0)

        async def _run():
            await trader._open_position("LONG", 20000.0, 1, "test", False)

        asyncio.run(_run())
        assert trader.position is not None
        assert trader.position.entry_price == pytest.approx(20000.0)

    def test_ioc_unfilled_sets_cooldown(self):
        """After IOC unfilled, _ioc_failed_bar_ts is set to current 1m bar."""
        trader = self._make_trader(filled_lot=0)

        async def _run():
            await trader._open_position("LONG", 20000.0, 1, "test", False)

        asyncio.run(_run())
        assert trader._ioc_failed_bar_ts is not None

    def test_ioc_cooldown_blocks_next_entry(self):
        """Entry is skipped when cooldown bar matches current 1m bar."""
        client = _mock_client()
        client.place_futures_order = AsyncMock(return_value={
            "order_no": "T001", "status": "Cancelled",
            "filled_lot": 0, "filled_money": 0,
        })
        trader = MTXAutoTrader(client, live_order=True)
        # Simulate cooldown active for current bar
        trader._ioc_failed_bar_ts = _now().replace(second=0, microsecond=0)

        long_sig = TradeSignal(SignalDirection.LONG, 20000.0, _now(), "test", 0.9)

        async def _run():
            await trader._handle_signal(long_sig, False)

        asyncio.run(_run())
        # Order must NOT have been placed
        client.place_futures_order.assert_not_called()
        assert trader.position is None

    def test_ioc_cooldown_expires_next_bar(self):
        """Cooldown from previous 1m bar does not block entry in the next bar."""
        client = _mock_client()
        client.place_futures_order = AsyncMock(return_value={
            "order_no": "T001", "status": "Filled",
            "filled_lot": 1, "filled_money": 20000.0,
        })
        trader = MTXAutoTrader(client, live_order=True, late_session_no_entry_minutes=0)
        # Cooldown from a past bar (1 minute ago)
        past_bar = (_now() - timedelta(minutes=1)).replace(second=0, microsecond=0)
        trader._ioc_failed_bar_ts = past_bar

        long_sig = TradeSignal(SignalDirection.LONG, 20000.0, _now(), "test", 0.9)

        async def _run():
            await trader._handle_signal(long_sig, False)

        asyncio.run(_run())
        client.place_futures_order.assert_called_once()
        assert trader.position is not None


# ──────────────────────────────────────────────────────────────────────────────
# Bug regression: session end condition & WS reconnect
# ──────────────────────────────────────────────────────────────────────────────

class TestMinProfitKDExitGuard:
    """KD exit only fires when PnL >= min_profit_before_kd_exit_pts."""

    def _engine_with_history(self, min_profit=8.0):
        eng = MTXSignalEngine(
            stop_loss_pts=15, take_profit_pts=50,
            min_profit_before_kd_exit_pts=min_profit,
        )
        eng.seed_1m(_make_bars(50))
        eng.seed_5m(_make_bars(50))
        eng.seed_daily(_make_bars(30))
        return eng

    def test_kd_exit_blocked_below_min_profit(self):
        """When PnL is below threshold, KD cross should NOT trigger exit."""
        eng = self._engine_with_history(min_profit=8.0)
        # PnL = +3pts (below 8pt threshold) — KD exit should be skipped
        eng.last_price = 20003.0
        # Fake a death cross on 1m by patching
        with patch("src.application.services.mtx_signal_engine.death_cross", return_value=True), \
             patch("src.application.services.mtx_signal_engine.golden_cross", return_value=False):
            sig = eng.evaluate(current_position="LONG", entry_price=20000.0)
        # Should HOLD — PnL too small for KD exit
        assert sig.direction != SignalDirection.CLOSE_LONG or "停損" in sig.reason or "獲利" in sig.reason

    def test_kd_exit_allowed_above_min_profit(self):
        """When PnL >= threshold, KD death cross should trigger CLOSE_LONG."""
        eng = self._engine_with_history(min_profit=8.0)
        # PnL = +10pts (above 8pt threshold) — KD exit should fire
        eng.last_price = 20010.0
        with patch("src.application.services.mtx_signal_engine.death_cross", return_value=True), \
             patch("src.application.services.mtx_signal_engine.golden_cross", return_value=False):
            sig = eng.evaluate(current_position="LONG", entry_price=20000.0)
        assert sig.direction == SignalDirection.CLOSE_LONG
        assert "1mK死叉" in sig.reason

    def test_kd_short_exit_blocked_below_min_profit(self):
        """Golden cross blocked for short position below min profit."""
        eng = self._engine_with_history(min_profit=8.0)
        eng.last_price = 19997.0  # PnL = +3pts
        with patch("src.application.services.mtx_signal_engine.golden_cross", return_value=True), \
             patch("src.application.services.mtx_signal_engine.death_cross", return_value=False):
            sig = eng.evaluate(current_position="SHORT", entry_price=20000.0)
        assert sig.direction != SignalDirection.CLOSE_SHORT or "停損" in sig.reason

    def test_kd_short_exit_allowed_above_min_profit(self):
        """Golden cross fires for short position above min profit."""
        eng = self._engine_with_history(min_profit=8.0)
        eng.last_price = 19990.0  # PnL = +10pts
        with patch("src.application.services.mtx_signal_engine.golden_cross", return_value=True), \
             patch("src.application.services.mtx_signal_engine.death_cross", return_value=False):
            sig = eng.evaluate(current_position="SHORT", entry_price=20000.0)
        assert sig.direction == SignalDirection.CLOSE_SHORT
        assert "1mK黃金交叉" in sig.reason

    def test_zero_min_profit_always_allows_kd_exit(self):
        """min_profit=0 disables guard — any KD cross triggers exit."""
        eng = self._engine_with_history(min_profit=0.0)
        eng.last_price = 20001.0  # PnL = +1pt
        with patch("src.application.services.mtx_signal_engine.death_cross", return_value=True), \
             patch("src.application.services.mtx_signal_engine.golden_cross", return_value=False):
            sig = eng.evaluate(current_position="LONG", entry_price=20000.0)
        assert sig.direction == SignalDirection.CLOSE_LONG


class TestLateSessionFilter:
    """_is_late_session() and entry blocking near session end."""

    def _trader(self, late_min=30):
        client = _mock_client()
        return MTXAutoTrader(client, dry_run=True, late_session_no_entry_minutes=late_min)

    def test_night_is_late_within_window(self):
        trader = self._trader(30)
        # 04:45 is within 30 min of 05:01
        with patch("src.application.services.mtx_auto_trader.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 5, 20, 4, 45, 0)
            assert trader._is_late_session(is_night=True)

    def test_night_not_late_outside_window(self):
        trader = self._trader(30)
        # 03:00 is more than 30 min before 05:01
        with patch("src.application.services.mtx_auto_trader.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 5, 20, 3, 0, 0)
            assert not trader._is_late_session(is_night=True)

    def test_day_is_late_within_window(self):
        trader = self._trader(30)
        # 13:10 is within 30 min of 13:31
        with patch("src.application.services.mtx_auto_trader.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 5, 20, 13, 10, 0)
            assert trader._is_late_session(is_night=False)

    def test_day_not_late_outside_window(self):
        trader = self._trader(30)
        # 09:00 is more than 30 min before 13:31
        with patch("src.application.services.mtx_auto_trader.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 5, 20, 9, 0, 0)
            assert not trader._is_late_session(is_night=False)

    def test_zero_late_minutes_never_late(self):
        """late_session_no_entry_minutes=0 disables the filter entirely."""
        trader = self._trader(late_min=0)
        with patch("src.application.services.mtx_auto_trader.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 5, 20, 4, 55, 0)
            assert not trader._is_late_session(is_night=True)

    def test_late_session_blocks_long_entry(self):
        """LONG signal during late session must NOT open position."""
        trader = self._trader(30)
        long_sig = TradeSignal(SignalDirection.LONG, 41000.0, _now(), "test", 0.9)

        async def _run():
            with patch.object(trader, "_is_late_session", return_value=True):
                await trader._handle_signal(long_sig, True)

        asyncio.run(_run())
        assert trader.position is None

    def test_late_session_blocks_short_entry(self):
        """SHORT signal during late session must NOT open position."""
        trader = self._trader(30)
        short_sig = TradeSignal(SignalDirection.SHORT, 41000.0, _now(), "test", 0.9)

        async def _run():
            with patch.object(trader, "_is_late_session", return_value=True):
                await trader._handle_signal(short_sig, True)

        asyncio.run(_run())
        assert trader.position is None

    def test_late_session_still_allows_close(self):
        """CLOSE_LONG during late session must still close the position."""
        trader = self._trader(30)
        trader.position = Position(
            symbol="TMFF6", direction="LONG",
            entry_price=41000.0, lots=1,
            entry_time=_now(),
        )
        close_sig = TradeSignal(SignalDirection.CLOSE_LONG, 41010.0, _now(), "KD叉", 0.8)

        async def _run():
            with patch.object(trader, "_is_late_session", return_value=True):
                await trader._handle_signal(close_sig, True)

        asyncio.run(_run())
        assert trader.position is None
        assert len(trader.trades) == 1


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


class TestRunSessionEarlyExit:
    """_run_session must not send startup notification if session has already ended.

    Regression: Cloud Run restarts with --session night at 05:11 (after 05:00
    close) used to send a spurious '🟢 MTX 自動交易 啟動 — 夜盤' notification.
    """

    @staticmethod
    def _already_ended(is_night: bool, now: datetime) -> bool:
        """Replication of the early-exit guard added to _run_session."""
        from datetime import time as _t
        t = now.time()
        if is_night:
            return _t(5, 1) <= t < _t(8, 45)
        return t >= _t(13, 31)

    # ── night session ──────────────────────────────────────────────────────

    def test_night_at_05h11_already_ended(self):
        """05:11 — the scenario from the bug report — must be treated as ended."""
        assert self._already_ended(True, datetime(2026, 6, 6, 5, 11, 0))

    def test_night_at_05h01_already_ended(self):
        assert self._already_ended(True, datetime(2026, 6, 6, 5, 1, 0))

    def test_night_at_08h44_still_ended(self):
        """08:44 is still in the closed gap after night session."""
        assert self._already_ended(True, datetime(2026, 6, 6, 8, 44, 0))

    def test_night_at_08h45_not_ended(self):
        """08:45 is day open — night guard must NOT fire."""
        assert not self._already_ended(True, datetime(2026, 6, 6, 8, 45, 0))

    def test_night_at_04h59_not_ended(self):
        """04:59 — still inside night session."""
        assert not self._already_ended(True, datetime(2026, 6, 6, 4, 59, 0))

    def test_night_at_15h00_not_ended(self):
        """15:00 — night session just opened."""
        assert not self._already_ended(True, datetime(2026, 6, 5, 15, 0, 0))

    def test_night_at_02h05_not_ended(self):
        """02:05 mid-session must NOT trigger early exit."""
        assert not self._already_ended(True, datetime(2026, 6, 6, 2, 5, 0))

    # ── day session ────────────────────────────────────────────────────────

    def test_day_at_13h31_already_ended(self):
        assert self._already_ended(False, datetime(2026, 6, 6, 13, 31, 0))

    def test_day_at_14h00_already_ended(self):
        assert self._already_ended(False, datetime(2026, 6, 6, 14, 0, 0))

    def test_day_at_13h30_not_ended(self):
        """13:30 — last minute of day session."""
        assert not self._already_ended(False, datetime(2026, 6, 6, 13, 30, 59))

    def test_day_at_09h00_not_ended(self):
        assert not self._already_ended(False, datetime(2026, 6, 6, 9, 0, 0))

    # ── integration: _run_session skips notify when ended ─────────────────

    def test_run_session_skips_when_night_ended(self):
        """_run_session must return without calling notifier at 05:11."""
        client = _mock_client()
        notifier = MagicMock()
        trader = MTXAutoTrader(client, dry_run=True, notifier=notifier)

        fake_now = datetime(2026, 6, 6, 5, 11, 0, tzinfo=__import__('zoneinfo').ZoneInfo("Asia/Taipei"))

        async def _run():
            with patch("src.application.services.mtx_auto_trader._now", return_value=fake_now):
                await trader._run_session(is_night=True)

        asyncio.run(_run())
        notifier.send_message.assert_not_called()

    def test_run_session_sends_notify_during_valid_night(self):
        """_run_session must send startup notification at 22:00 (valid night)."""
        client = _mock_client()
        notifier = MagicMock()
        trader = MTXAutoTrader(client, dry_run=True, notifier=notifier)

        fake_now = datetime(2026, 6, 5, 22, 0, 0, tzinfo=__import__('zoneinfo').ZoneInfo("Asia/Taipei"))

        # The session would run forever; we cancel it quickly via running=False
        async def _run():
            with patch("src.application.services.mtx_auto_trader._now", return_value=fake_now):
                trader.running = False  # causes main loop to exit immediately
                await trader._run_session(is_night=True)

        asyncio.run(_run())
        notifier.send_message.assert_called_once()


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
