"""
GCP Secret Manager integration.

When GCP_PROJECT_ID is set in the environment, ALL secrets in the project are
automatically loaded into os.environ before pydantic-settings initializes.

Local development uses .env as usual (GCP_PROJECT_ID not set = no-op).
To add a new secret: create it in Secret Manager — no code changes needed.
"""
import logging
import os

logger = logging.getLogger(__name__)

try:
    from google.cloud import secretmanager as _secretmanager
    from google.api_core.exceptions import NotFound, PermissionDenied
    _SECRET_MANAGER_AVAILABLE = True
except ImportError:
    _secretmanager = None  # type: ignore[assignment]
    NotFound = Exception  # type: ignore[assignment,misc]
    PermissionDenied = Exception  # type: ignore[assignment,misc]
    _SECRET_MANAGER_AVAILABLE = False


def load_secrets_to_env(project_id: str) -> None:
    """
    列出 GCP 專案內所有 secrets，並將其值注入到 os.environ。

    - 若 os.environ 已有值（例如 Cloud Run --set-env-vars 或本機 .env）則不覆蓋
    - 若 secret 存取失敗（無權限、停用等）則跳過並記錄 warning
    - 新增 secret 到 Secret Manager 後自動生效，無需修改任何程式碼

    Args:
        project_id: GCP 專案 ID
    """
    if not _SECRET_MANAGER_AVAILABLE:
        logger.warning(
            "google-cloud-secret-manager 未安裝，跳過 Secret Manager 載入。"
            " 請執行: pip install google-cloud-secret-manager"
        )
        return

    client = _secretmanager.SecretManagerServiceClient()
    parent = f"projects/{project_id}"

    try:
        secrets = list(client.list_secrets(request={"parent": parent}))
    except PermissionDenied:
        logger.warning(
            "無權限列出 Secret Manager secrets，請確認服務帳戶有 "
            "roles/secretmanager.viewer 或 roles/secretmanager.secretAccessor 權限"
        )
        return
    except Exception as e:
        logger.warning("無法列出 Secret Manager secrets: %s", e)
        return

    loaded = []
    skipped_existing = []

    for secret in secrets:
        # secret.name 格式：projects/{project}/secrets/{secret_id}
        secret_name = secret.name.split("/")[-1]

        # 若環境變數已顯式設定，不覆蓋
        if os.environ.get(secret_name):
            skipped_existing.append(secret_name)
            continue

        secret_path = f"{secret.name}/versions/latest"
        try:
            response = client.access_secret_version(request={"name": secret_path})
            secret_value = response.payload.data.decode("utf-8").strip()
            os.environ[secret_name] = secret_value
            loaded.append(secret_name)
        except NotFound:
            pass  # secret 存在但沒有任何版本，跳過
        except PermissionDenied:
            logger.warning("無權限讀取 secret: %s", secret_name)
        except Exception as e:
            logger.warning("讀取 secret %s 失敗: %s", secret_name, e)

    if loaded:
        logger.info("從 Secret Manager 載入 %d 個 secrets: %s", len(loaded), ", ".join(loaded))
    if skipped_existing:
        logger.debug("環境變數已設定，跳過: %s", ", ".join(skipped_existing))


def init_secrets() -> None:
    """
    若 GCP_PROJECT_ID 環境變數存在，從 Secret Manager 自動載入所有機敏設定。
    本機開發時不設定 GCP_PROJECT_ID，此函式為 no-op。
    """
    project_id = os.environ.get("GCP_PROJECT_ID")
    if not project_id:
        return  # 本機開發，使用 .env

    logger.info("偵測到 GCP_PROJECT_ID=%s，從 Secret Manager 自動載入所有 secrets", project_id)
    load_secrets_to_env(project_id)
