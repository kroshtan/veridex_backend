import asyncpg

from veridex.config import settings

_CREATE_ACCOUNTS_TABLE = """
    CREATE TABLE IF NOT EXISTS accounts (
        id                  SERIAL PRIMARY KEY,
        username            TEXT UNIQUE NOT NULL CHECK (username = LOWER(username)),
        hashed_password     TEXT NOT NULL,
        contact_email       TEXT UNIQUE NOT NULL,
        subscription_status TEXT NOT NULL DEFAULT 'free',
        created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
"""

_CREATE_ANALYZE_LOG_TABLE = """
    CREATE TABLE IF NOT EXISTS analyze_log (
        id          SERIAL PRIMARY KEY,
        username    TEXT NOT NULL REFERENCES accounts(username) ON DELETE CASCADE,
        url         TEXT NOT NULL,
        score       INTEGER NOT NULL,
        explanation TEXT NOT NULL,
        analyzed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
"""


async def create_pool() -> asyncpg.Pool:
    """Create and return an asyncpg connection pool."""
    return await asyncpg.create_pool(settings.postgres_uri)


async def init_db(pool: asyncpg.Pool) -> None:
    """Create database tables if they do not already exist."""
    async with pool.acquire() as conn:
        await conn.execute(_CREATE_ACCOUNTS_TABLE)
        await conn.execute(_CREATE_ANALYZE_LOG_TABLE)


async def get_subscription_status(pool: asyncpg.Pool, username: str) -> str:
    """
    Return the subscription_status for the given username.

    :param pool: The asyncpg connection pool.
    :param username: The username to look up.
    :return: The subscription status string (e.g. ``'free'``).
    """
    row = await pool.fetchrow("SELECT subscription_status FROM accounts WHERE username = $1", username)
    return str(row["subscription_status"])


async def count_analyses_today(pool: asyncpg.Pool, username: str) -> int:
    """
    Return the number of logged analyses for a user since midnight UTC today.

    :param pool: The asyncpg connection pool.
    :param username: The username to count for.
    :return: Number of analyze_log rows for the user today.
    """
    row = await pool.fetchrow(
        "SELECT COUNT(*) FROM analyze_log WHERE username = $1 AND analyzed_at >= CURRENT_DATE",
        username,
    )
    return int(row["count"])


async def log_analyze(pool: asyncpg.Pool, username: str, url: str, score: int, explanation: str) -> None:
    """
    Insert a completed analysis result into the audit log.

    :param pool: The asyncpg connection pool.
    :param username: The authenticated user who requested the analysis.
    :param url: The URL that was analysed.
    :param score: The reliability score returned by the graph.
    :param explanation: The one-line explanation returned by the graph.
    """
    await pool.execute(
        "INSERT INTO analyze_log (username, url, score, explanation) VALUES ($1, $2, $3, $4)",
        username,
        url,
        score,
        explanation,
    )
