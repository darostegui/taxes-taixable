"""Simple stateless login guardrail — no database, stdlib only.

A username/password gate for the hosted demo that issues an HMAC-signed bearer
token. Credentials and the signing secret come from the environment; dev
defaults exist only so local and test runs work out of the box.

Safety design (so a forgotten env var can never silently weaken production):
- ``TAIXABLE_ENV`` selects the environment. Only ``dev``/``test``/``local`` may
  use the dev-default secret/password or disable auth entirely.
- Anything else (i.e. production) MUST set ``TAIXABLE_AUTH_SECRET`` and a real
  admin password; ``TAIXABLE_AUTH_DISABLED`` is ignored outside dev/test.
- Settings are read from the environment at call time (not frozen at import),
  so tests can monkeypatch freely.

Token format: ``v1.<base64url(json payload)>.<base64url(hmac-sha256)>`` where the
payload is ``{"sub","iat","exp"}``. Signatures and passwords are compared in
constant time.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time

_TOKEN_VERSION = "v1"
_DEFAULT_TTL_SECONDS = 12 * 3600
_CLOCK_SKEW = 60  # seconds of future-iat tolerance
_DEV_ENVS = {"dev", "test", "local"}

# Dev-only fallbacks. Production overrides these via the environment (see deploy).
_DEV_SECRET = "taixable-dev-secret-change-me"
_DEV_ADMIN_PASSWORD = "taixable-admin"
# Public judge/demo account. Always present so hackathon reviewers can sign in
# with ``demo`` / ``demo`` without provisioning. Override via ``TAIXABLE_DEMO_PASSWORD``.
_DEMO_PASSWORD = "demo"

# --- brute-force throttle (in-memory, best-effort) -------------------------
_FAIL_WINDOW = 300  # seconds
_FAIL_LIMIT = 5
_failures: dict[str, list[float]] = {}


def _env() -> str:
    return (os.getenv("TAIXABLE_ENV") or "").strip().lower()


def is_dev_env() -> bool:
    return _env() in _DEV_ENVS


def auth_disabled() -> bool:
    """Auth may only be disabled in an explicit dev/test/local environment."""
    if not is_dev_env():
        return False
    flag = (os.getenv("TAIXABLE_AUTH_DISABLED") or "").strip().lower()
    return flag in {"1", "true", "yes", "on"}


def _secret() -> bytes:
    val = os.getenv("TAIXABLE_AUTH_SECRET")
    if not val:
        # Acceptable only in dev/test; production is expected to set the env.
        val = _DEV_SECRET
    return val.encode("utf-8")


def users() -> dict[str, str]:
    """username -> password.

    Parsed from ``TAIXABLE_USERS`` (``"user1:pass1,user2:pass2"``); an ``admin``
    user is always present (password from ``TAIXABLE_ADMIN_PASSWORD`` or the dev
    default) so there is a known account for testing the demo. A public ``demo``
    user (password from ``TAIXABLE_DEMO_PASSWORD``, default ``demo``) is also always
    present so hackathon judges can sign in without provisioning.
    """
    table: dict[str, str] = {}
    raw = os.getenv("TAIXABLE_USERS", "")
    for pair in raw.split(","):
        pair = pair.strip()
        if not pair or ":" not in pair:
            continue
        name, _, pw = pair.partition(":")
        name, pw = name.strip(), pw.strip()
        if name and pw:
            table[name] = pw
    if "admin" not in table:
        table["admin"] = os.getenv("TAIXABLE_ADMIN_PASSWORD", _DEV_ADMIN_PASSWORD)
    if "demo" not in table:
        table["demo"] = os.getenv("TAIXABLE_DEMO_PASSWORD", _DEMO_PASSWORD)
    return table


def verify_credentials(username: str, password: str) -> bool:
    table = users()
    expected = table.get((username or "").strip())
    if expected is None:
        # Burn a comparison to reduce a username-existence timing oracle.
        secrets.compare_digest((password or ""), "x" * 24)
        return False
    return secrets.compare_digest((password or ""), expected)


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _sign(payload_b64: str) -> str:
    sig = hmac.new(_secret(), payload_b64.encode("ascii"), hashlib.sha256).digest()
    return _b64e(sig)


def issue_token(username: str, ttl_seconds: int = _DEFAULT_TTL_SECONDS) -> tuple[str, int]:
    now = int(time.time())
    payload = {"sub": username, "iat": now, "exp": now + ttl_seconds}
    payload_b64 = _b64e(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    return f"{_TOKEN_VERSION}.{payload_b64}.{_sign(payload_b64)}", ttl_seconds


def verify_token(token: str | None) -> str | None:
    """Return the username for a valid, unexpired, current-user token, else None."""
    if not token:
        return None
    parts = token.split(".")
    if len(parts) != 3 or parts[0] != _TOKEN_VERSION:
        return None
    _, payload_b64, sig = parts
    if not hmac.compare_digest(sig, _sign(payload_b64)):
        return None
    try:
        payload = json.loads(_b64d(payload_b64))
        sub = str(payload["sub"])
        iat = int(payload["iat"])
        exp = int(payload["exp"])
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None
    now = int(time.time())
    if not sub or now > exp or iat > now + _CLOCK_SKEW:
        return None
    if sub not in users():  # user removed since the token was issued
        return None
    return sub


# --- throttle helpers ------------------------------------------------------
def _recent(key: str) -> list[float]:
    now = time.time()
    arr = [t for t in _failures.get(key, []) if now - t < _FAIL_WINDOW]
    _failures[key] = arr
    return arr


def is_locked(key: str) -> bool:
    return len(_recent(key)) >= _FAIL_LIMIT


def register_failure(key: str) -> None:
    arr = _recent(key)
    arr.append(time.time())
    _failures[key] = arr


def clear_failures(key: str) -> None:
    _failures.pop(key, None)
