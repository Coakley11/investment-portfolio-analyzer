"""Canonical AMI decision response (P1 shell — populated in later phases)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class EvidenceItem:
    label: str
    value: str
    source: str = ""


@dataclass
class AmiDecisionResponse:
    executive_summary: str = ""
    recommendation: str = ""
    confidence_level: int | None = None
    supporting_evidence: list[EvidenceItem] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    alternative_viewpoints: list[str] = field(default_factory=list)
    portfolio_impact: str = ""
    macroeconomic_considerations: str = ""
    suggested_next_steps: list[str] = field(default_factory=list)
    related_question_ids: list[str] = field(default_factory=list)
    analyst_sections: dict[str, str] = field(default_factory=dict)
    computed: dict[str, Any] = field(default_factory=dict)
    assumptions: list[str] = field(default_factory=list)
    intent_id: str = ""
    pipeline_profile: str = "legacy"
