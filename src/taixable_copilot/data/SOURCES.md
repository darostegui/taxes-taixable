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

## Citation id scheme

`<COUNTRY-PAIR>#art<N>` for treaty articles, `<COUNTRY-PAIR>#art<N>-rate` for the
associated withholding/relief entry, `<COUNTRY>#<topic>` for residency and deadlines.
Cited reference entries use `<ISO2>#residence` and `<ISO2>#income-tax` (plus
`RU#tax-authority` for Russia). Every figure surfaced by the agent carries one of
these ids, validated against the known corpus before a memo is rendered or a case is
persisted.
