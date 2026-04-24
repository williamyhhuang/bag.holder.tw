"""
Unit tests for config/secret_manager.py
"""
import os
import pytest
from unittest.mock import MagicMock, patch


class TestInitSecrets:
    def test_no_op_when_gcp_project_id_not_set(self):
        """本機開發：GCP_PROJECT_ID 未設定時應直接 return，不呼叫 Secret Manager"""
        env = {k: v for k, v in os.environ.items() if k != "GCP_PROJECT_ID"}
        with patch.dict(os.environ, env, clear=True):
            with patch("config.secret_manager.load_secrets_to_env") as mock_load:
                from config.secret_manager import init_secrets
                init_secrets()
                mock_load.assert_not_called()

    def test_calls_load_when_gcp_project_id_set(self):
        """GCP_PROJECT_ID 設定時應呼叫 load_secrets_to_env"""
        with patch.dict(os.environ, {"GCP_PROJECT_ID": "my-project"}):
            with patch("config.secret_manager.load_secrets_to_env") as mock_load:
                from config.secret_manager import init_secrets
                init_secrets()
                mock_load.assert_called_once_with("my-project")


class TestLoadSecretsToEnv:
    def _make_secret_response(self, value: str):
        response = MagicMock()
        response.payload.data = value.encode("utf-8")
        return response

    def test_loads_secret_into_environ(self):
        """成功讀取的 secret 應被注入到 os.environ"""
        mock_client = MagicMock()
        mock_client.access_secret_version.return_value = self._make_secret_response("token123")
        mock_sm = MagicMock()
        mock_sm.SecretManagerServiceClient.return_value = mock_client

        env_snapshot = {k: v for k, v in os.environ.items()}
        env_snapshot.pop("TELEGRAM_BOT_TOKEN", None)

        with patch.dict(os.environ, env_snapshot, clear=True):
            with patch("config.secret_manager._secretmanager", mock_sm):
                with patch("config.secret_manager._SECRET_MANAGER_AVAILABLE", True):
                    from config.secret_manager import load_secrets_to_env
                    load_secrets_to_env("my-project")
                    assert os.environ.get("TELEGRAM_BOT_TOKEN") == "token123"

    def test_skips_existing_env_var(self):
        """os.environ 已有值時不應覆蓋"""
        mock_client = MagicMock()
        mock_sm = MagicMock()
        mock_sm.SecretManagerServiceClient.return_value = mock_client

        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "existing_token"}):
            with patch("config.secret_manager._secretmanager", mock_sm):
                with patch("config.secret_manager._SECRET_MANAGER_AVAILABLE", True):
                    from config.secret_manager import load_secrets_to_env
                    load_secrets_to_env("my-project")

                    # 不應呼叫 access_secret_version for TELEGRAM_BOT_TOKEN
                    calls = [
                        str(call)
                        for call in mock_client.access_secret_version.call_args_list
                        if "TELEGRAM_BOT_TOKEN" in str(call)
                    ]
                    assert len(calls) == 0
                    assert os.environ["TELEGRAM_BOT_TOKEN"] == "existing_token"

    def test_skips_not_found_secret(self):
        """Secret Manager 中不存在的 secret 應跳過，不拋出例外"""
        from google.api_core.exceptions import NotFound

        mock_client = MagicMock()
        mock_client.access_secret_version.side_effect = NotFound("not found")
        mock_sm = MagicMock()
        mock_sm.SecretManagerServiceClient.return_value = mock_client

        env_snapshot = {k: v for k, v in os.environ.items()}
        for key in ["TELEGRAM_BOT_TOKEN", "ANTHROPIC_API_KEY"]:
            env_snapshot.pop(key, None)

        with patch.dict(os.environ, env_snapshot, clear=True):
            with patch("config.secret_manager._secretmanager", mock_sm):
                with patch("config.secret_manager._SECRET_MANAGER_AVAILABLE", True):
                    with patch("config.secret_manager.NotFound", NotFound):
                        from config.secret_manager import load_secrets_to_env
                        # 不應拋出例外
                        load_secrets_to_env("my-project")

    def test_warns_on_permission_denied(self):
        """PermissionDenied 應記錄 warning 但不拋出例外"""
        from google.api_core.exceptions import PermissionDenied

        mock_client = MagicMock()
        mock_client.access_secret_version.side_effect = PermissionDenied("denied")
        mock_sm = MagicMock()
        mock_sm.SecretManagerServiceClient.return_value = mock_client

        env_snapshot = {k: v for k, v in os.environ.items()}
        env_snapshot.pop("TELEGRAM_BOT_TOKEN", None)

        with patch.dict(os.environ, env_snapshot, clear=True):
            with patch("config.secret_manager._secretmanager", mock_sm):
                with patch("config.secret_manager._SECRET_MANAGER_AVAILABLE", True):
                    with patch("config.secret_manager.PermissionDenied", PermissionDenied):
                        with patch("config.secret_manager.logger") as mock_logger:
                            from config.secret_manager import load_secrets_to_env
                            load_secrets_to_env("my-project")
                            assert mock_logger.warning.called

    def test_unavailable_library_logs_warning(self):
        """google-cloud-secret-manager 未安裝時應記錄 warning 但不拋出例外"""
        with patch("config.secret_manager._SECRET_MANAGER_AVAILABLE", False):
            with patch("config.secret_manager.logger") as mock_logger:
                from config.secret_manager import load_secrets_to_env
                load_secrets_to_env("my-project")
                mock_logger.warning.assert_called_once()
