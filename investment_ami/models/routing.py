"""Routing result models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from investment_ami.models.question import AmiQuestionDefinition


@dataclass(frozen=True)
class RoutedQuestion:
    intent_id: str
    definition: AmiQuestionDefinition
    question_text: str
    source_page: str
    response_mode: str = "deterministic"
    question_tag: str = ""
    mode_routing: dict[str, Any] = field(default_factory=dict)

    @property
    def supported(self) -> bool:
        return bool(self.intent_id)
