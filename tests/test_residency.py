from taixable_copilot.models import Country
from taixable_copilot.residency import determine_residency

RULES = {
    Country.UK: {"days_threshold": 183, "citation_id": "UK#srt-day-count"},
    Country.ES: {"days_threshold": 183, "citation_id": "ES#183-day-rule"},
    Country.DE: {"days_threshold": 183, "citation_id": "DE#habitual-abode"},
}


def test_uk_resident_by_day_count():
    finding = determine_residency(days_present={Country.UK: 250, Country.ES: 40}, rules=RULES)
    assert finding.primary_residence == Country.UK
    assert finding.per_country[Country.UK] is True
    assert finding.per_country[Country.ES] is False
    assert finding.citations  # non-empty, references the rule source
    assert 0.0 < finding.confidence <= 1.0


def test_no_country_over_threshold_picks_most_days_low_confidence():
    finding = determine_residency(days_present={Country.UK: 120, Country.ES: 100}, rules=RULES)
    assert finding.primary_residence == Country.UK
    assert finding.confidence < 0.6
