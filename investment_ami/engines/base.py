"""Instant reasoning engine contracts (P2+)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class InstantEngineRequest:
    context: dict[str, Any]
    beginner: bool
    question: str = ""


class InstantEngine(Protocol):
    """Single-family instant solver extracted from legacy phase-2 modules."""

    engine_id: str

    def solve(self, request: InstantEngineRequest) -> Any:
        """Return ``InvestmentSolverResult`` (legacy shape)."""
