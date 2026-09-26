from typing import Any

import httpx
import pytest

SIGNUP = {"X-Signup-Key": "test-signup-secret"}


async def test_signup_requires_key(client: httpx.AsyncClient) -> None:
    body = {"username": "alice", "password": "password123", "contact_email": "a@example.com"}
    assert (await client.post("/v1/accounts", json=body, headers={"X-Signup-Key": "wrong"})).status_code == 403


async def test_signup_login_and_me(client: httpx.AsyncClient) -> None:
    body = {"username": "Alice", "password": "password123", "contact_email": "a@example.com"}
    created = await client.post("/v1/accounts", json=body, headers=SIGNUP)
    assert created.status_code == 201
    assert created.json()["username"] == "alice"
    assert created.json()["subscription_status"] == "free"
    assert "password" not in created.text

    me = await client.get("/v1/accounts/me", auth=("ALICE", "password123"))
    assert me.status_code == 200
    assert me.json()["contact_email"] == "a@example.com"


async def test_duplicate_signup_rejected(client: httpx.AsyncClient) -> None:
    body = {"username": "bob", "password": "password123", "contact_email": "b@example.com"}
    assert (await client.post("/v1/accounts", json=body, headers=SIGNUP)).status_code == 201
    dup = await client.post("/v1/accounts", json={**body, "contact_email": "other@example.com"}, headers=SIGNUP)
    assert dup.status_code == 400


@pytest.mark.parametrize(
    "body",
    [
        {"username": "carol", "password": "short", "contact_email": "c@example.com"},
        {"username": "carol", "password": "password123", "contact_email": "not-an-email"},
        {"username": "carol", "password": "é" * 40, "contact_email": "c@example.com"},  # 80 bytes > bcrypt limit
    ],
)
async def test_signup_validation(client: httpx.AsyncClient, body: dict[str, str]) -> None:
    assert (await client.post("/v1/accounts", json=body, headers=SIGNUP)).status_code == 422


async def test_bad_credentials(client: httpx.AsyncClient, create_account: Any) -> None:
    await create_account("dave")
    assert (await client.get("/v1/accounts/me", auth=("dave", "wrong-password"))).status_code == 401
    assert (await client.get("/v1/accounts/me", auth=("nobody", "password123"))).status_code == 401
    assert (await client.get("/v1/accounts/me", auth=("dave", "x" * 100))).status_code == 401


async def test_blocked_account_is_forbidden(client: httpx.AsyncClient, create_account: Any) -> None:
    headers = await create_account("eve", status="blocked")
    assert (await client.get("/v1/accounts/me", headers=headers)).status_code == 403


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("free", {"used_today": 0, "daily_limit": 5, "remaining": 5}),
        ("premium", {"used_today": 0, "daily_limit": 25, "remaining": 25}),
        ("admin", {"used_today": 0, "daily_limit": None, "remaining": None}),
    ],
)
async def test_usage(client: httpx.AsyncClient, create_account: Any, status: str, expected: dict) -> None:
    headers = await create_account("frank", status=status)
    assert (await client.get("/v1/accounts/me/usage", headers=headers)).json() == expected
