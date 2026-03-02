import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from veridex.auth import require_admin
from veridex.config import settings

logger = structlog.get_logger("veridex")

router = APIRouter(prefix="/v1/admin", tags=["Admin"])


def _paddle_headers() -> dict:
    return {"Authorization": f"Bearer {settings.paddle_api_key}", "Content-Type": "application/json"}


def _paddle_base() -> str:
    if getattr(settings, "paddle_environment", "production") == "sandbox":
        return "https://sandbox-api.paddle.com"
    return "https://api.paddle.com"


async def _cancel_paddle_subscription(subscription_id: str) -> None:
    """Cancel a Paddle subscription immediately via the Paddle API."""
    if not settings.paddle_api_key or not subscription_id:
        return
    url = f"{_paddle_base()}/subscriptions/{subscription_id}/cancel"
    async with httpx.AsyncClient() as client:
        r = await client.post(url, json={"effective_from": "immediately"}, headers=_paddle_headers())
    if r.status_code not in (200, 201):
        logger.warning("paddle_cancel_failed", subscription_id=subscription_id, status=r.status_code)


@router.get("/accounts")
async def list_accounts(
    request: Request,
    search: str = Query(default="", description="Filter by username or email"),
    _admin: str = Depends(require_admin),
) -> list[dict]:
    """
    Return all accounts, optionally filtered by a search term (username or email).

    :param search: Case-insensitive substring to match against username or email.
    :return: List of account dicts with id, username, contact_email, subscription_status.
    """
    pool = request.app.db_pool
    if search:
        rows = await pool.fetch(
            """
            SELECT id, username, contact_email, subscription_status
            FROM accounts
            WHERE username ILIKE $1 OR contact_email ILIKE $1
            ORDER BY username
            """,
            f"%{search}%",
        )
    else:
        rows = await pool.fetch(
            "SELECT id, username, contact_email, subscription_status FROM accounts ORDER BY username"
        )
    return [dict(r) for r in rows]


@router.post("/accounts/{username}/downgrade")
async def downgrade_account(
    username: str,
    request: Request,
    _admin: str = Depends(require_admin),
) -> dict:
    """
    Downgrade an account to free and cancel any active Paddle subscription.

    :param username: The account to downgrade.
    :return: {"ok": true}
    """
    pool = request.app.db_pool
    row = await pool.fetchrow(
        "SELECT subscription_status, paddle_subscription_id FROM accounts WHERE username = $1",
        username.lower(),
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found.")

    if row["paddle_subscription_id"]:
        await _cancel_paddle_subscription(row["paddle_subscription_id"])

    await pool.execute(
        "UPDATE accounts SET subscription_status = 'free', paddle_subscription_id = NULL WHERE username = $1",
        username.lower(),
    )
    logger.info("admin_downgraded", username=username)
    return {"ok": True}


@router.post("/accounts/{username}/block")
async def block_account(
    username: str,
    request: Request,
    _admin: str = Depends(require_admin),
) -> dict:
    """
    Block an account and cancel any active Paddle subscription.

    :param username: The account to block.
    :return: {"ok": true}
    """
    pool = request.app.db_pool
    row = await pool.fetchrow(
        "SELECT subscription_status, paddle_subscription_id FROM accounts WHERE username = $1",
        username.lower(),
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found.")

    if row["paddle_subscription_id"]:
        await _cancel_paddle_subscription(row["paddle_subscription_id"])

    await pool.execute(
        "UPDATE accounts SET subscription_status = 'blocked', paddle_subscription_id = NULL WHERE username = $1",
        username.lower(),
    )
    logger.info("admin_blocked", username=username)
    return {"ok": True}
