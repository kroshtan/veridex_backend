import asyncpg
import bcrypt
import structlog
from fastapi import APIRouter, Depends, Request

from veridex.auth import verify_credentials
from veridex.config import settings
from veridex.db import count_analyses_today
from veridex.schemas.errors import BadRequestError, NotFoundError
from veridex.schemas.requests import CreateAccountRequest
from veridex.schemas.responses import AccountResponse, UsageResponse

logger = structlog.get_logger("veridex")

router = APIRouter(prefix="/v1/accounts", tags=["Accounts"])


@router.post("", response_model=AccountResponse, status_code=201)
async def create_account(body: CreateAccountRequest, request: Request) -> AccountResponse:
    """
    Create a new user account.

    The password is hashed server-side before storage. Subscription status is set to
    ``'free'`` by the system and is not configurable by the caller.

    :param body: The request body with username, password, and contact email.
    :param request: The FastAPI request (used to access the DB pool).
    :return: The created account (without password).
    :raises BadRequestError: If the username or email is already registered.
    """
    hashed_password = bcrypt.hashpw(body.password.encode(), bcrypt.gensalt()).decode()
    try:
        row = await request.app.db_pool.fetchrow(
            "INSERT INTO accounts (username, hashed_password, contact_email) "
            "VALUES ($1, $2, $3) "
            "RETURNING id, username, contact_email, subscription_status",
            body.username,
            hashed_password,
            body.contact_email,
        )
    except asyncpg.UniqueViolationError as exc:
        raise BadRequestError("Username or email is already registered.") from exc

    logger.info("account_created", username=body.username)
    return AccountResponse(**dict(row))


@router.get("/me/usage", response_model=UsageResponse)
async def get_usage(request: Request, username: str = Depends(verify_credentials)) -> UsageResponse:
    """
    Return today's analysis usage for the authenticated user.

    Free accounts have a daily limit configured in settings. Other tiers are unlimited.

    :param request: The FastAPI request (used to access the DB pool).
    :param username: The authenticated username (injected by verify_credentials).
    :return: Used today, daily limit, and remaining count.
    """
    pool = request.app.db_pool
    used_today = await count_analyses_today(pool, username)
    subscription = await pool.fetchrow("SELECT subscription_status FROM accounts WHERE username = $1", username)
    if subscription and subscription["subscription_status"] == "free":
        limit: int = settings.free_daily_limit
        remaining: int = max(0, limit - used_today)
    else:
        raise ValueError(
            f"Unknown subscription status: {subscription['subscription_status']}"
            if subscription
            else "Account not found."
        )
    return UsageResponse(used_today=used_today, daily_limit=limit, remaining=remaining)


async def get_me(request: Request, username: str = Depends(verify_credentials)) -> AccountResponse:
    """
    Return the authenticated user's account details.

    :param request: The FastAPI request (used to access the DB pool).
    :param username: The authenticated username (injected by verify_credentials).
    :return: The account details for the current user.
    :raises NotFoundError: If the account no longer exists.
    """
    row = await request.app.db_pool.fetchrow(
        "SELECT id, username, contact_email, subscription_status FROM accounts WHERE username = $1",
        username,
    )
    if row is None:
        raise NotFoundError("Account not found.")
    return AccountResponse(**dict(row))
