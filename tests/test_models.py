from taixable_copilot.models import (
    Country,
    CustomerProfile,
    IncomeSource,
    IncomeType,
)


def test_profile_foreign_sourced_income():
    p = CustomerProfile(
        residence_country=Country.UK,
        days_present={Country.UK: 250, Country.ES: 40},
        income=[
            IncomeSource(type=IncomeType.RENTAL, source_country=Country.ES, amount=12000),
            IncomeSource(type=IncomeType.DIVIDEND, source_country=Country.DE, amount=5000),
            IncomeSource(type=IncomeType.EMPLOYMENT, source_country=Country.UK, amount=60000),
        ],
    )
    foreign = p.foreign_sourced()
    assert {i.source_country for i in foreign} == {Country.ES, Country.DE}
    assert all(i.source_country != p.residence_country for i in foreign)


def test_country_pair_is_order_independent():
    assert Country.pair(Country.UK, Country.ES) == Country.pair(Country.ES, Country.UK)
    assert Country.pair(Country.ES, Country.UK) == "ES-UK"
