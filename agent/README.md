# Agent Builder + Elastic MCP wiring

This folder holds the assets to assemble the agent in **Google Cloud Agent Builder**
(Vertex AI Agent Builder) using **Gemini 3** as the model and the **Elastic MCP server**
as the partner retrieval tool. The FastAPI service in `src/taixable_copilot/api/` exposes
the three actions the agent calls.

## Files
- `instructions.md` — the system prompt / agent instructions.
- `openapi.tools.json` — OpenAPI spec for the three tool endpoints, ready to import as an
  **OpenAPI tool** in Agent Builder. Regenerate after API changes:
  ```bash
  python -c "import json;from taixable_copilot.api.app import app;s=app.openapi();\
  s['paths']={k:v for k,v in s['paths'].items() if k.startswith('/tools/')};\
  open('agent/openapi.tools.json','w').write(json.dumps(s,indent=2))"
  ```

## One-time setup (requires your cloud credentials)
1. **Elastic Cloud Serverless** — create a project, generate an API key, then ingest the
   corpus:
   ```bash
   export ELASTIC_URL=... ELASTIC_API_KEY=...
   python scripts/ingest_elastic.py
   ```
   Enable the project's built-in **MCP server** and note its endpoint + key.
2. **Deploy the tool service** to Cloud Run (see repo README → Deploy). Set
   `ELASTIC_URL`, `ELASTIC_API_KEY`, and `DATABASE_URL` (Cloud SQL) as env vars so the
   service retrieves from Elastic and persists to MySQL.
3. **Agent Builder**:
   - Create an agent, model = Gemini 3.
   - Paste `instructions.md` as the system instructions.
   - Add the **Elastic MCP server** as a tool (partner-MCP requirement) so the model can do
     ad-hoc grounding/search over the tax corpus.
   - Import `openapi.tools.json` as an OpenAPI tool pointing at the Cloud Run base URL, so
     the agent can call `assess_obligations`, `generate_memo`, and `persist_case`.
   - Publish and capture the hosted agent URL for the submission.

## Why both the MCP server and the OpenAPI tools?
The **Elastic MCP server** satisfies the hackathon's partner-MCP requirement and gives the
model flexible retrieval/grounding over the corpus. The **OpenAPI tools** provide the
deterministic, guard-railed actions (citation validation + the human-approval persistence
gate) that we don't want the model to improvise. The domain logic behind those tools is
structured so it can itself be exposed as a *taixable* MCP server post-hackathon (see the
design spec, Appendix A).
