from taixable_copilot.models import Country, CustomerProfile, IncomeSource, IncomeType
from taixable_copilot.obligations import assess_obligations


def test_cross_border_assessment():
    p = CustomerProfile(
        residence_country=Country.UK,
        days_present={Country.UK: 250, Country.ES: 40},
        income=[
            IncomeSource(type=IncomeType.RENTAL, source_country=Country.ES, amount=12000),
            IncomeSource(type=IncomeType.EMPLOYMENT, source_country=Country.UK, amount=60000),
        ],
    )
    result = assess_obligations(
        p,
        tax_year=2025,
        residency_rules={
            Country.UK: {"days_threshold": 183, "citation_id": "UK#srt"},
            Country.ES: {"days_threshold": 183, "citation_id": "ES#183"},
        },
        treaty_retriever=lambda cp, it: {
            "article_no": "6",
            "topic": "Immovable property",
            "text": "",
            "citation_id": "ES-UK#art6",
        },
        rate_lookup=lambda cp, it: {
            "rate": 0.0,
            "relief": "taxable-in-source",
            "citation_id": "ES-UK#art6-rate",
        },
    )
    assert result.primary_residence == Country.UK
    rental_obs = [o for o in result.obligations if o.income_type == IncomeType.RENTAL]
    assert len(rental_obs) == 1
    assert rental_obs[0].treaty_article == "6"
    assert "ES-UK#art6" in rental_obs[0].citation_ids
    assert "ES-UK#art6-rate" in rental_obs[0].citation_ids
    # only foreign-sourced income produces a cross-border obligation
    assert all(o.source_country != Country.UK for o in result.obligations)
    # every obligation cites at least one source
    assert all(o.citation_ids for o in result.obligations)
    # residence-country filing deadline is present
    assert any(d.jurisdiction == Country.UK for d in result.deadlines)
