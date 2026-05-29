"""Render a client-ready compliance memo (markdown) from an Assessment.

Operates only on tokenized identifiers — never raw PII.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from taixable_copilot.obligations import Assessment

if TYPE_CHECKING:
    from taixable_copilot.citations import Citation


def render_memo(
    assessment: Assessment,
    customer_token: str,
    citation_index: "dict[str, Citation] | None" = None,
) -> str:
    lines: list[str] = []
    lines.append(f"# Cross-Border Tax Compliance Memo — {customer_token}")
    lines.append("")
    lines.append(
        f"**Primary tax residence:** {assessment.primary_residence} "
        f"(confidence {assessment.residence_confidence:.0%})"
    )
    lines.append("")

    lines.append("## Obligations")
    if assessment.obligations:
        lines.append("| Income type | Source | Treaty art. | Rate | Relief | Citations |")
        lines.append("|---|---|---|---|---|---|")
        for o in assessment.obligations:
            lines.append(
                f"| {o.income_type} | {o.source_country} | {o.treaty_article} "
                f"| {o.rate:.0%} | {o.relief} | {', '.join(o.citation_ids)} |"
            )
    else:
        lines.append("_No cross-border obligations identified._")
    lines.append("")

    lines.append("## Filing deadlines")
    if assessment.deadlines:
        for d in assessment.deadlines:
            cite = f" [{d.citation_id}]" if d.citation_id else ""
            lines.append(f"- **{d.jurisdiction}** — {d.description}: due {d.due_date}{cite}")
    else:
        lines.append("_No filing deadlines identified._")
    lines.append("")

    lines.append("## Sources")
    from taixable_copilot.citations import resolve_citations

    for c in resolve_citations(assessment.citations, citation_index):
        if c.url:
            lines.append(f"- [{c.label}]({c.url}) — `{c.id}`")
        else:
            lines.append(f"- {c.label} — `{c.id}`")
    lines.append("")
    lines.append(
        "> _Information and workflow support for a qualified tax professional. "
        "Not autonomous tax or legal advice. Review before client delivery._"
    )
    return "\n".join(lines)
