#!/usr/bin/env python3
"""
Promote a user to admin by setting subscription_status = 'admin' directly in the DB.

Usage:
    uv run scripts/promote_admin.py <username>
"""

import asyncio
import sys

import asyncpg

from veridex.config import settings


async def promote(username: str) -> None:
    """Set ``subscription_status = 'admin'`` for ``username``."""
    conn = await asyncpg.connect(settings.postgres_uri)
    try:
        result = await conn.execute(
            "UPDATE accounts SET subscription_status = 'admin' WHERE username = $1",
            username.lower(),
        )
        if result == "UPDATE 0":
            sys.exit(f"Error: no account found for username '{username}'.")
        print(f"✓ '{username}' promoted to admin.")
    finally:
        await conn.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(f"Usage: python {sys.argv[0]} <username>")
    asyncio.run(promote(sys.argv[1]))
