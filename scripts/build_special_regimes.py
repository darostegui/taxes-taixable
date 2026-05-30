#!/usr/bin/env python3
"""Idempotent generator for the special mobility-regimes corpus.

This emits ``content_type="curated_regime"`` entries into ``legislation.json``.
Unlike the broad ``curated_reference`` tier (which deliberately asserts no legal
rule), regime cards DO carry concrete figures (flat rates, income caps, durations,
investment thresholds). The no-hallucination contract is preserved differently
here: every figure is HAND-VERIFIED against an official/primary or PwC Worldwide
Tax Summaries source, stamped with ``source_url`` + ``effective_date`` +
``status`` + provenance, and the LLM may only relay the cited passage for
*eligibility SCREENING* ("may be relevant if…") — never as an eligibility
determination ("you qualify") and never by mixing figures across jurisdictions.

Many flagship regimes changed in 2024–2025, so each entry carries a granular
``status`` (active | repealed | closed_to_new_entrants | replaced),
``status_effective_date`` and ``applies_to_new_applicants`` so the advisor never
recommends a route that is no longer open to a new mover.

Run: ``.venv/bin/python scripts/build_special_regimes.py``. Re-running is safe:
existing citation ids are never clobbered, only missing ones are appended.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import sys
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "src" / "taixable_copilot" / "data" / "legislation.json"
GENERATOR_VERSION = "special-regimes/1.0"
PACKAGE_VERSION = "2025.1"

# Each regime is verified data. ``summary`` MUST contain every figure/status in
# prose (knowledge.py indexes/highlights ``f"{title}. {summary}"``), and every
# numeric figure must also appear in the structured ``figures`` list.
REGIMES: list[dict] = [
    # ---------------------------------------------------------------- Spain
    {
        "citation_id": "ES#beckham-regime",
        "jurisdiction": "ES",
        "regime_name": "Special regime for inbound workers (Beckham regime)",
        "title": "Spain — Beckham / impatriate regime (Art. 93 LIRPF, as amended by the Startups Law)",
        "article": "Art. 93 LIRPF",
        "status": "active",
        "status_effective_date": "2023-01-01",
        "applies_to_new_applicants": True,
        "effective_date": "2023-01-01",
        "source_url": "https://www.boe.es/buscar/act.php?id=BOE-A-2006-20764",
        "summary": (
            "Spain's special regime for inbound workers (the 'Beckham regime', Art. 93 LIRPF), "
            "as amended by the Startups Law (Ley 28/2022, in force 2023). It MAY BE RELEVANT to a "
            "person newly moving their tax residence to Spain who was not Spanish tax resident in "
            "the previous 5 tax years. Where it applies and is elected, the taxpayer is taxed at a "
            "flat 24% on employment income up to EUR 600,000 (47% on the excess) for the arrival "
            "year plus the following 5 tax years, and broadly on Spanish-source rather than "
            "worldwide income. The Startups Law widened access to qualifying remote workers "
            "('digital nomads'), entrepreneurs and certain highly-qualified professionals. "
            "Informational regime evidence — not an eligibility determination or a tax computation; "
            "confirm eligibility and figures at the cited source and with a qualified professional."
        ),
        "figures": [
            {"label": "flat rate on employment income up to cap", "value": "24%", "scope": "ES"},
            {"label": "income cap for the flat rate", "value": "EUR 600,000", "scope": "ES"},
            {"label": "rate on the excess above the cap", "value": "47%", "scope": "ES"},
            {"label": "duration", "value": "arrival year + 5 tax years", "scope": "ES"},
            {"label": "prior non-residence required", "value": "5 tax years", "scope": "ES"},
        ],
        "eligibility_criteria": [
            "Becomes Spanish tax resident as a result of the move",
            "Was not Spanish tax resident in the previous 5 tax years",
            "Move linked to a qualifying employment, board/director role, entrepreneurial activity or qualifying remote work (digital nomad)",
        ],
        "exclusions": [
            "Professional sportspeople covered by their own special rules",
            "Individuals who do not formally elect the regime within the statutory window",
        ],
    },
    {
        "citation_id": "ES#startups-law",
        "jurisdiction": "ES",
        "regime_name": "Startups Law — entrepreneur and digital-nomad routes",
        "title": "Spain — Startups Law (Ley 28/2022) entrepreneur / digital-nomad framework",
        "article": "Ley 28/2022",
        "status": "active",
        "status_effective_date": "2023-01-01",
        "applies_to_new_applicants": True,
        "effective_date": "2023-01-01",
        "source_url": "https://www.boe.es/eli/es/l/2022/12/21/28/con",
        "summary": (
            "Spain's Startups Law (Ley 28/2022) promotes the emerging-companies ecosystem and "
            "created a dedicated international-teleworking ('digital nomad') visa and broadened the "
            "Beckham impatriate regime. It MAY BE RELEVANT to entrepreneurs, startup founders and "
            "qualifying remote workers relocating to Spain. Among other measures it reduced the "
            "prior-non-residence condition for the impatriate regime to 5 tax years and extended "
            "access to entrepreneurs and remote workers. Informational regime evidence — not an "
            "eligibility determination; confirm at the cited source and with a professional."
        ),
        "figures": [
            {"label": "prior non-residence condition for the impatriate regime", "value": "5 tax years", "scope": "ES"},
        ],
        "eligibility_criteria": [
            "Entrepreneur, startup founder or qualifying remote worker relocating to Spain",
            "Activity meets the innovative / international-teleworking conditions in the law",
        ],
        "exclusions": [],
    },
    {
        "citation_id": "ES#familia-numerosa",
        "jurisdiction": "ES",
        "regime_name": "Large-family (familia numerosa) IRPF deduction",
        "title": "Spain — Large-family deduction (Ley 40/2003; IRPF deducción por familia numerosa)",
        "article": "Ley 40/2003",
        "status": "active",
        "status_effective_date": "2015-01-01",
        "applies_to_new_applicants": True,
        "effective_date": "2015-01-01",
        "source_url": "https://sede.agenciatributaria.gob.es/Sede/ciudadanos-familias-personas-discapacidad/deducciones-relacionadas-hijos-descendientes/deduccion-familia-numerosa.html",
        "summary": (
            "Spain's large-family ('familia numerosa', Ley 40/2003) IRPF deduction MAY BE RELEVANT "
            "to a family that holds a valid official large-family title and carries on an economic "
            "activity or receives a contributory/assistance benefit. The deduction is up to EUR "
            "1,200 per year for a general-category large family and up to EUR 2,400 per year for the "
            "special category, increased by up to EUR 600 per year for each child beyond the "
            "category minimum; it can be drawn in advance (Modelo 143). Informational regime "
            "evidence — not an eligibility determination; confirm at the cited source and with a "
            "professional."
        ),
        "figures": [
            {"label": "general-category annual deduction", "value": "up to EUR 1,200", "scope": "ES"},
            {"label": "special-category annual deduction", "value": "up to EUR 2,400", "scope": "ES"},
            {"label": "increase per additional child", "value": "up to EUR 600 per year", "scope": "ES"},
        ],
        "eligibility_criteria": [
            "Holds a valid official large-family (familia numerosa) title",
            "Carries on an economic activity or receives a qualifying contributory/assistance benefit",
        ],
        "exclusions": [],
    },
    {
        "citation_id": "ES#golden-visa-repeal",
        "jurisdiction": "ES",
        "regime_name": "Residency-by-investment (golden visa) — real-estate route",
        "title": "Spain — Golden visa real-estate investment route (REPEALED)",
        "article": "Ley 14/2013 arts. 63–67 (repealed)",
        "status": "repealed",
        "status_effective_date": "2025-04-03",
        "applies_to_new_applicants": False,
        "grandfathering": "Permits granted before 3 April 2025 remain valid and may be renewed under the prior rules.",
        "effective_date": "2025-04-03",
        "source_url": "https://www.boe.es/diario_boe/txt.php?id=BOE-A-2025-76",
        "summary": (
            "Spain's residency-by-investment 'golden visa' real-estate route (EUR 500,000 property "
            "investment, formerly Ley 14/2013) was REPEALED with effect from 3 April 2025 by Ley "
            "Orgánica 1/2025. New applicants can no longer obtain Spanish residency through that "
            "EUR 500,000 property route; permits granted before 3 April 2025 remain valid and "
            "renewable. This is a closed route — do NOT recommend it for a new move. Informational "
            "regime evidence — confirm status at the cited source and with a professional."
        ),
        "figures": [
            {"label": "former real-estate investment threshold (now closed)", "value": "EUR 500,000", "scope": "ES"},
        ],
        "eligibility_criteria": [],
        "exclusions": ["Closed to new applicants from 3 April 2025"],
    },
    {
        "citation_id": "ES#solidarity-tax-itsgf",
        "jurisdiction": "ES",
        "regime_name": "Temporary Solidarity Tax on Large Fortunes (ITSGF)",
        "title": "Spain — Solidarity Tax on Large Fortunes (Impuesto de Solidaridad, ITSGF)",
        "article": "Ley 38/2022",
        "status": "active",
        "status_effective_date": "2022-12-29",
        "applies_to_new_applicants": True,
        "effective_date": "2022-12-29",
        "source_url": "https://taxsummaries.pwc.com/spain/individual/other-taxes",
        "summary": (
            "Spain's national Solidarity Tax on Large Fortunes (ITSGF) MAY BE RELEVANT to high-net-"
            "worth residents: it applies to individual net wealth above EUR 3,000,000 and operates "
            "alongside the regional Wealth Tax, with the regional Wealth Tax paid credited against "
            "it. Because it is a national tax, it can effectively override regional Wealth-Tax "
            "rebates (such as Madrid's or Andalucía's) for net wealth above the threshold. "
            "Informational regime evidence — not an eligibility determination; confirm at the cited "
            "source and with a professional."
        ),
        "figures": [
            {"label": "net-wealth threshold", "value": "EUR 3,000,000", "scope": "ES"},
        ],
        "eligibility_criteria": ["Individual net wealth above EUR 3,000,000"],
        "exclusions": [],
    },
    {
        "citation_id": "ES-MD#wealth-bonificacion",
        "jurisdiction": "ES",
        "region": "Madrid",
        "regime_name": "Madrid regional Wealth-Tax rebate",
        "title": "Spain (Madrid) — 100% regional Wealth-Tax rebate (bonificación)",
        "article": "Comunidad de Madrid",
        "status": "active",
        "status_effective_date": "2023-01-01",
        "applies_to_new_applicants": True,
        "effective_date": "2023-01-01",
        "source_url": "https://taxsummaries.pwc.com/spain/individual/other-taxes",
        "summary": (
            "The Comunidad de Madrid applies a 100% rebate (bonificación) on the regional Wealth "
            "Tax, so Madrid-resident individuals broadly pay no regional Wealth Tax. This MAY BE "
            "RELEVANT to a high-net-worth person considering residence in Madrid, but note the "
            "national Solidarity Tax on Large Fortunes (ITSGF) can still apply to net wealth above "
            "EUR 3,000,000. Regional rule — applies only to Madrid; do not apply it to other "
            "Spanish regions. Informational regime evidence — confirm at the cited source and with "
            "a professional."
        ),
        "figures": [
            {"label": "regional Wealth-Tax rebate", "value": "100%", "scope": "ES-Madrid"},
        ],
        "eligibility_criteria": ["Tax resident in the Comunidad de Madrid"],
        "exclusions": ["Does not remove the national Solidarity Tax (ITSGF) above EUR 3,000,000"],
    },
    {
        "citation_id": "ES-AN#wealth-bonificacion",
        "jurisdiction": "ES",
        "region": "Andalucía",
        "regime_name": "Andalucía regional Wealth-Tax rebate",
        "title": "Spain (Andalucía) — 100% regional Wealth-Tax rebate (bonificación)",
        "article": "Junta de Andalucía",
        "status": "active",
        "status_effective_date": "2022-09-21",
        "applies_to_new_applicants": True,
        "effective_date": "2022-09-21",
        "source_url": "https://taxsummaries.pwc.com/spain/individual/other-taxes",
        "summary": (
            "Andalucía applies a 100% rebate (bonificación) on the regional Wealth Tax, so "
            "Andalucía-resident individuals broadly pay no regional Wealth Tax. This MAY BE "
            "RELEVANT to a high-net-worth person considering residence in Andalucía, but the "
            "national Solidarity Tax on Large Fortunes (ITSGF) can still apply to net wealth above "
            "EUR 3,000,000. Regional rule — applies only to Andalucía. Informational regime "
            "evidence — confirm at the cited source and with a professional."
        ),
        "figures": [
            {"label": "regional Wealth-Tax rebate", "value": "100%", "scope": "ES-Andalucia"},
        ],
        "eligibility_criteria": ["Tax resident in Andalucía"],
        "exclusions": ["Does not remove the national Solidarity Tax (ITSGF) above EUR 3,000,000"],
    },
    {
        "citation_id": "ES-CT#regional-irpf",
        "jurisdiction": "ES",
        "region": "Cataluña",
        "regime_name": "Catalonia regional IRPF and Wealth Tax",
        "title": "Spain (Cataluña) — regional IRPF scale and Wealth Tax",
        "article": "Generalitat de Catalunya",
        "status": "active",
        "status_effective_date": "2024-01-01",
        "applies_to_new_applicants": True,
        "effective_date": "2024-01-01",
        "source_url": "https://taxsummaries.pwc.com/spain/individual/taxes-on-personal-income",
        "summary": (
            "Spanish personal income tax (IRPF) is split into a state portion and a regional "
            "portion, so the total rate depends on the autonomous community of residence. Cataluña "
            "applies one of the higher combined top marginal IRPF rates (around 50% on the top "
            "band, broadly above EUR 300,000) and levies its regional Wealth Tax (top marginal "
            "rate around 3.75%). This MAY BE RELEVANT to a person moving to Barcelona/Cataluña, "
            "whose regional rates differ from, e.g., Madrid. Regional rule — applies only to "
            "Cataluña. Informational regime evidence — confirm at the cited source and with a "
            "professional."
        ),
        "figures": [
            {"label": "approximate combined top marginal IRPF rate", "value": "around 50%", "scope": "ES-Cataluna"},
            {"label": "approximate top marginal Wealth-Tax rate", "value": "around 3.75%", "scope": "ES-Cataluna"},
        ],
        "eligibility_criteria": ["Tax resident in Cataluña"],
        "exclusions": [],
    },
    {
        "citation_id": "ES-PV#foral-regime",
        "jurisdiction": "ES",
        "region": "País Vasco",
        "regime_name": "Basque Country foral tax system",
        "title": "Spain (País Vasco) — foral (provincial) tax system",
        "article": "Concierto Económico",
        "status": "active",
        "status_effective_date": "2024-01-01",
        "applies_to_new_applicants": True,
        "effective_date": "2024-01-01",
        "source_url": "https://taxsummaries.pwc.com/spain/individual/taxes-on-personal-income",
        "summary": (
            "The Basque Country (País Vasco) operates a 'foral' tax system under the Economic "
            "Agreement (Concierto Económico): each of its provinces sets its own personal income "
            "tax and wealth-tax rules, distinct from the common Spanish (territorio común) regime. "
            "This MAY BE RELEVANT to a person moving to the Basque Country, whose income and wealth "
            "tax can differ materially from common-territory Spain. Regional/foral rule — applies "
            "only to the Basque provinces. Informational regime evidence — confirm at the cited "
            "source and with a professional."
        ),
        "figures": [],
        "eligibility_criteria": ["Tax resident in a Basque (foral) province"],
        "exclusions": [],
    },
    {
        "citation_id": "ES-NC#foral-regime",
        "jurisdiction": "ES",
        "region": "Navarra",
        "regime_name": "Navarra foral tax system",
        "title": "Spain (Navarra) — foral tax system",
        "article": "Convenio Económico",
        "status": "active",
        "status_effective_date": "2024-01-01",
        "applies_to_new_applicants": True,
        "effective_date": "2024-01-01",
        "source_url": "https://taxsummaries.pwc.com/spain/individual/taxes-on-personal-income",
        "summary": (
            "Navarra operates its own 'foral' tax system under the Economic Convention (Convenio "
            "Económico), setting personal income tax and wealth-tax rules distinct from the common "
            "Spanish regime. This MAY BE RELEVANT to a person moving to Navarra, whose income and "
            "wealth tax can differ from common-territory Spain. Regional/foral rule — applies only "
            "to Navarra. Informational regime evidence — confirm at the cited source and with a "
            "professional."
        ),
        "figures": [],
        "eligibility_criteria": ["Tax resident in Navarra"],
        "exclusions": [],
    },
    # ------------------------------------------------------------- Portugal
    {
        "citation_id": "PT#nhr-closed",
        "jurisdiction": "PT",
        "regime_name": "Non-Habitual Resident (NHR) regime",
        "title": "Portugal — Non-Habitual Resident (NHR) regime (CLOSED to new entrants)",
        "article": "NHR",
        "status": "closed_to_new_entrants",
        "status_effective_date": "2024-01-01",
        "applies_to_new_applicants": False,
        "grandfathering": "Individuals already registered as NHR keep the benefit for the remainder of their 10-year period; limited transitional access applied for some who relocated by 2024.",
        "effective_date": "2024-01-01",
        "source_url": "https://taxsummaries.pwc.com/portugal/individual/other-tax-credits-and-incentives",
        "summary": (
            "Portugal's Non-Habitual Resident (NHR) regime CLOSED to new entrants from 2024. "
            "Existing NHR holders keep the benefit for the remainder of their 10-year period, but "
            "new movers generally cannot register for the original NHR; the successor route is the "
            "tax incentive for scientific research and innovation (IFICI / 'NHR 2.0'). Do NOT "
            "recommend the original NHR for a new move. Informational regime evidence — confirm "
            "status at the cited source and with a professional."
        ),
        "figures": [
            {"label": "benefit period for existing holders", "value": "10 years", "scope": "PT"},
        ],
        "eligibility_criteria": [],
        "exclusions": ["Closed to new entrants from 2024 (see IFICI for the successor regime)"],
    },
    {
        "citation_id": "PT#ifici",
        "jurisdiction": "PT",
        "regime_name": "Tax incentive for scientific research and innovation (IFICI / NHR 2.0)",
        "title": "Portugal — IFICI tax incentive for scientific research and innovation ('NHR 2.0')",
        "article": "IFICI",
        "status": "active",
        "status_effective_date": "2024-01-01",
        "applies_to_new_applicants": True,
        "effective_date": "2024-01-01",
        "source_url": "https://taxsummaries.pwc.com/portugal/individual/other-tax-credits-and-incentives",
        "summary": (
            "Portugal's tax incentive for scientific research and innovation (IFICI, the 'NHR 2.0' "
            "successor to the closed NHR) MAY BE RELEVANT to qualifying new residents in eligible "
            "scientific research, innovation, higher-education or qualifying high-value roles. "
            "Where it applies it provides a flat 20% rate on qualifying Portuguese employment and "
            "self-employment income and exemptions on certain foreign-source income, for up to 10 "
            "years. Note that, unlike the old NHR, foreign PENSIONS are generally taxed at the "
            "normal progressive rates under IFICI. Informational regime evidence — not an "
            "eligibility determination; confirm at the cited source and with a professional."
        ),
        "figures": [
            {"label": "flat rate on qualifying PT employment/self-employment income", "value": "20%", "scope": "PT"},
            {"label": "maximum duration", "value": "10 years", "scope": "PT"},
        ],
        "eligibility_criteria": [
            "Becomes Portuguese tax resident and was not resident in the prior years required by the rules",
            "Works in a qualifying scientific research, innovation, higher-education or eligible high-value role",
        ],
        "exclusions": ["Foreign pensions are taxed at normal progressive rates (no pension exemption)"],
    },
    # ---------------------------------------------------------------- Italy
    {
        "citation_id": "IT#impatriati",
        "jurisdiction": "IT",
        "regime_name": "Impatriate workers regime (lavoratori impatriati)",
        "title": "Italy — Impatriate workers regime (2024 reform)",
        "article": "Impatriati",
        "status": "active",
        "status_effective_date": "2024-01-01",
        "applies_to_new_applicants": True,
        "effective_date": "2024-01-01",
        "source_url": "https://taxsummaries.pwc.com/italy/individual/other-tax-credits-and-incentives",
        "summary": (
            "Italy's impatriate-workers regime (lavoratori impatriati), as reformed for arrivals "
            "from 2024, MAY BE RELEVANT to a qualifying worker moving their tax residence to Italy "
            "after a required period of non-residence. Where it applies, 50% of qualifying "
            "employment/self-employment income produced in Italy is exempt (so half is taxed), on "
            "income up to EUR 600,000 per year, for 5 years (with possible extension). The 2024 "
            "reform reduced the exemption from the previous 70%/90% levels and added the EUR "
            "600,000 cap. Informational regime evidence — not an eligibility determination; confirm "
            "at the cited source and with a professional."
        ),
        "figures": [
            {"label": "income exemption", "value": "50%", "scope": "IT"},
            {"label": "annual income cap", "value": "EUR 600,000", "scope": "IT"},
            {"label": "duration", "value": "5 years (extension possible)", "scope": "IT"},
        ],
        "eligibility_criteria": [
            "Becomes Italian tax resident after the required period of prior non-residence",
            "Performs qualifying employment or self-employment work mainly in Italy",
        ],
        "exclusions": [],
    },
    {
        "citation_id": "IT#hnwi-flat",
        "jurisdiction": "IT",
        "regime_name": "Flat tax for new resident high-net-worth individuals",
        "title": "Italy — HNWI flat tax on foreign income (neo-domiciled regime)",
        "article": "HNWI flat tax",
        "status": "active",
        "status_effective_date": "2024-08-10",
        "applies_to_new_applicants": True,
        "effective_date": "2024-08-10",
        "source_url": "https://taxsummaries.pwc.com/italy/individual/other-tax-credits-and-incentives",
        "summary": (
            "Italy's flat-tax regime for new-resident high-net-worth individuals MAY BE RELEVANT to "
            "a wealthy person moving their tax residence to Italy after a required period of non-"
            "residence. It substitutes a fixed annual amount for tax on FOREIGN-source income: EUR "
            "200,000 per year for new electors who became resident after 10 August 2024 (EUR "
            "100,000 for those who elected earlier), plus EUR 25,000 per year for each included "
            "family member, for up to 15 years. Informational regime evidence — not an eligibility "
            "determination; confirm at the cited source and with a professional."
        ),
        "figures": [
            {"label": "annual flat tax on foreign income (new electors from 10 Aug 2024)", "value": "EUR 200,000", "scope": "IT"},
            {"label": "annual flat tax for earlier electors", "value": "EUR 100,000", "scope": "IT"},
            {"label": "additional annual amount per family member", "value": "EUR 25,000", "scope": "IT"},
            {"label": "maximum duration", "value": "15 years", "scope": "IT"},
        ],
        "eligibility_criteria": [
            "Moves tax residence to Italy after the required period of prior non-residence",
            "Formally elects the substitute flat tax on foreign-source income",
        ],
        "exclusions": [],
    },
    {
        "citation_id": "IT#pensioner-7pct",
        "jurisdiction": "IT",
        "regime_name": "7% flat tax for foreign pensioners in southern Italy",
        "title": "Italy — 7% flat tax for foreign-pension holders relocating to southern Italy",
        "article": "Pensioners 7%",
        "status": "active",
        "status_effective_date": "2019-01-01",
        "applies_to_new_applicants": True,
        "effective_date": "2019-01-01",
        "source_url": "https://taxsummaries.pwc.com/italy/individual/other-tax-credits-and-incentives",
        "summary": (
            "Italy offers a 7% flat tax on all foreign-source income to individuals who hold a "
            "foreign pension and move their tax residence to a small town (generally under 20,000 "
            "inhabitants) in southern Italy, for up to 10 years. This MAY BE RELEVANT to a retiree "
            "with foreign pension income relocating to qualifying municipalities. Informational "
            "regime evidence — not an eligibility determination; confirm at the cited source and "
            "with a professional."
        ),
        "figures": [
            {"label": "flat rate on foreign-source income", "value": "7%", "scope": "IT"},
            {"label": "town size condition", "value": "generally under 20,000 inhabitants", "scope": "IT"},
            {"label": "maximum duration", "value": "10 years", "scope": "IT"},
        ],
        "eligibility_criteria": [
            "Receives a foreign-source pension",
            "Moves tax residence to a qualifying small town in southern Italy",
            "Was not Italian tax resident in the prior period required by the rules",
        ],
        "exclusions": [],
    },
    # --------------------------------------------------------------- Greece
    {
        "citation_id": "GR#pensioner-7pct",
        "jurisdiction": "GR",
        "regime_name": "7% flat tax for foreign pensioners (Art. 5B)",
        "title": "Greece — 7% flat tax for foreign-pension holders (Art. 5B ITC)",
        "article": "Art. 5B",
        "status": "active",
        "status_effective_date": "2020-01-01",
        "applies_to_new_applicants": True,
        "effective_date": "2020-01-01",
        "source_url": "https://taxsummaries.pwc.com/greece/individual/other-tax-credits-and-incentives",
        "summary": (
            "Greece's regime for foreign pensioners (Art. 5B of the Income Tax Code) MAY BE "
            "RELEVANT to a retiree with foreign-source pension income who transfers their tax "
            "residence to Greece after a required period of non-residence. Where it applies, all "
            "foreign-source income is taxed at a flat 7%, for up to 15 years. Informational regime "
            "evidence — not an eligibility determination; confirm at the cited source and with a "
            "professional."
        ),
        "figures": [
            {"label": "flat rate on foreign-source income", "value": "7%", "scope": "GR"},
            {"label": "maximum duration", "value": "15 years", "scope": "GR"},
        ],
        "eligibility_criteria": [
            "Receives foreign-source pension income",
            "Transfers tax residence to Greece after the required prior non-residence",
            "Moves from a country with an administrative-cooperation agreement with Greece",
        ],
        "exclusions": ["Cannot be combined with the Art. 5A non-dom or Art. 5C impatriate regimes"],
    },
    {
        "citation_id": "GR#impatriate-5c",
        "jurisdiction": "GR",
        "regime_name": "50% impatriate exemption (Art. 5C)",
        "title": "Greece — 50% exemption for inbound employees/self-employed (Art. 5C ITC)",
        "article": "Art. 5C",
        "status": "active",
        "status_effective_date": "2021-01-01",
        "applies_to_new_applicants": True,
        "effective_date": "2021-01-01",
        "source_url": "https://taxsummaries.pwc.com/greece/individual/other-tax-credits-and-incentives",
        "summary": (
            "Greece's impatriate regime (Art. 5C of the Income Tax Code) MAY BE RELEVANT to a "
            "person who transfers their tax residence to Greece to take up new employment or "
            "self-employment there. Where it applies, 50% of Greek employment or business income "
            "is exempt from income tax (and from the special solidarity contribution) for 7 years. "
            "Informational regime evidence — not an eligibility determination; confirm at the cited "
            "source and with a professional."
        ),
        "figures": [
            {"label": "exemption on Greek employment/business income", "value": "50%", "scope": "GR"},
            {"label": "duration", "value": "7 years", "scope": "GR"},
        ],
        "eligibility_criteria": [
            "Transfers tax residence to Greece after the required prior non-residence",
            "Takes up new employment or self-employment in Greece",
            "Commits to remain a Greek tax resident for the minimum required period",
        ],
        "exclusions": ["Cannot be combined with the Art. 5A non-dom or Art. 5B pensioner regimes"],
    },
    {
        "citation_id": "GR#non-dom-5a",
        "jurisdiction": "GR",
        "regime_name": "Non-dom lump-sum regime (Art. 5A)",
        "title": "Greece — Non-dom EUR 100,000 lump-sum regime (Art. 5A ITC)",
        "article": "Art. 5A",
        "status": "active",
        "status_effective_date": "2020-01-01",
        "applies_to_new_applicants": True,
        "effective_date": "2020-01-01",
        "source_url": "https://taxsummaries.pwc.com/greece/individual/other-tax-credits-and-incentives",
        "summary": (
            "Greece's non-dom regime (Art. 5A of the Income Tax Code) MAY BE RELEVANT to a high-"
            "net-worth individual who transfers their tax residence to Greece and makes a "
            "qualifying investment of at least EUR 500,000. Where it applies, foreign-source income "
            "is covered by a fixed annual lump-sum tax of EUR 100,000 (plus EUR 20,000 per included "
            "family member), for up to 15 years. Informational regime evidence — not an eligibility "
            "determination; confirm at the cited source and with a professional."
        ),
        "figures": [
            {"label": "annual lump-sum tax on foreign income", "value": "EUR 100,000", "scope": "GR"},
            {"label": "additional annual amount per family member", "value": "EUR 20,000", "scope": "GR"},
            {"label": "minimum qualifying investment", "value": "EUR 500,000", "scope": "GR"},
            {"label": "maximum duration", "value": "15 years", "scope": "GR"},
        ],
        "eligibility_criteria": [
            "Transfers tax residence to Greece after the required prior non-residence",
            "Makes a qualifying investment of at least EUR 500,000",
        ],
        "exclusions": ["Cannot be combined with the Art. 5B pensioner or Art. 5C impatriate regimes"],
    },
    # --------------------------------------------------------------- France
    {
        "citation_id": "FR#impatriate-155b",
        "jurisdiction": "FR",
        "regime_name": "Impatriate regime (régime des impatriés, Art. 155 B CGI)",
        "title": "France — Impatriate regime (Art. 155 B CGI)",
        "article": "Art. 155 B CGI",
        "status": "active",
        "status_effective_date": "2023-01-01",
        "applies_to_new_applicants": True,
        "effective_date": "2023-01-01",
        "source_url": "https://taxsummaries.pwc.com/france/individual/other-tax-credits-and-incentives",
        "summary": (
            "France's impatriate regime (régime des impatriés, Art. 155 B CGI) MAY BE RELEVANT to "
            "an employee or manager recruited from abroad who becomes French tax resident and was "
            "not French resident in the previous 5 calendar years. Where it applies, the "
            "impatriation bonus is exempt and a 50% exemption can apply to certain foreign-source "
            "passive income (dividends, interest, royalties and gains), for up to 8 years. "
            "Informational regime evidence — not an eligibility determination; confirm at the cited "
            "source and with a professional."
        ),
        "figures": [
            {"label": "exemption on qualifying foreign passive income", "value": "50%", "scope": "FR"},
            {"label": "maximum duration", "value": "8 years", "scope": "FR"},
            {"label": "prior non-residence required", "value": "5 calendar years", "scope": "FR"},
        ],
        "eligibility_criteria": [
            "Recruited from abroad to take up employment or a management role in France",
            "Becomes French tax resident and was not French resident in the previous 5 calendar years",
        ],
        "exclusions": ["Individuals who moved to France on their own initiative outside a qualifying assignment"],
    },
    # ----------------------------------------------------------- Netherlands
    {
        "citation_id": "NL#expat-ruling",
        "jurisdiction": "NL",
        "regime_name": "Expat ruling (formerly the 30% ruling)",
        "title": "Netherlands — Expat ruling (30% ruling, moving to a flat 27% from 2027)",
        "article": "30%/27% ruling",
        "status": "active",
        "status_effective_date": "2025-01-01",
        "applies_to_new_applicants": True,
        "effective_date": "2025-01-01",
        "source_url": "https://www.pwc.nl/en/insights-and-publications/tax-news/pwc-special-budget-day/expat-ruling.html",
        "summary": (
            "The Netherlands' expat ruling (the former '30% ruling') MAY BE RELEVANT to a "
            "qualifying employee recruited from abroad with scarce specific expertise. It allows a "
            "tax-free reimbursement of a percentage of salary: 30% for 2025 and 2026, then a flat "
            "27% from 1 January 2027 for new users (the earlier 30/20/10 step-down was cancelled). "
            "It is capped at the public-sector ('WNT') salary norm and requires a minimum salary "
            "level; pre-2024 users keep their prior terms transitionally. Informational regime "
            "evidence — not an eligibility determination; confirm at the cited source and with a "
            "professional."
        ),
        "figures": [
            {"label": "tax-free percentage for 2025 and 2026", "value": "30%", "scope": "NL"},
            {"label": "flat tax-free percentage from 2027 (new users)", "value": "27%", "scope": "NL"},
        ],
        "eligibility_criteria": [
            "Employee recruited from abroad (resided beyond the qualifying distance before hiring)",
            "Has scarce specific expertise and meets the minimum-salary norm",
        ],
        "exclusions": ["Reimbursement is capped at the public-sector (WNT) salary norm"],
    },
    # --------------------------------------------------------------- United Kingdom
    {
        "citation_id": "UK#non-dom-abolished",
        "jurisdiction": "UK",
        "regime_name": "Non-domicile / remittance basis",
        "title": "United Kingdom — Non-dom remittance basis (ABOLISHED 6 April 2025)",
        "article": "Remittance basis",
        "status": "replaced",
        "status_effective_date": "2025-04-06",
        "applies_to_new_applicants": False,
        "grandfathering": "Transitional reliefs (e.g. the Temporary Repatriation Facility) apply to former remittance-basis users; the remittance basis itself is no longer available for new years.",
        "effective_date": "2025-04-06",
        "source_url": "https://www.gov.uk/government/publications/changes-to-the-taxation-of-non-uk-domiciled-individuals/technical-note-changes-to-the-taxation-of-non-uk-domiciled-individuals",
        "summary": (
            "The UK's domicile-based remittance basis for non-domiciled individuals was ABOLISHED "
            "from 6 April 2025 and replaced by a residence-based system, the centrepiece of which "
            "is the 4-year Foreign Income and Gains (FIG) regime. New movers can no longer claim "
            "the old remittance basis; do NOT recommend it for a new arrival. Transitional reliefs "
            "(such as the Temporary Repatriation Facility) apply to former users. Informational "
            "regime evidence — confirm status at the cited source and with a professional."
        ),
        "figures": [],
        "eligibility_criteria": [],
        "exclusions": ["Abolished from 6 April 2025 — see the 4-year FIG regime for the successor"],
    },
    {
        "citation_id": "UK#fig-regime",
        "jurisdiction": "UK",
        "regime_name": "4-year Foreign Income and Gains (FIG) regime",
        "title": "United Kingdom — 4-year Foreign Income and Gains (FIG) regime",
        "article": "FIG regime",
        "status": "active",
        "status_effective_date": "2025-04-06",
        "applies_to_new_applicants": True,
        "effective_date": "2025-04-06",
        "source_url": "https://www.gov.uk/government/publications/changes-to-the-taxation-of-non-uk-domiciled-individuals/technical-note-changes-to-the-taxation-of-non-uk-domiciled-individuals",
        "summary": (
            "The UK's 4-year Foreign Income and Gains (FIG) regime (in force from 6 April 2025) MAY "
            "BE RELEVANT to a person becoming UK tax resident after at least 10 consecutive tax "
            "years of non-UK residence. Where it applies, qualifying foreign income and gains can "
            "be exempt from UK tax for the first 4 tax years of residence, but claimants forfeit "
            "the personal allowance and the capital-gains annual exempt amount for those years. "
            "Informational regime evidence — not an eligibility determination; confirm at the cited "
            "source and with a professional."
        ),
        "figures": [
            {"label": "exemption period for qualifying foreign income/gains", "value": "first 4 UK tax years", "scope": "UK"},
            {"label": "required prior non-residence", "value": "10 consecutive tax years", "scope": "UK"},
        ],
        "eligibility_criteria": [
            "Becomes UK tax resident after at least 10 consecutive tax years of non-UK residence",
            "Claims the regime for the relevant tax year",
        ],
        "exclusions": [
            "Claimants lose the income-tax personal allowance and CGT annual exempt amount for claimed years",
        ],
    },
]


def _content_hash(entry: dict) -> str:
    """Reproducible SHA-256 fingerprint over the verified, citation-bearing fields."""
    canonical = json.dumps(
        {
            "citation_id": entry["citation_id"],
            "summary": entry["summary"],
            "status": entry["status"],
            "status_effective_date": entry["status_effective_date"],
            "figures": entry["figures"],
            "source_url": entry["source_url"],
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _build_entry(regime: dict, today: str) -> dict:
    entry = {
        "citation_id": regime["citation_id"],
        "jurisdiction": regime["jurisdiction"],
        "title": regime["title"],
        "article": regime["article"],
        "summary": regime["summary"],
        "content_type": "curated_regime",
        "effective_date": regime["effective_date"],
        "source_url": regime["source_url"],
        "package_version": PACKAGE_VERSION,
        "regime_name": regime["regime_name"],
        "status": regime["status"],
        "status_effective_date": regime["status_effective_date"],
        "applies_to_new_applicants": regime["applies_to_new_applicants"],
        "figures": regime["figures"],
        "eligibility_criteria": regime["eligibility_criteria"],
        "exclusions": regime["exclusions"],
        "generator_version": GENERATOR_VERSION,
        "retrieved_at": today,
    }
    if "region" in regime:
        entry["region"] = regime["region"]
    if "grandfathering" in regime:
        entry["grandfathering"] = regime["grandfathering"]
    entry["source_content_hash"] = _content_hash(regime)
    return entry


def main() -> int:
    doc = json.loads(DATA.read_text(encoding="utf-8"))
    existing = {e["citation_id"] for e in doc["legislation"]}
    today = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d")

    seen: set[str] = set()
    added: list[dict] = []
    for regime in REGIMES:
        cid = regime["citation_id"]
        if cid in seen:
            print(f"  duplicate id in source data: {cid}", file=sys.stderr)
            return 1
        seen.add(cid)
        if cid in existing:
            continue
        added.append(_build_entry(regime, today))
        print(f"  + {cid} [{regime['status']}]")

    if not added:
        print("No new regime entries to add (all present).")
        return 0

    doc["legislation"].extend(added)
    DATA.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Added {len(added)} curated_regime entries; total {len(doc['legislation'])}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
