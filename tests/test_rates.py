from taixable_copilot.models import Country, IncomeType
from taixable_copilot.rates import get_withholding_rate


def fake_lookup(country_pair, income_type):
    return {"rate": 0.15, "relief": "credit", "citation_id": "DE-UK#div-rate"}


def test_dividend_rate_lookup():
    r = get_withholding_rate(Country.DE, Country.UK, IncomeType.DIVIDEND, lookup=fake_lookup)
    assert r.rate == 0.15
    assert r.relief == "credit"
    assert r.citation_id == "DE-UK#div-rate"


def test_missing_rate_raises():
    import pytest

    with pytest.raises(LookupError):
        get_withholding_rate(
            Country.DE, Country.UK, IncomeType.DIVIDEND, lookup=lambda cp, it: None
        )
