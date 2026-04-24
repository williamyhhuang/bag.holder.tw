"""
Unit tests for config/secret_manager.py
"""
import os
import pytest
from unittest.mock import MagicMock, patch


def _make_secret(name: str, project: str = "my-project"):
    secret = MagicMock()
    secret.name = f"projects/{project}/secrets/{name}"
    return secret


def _make_version_response(value: str):
    response = MagicMock()
    response.payload.data = value.encode("utf-8")
    return response


class TestInitSecrets:
    def test_no_op_when_gcp_project_id_not_set(self):
        """本機開發：GCP_PROJECT_ID 未設定時應直接 return"""
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
    def _make_client(self, secrets: dict):
        """secrets: {secret_name: secret_value}"""
        mock_client = MagicMock()
        mock_client.list_secrets.return_value = [
            _make_secret(name) for name in secrets
        ]
        mock_client.access_secret_version.side_effect = lambda request: (
            _make_version_response(secrets[request["name"].split("/")[-3]])
        )
        return mock_client

    def _patch_sm(self, mock_client):
        mock_sm = MagicMock()
        mock_sm.SecretManagerServiceClient.return_value = mock_client
        return mock_sm

    def test_loads_all_secrets_into_environ(self):
        """列出的所有 secrets 應全部注入 os.environ"""
        secrets = {"TELEGRAM_BOT_TOKEN": "tok123", "GEMINI_API_KEY": "gem456"}
        mock_client = self._make_client(secrets)

        env_snapshot = {k: v for k, v in os.environ.items()}
        for k in secrets:
            env_snapshot.pop(k, None)

        with patch.dict(os.environ, env_snapshot, clear=True):
            with patch("config.secret_manager._secretmanager", self._patch_sm(mock_client)):
                with patch("config.secret_manager._SECRET_MANAGER_AVAILABLE", True):
                    from config.secret_manager import load_secrets_to_env
                    load_secrets_to_env("my-project")
                    assert os.environ["TELEGRAM_BOT_TOKEN"] == "tok123"
                    assert os.environ["GEMINI_API_KEY"] == "gem456"

    def test_skips_existing_env_var(self):
        """os.environ 已有值時不應覆蓋"""
        secrets = {"TELEGRAM_BOT_TOKEN": "new_value"}
        mock_client = self._make_client(secrets)

        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "existing_token"}):
            with patch("config.secret_manager._secretmanager", self._patch_sm(mock_client)):
                with patch("config.secret_manager._SECRET_MANAGER_AVAILABLE", True):
                    from config.secret_manager import load_secrets_to_env
                    load_secrets_to_env("my-project")
                    assert os.environ["TELEGRAM_BOT_TOKEN"] == "existing_token"

    def test_skips_not_found_version(self):
        """secret 存在但無版本時應跳過，不拋出例外"""
        from google.api_core.exceptions import NotFound

        mock_client = MagicMock()
        mock_client.list_secrets.return_value = [_make_secret("EMPTY_SECRET")]
        mock_client.access_secret_version.side_effect = NotFound("no version")

        env_snapshot = {k: v for k, v in os.environ.items()}
        env_snapshot.pop("EMPTY_SECRET", None)

        with patch.dict(os.environ, env_snapshot, clear=True):
            with patch("config.secret_manager._secretmanager", self._patch_sm(mock_client)):
                with patch("config.secret_manager._SECRET_MANAGER_AVAILABLE", True):
                    with patch("config.secret_manager.NotFound", NotFound):
                        from config.secret_manager import load_secrets_to_env
                        load_secrets_to_env("my-project")  # 不應拋出例外

    def test_warns_on_list_permission_denied(self):
        """list_secrets 無權限時應記錄 warning 並 return"""
        from google.api_core.exceptions import PermissionDenied

        mock_client = MagicMock()
        mock_client.list_secrets.side_effect = PermissionDenied("denied")

        with patch("config.secret_manager._secretmanager", self._patch_sm(mock_client)):
            with patch("config.secret_manager._SECRET_MANAGER_AVAILABLE", True):
                with patch("config.secret_manager.PermissionDenied", PermissionDenied):
                    with patch("config.secret_manager.logger") as mock_logger:
                        from config.secret_manager import load_secrets_to_env
                        load_secrets_to_env("my-project")
                        assert mock_logger.warning.called

    def test_unavailable_library_logs_warning(self):
        """google-cloud-secret-manager 未安裝時應記錄 warning"""
        with patch("config.secret_manager._SECRET_MANAGER_AVAILABLE", False):
            with patch("config.secret_manager.logger") as mock_logger:
                from config.secret_manager import load_secrets_to_env
                load_secrets_to_env("my-project")
                mock_logger.warning.assert_called_once()
