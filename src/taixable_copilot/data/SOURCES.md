# Data sources & disclaimer

> **⚠️ Illustrative demo data.** The figures, thresholds, and treaty rates in this
> directory are simplified and intended to demonstrate the agent's retrieval and
> citation workflow. They are **not** a substitute for the primary legal texts and
> **must be verified** against the official sources below before any real-world use.
> The product positions the agent as decision **support for a qualified tax
> professional**, never as autonomous tax or legal advice.

## Coverage

3 jurisdictions (Spain `ES`, United Kingdom `UK`, Germany `DE`) and the 3 bilateral
double-taxation conventions between them.

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

## Citation id scheme

`<COUNTRY-PAIR>#art<N>` for treaty articles, `<COUNTRY-PAIR>#art<N>-rate` for the
associated withholding/relief entry, `<COUNTRY>#<topic>` for residency and deadlines.
Every figure surfaced by the agent carries one of these ids, validated against the
known corpus before a memo is rendered or a case is persisted.
