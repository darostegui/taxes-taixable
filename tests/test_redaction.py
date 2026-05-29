from taixable_copilot.redaction import redact_profile


def test_redaction_round_trip():
    raw = {
        "name": "Jane Doe",
        "national_id": "AB123456C",
        "email": "jane@example.com",
        "residence_country": "UK",
        "days_present": {"UK": 250, "ES": 40},
        "income": [{"type": "rental", "source_country": "ES", "amount": 12000}],
    }
    redacted, rehydrator = redact_profile(raw)

    blob = str(redacted)
    assert "Jane Doe" not in blob
    assert "AB123456C" not in blob
    assert "jane@example.com" not in blob

    assert redacted["customer_token"].startswith("CUST-")
    # tax-relevant attributes are preserved
    assert redacted["residence_country"] == "UK"
    assert redacted["days_present"] == {"UK": 250, "ES": 40}

    # identity recoverable only locally via the rehydrator
    token = redacted["customer_token"]
    assert rehydrator.name(token) == "Jane Doe"
    assert rehydrator.identity(token)["national_id"] == "AB123456C"


def test_same_raw_identity_is_stable_token():
    raw = {"name": "Jane Doe", "national_id": "AB123456C", "residence_country": "UK"}
    r1, _ = redact_profile(raw)
    r2, _ = redact_profile(raw)
    assert r1["customer_token"] == r2["customer_token"]
