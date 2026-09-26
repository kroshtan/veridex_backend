import hashlib
import hmac
import json
import time
from typing import Any

import asyncpg
import httpx
import pytest

from veridex.config import settings


def _webhook(event_type: str, username: str, subscription_id: str = "sub_1") -> tuple[bytes, dict[str, str]]:
    body = json.dumps(
        {"event_type": event_type, "data": {"id": subscription_id, "custom_data": {"username": username}}}
    ).encode()
    ts = int(time.time())
    digest = hmac.new(b"test-webhook-secret", f"{ts}:".encode() + body, hashlib.sha256).hexdigest()
    return body, {"Paddle-Signature": f"ts={ts};h1={digest}", "Content-Type": "application/json"}


async def _status(pool: asyncpg.Pool, username: str) -> str:
    return str(await pool.fetchval("SELECT subscription_status FROM accounts WHERE username = $1", username))


async def test_admin_routes_require_admin(client: httpx.AsyncClient, create_account: Any) -> None:
    headers = await create_account("alice")
    assert (await client.get("/v1/admin/accounts", headers=headers)).status_code == 403


async def test_admin_list_search(client: httpx.AsyncClient, create_account: Any) -> None:
    admin = await create_account("root", status="admin")
    await create_account("alice")
    await create_account("bob")

    everyone = await client.get("/v1/admin/accounts", headers=admin)
    assert [a["username"] for a in everyone.json()] == ["alice", "bob", "root"]

    found = await client.get("/v1/admin/accounts", params={"search": "BOB@"}, headers=admin)
    assert [a["username"] for a in found.json()] == ["bob"]


async def test_admin_block_and_downgrade(client: httpx.AsyncClient, pool: asyncpg.Pool, create_account: Any) -> None:
    admin = await create_account("root", status="admin")
    await create_account("alice", status="premium")

    assert (await client.post("/v1/admin/accounts/Alice/downgrade", headers=admin)).status_code == 200
    assert await _status(pool, "alice") == "free"

    assert (await client.post("/v1/admin/accounts/alice/block", headers=admin)).status_code == 200
    assert await _status(pool, "alice") == "blocked"

    assert (await client.post("/v1/admin/accounts/ghost/block", headers=admin)).status_code == 404


async def test_webhook_activates_and_cancels(
    client: httpx.AsyncClient, pool: asyncpg.Pool, create_account: Any
) -> None:
    await create_account("alice")

    body, headers = _webhook("subscription.activated", "Alice")
    assert (await client.post("/v1/paddle/webhook", content=body, headers=headers)).status_code == 200
    assert await _status(pool, "alice") == "premium"

    # Cancellation of some other (stale) subscription must not downgrade the account.
    body, headers = _webhook("subscription.canceled", "alice", subscription_id="sub_old")
    await client.post("/v1/paddle/webhook", content=body, headers=headers)
    assert await _status(pool, "alice") == "premium"

    body, headers = _webhook("subscription.canceled", "alice")
    await client.post("/v1/paddle/webhook", content=body, headers=headers)
    assert await _status(pool, "alice") == "free"


@pytest.mark.parametrize("status", ["blocked", "admin"])
async def test_webhook_cannot_change_blocked_or_admin(
    client: httpx.AsyncClient, pool: asyncpg.Pool, create_account: Any, status: str
) -> None:
    await create_account("alice", status=status)
    body, headers = _webhook("subscription.activated", "alice")
    await client.post("/v1/paddle/webhook", content=body, headers=headers)
    assert await _status(pool, "alice") == status


async def test_webhook_rejects_bad_signature(
    client: httpx.AsyncClient, pool: asyncpg.Pool, create_account: Any
) -> None:
    await create_account("alice")
    body, headers = _webhook("subscription.activated", "alice")
    headers["Paddle-Signature"] = headers["Paddle-Signature"][:-4] + "0000"
    assert (await client.post("/v1/paddle/webhook", content=body, headers=headers)).status_code == 400
    assert await _status(pool, "alice") == "free"


async def test_webhook_fails_closed_without_secret(
    client: httpx.AsyncClient, pool: asyncpg.Pool, create_account: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    await create_account("alice")
    monkeypatch.setattr(settings, "paddle_webhook_secret", "")
    body, headers = _webhook("subscription.activated", "alice")
    assert (await client.post("/v1/paddle/webhook", content=body, headers=headers)).status_code == 500
    assert await _status(pool, "alice") == "free"
