import asyncpg
import bcrypt
import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from veridex.auth import verify_credentials
from veridex.config import settings
from veridex.db import count_analyses_today
from veridex.schemas.errors import BadRequestError, NotFoundError
from veridex.schemas.requests import CreateAccountRequest
from veridex.schemas.responses import AccountResponse, UsageResponse

logger = structlog.get_logger("veridex")

router = APIRouter(prefix="/v1/accounts", tags=["Accounts"])


@router.post("", response_model=AccountResponse, status_code=201)
async def create_account(
    body: CreateAccountRequest,
    request: Request,
    x_signup_key: str = Header(...),
) -> AccountResponse:
    """
    Create a new user account.

    Requires a valid ``X-Signup-Key`` header matching the configured secret, so only
    the web portal server (which holds the key in its environment) can call this endpoint.

    The password is hashed server-side before storage. Subscription status is set to
    ``'free'`` by the system and is not configurable by the caller.

    :param body: The request body with username, password, and contact email.
    :param request: The FastAPI request (used to access the DB pool).
    :param x_signup_key: Server-to-server secret key.
    :return: The created account (without password).
    :raises HTTPException: 403 if the signup key is missing or wrong.
    :raises BadRequestError: If the username or email is already registered.
    """
    if not settings.signup_secret or x_signup_key != settings.signup_secret:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid signup key.")
    hashed_password = bcrypt.hashpw(body.password.encode(), bcrypt.gensalt()).decode()
    username = body.username.lower()
    try:
        row = await request.app.db_pool.fetchrow(
            "INSERT INTO accounts (username, hashed_password, contact_email) "
            "VALUES ($1, $2, $3) "
            "RETURNING id, username, contact_email, subscription_status",
            username,
            hashed_password,
            body.contact_email,
        )
    except asyncpg.UniqueViolationError as exc:
        raise BadRequestError("Username or email is already registered.") from exc

    logger.info("account_created", username=username)
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
    sub_status = subscription["subscription_status"] if subscription else None
    if sub_status == "admin":
        return UsageResponse(used_today=used_today, daily_limit=None, remaining=None)
    if sub_status == "free":
        limit: int = settings.free_daily_limit
    elif sub_status == "premium":
        limit = settings.premium_daily_limit
    else:
        raise ValueError(
            f"Unknown subscription status: {sub_status}" if sub_status is not None else "Account not found."
        )
    remaining: int = max(0, limit - used_today)
    return UsageResponse(used_today=used_today, daily_limit=limit, remaining=remaining)


@router.get("/me", response_model=AccountResponse)
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
