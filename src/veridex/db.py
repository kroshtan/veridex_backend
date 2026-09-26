import asyncpg

from veridex.config import settings

_CREATE_ACCOUNTS_TABLE = """
    CREATE TABLE IF NOT EXISTS accounts (
        id                      SERIAL PRIMARY KEY,
        username                TEXT UNIQUE NOT NULL CHECK (username = LOWER(username)),
        hashed_password         TEXT NOT NULL,
        contact_email           TEXT UNIQUE NOT NULL,
        subscription_status     TEXT NOT NULL DEFAULT 'free',
        paddle_subscription_id  TEXT,
        created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
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


_CREATE_ANALYZE_LOG_INDEX = """
    CREATE INDEX IF NOT EXISTS analyze_log_username_analyzed_at_idx ON analyze_log (username, analyzed_at)
"""


async def create_pool() -> asyncpg.Pool:
    """Create and return an asyncpg connection pool."""
    return await asyncpg.create_pool(settings.postgres_uri)


async def init_db(pool: asyncpg.Pool) -> None:
    """Create database tables if they do not already exist."""
    async with pool.acquire() as conn:
        await conn.execute(_CREATE_ACCOUNTS_TABLE)
        await conn.execute(_CREATE_ANALYZE_LOG_TABLE)
        # Migrations
        await conn.execute("ALTER TABLE accounts ADD COLUMN IF NOT EXISTS paddle_subscription_id TEXT")
        await conn.execute(_CREATE_ANALYZE_LOG_INDEX)


async def count_analyses_today(pool: asyncpg.Pool, username: str) -> int:
    """
    Return the number of logged analyses for a user since midnight UTC today.

    :param pool: The asyncpg connection pool.
    :param username: The username to count for.
    :return: Number of analyze_log rows for the user today.
    """
    row = await pool.fetchrow(
        "SELECT COUNT(*) FROM analyze_log "
        "WHERE username = $1 AND analyzed_at >= date_trunc('day', NOW() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'",
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


async def set_subscription(
    pool: asyncpg.Pool,
    username: str,
    subscription_status: str,
    paddle_subscription_id: str | None = None,
) -> None:
    """
    Set an account's subscription tier and linked Paddle subscription.

    :param pool: The asyncpg connection pool.
    :param username: The (lowercase) account username.
    :param subscription_status: The new tier.
    :param paddle_subscription_id: The Paddle subscription backing the tier, if any.
    """
    await pool.execute(
        "UPDATE accounts SET subscription_status = $2, paddle_subscription_id = $3 WHERE username = $1",
        username,
        subscription_status,
        paddle_subscription_id,
    )
