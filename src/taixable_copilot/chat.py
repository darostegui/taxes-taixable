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
    "cross-border global mobility. The deterministic engine determines tax "
    "residence by day-count for ~20 countries and computes illustrative tax "
    "amounts (from published progressive bands) for the UK, Spain (ES), Germany "
    "(DE), Ireland (IE), Portugal (PT) and Andorra (AD).\n\n"
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
    "COVERAGE — FAIL CLOSED: Tax residence is determined for ~20 day-count "
    "countries; the engine reports `residency_modelled` and a confidence band. "
    "Illustrative tax AMOUNTS are computed only where bands exist (UK, ES, DE, "
    "IE, PT, AD). Cross-border treaty relief and rates are modelled only for curated "
    "treaty pairs (ES-UK, DE-UK, DE-ES); for any other pair an obligation comes "
    "back with status `not_modelled` and NO rate — relay that honestly and never "
    "fill in a rate yourself. For jurisdictions outside the day-count set you may "
    "search and surface the cited reference card, but you MUST say plainly that "
    "Taixable does not yet COMPUTE that country's tax and point to the cited "
    "source. This fail-closed honesty is a feature, not a limitation.\n\n"
    "SPECIAL REGIMES & BENEFITS (eligibility SCREENING only): search_tax_knowledge "
    "also returns curated 'regime' cards for special mobility regimes and benefits "
    "(e.g. Spain's Beckham/impatriate regime, familia numerosa deduction, regional "
    "IRPF/wealth rules, the repealed golden visa; Portugal NHR/IFICI; Italy "
    "impatriati, HNWI and 7% pensioner regimes; Greece 5A/5B/5C; France Art. 155 B; "
    "the Netherlands expat ruling; the UK non-dom abolition and 4-year FIG regime). "
    "You MAY proactively raise a relevant regime as a SCREENING suggestion — phrase "
    "it as 'this regime MAY BE RELEVANT if…' and list the cited eligibility "
    "criteria. You must NEVER say 'you qualify', 'you can apply', 'this applies to "
    "you' or assert that the person WILL pay a given amount — you are flagging a "
    "route to investigate, not making an eligibility determination. Relay rates, "
    "caps, durations and thresholds EXACTLY as the cited card states them and never "
    "invent or round them. Respect each card's status: if a regime is 'repealed', "
    "'closed_to_new_entrants' or 'replaced' (applies_to_new_applicants is false), "
    "say it is no longer open to a new mover and never recommend it for a new move "
    "(point to any named successor instead, e.g. UK non-dom → FIG, Portugal NHR → "
    "IFICI). NEVER mix figures across jurisdictions or regions (e.g. do not apply "
    "Italy's flat tax in Spain, or Madrid's wealth rebate in Cataluña) — each "
    "figure is valid only for the jurisdiction/region on its card. Always cite the "
    "card's source and add: this is informational regime evidence, not an "
    "eligibility determination — verify at source and confirm eligibility with a "
    "qualified professional.\n\n"
    "GATHERING INFORMATION: Tax residence is normally the country where the "
    "person spends the most days in the tax year — infer it from the days unless "
    "the user states otherwise. Call assess_tax_obligations as soon as you know "
    "(a) the days spent in each country, summing to 365 (or 366 in a leap year), "
    "and (b) the person's income items (pass an empty list if they have none). "
    "Computed tax amounts are available for UK, ES, DE, IE and PT; residence is "
    "determined for ~20 day-count countries; if another country is mentioned, you "
    "may still search and cite its reference card, but say clearly that Taixable "
    "does not yet compute that country's tax.\n\n"
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

# Display names for the languages the advisor can answer in. Keys are the codes
# the UI sends; the value is what we tell the model to write in.
_LANGUAGE_NAMES = {
    "en": "English",
    "es": "Spanish (Español)",
    "fr": "French (Français)",
    "de": "German (Deutsch)",
    "ru": "Russian (Русский)",
    "nl": "Dutch (Nederlands)",
    "zh": "Chinese, Simplified (简体中文)",
    "ar": "Arabic (العربية)",
}

# Localized UI fallbacks for when the model is offline/unreachable. These carry
# NO tax facts, so translating them does not touch the no-hallucination contract.
_FALLBACKS: dict[str, dict[str, str]] = {
    "offline": {
        "en": (
            "The AI advisor is currently offline. Please use the structured form "
            "to allocate days across countries and add income — it produces the "
            "same cited assessment."
        ),
        "es": (
            "El asesor con IA no está disponible en este momento. Utilice el "
            "formulario estructurado para asignar días por país y añadir ingresos: "
            "genera la misma evaluación con fuentes citadas."
        ),
        "fr": (
            "Le conseiller IA est actuellement hors ligne. Veuillez utiliser le "
            "formulaire structuré pour répartir les jours par pays et ajouter les "
            "revenus : il produit la même évaluation sourcée."
        ),
        "de": (
            "Der KI-Berater ist derzeit offline. Bitte nutzen Sie das strukturierte "
            "Formular, um Tage auf Länder zu verteilen und Einkünfte hinzuzufügen – "
            "es liefert dieselbe belegte Einschätzung."
        ),
        "ru": (
            "ИИ-консультант сейчас недоступен. Воспользуйтесь структурированной "
            "формой, чтобы распределить дни по странам и добавить доходы — она даёт "
            "ту же оценку со ссылками на источники."
        ),
        "nl": (
            "De AI-adviseur is momenteel offline. Gebruik het gestructureerde "
            "formulier om dagen over landen te verdelen en inkomsten toe te voegen — "
            "het levert dezelfde onderbouwde beoordeling."
        ),
        "zh": (
            "AI 顾问当前不可用。请使用结构化表单按国家分配天数并添加收入——"
            "它会生成同样带来源引用的评估。"
        ),
        "ar": (
            "مستشار الذكاء الاصطناعي غير متاح حاليًا. يُرجى استخدام النموذج المنظَّم "
            "لتوزيع الأيام على البلدان وإضافة الدخل، فهو ينتج التقييم نفسه مع ذكر "
            "المصادر."
        ),
    },
    "error": {
        "en": (
            "Sorry — I couldn't reach the AI advisor just now. Please try again, or "
            "use the structured form for an immediate cited assessment."
        ),
        "es": (
            "Lo sentimos: no se ha podido contactar con el asesor con IA en este "
            "momento. Inténtelo de nuevo o utilice el formulario estructurado para "
            "obtener una evaluación citada al instante."
        ),
        "fr": (
            "Désolé — impossible de joindre le conseiller IA pour le moment. "
            "Réessayez ou utilisez le formulaire structuré pour une évaluation "
            "sourcée immédiate."
        ),
        "de": (
            "Entschuldigung – der KI-Berater ist gerade nicht erreichbar. Bitte "
            "versuchen Sie es erneut oder nutzen Sie das strukturierte Formular für "
            "eine sofortige belegte Einschätzung."
        ),
        "ru": (
            "Извините — не удалось связаться с ИИ-консультантом. Попробуйте ещё раз "
            "или воспользуйтесь структурированной формой для мгновенной оценки со "
            "ссылками."
        ),
        "nl": (
            "Sorry — de AI-adviseur is nu niet bereikbaar. Probeer het opnieuw of "
            "gebruik het gestructureerde formulier voor een directe onderbouwde "
            "beoordeling."
        ),
        "zh": (
            "抱歉，暂时无法连接 AI 顾问。请重试，或使用结构化表单立即获取"
            "带来源的评估。"
        ),
        "ar": (
            "عذرًا — تعذّر الوصول إلى مستشار الذكاء الاصطناعي الآن. حاول مرة أخرى أو "
            "استخدم النموذج المنظَّم للحصول على تقييم موثَّق فوري."
        ),
    },
    "more_detail": {
        "en": "Could you share a little more detail so I can assess your situation?",
        "es": "¿Podría darme algún detalle más para poder evaluar su situación?",
        "fr": (
            "Pourriez-vous me donner un peu plus de détails afin que je puisse "
            "évaluer votre situation ?"
        ),
        "de": (
            "Könnten Sie mir noch ein paar Details nennen, damit ich Ihre Situation "
            "einschätzen kann?"
        ),
        "ru": (
            "Не могли бы вы добавить немного деталей, чтобы я мог оценить вашу "
            "ситуацию?"
        ),
        "nl": "Kunt u iets meer details geven zodat ik uw situatie kan beoordelen?",
        "zh": "您能否再提供一些细节，以便我评估您的情况？",
        "ar": "هل يمكنك تقديم مزيد من التفاصيل حتى أتمكّن من تقييم وضعك؟",
    },
}


def _norm_lang(language: str) -> str:
    code = (language or "en").lower()
    return code if code in _LANGUAGE_NAMES else "en"


def _fallback(key: str, language: str) -> str:
    table = _FALLBACKS[key]
    return table.get(_norm_lang(language), table["en"])


def _language_directive(language: str) -> str:
    code = _norm_lang(language)
    if code == "en":
        return ""
    name = _LANGUAGE_NAMES[code]
    return (
        "\n\nLANGUAGE: Write your ENTIRE reply to the user in " + name + ". "
        "Translate all explanatory prose, headings and labels into that language. "
        "Keep the following UNCHANGED and do NOT translate them: citation "
        "identifiers (e.g. ES#residency-183, ES-UK#art14), statute, treaty and "
        "regime names together with their article numbers, official source URLs, "
        "all numeric figures, percentages, dates and ISO currency codes. Use that "
        "language's number and date formatting conventions. Every no-hallucination "
        "rule above still applies — translating a cited fact is allowed, inventing "
        "one is not."
    )

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
        "residency_modelled": assessment.residency_modelled,
        "tax_base_scope": assessment.tax_base_scope,
        "scope_note": assessment.scope_note,
        "other_tests_exist": assessment.other_tests_exist,
        "obligations": [
            {
                "income_type": str(o.income_type),
                "source_country": str(o.source_country),
                "treaty_article": o.treaty_article,
                "rate": o.rate,
                "relief": o.relief,
                "status": o.status,
                "reason": o.reason,
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
                deps.known_citation_ids,
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
            return {
                "error": str(exc),
                "computable_amount_countries": ["UK", "ES", "DE", "IE", "PT", "AD"],
                "note": (
                    "Residence is determined for ~20 day-count countries; tax "
                    "amounts are computed only for the listed countries."
                ),
            }
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
    language: str = "en",
) -> dict[str, Any]:
    """Run one conversational turn. Returns reply text, tool-use flag, assessment.

    Never raises: on any SDK/credential/model failure it returns a graceful,
    professional message and ``available=False``/``error`` so the UI can fall
    back to the structured form.
    """
    client = _make_client()
    if client is None:
        return {
            "reply": _fallback("offline", language),
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
                system_instruction=_SYSTEM_INSTRUCTION + _language_directive(language),
                tools=[assess_tool, search_tool],
                temperature=0.2,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        )
        reply = (resp.text or "").strip()
    except Exception:  # noqa: BLE001 - network/model/quota error → graceful message
        return {
            "reply": _fallback("error", language),
            "available": False,
            "used_tool": False,
            "used_search": False,
            "assessment": None,
            "knowledge": [],
            "search_meta": None,
        }

    return {
        "reply": reply or _fallback("more_detail", language),
        "available": True,
        "used_tool": "assessment" in captured,
        "used_search": captured_search["used"],
        "assessment": captured.get("assessment"),
        "knowledge": captured_search["passages"],
        "search_meta": captured_search["meta"],
    }
