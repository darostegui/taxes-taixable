"""Tests for the approximate progressive-tax liability estimator.

The estimator is deterministic arithmetic over published, cited bands — it must
reproduce the worked example exactly and honour the currency-gating and
proportional foreign-tax-credit rules.
"""

from taixable_copilot.models import Country, CustomerProfile, IncomeSource, IncomeType
from taixable_copilot.taxbands import (
    ASSUMED_CURRENCY,
    estimate_liabilities,
    load_tax_bands,
    progressive_tax,
)

# A self-contained band fixture (mirrors data/tax_bands.json shape) so the unit
# tests do not depend on the exact shipped numbers drifting.
_BANDS = {
    "ES": {
        "currency": "EUR",
        "personal_allowance": 5550,
        "citation_id": "ES#irpf-bands",
        "bands": [
            {"up_to": 12450, "rate": 0.19},
            {"up_to": 20200, "rate": 0.24},
            {"up_to": 35200, "rate": 0.30},
            {"up_to": 60000, "rate": 0.37},
            {"up_to": 300000, "rate": 0.45},
            {"up_to": None, "rate": 0.47},
        ],
    },
    "UK": {
        "currency": "GBP",
        "personal_allowance": 12570,
        "citation_id": "UK#income-tax-bands",
        "bands": [
            {"up_to": 37700, "rate": 0.20},
            {"up_to": 112570, "rate": 0.40},
            {"up_to": None, "rate": 0.45},
        ],
    },
}


def _rate_lookup(cp, it):
    # Rental is taxed at source (rate>0, credited); everything else residence-only.
    if it == IncomeType.RENTAL:
        return {"rate": 0.19, "relief": "foreign tax credit", "citation_id": "ES-UK#art6-rate"}
    return {"rate": 0.0, "relief": "taxable in residence", "citation_id": "ES-UK#art14"}


def test_progressive_tax_matches_spanish_brackets():
    # 108,450 taxable through the ES brackets = 39,704.
    assert progressive_tax(108450, _BANDS["ES"]["bands"]) == 39704.0


def test_progressive_tax_zero_and_first_band():
    assert progressive_tax(0, _BANDS["ES"]["bands"]) == 0.0
    assert progressive_tax(-100, _BANDS["ES"]["bands"]) == 0.0
    assert progressive_tax(10000, _BANDS["ES"]["bands"]) == 1900.0  # 10000 * 19%


def test_worked_example_es_residence_with_uk_source_credit():
    profile = CustomerProfile(
        residence_country=Country.ES,
        days_present={Country.ES: 190, Country.UK: 175},
        income=[
            IncomeSource(type=IncomeType.EMPLOYMENT, source_country=Country.UK, amount=90000),
            IncomeSource(type=IncomeType.RENTAL, source_country=Country.UK, amount=24000),
        ],
    )
    estimates = estimate_liabilities(profile, Country.ES, _rate_lookup, _BANDS)

    res = [e for e in estimates if e.role == "residence"]
    src = [e for e in estimates if e.role == "source"]
    assert len(res) == 1 and len(src) == 1

    r = res[0]
    assert r.country == Country.ES
    assert r.currency == "EUR"
    assert r.gross_tax == 39704.0
    assert r.credit == 4560.0  # min(source tax, proportional cap)
    assert r.net_tax == 35144.0
    assert "ES#irpf-bands" in r.citation_ids
    assert "ES-UK#art6-rate" in r.citation_ids  # the credited rate is cited
    assert r.trace  # a human-readable calculation trace is present

    s = src[0]
    assert s.country == Country.UK
    assert s.gross_tax == 4560.0  # 24000 * 19%
    assert s.net_tax == 4560.0
    assert "ES-UK#art6-rate" in s.citation_ids


def test_uk_residence_progressive_estimate_withheld_for_currency():
    """Amounts are assumed EUR; UK bands are GBP, so the residence number is
    withheld rather than applying GBP thresholds to EUR figures."""
    profile = CustomerProfile(
        residence_country=Country.UK,
        days_present={Country.UK: 365},
        income=[
            IncomeSource(type=IncomeType.EMPLOYMENT, source_country=Country.UK, amount=90000),
        ],
    )
    estimates = estimate_liabilities(profile, Country.UK, _rate_lookup, _BANDS)
    res = [e for e in estimates if e.role == "residence"]
    assert len(res) == 1
    assert res[0].gross_tax is None  # withheld
    assert res[0].net_tax is None
    assert res[0].currency == "GBP"
    assert "currency" in res[0].note.lower()


def test_single_country_no_income_yields_no_source_estimates():
    profile = CustomerProfile(
        residence_country=Country.ES,
        days_present={Country.ES: 365},
        income=[],
    )
    estimates = estimate_liabilities(profile, Country.ES, _rate_lookup, _BANDS)
    # No income → residence taxable base 0, no source estimates.
    assert all(e.role == "residence" for e in estimates)
    res = estimates[0]
    assert res.gross_tax == 0.0
    assert res.net_tax == 0.0


def test_no_bands_returns_empty():
    profile = CustomerProfile(
        residence_country=Country.ES,
        days_present={Country.ES: 365},
        income=[],
    )
    assert estimate_liabilities(profile, Country.ES, _rate_lookup, None) == []
    assert estimate_liabilities(profile, Country.ES, _rate_lookup, {}) == []


def test_load_tax_bands_corpus_has_three_countries():
    bands = load_tax_bands()
    assert {"ES", "UK", "DE"} <= set(bands.keys())
    for spec in bands.values():
        assert spec["currency"] in {"EUR", "GBP"}
        assert spec["bands"]
        assert spec["citation_id"]
    assert ASSUMED_CURRENCY == "EUR"
