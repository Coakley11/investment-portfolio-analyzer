"""Question catalog registry."""

from __future__ import annotations

from investment_ami.catalog.generated_from_legacy import build_legacy_question_catalog
from investment_ami.models.question import AmiQuestionDefinition

_CATALOG: dict[str, AmiQuestionDefinition] | None = None


def _catalog() -> dict[str, AmiQuestionDefinition]:
    global _CATALOG
    if _CATALOG is None:
        _CATALOG = build_legacy_question_catalog()
    return _CATALOG


def reset_question_catalog_for_tests() -> None:
    global _CATALOG
    _CATALOG = None


def get_question_definition(question_id: str) -> AmiQuestionDefinition | None:
    return _catalog().get(str(question_id or "").strip())


def question_for_intent(intent_id: str) -> AmiQuestionDefinition | None:
    return get_question_definition(intent_id)


def all_question_definitions() -> tuple[AmiQuestionDefinition, ...]:
    return tuple(_catalog()[k] for k in sorted(_catalog()))
