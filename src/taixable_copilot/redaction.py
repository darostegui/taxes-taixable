"""PII redaction / tokenization.

Strips identity fields from a raw customer record before anything is sent to the
cloud model. The model reasons only over tax-relevant attributes; identity is
recoverable locally via the returned Rehydrator (which never leaves the backend).
"""

from __future__ import annotations

import hashlib

# Fields treated as identity / PII and removed from the redacted profile.
IDENTITY_FIELDS = ("name", "national_id", "email", "phone", "address", "dob")

# Fields that are tax-relevant and safe to send to the model.
TAX_FIELDS = ("residence_country", "days_present", "income")


class Rehydrator:
    """Local-only map from customer_token back to the original identity fields."""

    def __init__(self) -> None:
        self._by_token: dict[str, dict] = {}

    def register(self, token: str, identity: dict) -> None:
        self._by_token[token] = identity

    def identity(self, token: str) -> dict:
        return self._by_token[token]

    def name(self, token: str) -> str | None:
        return self._by_token.get(token, {}).get("name")


def _stable_token(identity: dict) -> str:
    basis = "|".join(
        str(identity.get(f, "")) for f in ("national_id", "email", "name")
    )
    digest = hashlib.sha256(basis.encode("utf-8")).hexdigest()[:10].upper()
    return f"CUST-{digest}"


def redact_profile(raw: dict) -> tuple[dict, Rehydrator]:
    """Split a raw record into (redacted_profile, rehydrator)."""
    identity = {f: raw[f] for f in IDENTITY_FIELDS if f in raw}
    token = _stable_token(identity)

    redacted: dict = {"customer_token": token}
    for f in TAX_FIELDS:
        if f in raw:
            redacted[f] = raw[f]

    rehydrator = Rehydrator()
    rehydrator.register(token, identity)
    return redacted, rehydrator
