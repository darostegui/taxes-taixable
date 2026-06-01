# Cross-Border Tax Obligations Copilot

> **Google Cloud Rapid Agent Hackathon — Elastic track.** A functional agent (not a chatbot) that
> plans and executes a multi-step cross-border tax analysis, with a human-in-the-loop approval gate.

**License:** Apache-2.0 (see [`LICENSE`](LICENSE)).

## What it does

Given a tax advisor's customer profile (residence + income/assets, some foreign-sourced), the agent:

1. **Determines tax residency** per country from official residency rules.
2. **Applies the relevant bilateral double-tax treaty** (ES·UK·DE·FR·IE·NL pairs) per income type.
3. **Looks up withholding/relief rates** from the treaty rate tables.
4. **Computes obligations + filing deadlines** — every conclusion **cited** to a real source.
5. **Drafts a client-ready memo**, and **only after the advisor approves**, persists a compliance
   case + deadlines to the system-of-record.

## Architecture

```
                 ┌───────────────────────────────────────────────┐
   Advisor ──▶   │  Web UI (Cloud Run)                           │
                 │   select customer · run · review · approve    │
                 └───────────────┬───────────────────────────────┘
                                 │  invokes
                 ┌───────────────▼───────────────────────────────┐
                 │  Google Cloud Agent Builder  (Gemini 3)       │
                 │  plan → retrieve → compute → draft → persist  │
                 └───────┬───────────────────────┬───────────────┘
              MCP tools  │                       │  function tools
                 ┌───────▼────────┐      ┌───────▼─────────────────┐
                 │ Elastic (MCP)  │      │ FastAPI tool service    │
                 │ hybrid search  │      │ assess · memo ·         │
                 │ + ES|QL rates  │      │ persist (approval gate) │
                 │ curated corpus │      └───────┬─────────────────┘
                 └────────────────┘              │
                                          ┌──────▼──────────┐
                                          │ Cloud SQL MySQL │
                                          │ system-of-record│
                                          └─────────────────┘
```

The domain logic (`src/taixable_copilot/`) is a pure-Python, modular layer designed to be
**MCP-mappable** — the same units can later back a standalone "taixable MCP server."

> **What is the judged "hosted URL"?** The submission's hosted agent is the **Google Cloud
> Agent Builder agent (Gemini 3)**, which orchestrates the flow: it consumes the **Elastic
> MCP server** (partner-MCP requirement) for grounding/retrieval and calls this repo's
> FastAPI endpoints as **OpenAPI action tools**. The FastAPI service also serves a small
> **local demo UI** (`/`) that calls the tools directly — that UI is a developer harness for
> running the flow without cloud, **not** the Gemini-orchestrated path. The FastAPI tools are
> OpenAPI actions, not an MCP server; Elastic is the MCP server, consumed by the agent.

**Privacy:** synthetic customers only; PII is redacted/tokenized before anything reaches the model.

## Setup (local development)

```bash
make install      # create venv + install (editable) with dev deps
make test         # run pytest (126 tests)
make evals        # run the golden-case eval harness
make run          # serve the agent tool service + demo UI on :8080
```

Then open http://localhost:8080 — the demo UI runs the **whole flow locally**
(assess → memo → approve & persist) backed by the curated corpus in
`src/taixable_copilot/data/`, with **no cloud dependency**. Set `ELASTIC_URL`
(+`ELASTIC_API_KEY`) to switch retrieval to Elastic, and `DATABASE_URL` to target
Cloud SQL / MySQL instead of the local SQLite file.

```bash
make db-up        # optional: local MySQL (docker) for prod parity
make es-up        # optional: local Elasticsearch (docker)
```

Cloud credentials (Elastic, Google Cloud, MySQL) are read from a local
`secrets.env` (git-ignored) or your environment and are **never committed**.

## Curated data & disclaimer

The tax corpus lives in `src/taixable_copilot/data/` (with sources and a
disclaimer in [`SOURCES.md`](src/taixable_copilot/data/SOURCES.md)) and spans:

- **31 jurisdictions** with official tax-residency day-count rules;
- **6 bilateral double-tax treaty pairs** (ES-UK, DE-UK, DE-ES, FR-UK, IE-UK,
  NL-UK) with verified article references;
- **deterministic tax-band / withholding tables** for the 6 core compute
  countries (AD, DE, ES, IE, PT, UK), so "how much" figures are arithmetic over
  cited statutory bands — never model-invented;
- a **searchable cited reference corpus of 336 documents** across ~148
  jurisdictions (residency, income-tax, special-mobility-regime and treaty
  cards), indexed for Elastic hybrid (BM25 + vector + RRF) retrieval and
  citation highlighting.

**Figures are illustrative and
must be verified against the primary legal texts before any real-world use** — the
agent is decision support for a qualified professional, not autonomous tax advice.

## Deploy (Cloud Run + Agent Builder)

```bash
make docker-build                       # build the container
# push to Artifact Registry and deploy (attach Cloud SQL via the connector):
gcloud run deploy taixable-copilot \
  --source . --region <region> --allow-unauthenticated \
  --add-cloudsql-instances <project:region:instance> \
  --set-env-vars ELASTIC_URL=...,ELASTIC_API_KEY=...,DATABASE_URL=mysql+pymysql://USER:PASS@/taixable?unix_socket=/cloudsql/<project:region:instance>
```

Then assemble the agent per [`agent/README.md`](agent/README.md): ingest the corpus
into Elastic (`make ingest`), add the **Elastic MCP server** as a tool, and import
[`agent/openapi.tools.json`](agent/openapi.tools.json) as the action tool set in
**Google Cloud Agent Builder** (Gemini 3).

### Hosted URL & access

The live demo is hosted on **Cloud Run** at **https://taxes.taixable.net**.

Access is **protected by a login** (username + password), so customer-style
queries aren't exposed to the open internet. For the hackathon, a shared
read-only demo account is provided so judges can sign in immediately:

| Field | Value |
| --- | --- |
| Username | `demo` |
| Password | `demo` |

> The `demo` / `demo` credentials are intentionally published for judging only and
> grant access to the synthetic-data sandbox. The login gate is the app's own
> JSON `/login` endpoint (HMAC bearer token), **not** HTTP Basic Auth — enter the
> credentials in the on-page form. Production secrets are set via environment
> variables and are never committed.

A dedicated subdomain (`taxes.taixable.net`) is mapped to the service so the
demo is clearly scoped as new hackathon work, separate from any production
marketing site. To map your own subdomain:

```bash
gcloud beta run domain-mappings create \
  --service taixable-copilot --domain <your-subdomain> --region <region>
```

## Tech stack

Python · FastAPI · Elasticsearch (Elastic Cloud Serverless + Agent Builder/MCP) · Cloud SQL (MySQL) ·
Vertex AI / Google Cloud Agent Builder (Gemini 3) · Cloud Run · Docker.
