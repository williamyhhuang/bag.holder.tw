"""
Unit tests for Telegram Webhook (Option A — Cloud Run Service)

Tests cover:
  - HandleTelegramWebhookUseCase: correct delegation to TradingBot
  - webhook_app FastAPI endpoints: /health, /webhook
    - secret token validation
    - message / channel_post routing
    - graceful handling of malformed payloads
"""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# HandleTelegramWebhookUseCase
# ---------------------------------------------------------------------------

class TestHandleTelegramWebhookUseCase:
    @pytest.fixture
    def use_case(self):
        with (
            patch("src.infrastructure.notification.telegram_trade_bot.UserTradesRecorder"),
            patch("src.infrastructure.notification.telegram_trade_bot.GoogleSheetsRecorder"),
            patch("src.infrastructure.notification.telegram_trade_bot.TelegramNotifier"),
        ):
            from src.infrastructure.notification.telegram_trade_bot import TradingBot
            from src.application.use_cases.handle_telegram_webhook import HandleTelegramWebhookUseCase

            mock_bot = MagicMock(spec=TradingBot)
            mock_bot.process_telegram_command.return_value = "✅ 交易記錄已確認"
            return HandleTelegramWebhookUseCase(trading_bot=mock_bot)

    def test_execute_delegates_to_trading_bot(self, use_case):
        reply = use_case.execute("買入 2330 150 1000", "chat123")
        use_case._bot.process_telegram_command.assert_called_once_with(
            "買入 2330 150 1000", "chat123"
        )
        assert reply == "✅ 交易記錄已確認"

    def test_execute_returns_bot_reply(self, use_case):
        use_case._bot.process_telegram_command.return_value = "📖 說明文字"
        reply = use_case.execute("/help", "chat999")
        assert reply == "📖 說明文字"


# ---------------------------------------------------------------------------
# FastAPI webhook_app
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    """Return a TestClient for the FastAPI webhook app with mocked dependencies."""
    with (
        patch("src.interfaces.api.webhook_app._use_case") as mock_uc,
        patch("src.interfaces.api.webhook_app._send_reply", new_callable=AsyncMock) as mock_send,
        patch("src.interfaces.api.webhook_app.settings") as mock_settings,
    ):
        mock_settings.telegram.webhook_secret = None  # disable secret check by default
        mock_settings.telegram.bot_token = "test_token"
        mock_uc.execute.return_value = "✅ 交易記錄已確認"

        from fastapi.testclient import TestClient
        from src.interfaces.api.webhook_app import app

        yield TestClient(app), mock_uc, mock_send, mock_settings


class TestHealthEndpoint:
    def test_health_returns_ok(self, client):
        tc, *_ = client
        resp = tc.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


class TestWebhookEndpoint:
    def _update(self, text="買入 2330 150 1000", chat_id="12345", key="message"):
        return {key: {"chat": {"id": chat_id}, "text": text}}

    def test_message_triggers_use_case(self, client):
        tc, mock_uc, mock_send, _ = client
        resp = tc.post("/webhook", json=self._update())
        assert resp.status_code == 200
        mock_uc.execute.assert_called_once_with("買入 2330 150 1000", "12345")

    def test_channel_post_triggers_use_case(self, client):
        tc, mock_uc, mock_send, _ = client
        resp = tc.post("/webhook", json=self._update(key="channel_post"))
        assert resp.status_code == 200
        mock_uc.execute.assert_called_once()

    def test_no_message_field_is_ignored(self, client):
        tc, mock_uc, *_ = client
        resp = tc.post("/webhook", json={"update_id": 1})
        assert resp.status_code == 200
        mock_uc.execute.assert_not_called()

    def test_empty_text_is_ignored(self, client):
        tc, mock_uc, *_ = client
        resp = tc.post("/webhook", json={"message": {"chat": {"id": "1"}, "text": ""}})
        assert resp.status_code == 200
        mock_uc.execute.assert_not_called()

    def test_valid_secret_is_accepted(self, client):
        tc, mock_uc, _, mock_settings = client
        mock_settings.telegram.webhook_secret = "mysecret"
        resp = tc.post(
            "/webhook",
            json=self._update(),
            headers={"X-Telegram-Bot-Api-Secret-Token": "mysecret"},
        )
        assert resp.status_code == 200
        mock_uc.execute.assert_called_once()

    def test_invalid_secret_returns_403(self, client):
        tc, mock_uc, _, mock_settings = client
        mock_settings.telegram.webhook_secret = "mysecret"
        resp = tc.post(
            "/webhook",
            json=self._update(),
            headers={"X-Telegram-Bot-Api-Secret-Token": "wrongsecret"},
        )
        assert resp.status_code == 403
        mock_uc.execute.assert_not_called()

    def test_missing_secret_returns_403_when_configured(self, client):
        tc, mock_uc, _, mock_settings = client
        mock_settings.telegram.webhook_secret = "mysecret"
        resp = tc.post("/webhook", json=self._update())  # no secret header
        assert resp.status_code == 403

    def test_use_case_exception_does_not_crash_handler(self, client):
        tc, mock_uc, mock_send, _ = client
        mock_uc.execute.side_effect = RuntimeError("boom")
        resp = tc.post("/webhook", json=self._update())
        # Telegram must always get HTTP 200
        assert resp.status_code == 200

    def test_pnl_command_calls_handle_pnl_directly(self, client):
        tc, mock_uc, mock_send, _ = client
        mock_uc._bot = MagicMock()
        mock_uc._bot.handle_pnl_command.return_value = "📊 損益摘要"
        resp = tc.post("/webhook", json=self._update(text="/pnl"))
        assert resp.status_code == 200
        # Should NOT call use_case.execute for /pnl
        mock_uc.execute.assert_not_called()
        # Should call handle_pnl_command and send reply
        mock_uc._bot.handle_pnl_command.assert_called_once()
        mock_send.assert_awaited_once()


class TestSendSync:
    """Tests for _send_sync Markdown fallback logic."""

    def test_send_sync_success_with_markdown(self):
        from src.interfaces.api.webhook_app import _send_sync
        with patch("src.interfaces.api.webhook_app.settings") as mock_settings, \
             patch("httpx.Client") as mock_client_cls:
            mock_settings.telegram.bot_token = "test_token"
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_client_cls.return_value.__enter__.return_value.post.return_value = mock_resp

            _send_sync("123", "hello")

            mock_client_cls.return_value.__enter__.return_value.post.assert_called_once()
            call_kwargs = mock_client_cls.return_value.__enter__.return_value.post.call_args[1]
            assert call_kwargs["json"]["parse_mode"] == "Markdown"

    def test_send_sync_fallback_to_plain_on_4xx(self):
        from src.interfaces.api.webhook_app import _send_sync
        with patch("src.interfaces.api.webhook_app.settings") as mock_settings, \
             patch("httpx.Client") as mock_client_cls:
            mock_settings.telegram.bot_token = "test_token"
            bad_resp = MagicMock()
            bad_resp.status_code = 400
            bad_resp.text = '{"error_code":400}'
            ok_resp = MagicMock()
            ok_resp.status_code = 200
            mock_client_cls.return_value.__enter__.return_value.post.side_effect = [bad_resp, ok_resp]

            _send_sync("123", "hello *world*")

            assert mock_client_cls.return_value.__enter__.return_value.post.call_count == 2
            # Second call should not have parse_mode
            second_call = mock_client_cls.return_value.__enter__.return_value.post.call_args_list[1]
            assert "parse_mode" not in second_call[1]["json"]
