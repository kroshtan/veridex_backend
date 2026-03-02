import hashlib
import hmac
import json

import structlog
from fastapi import APIRouter, Header, HTTPException, Request, status

from veridex.config import settings

logger = structlog.get_logger("veridex")

router = APIRouter(prefix="/v1/paddle", tags=["Paddle"])


def _verify_signature(raw_body: bytes, signature_header: str) -> bool:
    """
    Verify a Paddle webhook signature.

    Paddle signs the payload as ``{ts}:{raw_body}`` using HMAC-SHA256 with the
    webhook secret.  The ``Paddle-Signature`` header has the form
    ``ts=<timestamp>;h1=<hex_digest>``.

    When no secret is configured the check is skipped (useful in development).

    :param raw_body: The raw request body bytes.
    :param signature_header: The value of the ``Paddle-Signature`` header.
    :return: ``True`` if the signature is valid (or verification is disabled).
    """
    secret: str = getattr(settings, "paddle_webhook_secret", "")
    if not secret:
        logger.warning("paddle_webhook_secret not configured – skipping signature check")
        return True

    try:
        parts = dict(part.split("=", 1) for part in signature_header.split(";"))
        ts = parts["ts"]
        h1 = parts["h1"]
    except (ValueError, KeyError):
        return False

    signed_payload = f"{ts}:{raw_body.decode()}"
    expected = hmac.new(secret.encode(), signed_payload.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, h1)


@router.post("/webhook", include_in_schema=False)
async def paddle_webhook(
    request: Request,
    paddle_signature: str = Header(..., alias="Paddle-Signature"),
) -> dict:
    """
    Receive and process Paddle Billing webhook events.

    Handled events:

    * ``subscription.activated`` – sets the account tier to ``premium``.
    * ``subscription.canceled``  – reverts the account tier to ``free``
      (fires at the end of the billing period after a cancellation request).

    The Paddle checkout must pass ``customData: { username: "<username>" }`` so
    we know which account to update.

    :param request: The raw FastAPI request (body read for signature verification).
    :param paddle_signature: Value of the ``Paddle-Signature`` header.
    :return: ``{"ok": true}`` on success.
    :raises HTTPException: 400 if the signature is invalid.
    """
    raw_body = await request.body()

    if not _verify_signature(raw_body, paddle_signature):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid signature.")

    event = json.loads(raw_body)
    event_type: str = event.get("event_type", "")
    data: dict = event.get("data", {})
    custom_data: dict = data.get("custom_data") or {}
    username: str | None = custom_data.get("username")

    if not username:
        logger.warning("paddle_webhook_missing_username", event_type=event_type)
        return {"ok": True}

    pool = request.app.db_pool

    if event_type == "subscription.activated":
        await pool.execute(
            "UPDATE accounts SET subscription_status = 'premium', paddle_subscription_id = $2 WHERE username = $1",
            username,
            data.get("id"),
        )
        logger.info("subscription_upgraded", username=username)

    elif event_type == "subscription.canceled":
        await pool.execute(
            "UPDATE accounts SET subscription_status = 'free', paddle_subscription_id = NULL WHERE username = $1",
            username,
        )
        logger.info("subscription_downgraded", username=username)

    return {"ok": True}
