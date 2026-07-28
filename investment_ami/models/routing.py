"""Routing result models."""

from __future__ import annotations

from dataclasses import dataclass

from investment_ami.models.question import AmiQuestionDefinition


@dataclass(frozen=True)
class RoutedQuestion:
    intent_id: str
    definition: AmiQuestionDefinition
    question_text: str
    source_page: str

    @property
    def supported(self) -> bool:
        return bool(self.intent_id)
