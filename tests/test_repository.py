from taixable_copilot.db import repository as repo


def test_persist_and_read_case_round_trip():
    engine = repo.make_engine("sqlite:///:memory:")
    cust_id = repo.create_customer(
        engine, customer_token="CUST-ABC123", residence_country="UK", display_label="UK contractor"
    )
    case_id = repo.create_case(
        engine,
        customer_id=cust_id,
        tax_year=2025,
        primary_residence="UK",
        summary="UK resident with ES rental income",
        approved_by="advisor@firm.example",
        deadlines=[
            {
                "jurisdiction": "UK",
                "description": "UK annual tax return for 2025",
                "due_date": "2026-01-31",
                "citation_id": "UK#sa-deadline",
            }
        ],
        citation_ids=["ES-UK#art6", "ES-UK#art6-rate"],
    )

    case = repo.get_case(engine, case_id)
    assert case is not None
    assert case["customer_id"] == cust_id
    assert case["status"] == "approved"
    assert case["approved_by"] == "advisor@firm.example"
    assert len(case["deadlines"]) == 1
    assert case["deadlines"][0]["citation_id"] == "UK#sa-deadline"
    assert set(case["citations"]) == {"ES-UK#art6", "ES-UK#art6-rate"}


def test_create_customer_is_idempotent_on_token():
    engine = repo.make_engine("sqlite:///:memory:")
    a = repo.create_customer(engine, customer_token="CUST-DUP", residence_country="ES")
    b = repo.create_customer(engine, customer_token="CUST-DUP", residence_country="ES")
    assert a == b
