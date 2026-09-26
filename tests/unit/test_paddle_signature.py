import hashlib
import hmac

from veridex.routes.paddle import verify_signature

SECRET = "whsec"
BODY = b'{"event_type":"subscription.activated"}'
NOW = 1_700_000_000


def _sign(body: bytes, ts: int, secret: str = SECRET) -> str:
    digest = hmac.new(secret.encode(), f"{ts}:".encode() + body, hashlib.sha256).hexdigest()
    return f"ts={ts};h1={digest}"


def test_valid_signature() -> None:
    assert verify_signature(BODY, _sign(BODY, NOW), SECRET, now=NOW)


def test_wrong_secret() -> None:
    assert not verify_signature(BODY, _sign(BODY, NOW, secret="other"), SECRET, now=NOW)


def test_tampered_body() -> None:
    assert not verify_signature(BODY + b" ", _sign(BODY, NOW), SECRET, now=NOW)


def test_stale_timestamp_rejected() -> None:
    assert not verify_signature(BODY, _sign(BODY, NOW - 3600), SECRET, now=NOW)


def test_malformed_header() -> None:
    for header in ("", "garbage", "ts=abc;h1=00", "h1=00"):
        assert not verify_signature(BODY, header, SECRET, now=NOW)
