"""Conversational tax-advisor agent: Gemini tool-calling over the deterministic engine.

This is the same no-hallucination contract as ``llm.py``, applied to a chat
interface. Gemini holds the conversation and decides *when* to call the
deterministic engine via the ``assess_tax_obligations`` tool; every tax figure,
treaty article, deadline and residency conclusion in the reply therefore comes
from the engine (with real, cited sources), never from the model's own
knowledge.

The agent is **optional and non-fatal**: if the SDK is missing or no credentials
are configured, :func:`chat` returns ``available=False`` and a message pointing
the user at the structured form. The deterministic core keeps working offline.
"""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING, Any

from taixable_copilot.citations import resolve_citations
from taixable_copilot.llm import _make_client
from taixable_copilot.models import Country, CustomerProfile, IncomeSource, IncomeType
from taixable_copilot.obligations import Assessment, assess_obligations

if TYPE_CHECKING:
    from taixable_copilot.api.deps import Deps

_SYSTEM_INSTRUCTION = (
    "You are Taixable, a professional virtual tax advisor specialising in "
    "cross-border global mobility for the United Kingdom (UK), Spain (ES) and "
    "Germany (DE).\n\n"
    "ABSOLUTE RULE — NEVER HALLUCINATE: You must never state a tax rate, treaty "
    "article, filing deadline, residency conclusion, monetary figure or legal "
    "claim that did not come from the assess_tax_obligations tool. If the tool "
    "has not given you a fact, you do not know it. Do not rely on your own "
    "training knowledge for any specific tax rule.\n\n"
    "GATHERING INFORMATION: Tax residence is normally the country where the "
    "person spends the most days in the tax year — infer it from the days unless "
    "the user states otherwise. Call assess_tax_obligations as soon as you know "
    "(a) the days spent in each country, summing to 365 (or 366 in a leap year), "
    "and (b) the person's income items (pass an empty list if they have none). "
    "Only UK, ES and DE are supported; if another country is mentioned, say so "
    "politely.\n\n"
    "WHEN INFORMATION IS MISSING: If the days do not sum to 365/366, or income is "
    "unknown, ask ONE short, specific clarifying question instead of guessing. "
    "Never assume.\n\n"
    "PRESENTING RESULTS: After the tool returns, explain the outcome clearly and "
    "professionally for a client: primary residence, each obligation (income "
    "type, where taxable, rate, relief), and filing deadlines. Always list the "
    "cited sources the tool returned. Close by noting this is decision support "
    "for a qualified tax professional, not a substitute for formal advice. Keep "
    "replies concise and well-structured."
)

_DEFAULT_MODEL = "gemini-2.5-flash"

_TOOL_DOC = (
    "Run the deterministic cross-border tax engine to compute obligations. Call "
    "this ONLY once you know the days per country (summing to 365/366) and the "
    "person's income items.\n\n"
    "Args:\n"
    "    days_present_json: JSON object mapping country code to days, e.g. "
    '\'{"UK":180,"ES":185}\'. Countries are limited to UK, ES, DE.\n'
    "    income_json: JSON array of income items, each "
    '{"type": one of employment|rental|dividend|interest|pension|capital_gain, '
    '"source_country": code, "amount": number}. Use \'[]\' if there is no '
    "income.\n"
    "    residence_country: Optional ISO-2 code (UK/ES/DE). If empty, the engine "
    "uses the country with the most days.\n"
    "    tax_year: The tax year, e.g. 2025."
)


def _serialize_assessment(
    assessment: Assessment, citation_index: dict | None
) -> dict[str, Any]:
    details = resolve_citations(assessment.citations, citation_index)
    return {
        "primary_residence": str(assessment.primary_residence),
        "residence_confidence": assessment.residence_confidence,
        "obligations": [
            {
                "income_type": str(o.income_type),
                "source_country": str(o.source_country),
                "treaty_article": o.treaty_article,
                "rate": o.rate,
                "relief": o.relief,
            }
            for o in assessment.obligations
        ],
        "deadlines": [
            {
                "jurisdiction": str(d.jurisdiction),
                "description": d.description,
                "due_date": d.due_date,
            }
            for d in assessment.deadlines
        ],
        "sources": [
            {"id": c.id, "label": c.label, "url": c.url} for c in details
        ],
    }


_COUNTRY_ALIASES = {
    "UK": Country.UK, "GB": Country.UK, "GBR": Country.UK,
    "UNITED KINGDOM": Country.UK, "GREAT BRITAIN": Country.UK, "BRITAIN": Country.UK,
    "ENGLAND": Country.UK, "SCOTLAND": Country.UK, "WALES": Country.UK,
    "ES": Country.ES, "ESP": Country.ES, "SPAIN": Country.ES,
    "ESPANA": Country.ES, "ESPAÑA": Country.ES,
    "DE": Country.DE, "DEU": Country.DE, "GERMANY": Country.DE,
    "DEUTSCHLAND": Country.DE,
}


def _norm_country(value: str) -> Country:
    """Map a code or common country name to a supported Country (raises if unknown)."""
    key = str(value).strip().upper()
    if key in _COUNTRY_ALIASES:
        return _COUNTRY_ALIASES[key]
    return Country(key)  # raises ValueError for anything unsupported


_INCOME_ALIASES = {
    "salary": IncomeType.EMPLOYMENT, "wage": IncomeType.EMPLOYMENT,
    "wages": IncomeType.EMPLOYMENT, "employment": IncomeType.EMPLOYMENT,
    "job": IncomeType.EMPLOYMENT,
    "rent": IncomeType.RENTAL, "rental": IncomeType.RENTAL,
    "property": IncomeType.RENTAL,
    "dividend": IncomeType.DIVIDEND, "dividends": IncomeType.DIVIDEND,
    "interest": IncomeType.INTEREST,
    "pension": IncomeType.PENSION, "pensions": IncomeType.PENSION,
    "capital_gain": IncomeType.CAPITAL_GAIN, "capital gains": IncomeType.CAPITAL_GAIN,
    "capital gain": IncomeType.CAPITAL_GAIN, "capitalgain": IncomeType.CAPITAL_GAIN,
}


def _norm_income_type(value: str) -> IncomeType:
    key = str(value).strip().lower()
    if key in _INCOME_ALIASES:
        return _INCOME_ALIASES[key]
    return IncomeType(key)  # raises ValueError for anything unsupported


def _build_profile(
    days: dict, income_raw: list, residence_country: str
) -> CustomerProfile:
    """Validate model-supplied data and build a CustomerProfile (raises on bad input)."""
    days_present: dict[Country, int] = {}
    for code, n in days.items():
        days_present[_norm_country(code)] = int(n)
    if not days_present:
        raise ValueError("No days_present provided.")

    income: list[IncomeSource] = []
    for item in income_raw:
        income.append(
            IncomeSource(
                type=_norm_income_type(item["type"]),
                source_country=_norm_country(item["source_country"]),
                amount=float(item["amount"]),
            )
        )

    if residence_country:
        residence = _norm_country(residence_country)
    else:
        residence = max(days_present.items(), key=lambda kv: kv[1])[0]
    return CustomerProfile(
        residence_country=residence, days_present=days_present, income=income
    )


def _make_assess_tool(deps: "Deps"):
    """Build the engine-backed tool plus a container that captures its last result."""
    captured: dict[str, Any] = {}

    def assess_tax_obligations(
        days_present_json: str,
        income_json: str,
        residence_country: str = "",
        tax_year: int = 2025,
    ) -> dict:
        try:
            days = json.loads(days_present_json)
            income_raw = json.loads(income_json) if income_json else []
            profile = _build_profile(days, income_raw, residence_country)
            assessment = assess_obligations(
                profile,
                int(tax_year),
                deps.residency_rules,
                deps.treaty_retriever,
                deps.rate_lookup,
            )
            result = _serialize_assessment(assessment, deps.citation_index)
        except Exception as exc:  # noqa: BLE001 - report bad input back to the model
            if os.getenv("TAIXABLE_DEBUG"):
                import sys
                print(
                    f"[assess_tool] days={days_present_json!r} income={income_json!r} "
                    f"res={residence_country!r} yr={tax_year!r} -> "
                    f"{type(exc).__name__}: {exc}",
                    file=sys.stderr,
                )
            # Return a structured error so the model asks a clarifying question
            # rather than fabricating an answer.
            return {"error": str(exc), "supported_countries": ["UK", "ES", "DE"]}
        captured["assessment"] = result
        return result

    assess_tax_obligations.__doc__ = _TOOL_DOC
    # `from __future__ import annotations` turns the signature annotations into
    # strings; the google-genai SDK coerces tool args via isinstance() against
    # these annotations, which raises "isinstance() arg 2 must be a type". Bind
    # real types so automatic function calling can invoke the tool.
    assess_tax_obligations.__annotations__ = {
        "days_present_json": str,
        "income_json": str,
        "residence_country": str,
        "tax_year": int,
        "return": dict,
    }
    return assess_tax_obligations, captured


def _to_contents(history: list[dict], message: str):
    """Map a plain {role, content} history + new message to genai Content list."""
    from google.genai import types

    contents = []
    for turn in history:
        role = "model" if turn.get("role") in {"assistant", "model"} else "user"
        text = turn.get("content", "")
        if text:
            contents.append(types.Content(role=role, parts=[types.Part(text=text)]))
    contents.append(types.Content(role="user", parts=[types.Part(text=message)]))
    return contents


def chat(
    deps: "Deps",
    history: list[dict],
    message: str,
    tax_year: int = 2025,
) -> dict[str, Any]:
    """Run one conversational turn. Returns reply text, tool-use flag, assessment.

    Never raises: on any SDK/credential/model failure it returns a graceful,
    professional message and ``available=False``/``error`` so the UI can fall
    back to the structured form.
    """
    client = _make_client()
    if client is None:
        return {
            "reply": (
                "The AI advisor is currently offline. Please use the structured "
                "form to allocate days across countries and add income — it "
                "produces the same cited assessment."
            ),
            "available": False,
            "used_tool": False,
            "assessment": None,
        }

    assess_tool, captured = _make_assess_tool(deps)
    model = os.getenv("GEMINI_MODEL", _DEFAULT_MODEL)
    try:
        from google.genai import types

        resp = client.models.generate_content(
            model=model,
            contents=_to_contents(history, message),
            config=types.GenerateContentConfig(
                system_instruction=_SYSTEM_INSTRUCTION,
                tools=[assess_tool],
                temperature=0.2,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        )
        reply = (resp.text or "").strip()
    except Exception:  # noqa: BLE001 - network/model/quota error → graceful message
        return {
            "reply": (
                "Sorry — I couldn't reach the AI advisor just now. Please try "
                "again, or use the structured form for an immediate cited "
                "assessment."
            ),
            "available": False,
            "used_tool": False,
            "assessment": None,
        }

    return {
        "reply": reply
        or "Could you share a little more detail so I can assess your situation?",
        "available": True,
        "used_tool": "assessment" in captured,
        "assessment": captured.get("assessment"),
    }
