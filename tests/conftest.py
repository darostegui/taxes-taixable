import pytest

from taixable_copilot.models import Country, IncomeType
from taixable_copilot.obligations import Assessment, Deadline, Obligation


@pytest.fixture
def sample_assessment() -> Assessment:
    return Assessment(
        primary_residence=Country.UK,
        residence_confidence=0.95,
        obligations=[
            Obligation(
                income_type=IncomeType.RENTAL,
                source_country=Country.ES,
                treaty_article="6",
                rate=0.0,
                relief="taxable-in-source",
                citation_ids=["ES-UK#art6", "ES-UK#art6-rate"],
            )
        ],
        deadlines=[
            Deadline(
                jurisdiction=Country.UK,
                description="UK annual tax return for 2025",
                due_date="2026-01-31",
                citation_id="UK#sa-deadline",
            )
        ],
        citations=["ES-UK#art6", "ES-UK#art6-rate", "UK#sa-deadline"],
    )
