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
    """
    row = await request.app.db_pool.fetchrow(
        "SELECT hashed_password FROM accounts WHERE username = $1",
        credentials.username.lower(),
    )
    if row is None or not bcrypt.checkpw(credentials.password.encode(), row["hashed_password"].encode()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials.",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username.lower()  # type: ignore[no-any-return]
