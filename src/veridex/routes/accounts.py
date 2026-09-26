import asyncpg
import structlog
from fastapi import APIRouter, Depends, Header, Request

from veridex.auth import Account, hash_password, verify_credentials
from veridex.config import settings
from veridex.db import count_analyses_today
from veridex.schemas.errors import BadRequestError, ForbiddenError, NotFoundError
from veridex.schemas.requests import CreateAccountRequest
from veridex.schemas.responses import AccountResponse, UsageResponse

logger = structlog.get_logger("veridex")

router = APIRouter(prefix="/v1/accounts", tags=["Accounts"])

_ACCOUNT_COLUMNS = "id, username, contact_email, subscription_status"


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
    :raises ForbiddenError: If the signup key is missing or wrong.
    :raises BadRequestError: If the username or email is already registered.
    """
    if not settings.signup_secret or x_signup_key != settings.signup_secret:
        raise ForbiddenError("Invalid signup key.")
    username = body.username.lower()
    try:
        row = await request.app.db_pool.fetchrow(
            "INSERT INTO accounts (username, hashed_password, contact_email) "
            f"VALUES ($1, $2, $3) RETURNING {_ACCOUNT_COLUMNS}",
            username,
            await hash_password(body.password),
            body.contact_email,
        )
    except asyncpg.UniqueViolationError as exc:
        raise BadRequestError("Username or email is already registered.") from exc

    logger.info("account_created", username=username)
    return AccountResponse(**dict(row))


@router.get("/me/usage", response_model=UsageResponse)
async def get_usage(request: Request, account: Account = Depends(verify_credentials)) -> UsageResponse:
    """
    Return today's analysis usage for the authenticated user.

    Free and premium accounts have daily limits configured in settings; admins are unlimited.

    :param request: The FastAPI request (used to access the DB pool).
    :param account: The authenticated account (injected by verify_credentials).
    :return: Used today, daily limit, and remaining count.
    """
    used_today = await count_analyses_today(request.app.db_pool, account.username)
    limit = account.daily_limit
    if limit is None:
        return UsageResponse(used_today=used_today)
    return UsageResponse(used_today=used_today, daily_limit=limit, remaining=max(0, limit - used_today))


@router.get("/me", response_model=AccountResponse)
async def get_me(request: Request, account: Account = Depends(verify_credentials)) -> AccountResponse:
    """
    Return the authenticated user's account details.

    :param request: The FastAPI request (used to access the DB pool).
    :param account: The authenticated account (injected by verify_credentials).
    :return: The account details for the current user.
    :raises NotFoundError: If the account no longer exists.
    """
    row = await request.app.db_pool.fetchrow(
        f"SELECT {_ACCOUNT_COLUMNS} FROM accounts WHERE username = $1", account.username
    )
    if row is None:
        raise NotFoundError("Account not found.")
    return AccountResponse(**dict(row))
