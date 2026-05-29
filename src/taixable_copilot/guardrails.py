"""Citation guardrail: ensure every cited source resolves to a real corpus chunk.

Used to reject hallucinated treaty-article references before a memo is shown or a
case is persisted.
"""

from __future__ import annotations

from collections.abc import Iterable


def validate_citations(
    cited: Iterable[str],
    known_ids: set[str],
) -> tuple[bool, list[str]]:
    """Return (all_valid, invalid_ids) for the given cited identifiers."""
    invalid = [c for c in cited if c not in known_ids]
    return (len(invalid) == 0, invalid)
