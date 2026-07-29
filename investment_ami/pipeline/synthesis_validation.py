"""Lightweight grounding checks for synthesis output (Phase 4 — expanded in Phase 5)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class GroundingValidationResult:
    ok: bool
    invalid_fact_ids: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    valid_citations: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "invalid_fact_ids": list(self.invalid_fact_ids),
            "warnings": list(self.warnings),
            "valid_citations": list(self.valid_citations),
        }


_BRACKET_FACT_RE = re.compile(r"\[([a-z0-9_.]+)\]", re.IGNORECASE)


def validate_synthesis_grounding(
    parsed: dict[str, Any],
    *,
    valid_fact_ids: set[str],
    answer_markdown: str,
) -> GroundingValidationResult:
    result = GroundingValidationResult(ok=True)
    citations = parsed.get("citations") if isinstance(parsed.get("citations"), list) else []
    cited_ids: set[str] = set()

    for item in citations:
        if not isinstance(item, dict):
            continue
        fid = str(item.get("fact_id") or "").strip()
        if not fid:
            continue
        cited_ids.add(fid)
        if fid not in valid_fact_ids:
            result.invalid_fact_ids.append(fid)
        else:
            result.valid_citations.append(
                {"fact_id": fid, "excerpt": str(item.get("excerpt") or "")[:240]}
            )

    for fid in _BRACKET_FACT_RE.findall(answer_markdown or ""):
        cited_ids.add(fid)
        if fid not in valid_fact_ids:
            result.invalid_fact_ids.append(fid)

    if result.invalid_fact_ids:
        result.ok = False
        result.warnings.append("One or more cited fact_id values are not in the PortfolioAnalysisBrief.")

    if valid_fact_ids and not cited_ids:
        result.warnings.append("No fact_id citations detected — answer may be under-grounded.")

    # Heuristic: percentage without any citation
    if re.search(r"\d+(?:\.\d+)?\s*%", answer_markdown or "") and not cited_ids:
        result.warnings.append("Numeric percentages present but no fact citations found.")

    return result
