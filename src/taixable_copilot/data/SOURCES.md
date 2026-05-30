# Data sources & disclaimer

> **⚠️ Illustrative demo data.** The figures, thresholds, and treaty rates in this
> directory are simplified and intended to demonstrate the agent's retrieval and
> citation workflow. They are **not** a substitute for the primary legal texts and
> **must be verified** against the official sources below before any real-world use.
> The product positions the agent as decision **support for a qualified tax
> professional**, never as autonomous tax or legal advice.

## Coverage

**Computable engine (deterministic figures):** 3 jurisdictions (Spain `ES`, United
Kingdom `UK`, Germany `DE`) and the 3 bilateral double-taxation conventions between
them. These are the only jurisdictions for which the engine computes residence,
rates, treaty relief and deadlines.

**Cited reference corpus (searchable, evidence-only):** ~147 jurisdictions worldwide.
These are searchable, source-linked reference cards — NOT computable liability. For
any jurisdiction outside UK/ES/DE the agent fails closed: it surfaces the cited
source and states plainly that Taixable does not yet compute that country's tax.

## Primary sources

### Double Taxation Conventions (treaty articles + reduced rates)
- **Spain–UK DTC (2013)** — HMRC tax treaties: https://www.gov.uk/government/publications/spain-tax-treaties
- **Germany–UK DTC (2010)** — HMRC tax treaties: https://www.gov.uk/government/publications/germany-tax-treaties
- **Germany–Spain DTC (2011)** — German Federal Ministry of Finance (BMF) treaty list: https://www.bundesfinanzministerium.de/
- OECD Model Tax Convention (article numbering reference): https://www.oecd.org/tax/treaties/model-tax-convention-on-income-and-on-capital-condensed-version-20745419.htm

### Residency tests (`residency_rules.yaml`)
- **Spain** — Ley 35/2006 IRPF, art. 9 (183-day rule): https://www.boe.es/buscar/act.php?id=BOE-A-2006-20764
- **UK** — Statutory Residence Test (RDR3): https://www.gov.uk/government/publications/rdr3-statutory-residence-test-srt (simplified to a 183-day proxy here)
- **Germany** — Abgabenordnung §§8–9 (Wohnsitz / gewöhnlicher Aufenthalt): https://www.gesetze-im-internet.de/ao_1977/

### Filing deadlines (referenced by `obligations.FILING_DEADLINES`)
- `UK#sa-deadline` — UK Self Assessment online deadline 31 January: https://www.gov.uk/self-assessment-tax-returns/deadlines
- `ES#renta-deadline` — Spain Renta campaign, typically to 30 June: https://sede.agenciatributaria.gob.es/
- `DE#est-deadline` — Germany Einkommensteuererklärung, statutory 31 July: https://www.bundesfinanzministerium.de/

### Cited reference corpus (`legislation.json`, `content_type="curated_reference"`)
- **PwC Worldwide Tax Summaries** — per-territory individual *residence* and *taxes on
  personal income* pages: https://taxsummaries.pwc.com/ . Used as a verified,
  authoritative pointer for ~146 territories. Each entry stores the exact source URL,
  a `retrieved_at` timestamp and a `source_content_hash` (sha256 of the fetched page
  body) for provenance/audit. Summaries are **reference-only** — they record where to
  read the rule, not the rule itself (no day-count thresholds, rates or article
  numbers are asserted).
- **Russia** — PwC withdrew its Russia summary in 2022; the corpus instead points to
  the Federal Tax Service of Russia (English): https://www.nalog.gov.ru/eng/
- Generated reproducibly by `scripts/build_reference_corpus.py`
  (`generator_version="reference-corpus/1.0"`, `package_version="2025.1"`); re-runnable
  and idempotent (never clobbers curated engine ids).

### Special mobility-regimes corpus (`legislation.json`, `content_type="curated_regime"`)
Curated, source-verified cards for the special regimes and benefits that drive mobility
decisions. **Unlike the reference tier these carry concrete figures** (flat rates, caps,
durations, thresholds) — every figure is verified against an official/primary source and
stored with `source_url`, `effective_date`, `status` + `status_effective_date`,
`applies_to_new_applicants`, structured `figures`/`eligibility_criteria`/`exclusions`,
optional `region`/`grandfathering`, and provenance (`retrieved_at`, `source_content_hash`).
They are surfaced for eligibility **screening** ("may be relevant if…"), never as an
eligibility determination, and the agent relays the cited figure verbatim.
- **Status enum** — `active | repealed | closed_to_new_entrants | replaced`. Closed routes
  carry `applies_to_new_applicants=false` and are never recommended for a new move (the card
  names any successor, e.g. UK non-dom → FIG, Portugal NHR → IFICI).
- **Up-to-date flagship facts (verified 2024–2025)** — UK non-dom abolished 6 Apr 2025 → 4-yr
  FIG; ES golden-visa real-estate route repealed 3 Apr 2025 (Ley Orgánica 1/2025); PT NHR
  closed to new entrants 2024 → IFICI; IT impatriati / €200k HNWI flat / 7% pensioners; GR
  5A non-dom / 5B pensioners / 5C impatriate; FR Art. 155 B; NL expat ruling 30% → 27% (2027);
  ES Beckham 24% (Art. 93 LIRPF + Startups Law 28/2022), familia numerosa, regional/foral
  (Madrid, Andalucía, Cataluña, País Vasco, Navarra) + national Solidarity Tax (ITSGF).
- **Sources** — BOE (Spanish statutes), Agencia Tributaria, gov.uk technical notes, official
  immigration portals, and PwC Worldwide Tax Summaries (`taxsummaries.pwc.com`) for cross-checks.
- **Integrity** — each `figure` carries a `scope` tag; figures are never mixed across
  jurisdictions/regions. Regional cards keep a single-country `jurisdiction` (e.g. `ES`) with
  the region in the `citation_id` (`ES-CT#regional-irpf`) and a `region` field, so coverage and
  treaty-pair logic never misread them.
- Generated reproducibly by `scripts/build_special_regimes.py`
  (`generator_version="special-regimes/1.0"`, `package_version="2025.1"`); idempotent.

## Citation id scheme

`<COUNTRY-PAIR>#art<N>` for treaty articles, `<COUNTRY-PAIR>#art<N>-rate` for the
associated withholding/relief entry, `<COUNTRY>#<topic>` for residency and deadlines.
Cited reference entries use `<ISO2>#residence` and `<ISO2>#income-tax` (plus
`RU#tax-authority` for Russia). Every figure surfaced by the agent carries one of
these ids, validated against the known corpus before a memo is rendered or a case is
persisted.
