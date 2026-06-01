"""Coverage-matrix contract tests for the 30-country deterministic engine.

These tests pin the *fail-closed* guarantees that let the LLM relay engine
output without hallucinating:

* day-count residency is modelled for the Tier-1 countries with a capped
  confidence (other statutory tests exist), and honours the 183-day boundary;
* coverage-only countries (no day_count rule) never assert residency as
  modelled and never fabricate a threshold;
* IE/PT have verified EUR bands and compute exact residence amounts;
* an *uncurated* treaty pair returns ``status="not_modelled"`` with no rate and
  withholds the residence net (so we never understate by inventing an FTC);
* every citation emitted by an assessment is in the known allowlist.
"""

from taixable_copilot.api.deps import build_default_deps
from taixable_copilot.models import Country, CustomerProfile, IncomeSource, IncomeType
from taixable_copilot.obligations import assess_obligations
from taixable_copilot.residency import determine_residency
from taixable_copilot.taxbands import load_tax_bands, progressive_tax


def _assess(profile, deps):
    return assess_obligations(
        profile,
        2025,
        deps.residency_rules,
        deps.treaty_retriever,
        deps.rate_lookup,
        deps.tax_bands,
        deps.known_citation_ids,
    )


def test_day_count_residency_is_capped_and_honours_boundary():
    deps = build_default_deps()
    rules = deps.residency_rules

    # 182 days in France is below the 183-day threshold -> UK (183) wins, and UK
    # is an original Tier-1 country with full confidence.
    below = determine_residency(
        days_present={Country.FR: 182, Country.UK: 183}, rules=rules
    )
    assert below.primary_residence == Country.UK
    assert below.confidence == 0.95

    # 183 days in France crosses the threshold; France is a newly-modelled
    # day-count country, so confidence is capped (other statutory tests exist).
    at = determine_residency(days_present={Country.FR: 183, Country.UK: 182}, rules=rules)
    assert at.primary_residence == Country.FR
    assert at.residency_modelled is True
    assert at.confidence <= 0.9
    assert at.tax_base_scope == "worldwide"


def test_coverage_only_country_never_asserts_modelled_residency():
    deps = build_default_deps()
    # The US uses a substantial-presence/citizenship test we do NOT model. Even
    # with 300 days the engine must flag residency as not modelled (no fabricated
    # day threshold) and keep confidence low.
    finding = determine_residency(
        days_present={Country.US: 300, Country.UK: 65}, rules=deps.residency_rules
    )
    assert finding.residency_modelled is False
    assert finding.confidence <= 0.5


def test_ireland_residence_computes_exact_band_amount():
    bands = load_tax_bands()
    # IE has no personal allowance in our cited band set; 50k through 20%/40%.
    expected = progressive_tax(50000, bands["IE"]["bands"])
    assert expected == 11200.0

    deps = build_default_deps()
    profile = CustomerProfile(
        residence_country=Country.IE,
        days_present={Country.IE: 220, Country.UK: 145},
        income=[IncomeSource(type=IncomeType.EMPLOYMENT, source_country=Country.IE, amount=50000)],
    )
    assessment = _assess(profile, deps)
    residence = next(e for e in assessment.estimates if e.role == "residence")
    assert residence.currency == "EUR"
    assert residence.gross_tax == 11200.0
    assert residence.citation_ids  # cited band source


def test_portugal_residence_computes_exact_band_amount():
    bands = load_tax_bands()
    expected = progressive_tax(50000, bands["PT"]["bands"])
    assert expected == 13858.28

    deps = build_default_deps()
    profile = CustomerProfile(
        residence_country=Country.PT,
        days_present={Country.PT: 220, Country.UK: 145},
        income=[IncomeSource(type=IncomeType.EMPLOYMENT, source_country=Country.PT, amount=50000)],
    )
    assessment = _assess(profile, deps)
    residence = next(e for e in assessment.estimates if e.role == "residence")
    assert residence.gross_tax == 13858.28


def test_andorra_residence_computes_exact_band_amount():
    bands = load_tax_bands()
    # 90k - 24k allowance = 66k taxable: 16k @ 5% + 50k @ 10% = 5,800.
    expected = progressive_tax(90000 - bands["AD"]["personal_allowance"], bands["AD"]["bands"])
    assert expected == 5800.0

    deps = build_default_deps()
    profile = CustomerProfile(
        residence_country=Country.AD,
        days_present={Country.AD: 250, Country.ES: 110},
        income=[IncomeSource(type=IncomeType.EMPLOYMENT, source_country=Country.AD, amount=90000)],
    )
    assessment = _assess(profile, deps)
    assert assessment.primary_residence == Country.AD
    residence = next(e for e in assessment.estimates if e.role == "residence")
    assert residence.currency == "EUR"
    assert residence.gross_tax == 5800.0
    assert "AD#irpf-bands" in residence.citation_ids


def test_uncurated_pair_is_not_modelled_and_withholds_net():
    deps = build_default_deps()
    # IE resident with UK-source rental: the IE-UK treaty pair is NOT curated, so
    # the engine must refuse to assert a withholding rate and must withhold the
    # residence net (omitting an FTC would overstate the bill).
    profile = CustomerProfile(
        residence_country=Country.IE,
        days_present={Country.IE: 200, Country.UK: 165},
        income=[
            IncomeSource(type=IncomeType.RENTAL, source_country=Country.UK, amount=24000),
            IncomeSource(type=IncomeType.EMPLOYMENT, source_country=Country.IE, amount=50000),
        ],
    )
    assessment = _assess(profile, deps)

    rental = next(o for o in assessment.obligations if o.income_type == IncomeType.RENTAL)
    assert rental.status == "not_modelled"
    assert rental.rate is None
    assert rental.treaty_article is None

    residence = next(e for e in assessment.estimates if e.role == "residence")
    assert residence.credit is None
    assert residence.net_tax is None


def test_assessment_citations_are_all_in_allowlist():
    deps = build_default_deps()
    known = set(deps.known_citation_ids)
    profile = CustomerProfile(
        residence_country=Country.ES,
        days_present={Country.ES: 190, Country.UK: 175},
        income=[
            IncomeSource(type=IncomeType.EMPLOYMENT, source_country=Country.UK, amount=90000),
            IncomeSource(type=IncomeType.RENTAL, source_country=Country.UK, amount=24000),
        ],
    )
    assessment = _assess(profile, deps)
    unknown = [c for c in assessment.citations if c not in known]
    assert unknown == []

def test_new_treaty_pairs_model_safe_income_and_fail_closed_on_rest():
    """FR-UK / NL-UK / IE-UK: interest, employment and (private) pension are
    curated from primary gov.uk treaty text and resolve as *modelled* with the
    verified article + a 0% source rate; dividend and rental are deliberately
    omitted (direction-dependent) and must fail closed."""
    from taixable_copilot.api.deps import build_default_deps
    from taixable_copilot.crossborder import resolve_cross_border

    deps = build_default_deps()
    known = set(deps.known_citation_ids)
    # (residence, source, {income_type: expected_article_no})
    expected = {
        (Country.FR, Country.UK): {
            IncomeType.INTEREST: "12",
            IncomeType.EMPLOYMENT: "15",
            IncomeType.PENSION: "18",
        },
        (Country.NL, Country.UK): {
            IncomeType.INTEREST: "11",
            IncomeType.EMPLOYMENT: "14",
            IncomeType.PENSION: "17",
        },
        (Country.IE, Country.UK): {
            IncomeType.INTEREST: "12",
            IncomeType.EMPLOYMENT: "15",
            IncomeType.PENSION: "17",
        },
    }
    for (res, src), arts in expected.items():
        for income, article_no in arts.items():
            t = resolve_cross_border(
                res, src, income, deps.treaty_retriever, deps.rate_lookup, known
            )
            assert t.modelled is True, (res, src, income)
            assert t.article_no == article_no, (res, src, income, t.article_no)
            assert t.rate == 0.0
            assert all(c in known for c in t.citation_ids)
        # direction-dependent flows must fail closed (no fabricated rate)
        for income in (IncomeType.DIVIDEND, IncomeType.RENTAL):
            t = resolve_cross_border(
                res, src, income, deps.treaty_retriever, deps.rate_lookup, known
            )
            assert t.modelled is False, (res, src, income)
            assert t.rate is None
            assert t.article_no is None


def test_russia_is_tier1_day_count_residency_capped():
    """Russia (RU) is modelled as a Tier-1 day-count residence (183 days in a
    rolling 12 months, simplified) with capped confidence because other
    statutory tests exist; the engine concludes residence and cites the FTS
    portal, but does NOT compute a Russian amount (no verified bands)."""
    deps = build_default_deps()
    rules = deps.residency_rules

    finding = determine_residency(
        days_present={Country.RU: 200, Country.UK: 165}, rules=rules
    )
    assert finding.primary_residence == Country.RU
    assert finding.per_country[Country.RU] is True
    assert finding.residency_modelled is True
    assert finding.confidence <= 0.9
    assert finding.tax_base_scope == "worldwide"
    assert "RU#tax-residency" in finding.citations

    # below the 183-day boundary -> not resident in RU
    below = determine_residency(
        days_present={Country.RU: 182, Country.UK: 183}, rules=rules
    )
    assert below.per_country[Country.RU] is False
    assert below.primary_residence == Country.UK

    # RU residency + scope citations are in the known allowlist (fail-closed)
    assert "RU#tax-residency" in deps.known_citation_ids
    assert "RU#income-tax" in deps.known_citation_ids


def test_south_africa_is_coverage_only_residency():
    """South Africa (ZA) uses an 'ordinarily resident' / physical-presence test
    that is not a single calendar-year day count, so residence is coverage-only:
    never concluded from days, never a fabricated threshold."""
    deps = build_default_deps()
    finding = determine_residency(
        days_present={Country.ZA: 300, Country.UK: 65}, rules=deps.residency_rules
    )
    assert finding.per_country[Country.ZA] is False
    assert finding.residency_modelled is False
    assert finding.confidence <= 0.5
    assert "days_threshold" not in deps.residency_rules[Country.ZA]
    assert "ZA#tax-residency" in deps.known_citation_ids
    assert "ZA#income-tax" in deps.known_citation_ids
