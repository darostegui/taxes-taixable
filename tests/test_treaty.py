from taixable_copilot.models import Country, IncomeType
from taixable_copilot.treaty import resolve_treaty_article


def fake_retriever(country_pair, income_type):
    assert country_pair == "ES-UK"
    return {
        "article_no": "6",
        "topic": "Income from immovable property",
        "text": "Income derived by a resident of a Contracting State from immovable property...",
        "citation_id": "ES-UK#art6",
    }


def test_rental_income_maps_to_article_6():
    art = resolve_treaty_article(
        Country.UK, Country.ES, IncomeType.RENTAL, retriever=fake_retriever
    )
    assert art.article_no == "6"
    assert art.citation_id == "ES-UK#art6"
    assert art.topic.startswith("Income from immovable")


def test_country_pair_normalized_regardless_of_direction():
    seen = {}

    def retriever(country_pair, income_type):
        seen["pair"] = country_pair
        return {"article_no": "10", "topic": "Dividends", "text": "", "citation_id": "ES-UK#art10"}

    resolve_treaty_article(Country.ES, Country.UK, IncomeType.DIVIDEND, retriever=retriever)
    assert seen["pair"] == "ES-UK"
