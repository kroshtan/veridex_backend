import bcrypt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

security = HTTPBasic()


async def verify_credentials(
    request: Request,
    credentials: HTTPBasicCredentials = Depends(security),
) -> str:
    """
    Verify HTTP Basic Auth credentials against the accounts table.

    :param request: The incoming request (used to access the DB pool).
    :param credentials: The HTTP Basic Auth credentials.
    :return: The authenticated username.
    :raises HTTPException: 401 if credentials are missing or invalid.
    :raises HTTPException: 403 if the account is blocked.
    """
    row = await request.app.db_pool.fetchrow(
        "SELECT hashed_password, subscription_status FROM accounts WHERE username = $1",
        credentials.username.lower(),
    )
    if row is None or not bcrypt.checkpw(credentials.password.encode(), row["hashed_password"].encode()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials.",
            headers={"WWW-Authenticate": "Basic"},
        )
    if row["subscription_status"] == "blocked":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is blocked.")
    return credentials.username.lower()  # type: ignore[no-any-return]


async def require_admin(
    request: Request,
    username: str = Depends(verify_credentials),
) -> str:
    """
    Extend verify_credentials to also require admin tier.

    :raises HTTPException: 403 if the account is not an admin.
    """
    row = await request.app.db_pool.fetchrow("SELECT subscription_status FROM accounts WHERE username = $1", username)
    if not row or row["subscription_status"] != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required.")
    return username
