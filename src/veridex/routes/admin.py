from typing import Literal

import httpx
import structlog
from fastapi import APIRouter, Depends, Query, Request

from veridex.auth import require_admin
from veridex.config import settings
from veridex.db import set_subscription
from veridex.schemas.errors import NotFoundError
from veridex.schemas.responses import AccountResponse, OkResponse

logger = structlog.get_logger("veridex")

router = APIRouter(prefix="/v1/admin", tags=["Admin"], dependencies=[Depends(require_admin)])


def _paddle_base_url() -> str:
    if settings.paddle_environment == "sandbox":
        return "https://sandbox-api.paddle.com"
    return "https://api.paddle.com"


async def _cancel_paddle_subscription(subscription_id: str) -> None:
    """
    Cancel a Paddle subscription immediately via the Paddle API.

    Failures are logged rather than raised so the local account change still applies.

    :param subscription_id: The Paddle subscription ID.
    """
    if not settings.paddle_api_key:
        return
    async with httpx.AsyncClient(base_url=_paddle_base_url(), timeout=10) as client:
        r = await client.post(
            f"/subscriptions/{subscription_id}/cancel",
            json={"effective_from": "immediately"},
            headers={"Authorization": f"Bearer {settings.paddle_api_key}"},
        )
    if not r.is_success:
        logger.warning("paddle_cancel_failed", subscription_id=subscription_id, status=r.status_code)


async def _revoke_subscription(request: Request, username: str, new_status: Literal["free", "blocked"]) -> None:
    """
    Cancel any Paddle subscription for an account and move it to ``new_status``.

    :param request: The FastAPI request (used to access the DB pool).
    :param username: The account to change.
    :param new_status: The tier to move the account to.
    :raises NotFoundError: If the account does not exist.
    """
    pool = request.app.db_pool
    username = username.lower()
    row = await pool.fetchrow("SELECT paddle_subscription_id FROM accounts WHERE username = $1", username)
    if not row:
        raise NotFoundError("Account not found.")
    if row["paddle_subscription_id"]:
        await _cancel_paddle_subscription(row["paddle_subscription_id"])
    await set_subscription(pool, username, new_status)
    logger.info("admin_subscription_changed", username=username, subscription_status=new_status)


@router.get("/accounts", response_model=list[AccountResponse])
async def list_accounts(
    request: Request,
    search: str = Query(default="", description="Filter by username or email"),
) -> list[AccountResponse]:
    """
    Return all accounts, optionally filtered by a search term (username or email).

    :param request: The FastAPI request (used to access the DB pool).
    :param search: Case-insensitive substring to match against username or email.
    :return: Matching accounts ordered by username.
    """
    rows = await request.app.db_pool.fetch(
        """
        SELECT id, username, contact_email, subscription_status
        FROM accounts
        WHERE $1 = '' OR username ILIKE '%' || $1 || '%' OR contact_email ILIKE '%' || $1 || '%'
        ORDER BY username
        """,
        search,
    )
    return [AccountResponse(**dict(r)) for r in rows]


@router.post("/accounts/{username}/downgrade", response_model=OkResponse)
async def downgrade_account(username: str, request: Request) -> OkResponse:
    """
    Downgrade an account to free and cancel any active Paddle subscription.

    :param username: The account to downgrade.
    :param request: The FastAPI request (used to access the DB pool).
    :return: ``{"ok": true}``.
    """
    await _revoke_subscription(request, username, "free")
    return OkResponse()


@router.post("/accounts/{username}/block", response_model=OkResponse)
async def block_account(username: str, request: Request) -> OkResponse:
    """
    Block an account and cancel any active Paddle subscription.

    :param username: The account to block.
    :param request: The FastAPI request (used to access the DB pool).
    :return: ``{"ok": true}``.
    """
    await _revoke_subscription(request, username, "blocked")
    return OkResponse()
