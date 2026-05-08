"""
Unit tests for GcpWorkflowTrigger and /scan Telegram command
"""
import pytest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# GcpWorkflowTrigger
# ---------------------------------------------------------------------------

class TestGcpWorkflowTrigger:
    def _make_trigger(self):
        from src.infrastructure.gcp.workflow_trigger import GcpWorkflowTrigger
        return GcpWorkflowTrigger(
            project_id="test-project",
            location="asia-east1",
            workflow_name="bag-holder-run-jobs",
        )

    def test_trigger_returns_execution_name(self):
        trigger = self._make_trigger()
        mock_creds = MagicMock()
        mock_creds.token = "fake-token"

        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = {
            "name": "projects/test-project/locations/asia-east1/workflows/bag-holder-run-jobs/executions/abc123"
        }

        with (
            patch("google.auth.default", return_value=(mock_creds, "test-project")),
            patch("google.auth.transport.requests.Request"),
            patch("src.infrastructure.gcp.workflow_trigger._requests.post", return_value=mock_resp),
        ):
            name = trigger.trigger()

        assert "abc123" in name

    def test_trigger_raises_on_api_error(self):
        trigger = self._make_trigger()
        mock_creds = MagicMock()
        mock_creds.token = "fake-token"

        mock_resp = MagicMock()
        mock_resp.ok = False
        mock_resp.status_code = 403
        mock_resp.text = "Permission denied"

        with (
            patch("google.auth.default", return_value=(mock_creds, "test-project")),
            patch("google.auth.transport.requests.Request"),
            patch("src.infrastructure.gcp.workflow_trigger._requests.post", return_value=mock_resp),
        ):
            with pytest.raises(RuntimeError, match="403"):
                trigger.trigger()

    def test_trigger_raises_when_google_auth_missing(self):
        trigger = self._make_trigger()
        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "google.auth":
                raise ImportError("No module named 'google'")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            with pytest.raises(RuntimeError, match="google-auth"):
                trigger.trigger()

    def test_trigger_raises_on_credential_failure(self):
        trigger = self._make_trigger()

        with patch("google.auth.default", side_effect=Exception("no credentials")):
            with pytest.raises(RuntimeError, match="credentials"):
                trigger.trigger()


# ---------------------------------------------------------------------------
# TradingBot /scan command
# ---------------------------------------------------------------------------

@pytest.fixture
def bot():
    with (
        patch("src.infrastructure.notification.telegram_trade_bot.UserTradesRecorder"),
        patch("src.infrastructure.notification.telegram_trade_bot.GoogleSheetsRecorder"),
        patch("src.infrastructure.notification.telegram_trade_bot.TelegramNotifier"),
    ):
        from src.infrastructure.notification.telegram_trade_bot import TradingBot
        b = TradingBot()
        b.trade_recorder = MagicMock()
        b.sheets_recorder = MagicMock()
        b.sheets_recorder.is_available.return_value = False
        return b


class TestScanCommand:
    def test_scan_triggers_workflow_and_returns_confirmation(self, bot):
        mock_trigger_instance = MagicMock()
        mock_trigger_instance.trigger.return_value = "projects/p/locations/l/workflows/w/executions/e1"
        mock_trigger_cls = MagicMock(return_value=mock_trigger_instance)

        with (
            patch("config.settings.settings.app.gcp_project_id", "test-project"),
            patch("src.infrastructure.gcp.workflow_trigger.GcpWorkflowTrigger", mock_trigger_cls),
        ):
            reply = bot.handle_scan_command()

        assert "已觸發" in reply or "工作流程" in reply
        mock_trigger_instance.trigger.assert_called_once()

    def test_scan_returns_error_when_no_project_id(self, bot):
        with patch("config.settings.settings.app.gcp_project_id", None):
            reply = bot.handle_scan_command()
        assert "GCP_PROJECT_ID" in reply or "❌" in reply

    def test_scan_returns_error_on_trigger_failure(self, bot):
        mock_trigger_instance = MagicMock()
        mock_trigger_instance.trigger.side_effect = RuntimeError("network error")
        mock_trigger_cls = MagicMock(return_value=mock_trigger_instance)

        with (
            patch("config.settings.settings.app.gcp_project_id", "test-project"),
            patch("src.infrastructure.gcp.workflow_trigger.GcpWorkflowTrigger", mock_trigger_cls),
        ):
            reply = bot.handle_scan_command()

        assert "❌" in reply

    def test_process_command_dispatches_scan(self, bot):
        with patch.object(bot, "handle_scan_command", return_value="⏳ ok") as mock_scan:
            reply = bot.process_telegram_command("/scan", "chat1")
        mock_scan.assert_called_once()
        assert reply == "⏳ ok"

    def test_process_command_scan_with_args(self, bot):
        """'/scan ' with trailing space still dispatches to scan handler"""
        with patch.object(bot, "handle_scan_command", return_value="⏳ ok") as mock_scan:
            bot.process_telegram_command("/scan  ", "chat1")
        mock_scan.assert_called_once()
