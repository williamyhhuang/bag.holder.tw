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
