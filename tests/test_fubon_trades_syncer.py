"""
Unit tests for FubonTradesSyncer
"""
import pytest
from unittest.mock import MagicMock, patch


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_order(symbol="2330", buy_sell="Buy", filled_qty=1000, filled_money=150000, order_no="X001"):
    """Build a mock order object with snake_case attributes (Fubon Python SDK style)."""
    o = MagicMock()
    o.symbol = symbol
    o.buy_sell = buy_sell
    o.filled_qty = filled_qty
    o.filled_money = filled_money
    o.order_no = order_no
    return o


def _make_syncer_with_mock_login(orders, is_success=True):
    """Return a FubonTradesSyncer whose _login/_logout is mocked."""
    from src.application.services.fubon_trades_syncer import FubonTradesSyncer

    syncer = FubonTradesSyncer()

    mock_sdk = MagicMock()
    mock_accounts = MagicMock()
    mock_accounts.data = [MagicMock(account_type="stock")]

    order_result = MagicMock()
    order_result.is_success = is_success
    order_result.message = "ok" if is_success else "error"
    order_result.data = orders

    mock_sdk.stock.get_order_results.return_value = order_result

    syncer._login = MagicMock(return_value=(mock_sdk, mock_accounts, None))
    syncer._logout = MagicMock()

    return syncer, mock_sdk, mock_accounts


# ── _get_attr ─────────────────────────────────────────────────────────────────

class TestGetAttr:
    def test_dict_key(self):
        from src.application.services.fubon_trades_syncer import _get_attr
        assert _get_attr({'filled_qty': 500}, 'filled_qty') == 500

    def test_object_attr(self):
        from src.application.services.fubon_trades_syncer import _get_attr
        obj = MagicMock()
        obj.filled_qty = 200
        assert _get_attr(obj, 'filled_qty') == 200

    def test_missing_key_returns_default(self):
        from src.application.services.fubon_trades_syncer import _get_attr
        assert _get_attr({}, 'missing_key', default=99) == 99

    def test_first_matching_key_wins(self):
        from src.application.services.fubon_trades_syncer import _get_attr
        d = {'filled_qty': 10}
        assert _get_attr(d, 'filled_qty', 'filledQty', default=0) == 10


# ── _get_stock_account ────────────────────────────────────────────────────────

class TestGetStockAccount:
    def test_finds_stock_account(self):
        from src.application.services.fubon_trades_syncer import FubonTradesSyncer
        syncer = FubonTradesSyncer()

        stock_acc = MagicMock(account_type="stock")
        futopt_acc = MagicMock(account_type="futopt")
        result = MagicMock(data=[futopt_acc, stock_acc])

        assert syncer._get_stock_account(result) is stock_acc

    def test_falls_back_to_first_account(self):
        from src.application.services.fubon_trades_syncer import FubonTradesSyncer
        syncer = FubonTradesSyncer()

        acc = MagicMock(account_type="futopt")
        result = MagicMock(data=[acc])

        assert syncer._get_stock_account(result) is acc

    def test_returns_none_when_empty(self):
        from src.application.services.fubon_trades_syncer import FubonTradesSyncer
        syncer = FubonTradesSyncer()

        result = MagicMock(data=[])
        assert syncer._get_stock_account(result) is None


# ── sync() ────────────────────────────────────────────────────────────────────

class TestFubonTradesSyncerSync:
    def test_sync_writes_filled_orders(self):
        orders = [
            _make_order("2330", "Buy", 1000, 150000, "A001"),
            _make_order("2454", "Sell", 2000, 600000, "A002"),
        ]
        syncer, mock_sdk, _ = _make_syncer_with_mock_login(orders)

        mock_recorder = MagicMock()
        mock_recorder.is_available.return_value = True
        mock_recorder.record_trade.return_value = True

        with patch("src.application.services.fubon_trades_syncer.GoogleSheetsRecorder",
                   return_value=mock_recorder):
            with patch("config.settings.settings") as mock_settings:
                mock_settings.fubon = MagicMock()
                result = syncer.sync()

        assert result['synced'] == 2
        assert result['errors'] == 0
        assert mock_recorder.record_trade.call_count == 2

        # Verify buy order
        call_args = mock_recorder.record_trade.call_args_list
        buy_call = call_args[0][1]
        assert buy_call['stock_code'] == "2330"
        assert buy_call['action'] == "買入"
        assert buy_call['price'] == 150.0
        assert buy_call['quantity'] == 1000

        # Verify sell order
        sell_call = call_args[1][1]
        assert sell_call['stock_code'] == "2454"
        assert sell_call['action'] == "賣出"

    def test_sync_filters_unfilled_orders(self):
        """filled_qty == 0 的委託不應寫入"""
        orders = [
            _make_order("2330", "Buy", 0, 0, "B001"),   # unfilled
            _make_order("2454", "Buy", 1000, 200000, "B002"),  # filled
        ]
        syncer, _, _ = _make_syncer_with_mock_login(orders)

        mock_recorder = MagicMock()
        mock_recorder.is_available.return_value = True
        mock_recorder.record_trade.return_value = True

        with patch("src.application.services.fubon_trades_syncer.GoogleSheetsRecorder",
                   return_value=mock_recorder):
            with patch("config.settings.settings") as mock_settings:
                mock_settings.fubon = MagicMock()
                result = syncer.sync()

        assert result['synced'] == 1
        assert mock_recorder.record_trade.call_count == 1

    def test_sync_skips_when_sheets_unavailable(self):
        orders = [_make_order("2330", "Buy", 1000, 150000)]
        syncer, _, _ = _make_syncer_with_mock_login(orders)

        mock_recorder = MagicMock()
        mock_recorder.is_available.return_value = False

        with patch("src.application.services.fubon_trades_syncer.GoogleSheetsRecorder",
                   return_value=mock_recorder):
            with patch("config.settings.settings") as mock_settings:
                mock_settings.fubon = MagicMock()
                result = syncer.sync()

        assert result['synced'] == 0
        assert result['skipped'] == 1
        mock_recorder.record_trade.assert_not_called()

    def test_sync_returns_zero_when_no_orders(self):
        syncer, _, _ = _make_syncer_with_mock_login([])

        with patch("src.application.services.fubon_trades_syncer.GoogleSheetsRecorder"):
            with patch("config.settings.settings") as mock_settings:
                mock_settings.fubon = MagicMock()
                result = syncer.sync()

        assert result == {'synced': 0, 'skipped': 0, 'errors': 0}

    def test_sync_counts_errors_on_sheet_write_failure(self):
        orders = [_make_order("2330", "Buy", 1000, 150000)]
        syncer, _, _ = _make_syncer_with_mock_login(orders)

        mock_recorder = MagicMock()
        mock_recorder.is_available.return_value = True
        mock_recorder.record_trade.return_value = False  # write failed

        with patch("src.application.services.fubon_trades_syncer.GoogleSheetsRecorder",
                   return_value=mock_recorder):
            with patch("config.settings.settings") as mock_settings:
                mock_settings.fubon = MagicMock()
                result = syncer.sync()

        assert result['synced'] == 0
        assert result['errors'] == 1

    def test_sync_handles_get_order_results_failure(self):
        from src.application.services.fubon_trades_syncer import FubonTradesSyncer
        syncer = FubonTradesSyncer()

        mock_sdk = MagicMock()
        mock_accounts = MagicMock()
        mock_accounts.data = [MagicMock(account_type="stock")]

        order_result = MagicMock()
        order_result.is_success = False
        order_result.message = "API error"
        mock_sdk.stock.get_order_results.return_value = order_result

        syncer._login = MagicMock(return_value=(mock_sdk, mock_accounts, None))
        syncer._logout = MagicMock()

        with patch("config.settings.settings") as mock_settings:
            mock_settings.fubon = MagicMock()
            result = syncer.sync()

        assert result == {'synced': 0, 'skipped': 0, 'errors': 0}

    def test_buy_sell_action_mapping(self):
        """測試 Buy/Sell BSAction 對應中文"""
        cases = [
            ("Buy",  "買入"),
            ("Sell", "賣出"),
            ("B",    "買入"),
        ]
        for buy_sell, expected_action in cases:
            orders = [_make_order("2330", buy_sell, 1000, 150000)]
            syncer, _, _ = _make_syncer_with_mock_login(orders)

            mock_recorder = MagicMock()
            mock_recorder.is_available.return_value = True
            mock_recorder.record_trade.return_value = True

            with patch("src.application.services.fubon_trades_syncer.GoogleSheetsRecorder",
                       return_value=mock_recorder):
                with patch("config.settings.settings") as mock_settings:
                    mock_settings.fubon = MagicMock()
                    syncer.sync()

            call_kwargs = mock_recorder.record_trade.call_args[1]
            assert call_kwargs['action'] == expected_action, f"buy_sell={buy_sell!r} → 預期 {expected_action!r}"
