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
    "claim that did not come from a tool. If a tool has not given you a fact, you "
    "do not know it. Do not rely on your own training knowledge for any specific "
    "tax rule.\n\n"
    "YOU HAVE TWO TOOLS:\n"
    "1. assess_tax_obligations — the deterministic engine and the ONLY source of "
    "computed figures: residence determination, rates, treaty articles, relief "
    "and filing deadlines for a specific person. Use it whenever the user gives "
    "you their days per country and income.\n"
    "2. search_tax_knowledge — a curated Elasticsearch knowledge base covering "
    "the UK/ES/DE legislation and double-tax-treaty articles AND a broader cited "
    "reference corpus of ~147 jurisdictions worldwide (residence and personal-"
    "income-tax source pointers from PwC Worldwide Tax Summaries and official tax "
    "authorities). Use it to EXPLAIN concepts and answer general questions (e.g. "
    "'what is the 183-day rule?', 'how does DE/ES treaty relief work?', 'where can "
    "I read France's residence rules?'). It returns curated passages with source "
    "URLs. This is EVIDENCE ONLY: you may explain and quote retrieved passages and "
    "you MUST cite their source, but you may NOT compute a person's rate, residence "
    "or deadline from them — that always comes from assess_tax_obligations.\n\n"
    "CHOOSING A TOOL: For a specific client's obligations, call "
    "assess_tax_obligations. For background, definitions, or 'how does X work' "
    "questions, call search_tax_knowledge and ground your answer strictly in the "
    "returned passages, citing the source. You may use both in one turn (e.g. "
    "assess, then explain a treaty article you searched).\n\n"
    "COVERAGE — TWO TIERS, FAIL CLOSED: Computed obligations (amounts, residence, "
    "treaty relief, deadlines) are available ONLY for the UK, ES and DE. For any "
    "other jurisdiction you may search and surface the cited reference card, but "
    "you MUST say plainly that Taixable does not yet COMPUTE that country's tax and "
    "point the user to the cited source — never estimate it yourself. This "
    "fail-closed honesty is a feature, not a limitation.\n\n"
    "GATHERING INFORMATION: Tax residence is normally the country where the "
    "person spends the most days in the tax year — infer it from the days unless "
    "the user states otherwise. Call assess_tax_obligations as soon as you know "
    "(a) the days spent in each country, summing to 365 (or 366 in a leap year), "
    "and (b) the person's income items (pass an empty list if they have none). "
    "Computed obligations are available for UK, ES and DE only; if another country "
    "is mentioned, you may still search and cite its reference card, but say "
    "clearly that Taixable does not yet compute that country's tax.\n\n"
    "WHEN INFORMATION IS MISSING: If the days do not sum to 365/366, or income is "
    "unknown, ask ONE short, specific clarifying question instead of guessing. "
    "If neither tool returns relevant facts, say plainly that you do not have "
    "grounded information rather than guessing. Never assume.\n\n"
    "PRESENTING RESULTS: After a tool returns, lead with the bottom line for the "
    "client: WHERE they pay and roughly HOW MUCH. Use the engine's `estimates` "
    "block for amounts — each entry gives a country, role (residence or source), "
    "currency, an illustrative gross/credit/net figure and a method note. State "
    "these figures exactly as the engine returned them and clearly label them as "
    "APPROXIMATE / ILLUSTRATIVE. If an estimate's gross is null (e.g. the "
    "residence country's bands are in a different currency from the income), say "
    "the amount cannot be reliably estimated rather than inventing one. ONLY "
    "discuss jurisdictions that actually tax this person — if a country appears in "
    "neither the obligations nor the estimates, do not raise its legislation or "
    "rules (it only adds confusion). Then give each obligation (income type, where "
    "taxable, rate, relief) and filing deadlines. Always cite the sources the "
    "tools returned. Always include this disclaimer when you give amounts: the "
    "figure is approximate, excludes deductions, allowances beyond the standard "
    "personal allowance, regional variation and social security, and applies no "
    "currency conversion. Close by noting this is decision support for a qualified "
    "tax professional, not a substitute for formal advice. Keep replies concise "
    "and well-structured."
)

_DEFAULT_MODEL = "gemini-3-flash-preview"

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

_SEARCH_TOOL_DOC = (
    "Search the curated Elasticsearch tax-knowledge base with hybrid keyword + "
    "semantic retrieval. Covers UK/ES/DE legislation and double-tax-treaty "
    "articles plus a cited reference corpus of ~147 jurisdictions (residence and "
    "personal-income-tax source pointers). Use this to explain concepts, answer "
    "general questions, or surface the authoritative source for a country Taixable "
    "does not compute; it returns curated passages with source URLs. EVIDENCE "
    "ONLY — do not derive a person's figures from it.\n\n"
    "Args:\n"
    "    query: A natural-language question or topic, e.g. 'Spain 183 day rule' "
    "or 'Germany UK pension treaty'.\n"
    "    jurisdiction: Optional filter — a country code (UK/ES/DE) or treaty pair "
    '(e.g. "ES-UK"). Leave empty to search everything.'
)


def _serialize_assessment(
    assessment: Assessment,
    citation_index: dict | None,
    legislation_lookup: Any | None = None,
) -> dict[str, Any]:
    details = resolve_citations(assessment.citations, citation_index)
    result = {
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
        "estimates": [
            {
                "country": str(e.country),
                "role": e.role,
                "currency": e.currency,
                "taxable_base": e.taxable_base,
                "gross_tax": e.gross_tax,
                "credit": e.credit,
                "net_tax": e.net_tax,
                "method": e.method,
                "note": e.note,
                "trace": e.trace,
            }
            for e in assessment.estimates
        ],
        "sources": [
            {"id": c.id, "label": c.label, "url": c.url} for c in details
        ],
    }
    # Deterministically attach supporting legislation for the exact citation ids
    # the engine produced — never via free-text search by the model.
    if legislation_lookup is not None:
        result["legislation"] = legislation_lookup(assessment.citations)
    return result


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
                deps.tax_bands,
            )
            result = _serialize_assessment(
                assessment, deps.citation_index, deps.legislation_lookup
            )
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


def _make_search_tool(deps: "Deps"):
    """Build the Elasticsearch knowledge-search tool + a capture of its results."""
    captured: dict[str, Any] = {"passages": [], "meta": None, "used": False}

    def search_tax_knowledge(query: str, jurisdiction: str = "") -> dict:
        if deps.knowledge_search is None:
            return {"results": [], "meta": {"mode": "unavailable"}}
        try:
            out = deps.knowledge_search(
                query, jurisdiction=(jurisdiction or None)
            )
        except Exception as exc:  # noqa: BLE001 - report back, never fabricate
            return {"error": str(exc), "results": []}
        captured["used"] = True
        captured["meta"] = out.get("meta")
        # Accumulate unique passages across multiple searches in one turn.
        seen = {p.get("citation_id") for p in captured["passages"]}
        for p in out.get("results", []):
            if p.get("citation_id") not in seen:
                captured["passages"].append(p)
                seen.add(p.get("citation_id"))
        return out

    search_tax_knowledge.__doc__ = _SEARCH_TOOL_DOC
    search_tax_knowledge.__annotations__ = {
        "query": str,
        "jurisdiction": str,
        "return": dict,
    }
    return search_tax_knowledge, captured


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
            "used_search": False,
            "assessment": None,
            "knowledge": [],
            "search_meta": None,
        }

    assess_tool, captured = _make_assess_tool(deps)
    search_tool, captured_search = _make_search_tool(deps)
    model = os.getenv("GEMINI_MODEL", _DEFAULT_MODEL)
    try:
        from google.genai import types

        resp = client.models.generate_content(
            model=model,
            contents=_to_contents(history, message),
            config=types.GenerateContentConfig(
                system_instruction=_SYSTEM_INSTRUCTION,
                tools=[assess_tool, search_tool],
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
            "used_search": False,
            "assessment": None,
            "knowledge": [],
            "search_meta": None,
        }

    return {
        "reply": reply
        or "Could you share a little more detail so I can assess your situation?",
        "available": True,
        "used_tool": "assessment" in captured,
        "used_search": captured_search["used"],
        "assessment": captured.get("assessment"),
        "knowledge": captured_search["passages"],
        "search_meta": captured_search["meta"],
    }
