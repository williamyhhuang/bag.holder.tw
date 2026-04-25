"""
Telegram Webhook HTTP API — Interfaces Layer

Cloud Run Service entry point.  Telegram sends a POST to /webhook for every
incoming message; this module validates the request, delegates to the
HandleTelegramWebhookUseCase, and sends the reply back via Telegram API.

架構說明 (DDD/六角架構):
  Telegram (外部) → POST /webhook
       ↓
  webhook_app (Interfaces layer — HTTP adapter)
       ↓
  HandleTelegramWebhookUseCase (Application layer)
       ↓
  TradingBot (Infrastructure layer — Telegram adapter)
       ↓
  UserTradesRecorder / GoogleSheetsRecorder (Infrastructure — Persistence adapters)
"""
import sys
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from src.application.use_cases.handle_telegram_webhook import HandleTelegramWebhookUseCase
from src.utils.logger import get_logger
from config.settings import settings

logger = get_logger(__name__)

app = FastAPI(title="Bag Holder — Telegram Webhook", docs_url=None, redoc_url=None)

# Singleton use-case (shared across requests within the same container instance)
_use_case = HandleTelegramWebhookUseCase()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _verify_secret(header_value: str | None) -> None:
    """Validate X-Telegram-Bot-Api-Secret-Token header (if configured)."""
    expected = settings.telegram.webhook_secret
    if not expected:
        return  # 未設定 secret → 開發環境，跳過驗證
    if header_value != expected:
        raise HTTPException(status_code=403, detail="Invalid secret token")


async def _send_reply(chat_id: str, text: str) -> None:
    """Send a text reply to the given Telegram chat."""
    token = settings.telegram.bot_token
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code != 200:
                logger.warning(f"Telegram sendMessage HTTP {resp.status_code}: {resp.text[:200]}")
    except Exception as exc:
        logger.error(f"Failed to send Telegram reply: {exc}")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe for Cloud Run."""
    return {"status": "ok"}


@app.post("/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> JSONResponse:
    """
    Receive Telegram update, process trade command, send reply.

    Telegram always expects HTTP 200; errors are logged and swallowed so
    Telegram does not retry the same message.
    """
    _verify_secret(x_telegram_bot_api_secret_token)

    body: dict[str, Any] = await request.json()

    # Support both private/group messages and channel posts
    message = body.get("message") or body.get("channel_post")
    if not message:
        return JSONResponse({"ok": True})

    chat_id = str(message.get("chat", {}).get("id", ""))
    text: str = message.get("text", "")

    if not text or not chat_id:
        return JSONResponse({"ok": True})

    try:
        reply = _use_case.execute(text, chat_id)
        await _send_reply(chat_id, reply)
    except Exception as exc:
        logger.error(f"Unhandled error in webhook handler: {exc}", exc_info=True)

    return JSONResponse({"ok": True})
