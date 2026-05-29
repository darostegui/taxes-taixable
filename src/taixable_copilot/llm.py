"""Gemini narration layer — the reasoning/language layer *around* the engine.

The deterministic engine (``obligations`` + ``citations``) is the single source
of truth: it produces the obligations, deadlines, rates and citation IDs. Gemini
never invents tax law — it only rewrites the **facts the engine already computed**
into plain English for a tax professional's client.

Design constraints:
  * **Optional & non-fatal.** If the ``google-genai`` SDK is missing, no
    credentials are configured, or the call fails for any reason,
    ``narrate_assessment`` returns ``None`` and the caller falls back to the
    deterministic markdown memo. The core agent therefore still runs fully
    offline with zero cloud dependencies.
  * **Auth resolution (in order):** explicit Vertex AI mode → Gemini API key →
    no client (returns ``None``). Vertex uses Application Default Credentials, so
    on Cloud Run it authenticates via the service account with no key to manage.
  * **Anti-hallucination prompt.** The system instruction forbids adding any
    rate, article, deadline or citation not present in the supplied facts.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from taixable_copilot.citations import resolve_citations

if TYPE_CHECKING:
    from taixable_copilot.citations import Citation
    from taixable_copilot.obligations import Assessment

_SYSTEM_INSTRUCTION = (
    "You are a tax-compliance writing assistant supporting a qualified tax "
    "professional. Rewrite the FACTS below into a clear, professional, plain-"
    "English explanation the professional can share with their client.\n"
    "STRICT RULES:\n"
    "- Use ONLY the facts provided. Do NOT add, infer, or estimate any tax "
    "rate, treaty article, filing deadline, monetary figure, or legal claim "
    "that is not explicitly present.\n"
    "- Do NOT invent or alter citations or source names.\n"
    "- Keep every figure, percentage, date and country exactly as given.\n"
    "- Write 2-4 short paragraphs. Do not use markdown headings or tables.\n"
    "- Close by deferring to the tax professional's review; this is workflow "
    "support, not autonomous tax or legal advice."
)

_DEFAULT_MODEL = "gemini-2.5-flash"


def build_narration_prompt(
    assessment: "Assessment",
    customer_token: str,
    citation_index: "dict[str, Citation] | None" = None,
) -> str:
    """Build the facts-only prompt fed to Gemini (pure, no network, testable)."""
    lines: list[str] = []
    lines.append(f"Client reference: {customer_token}")
    lines.append(
        f"Primary tax residence: {assessment.primary_residence} "
        f"(confidence {assessment.residence_confidence:.0%})"
    )
    lines.append("")
    lines.append("Cross-border obligations:")
    if assessment.obligations:
        for o in assessment.obligations:
            lines.append(
                f"- {o.income_type} income sourced in {o.source_country}: "
                f"treaty article {o.treaty_article}, rate {o.rate:.0%}, "
                f"relief {o.relief}."
            )
    else:
        lines.append("- None identified.")
    lines.append("")
    lines.append("Filing deadlines:")
    if assessment.deadlines:
        for d in assessment.deadlines:
            lines.append(f"- {d.jurisdiction}: {d.description}, due {d.due_date}.")
    else:
        lines.append("- None identified.")
    lines.append("")
    lines.append("Sources (cite these names exactly; do not add others):")
    for c in resolve_citations(assessment.citations, citation_index):
        lines.append(f"- {c.label}")
    return "\n".join(lines)


def _make_client():  # noqa: ANN202 - SDK type only available when installed
    """Return a configured ``google-genai`` client, or ``None`` if unavailable.

    Resolution order: Vertex AI (ADC) → Gemini API key → ``None``.
    """
    try:
        from google import genai
    except ImportError:
        return None

    use_vertex = os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "").lower() in {"1", "true", "yes"}
    project = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCP_PROJECT")
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")

    try:
        if use_vertex and project:
            location = os.getenv("GOOGLE_CLOUD_LOCATION", "europe-west1")
            return genai.Client(vertexai=True, project=project, location=location)
        if api_key:
            return genai.Client(api_key=api_key)
    except Exception:  # noqa: BLE001 - any SDK/auth error → graceful fallback
        return None
    return None


def narrate_assessment(
    assessment: "Assessment",
    customer_token: str,
    citation_index: "dict[str, Citation] | None" = None,
) -> str | None:
    """Return a Gemini plain-English narration of the assessment, or ``None``.

    ``None`` is returned (and the caller should fall back to the deterministic
    memo) whenever the SDK is missing, no credentials are configured, or the
    model call fails. This function never raises.
    """
    client = _make_client()
    if client is None:
        return None

    prompt = build_narration_prompt(assessment, customer_token, citation_index)
    model = os.getenv("GEMINI_MODEL", _DEFAULT_MODEL)
    try:
        from google.genai import types

        resp = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=_SYSTEM_INSTRUCTION,
                temperature=0.2,
                max_output_tokens=600,
            ),
        )
        text = (resp.text or "").strip()
        return text or None
    except Exception:  # noqa: BLE001 - network/model/quota error → graceful fallback
        return None
