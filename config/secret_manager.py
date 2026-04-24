"""
GCP Secret Manager integration.

When GCP_PROJECT_ID is set in the environment, secrets are loaded from
Google Cloud Secret Manager and injected into os.environ before pydantic-settings
initializes. Local development still uses .env as usual.
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

# 需要從 Secret Manager 讀取的機敏環境變數名稱
# 對應 GCP Secret Manager 中的 secret ID（名稱相同）
SENSITIVE_SECRETS = [
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    "TELEGRAM_WEBHOOK_SECRET",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "GEMINI_API_KEY",
    "OPENROUTER_API_KEY",
    "FUBON_API_KEY",
    "FUBON_API_SECRET",
    "FUBON_USER_ID",
    "FUBON_PASSWORD",
    "FUBON_CERT_PASSWORD",
    "REDIS_PASSWORD",
    "SECRET_KEY",
    "DATABASE_URL",
]


def load_secrets_to_env(project_id: str) -> None:
    """
    從 GCP Secret Manager 讀取機敏資訊並注入到 os.environ。

    每個 secret 的 ID 與環境變數名稱相同（例如 TELEGRAM_BOT_TOKEN）。
    若 Secret Manager 中不存在該 secret，則跳過（保留現有 env 或預設值）。
    若 os.environ 已有值，則不覆蓋（讓顯式設定的環境變數優先）。

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
    loaded = []
    skipped = []

    for secret_name in SENSITIVE_SECRETS:
        # 若環境變數已顯式設定，不覆蓋
        if os.environ.get(secret_name):
            skipped.append(secret_name)
            continue

        secret_path = f"projects/{project_id}/secrets/{secret_name}/versions/latest"
        try:
            response = client.access_secret_version(request={"name": secret_path})
            secret_value = response.payload.data.decode("utf-8").strip()
            os.environ[secret_name] = secret_value
            loaded.append(secret_name)
        except NotFound:
            # secret 不存在於 Secret Manager，保持原樣
            pass
        except PermissionDenied:
            logger.warning(
                "無權限讀取 Secret Manager secret: %s，請確認服務帳戶權限", secret_name
            )
        except Exception as e:
            logger.warning("讀取 Secret Manager secret %s 失敗: %s", secret_name, e)

    if loaded:
        logger.info("從 Secret Manager 載入 %d 個 secrets: %s", len(loaded), ", ".join(loaded))
    if skipped:
        logger.debug("環境變數已設定，跳過 Secret Manager: %s", ", ".join(skipped))


def init_secrets() -> None:
    """
    若 GCP_PROJECT_ID 環境變數存在，從 Secret Manager 載入機敏設定。
    本機開發時不設定 GCP_PROJECT_ID，此函式為 no-op。
    """
    project_id = os.environ.get("GCP_PROJECT_ID")
    if not project_id:
        return  # 本機開發，使用 .env

    logger.info("偵測到 GCP_PROJECT_ID=%s，從 Secret Manager 載入機敏設定", project_id)
    load_secrets_to_env(project_id)
