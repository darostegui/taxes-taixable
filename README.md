# Cross-Border Tax Obligations Copilot

> **Google Cloud Rapid Agent Hackathon — Elastic track.** A functional agent (not a chatbot) that
> plans and executes a multi-step cross-border tax analysis, with a human-in-the-loop approval gate.

**License:** Apache-2.0 (see [`LICENSE`](LICENSE)).

## What it does

Given a tax advisor's customer profile (residence + income/assets, some foreign-sourced), the agent:

1. **Determines tax residency** per country from official residency rules.
2. **Applies the relevant bilateral double-tax treaty** (Spain · UK · Germany) per income type.
3. **Looks up withholding/relief rates** from the treaty rate tables.
4. **Computes obligations + filing deadlines** — every conclusion **cited** to a real source.
5. **Drafts a client-ready memo**, and **only after the advisor approves**, persists a compliance
   case + deadlines to the system-of-record.

## Architecture

```
                 ┌─────────────────────────────────────────────┐
   Advisor ──▶   │  Web UI (Cloud Run)                          │
                 │   select customer · run · review · approve   │
                 └───────────────┬─────────────────────────────┘
                                 │  invokes
                 ┌───────────────▼─────────────────────────────┐
                 │  Google Cloud Agent Builder  (Gemini 3)      │
                 │  plan → retrieve → compute → draft → persist │
                 └───────┬───────────────────────┬─────────────┘
              MCP tools  │                       │  function tools
                 ┌───────▼────────┐      ┌───────▼──────────────┐
                 │ Elastic (MCP)  │      │ FastAPI tool service  │
                 │ hybrid search  │      │ assess · memo ·       │
                 │ + ES|QL rates  │      │ persist (approval gate)│
                 │ curated corpus │      └───────┬───────────────┘
                 └────────────────┘              │
                                          ┌──────▼──────────┐
                                          │ Cloud SQL MySQL │
                                          │ system-of-record│
                                          └─────────────────┘
```

The domain logic (`src/taixable_copilot/`) is a pure-Python, modular layer designed to be
**MCP-mappable** — the same units can later back a standalone "taixable MCP server."

**Privacy:** synthetic customers only; PII is redacted/tokenized before anything reaches the model.

## Setup (local development)

```bash
make install      # create venv + install (editable) with dev deps
make test         # run pytest
make db-up        # start local MySQL (docker)
```

Cloud credentials (Elastic, Google Cloud, MySQL) are read from `~/scratch/taixable-infra/secrets.env`
and are **never committed**.

## Tech stack

Python · FastAPI · Elasticsearch (Elastic Cloud Serverless + Agent Builder/MCP) · Cloud SQL (MySQL) ·
Vertex AI / Google Cloud Agent Builder (Gemini 3) · Cloud Run · Docker.
