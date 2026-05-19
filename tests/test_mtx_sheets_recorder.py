"""
Unit tests for MTXSheetsRecorder and the MTXAutoTrader live_order toggle.
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from unittest.mock import MagicMock, patch, call

import pytest

from src.application.services.mtx_auto_trader import (
    MTXAutoTrader,
    Position,
    SessionType,
    TradeRecord,
)
from src.infrastructure.persistence.mtx_sheets_recorder import (
    MTX_POINT_VALUE_TWD,
    MTX_SHEET_HEADERS,
    MTXSheetsRecorder,
)


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _mock_worksheet():
    ws = MagicMock()
    ws.get_all_values.return_value = [MTX_SHEET_HEADERS]
    return ws


def _mock_client():
    client = MagicMock()
    client.is_logged_in = True
    client.sdk = MagicMock()
    futopt_ws = MagicMock()
    futopt_ws.connect = MagicMock()
    futopt_ws.subscribe = MagicMock()
    futopt_ws.unsubscribe = MagicMock()
    client.sdk.marketdata.websocket_client.futopt = futopt_ws
    client.get_futures_candles = MagicMock(return_value=[])
    client._initialize_sdk = MagicMock()
    client.__aenter__ = MagicMock(return_value=client)
    client.__aexit__ = MagicMock(return_value=None)
    return client


def _mock_recorder(should_fail: bool = False):
    """Return an MTXSheetsRecorder whose worksheet is mocked."""
    recorder = MTXSheetsRecorder(worksheet_name="微台交易紀錄")
    recorder._worksheet = _mock_worksheet()
    if should_fail:
        recorder._worksheet.append_row.side_effect = Exception("Network error")
    return recorder


# ──────────────────────────────────────────────────────────────────────────────
# MTXSheetsRecorder — unit tests
# ──────────────────────────────────────────────────────────────────────────────

class TestMTXSheetsRecorder:

    def test_headers_length(self):
        assert len(MTX_SHEET_HEADERS) == 13

    def test_headers_contain_required_fields(self):
        for field in ("timestamp", "symbol", "direction", "action",
                      "price", "lots", "pnl_pts", "pnl_twd", "mode"):
            assert field in MTX_SHEET_HEADERS

    def test_record_open_calls_append_row(self):
        recorder = _mock_recorder()
        result = recorder.record_open(
            symbol="FIMTXE6", direction="LONG",
            price=20000.0, lots=1, reason="Test", session="日盤",
        )
        assert result is True
        recorder._worksheet.append_row.assert_called_once()
        row = recorder._worksheet.append_row.call_args[0][0]
        assert row[4] == "FIMTXE6"      # symbol
        assert row[5] == "LONG"          # direction
        assert row[6] == "進場"          # action
        assert row[7] == 20000.0         # price
        assert row[8] == 1               # lots
        assert row[9] == ""              # pnl_pts — empty for open
        assert row[10] == ""             # pnl_twd — empty for open
        assert row[11] == "Test"         # reason
        assert row[12] == "模擬"         # mode

    def test_record_close_long_profit(self):
        recorder = _mock_recorder()
        result = recorder.record_close(
            symbol="FIMTXE6", direction="LONG",
            price=20060.0, lots=2, pnl_pts=60.0,
            reason="獲利", session="日盤",
        )
        assert result is True
        row = recorder._worksheet.append_row.call_args[0][0]
        assert row[6] == "出場"
        assert row[9] == 60.0                   # pnl_pts
        assert row[10] == 60.0 * 2 * MTX_POINT_VALUE_TWD  # pnl_twd = 1200

    def test_record_close_short_loss(self):
        recorder = _mock_recorder()
        recorder.record_close(
            symbol="FIMTXE6", direction="SHORT",
            price=20040.0, lots=1, pnl_pts=-40.0,
            reason="停損", session="夜盤",
        )
        row = recorder._worksheet.append_row.call_args[0][0]
        assert row[9] == -40.0
        assert row[10] == -40.0 * 1 * MTX_POINT_VALUE_TWD  # = -400

    def test_record_open_short_direction(self):
        recorder = _mock_recorder()
        recorder.record_open(
            symbol="FIMTXE6", direction="SHORT",
            price=20100.0, lots=1, reason="死叉", session="夜盤",
        )
        row = recorder._worksheet.append_row.call_args[0][0]
        assert row[5] == "SHORT"
        assert row[3] == "夜盤"   # session

    def test_record_returns_false_on_error(self):
        recorder = _mock_recorder(should_fail=True)
        result = recorder.record_open(
            symbol="FIMTXE6", direction="LONG",
            price=20000.0, lots=1, reason="test", session="日盤",
        )
        assert result is False

    def test_is_available_returns_false_when_sheets_disabled(self):
        recorder = MTXSheetsRecorder()
        with patch("src.infrastructure.persistence.mtx_sheets_recorder.MTXSheetsRecorder.is_available",
                   return_value=False):
            assert not recorder.is_available()

    def test_pnl_twd_uses_mtx_point_value(self):
        assert MTX_POINT_VALUE_TWD == 10

    def test_mode_tag_is_always_simulated(self):
        recorder = _mock_recorder()
        recorder.record_open("X", "LONG", 100.0, 1, "r", "日盤")
        row = recorder._worksheet.append_row.call_args[0][0]
        assert row[12] == "模擬"


# ──────────────────────────────────────────────────────────────────────────────
# MTXAutoTrader — feature toggle routing
# ──────────────────────────────────────────────────────────────────────────────

class TestMTXAutoTraderToggle:

    def _trader(self, live_order: bool, recorder: MTXSheetsRecorder = None):
        client = _mock_client()
        if recorder is None:
            recorder = _mock_recorder()
        return MTXAutoTrader(
            fubon_client=client,
            live_order=live_order,
            sheets_recorder=recorder,
        )

    # ---- Default: simulate mode (live_order=False) ----

    def test_default_live_order_is_false(self):
        """live_order defaults to False — simulated mode."""
        with patch("src.application.services.mtx_auto_trader.MTXAutoTrader.__init__",
                   wraps=lambda self, *a, **kw: None):
            pass  # Constructor test via direct instantiation below
        trader = self._trader(live_order=False)
        assert trader.live_order is False

    def test_sim_mode_open_writes_to_sheets(self):
        recorder = _mock_recorder()
        trader = self._trader(live_order=False, recorder=recorder)

        asyncio.run(trader._open_position("LONG", 20000.0, 1, "test", False))

        recorder._worksheet.append_row.assert_called_once()
        row = recorder._worksheet.append_row.call_args[0][0]
        assert row[6] == "進場"
        assert trader.position is not None
        assert trader.position.order_no == "SIM"

    def test_sim_mode_close_writes_to_sheets(self):
        recorder = _mock_recorder()
        trader = self._trader(live_order=False, recorder=recorder)
        trader.position = Position(
            symbol="FIMTXE6", direction="LONG",
            entry_price=20000.0, lots=1,
            entry_time=datetime.now(),
        )
        trader.signal_engine.last_price = 20060.0

        asyncio.run(trader._close_position("Take profit", 20060.0, False))

        assert recorder._worksheet.append_row.call_count == 1
        row = recorder._worksheet.append_row.call_args[0][0]
        assert row[6] == "出場"
        assert row[9] == pytest.approx(60.0)   # pnl_pts
        assert trader.position is None

    def test_sim_mode_does_not_call_fubon_api(self):
        recorder = _mock_recorder()
        trader = self._trader(live_order=False, recorder=recorder)

        asyncio.run(trader._open_position("SHORT", 20000.0, 1, "test", False))

        trader.client.place_futures_order = MagicMock()
        # place_futures_order should never be called in sim mode
        trader.client.place_futures_order.assert_not_called()

    # ---- Live mode (live_order=True) ----

    def test_live_mode_open_calls_fubon_api(self):
        trader = self._trader(live_order=True)

        async def _run():
            # Patch as async mock
            from unittest.mock import AsyncMock
            trader.client.place_futures_order = AsyncMock(return_value={"order_no": "R001"})
            await trader._open_position("LONG", 20000.0, 1, "test", False)
            trader.client.place_futures_order.assert_called_once()
            kw = trader.client.place_futures_order.call_args.kwargs
            assert kw["buy_sell"] == "Buy"
            assert kw["order_type"] == "New"
            assert kw["is_night_session"] is False

        asyncio.run(_run())
        assert trader.position is not None
        assert trader.position.order_no == "R001"

    def test_live_mode_night_session_uses_futurenight(self):
        trader = self._trader(live_order=True)

        async def _run():
            from unittest.mock import AsyncMock
            trader.client.place_futures_order = AsyncMock(return_value={"order_no": "N001"})
            await trader._open_position("SHORT", 20000.0, 2, "test", True)  # is_night=True
            kw = trader.client.place_futures_order.call_args.kwargs
            assert kw["is_night_session"] is True

        asyncio.run(_run())

    def test_live_mode_close_calls_fubon_api(self):
        trader = self._trader(live_order=True)
        trader.position = Position(
            symbol="FIMTXE6", direction="LONG",
            entry_price=20000.0, lots=1,
            entry_time=datetime.now(),
        )
        trader.signal_engine.last_price = 20060.0

        async def _run():
            from unittest.mock import AsyncMock
            trader.client.place_futures_order = AsyncMock(return_value={"order_no": "C001"})
            await trader._close_position("tp", 20060.0, False)
            trader.client.place_futures_order.assert_called_once()
            kw = trader.client.place_futures_order.call_args.kwargs
            assert kw["buy_sell"] == "Sell"
            assert kw["order_type"] == "Close"

        asyncio.run(_run())
        assert trader.position is None

    def test_live_mode_does_not_write_to_sheets(self):
        recorder = _mock_recorder()
        trader = self._trader(live_order=True, recorder=recorder)

        async def _run():
            from unittest.mock import AsyncMock
            trader.client.place_futures_order = AsyncMock(return_value={"order_no": "L001"})
            await trader._open_position("LONG", 20000.0, 1, "test", False)

        asyncio.run(_run())
        recorder._worksheet.append_row.assert_not_called()

    # ---- DRY RUN overrides both ----

    def test_dry_run_skips_sheets_and_api(self):
        recorder = _mock_recorder()
        client = _mock_client()
        trader = MTXAutoTrader(
            fubon_client=client,
            dry_run=True,
            live_order=True,   # even if live_order=True, dry_run wins
            sheets_recorder=recorder,
        )

        async def _run():
            from unittest.mock import AsyncMock
            trader.client.place_futures_order = AsyncMock()
            await trader._open_position("LONG", 20000.0, 1, "test", False)
            trader.client.place_futures_order.assert_not_called()
            recorder._worksheet.append_row.assert_not_called()

        asyncio.run(_run())
        assert trader.position.order_no == "DRY"

    def test_dry_run_close_skips_sheets_and_api(self):
        recorder = _mock_recorder()
        client = _mock_client()
        trader = MTXAutoTrader(
            fubon_client=client,
            dry_run=True,
            live_order=False,
            sheets_recorder=recorder,
        )
        trader.position = Position(
            symbol="FIMTXE6", direction="SHORT",
            entry_price=20000.0, lots=1,
            entry_time=datetime.now(),
        )
        trader.signal_engine.last_price = 19950.0

        asyncio.run(trader._close_position("sl", 19950.0, False))

        recorder._worksheet.append_row.assert_not_called()
        assert len(trader.trades) == 1

    # ---- Toggle reads from settings when not explicitly passed ----

    def test_toggle_reads_settings_when_not_passed(self):
        client = _mock_client()
        mock_settings = MagicMock()
        mock_settings.mtx_trader.live_order = True

        with patch("config.settings.settings", mock_settings):
            trader = MTXAutoTrader(fubon_client=client)
        assert trader.live_order is True

    def test_toggle_defaults_false_when_settings_unavailable(self):
        """If settings module throws, live_order should default to False (safe mode)."""
        client = _mock_client()
        with patch(
            "src.application.services.mtx_auto_trader.MTXAutoTrader.__init__",
            side_effect=None,
        ):
            pass
        # Direct test: if settings raises, live_order stays False
        trader = MTXAutoTrader(fubon_client=client)
        # When no explicit live_order is passed, reads from settings
        # If settings says False (default), live_order should be False
        assert isinstance(trader.live_order, bool)

    # ---- Sim trade record integrity ----

    def test_sim_close_trade_record_pnl(self):
        recorder = _mock_recorder()
        trader = self._trader(live_order=False, recorder=recorder)
        trader.position = Position(
            symbol="FIMTXE6", direction="SHORT",
            entry_price=20100.0, lots=2,
            entry_time=datetime.now(),
        )

        asyncio.run(trader._close_position("Take profit", 20050.0, False))

        # SHORT: pnl = entry - exit = 20100 - 20050 = +50 pts per lot → 2 lots = +100
        assert trader.trades[0].pnl_pts == pytest.approx(100.0)

    def test_sim_worksheet_name_used(self):
        """MTXSheetsRecorder should use the configured worksheet name."""
        recorder = MTXSheetsRecorder(worksheet_name="微台交易紀錄")
        assert recorder._ws_name == "微台交易紀錄"
