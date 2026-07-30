"""Pluggable decision-support rules."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from investment_ami.decision_support.models import FinancialSnapshot, ReasoningFinding


class DecisionRule(Protocol):
    rule_id: str
    module_id: str
    topics: tuple[str, ...]

    def matches(self, snapshot: FinancialSnapshot, question: str) -> bool: ...

    def analyze(self, snapshot: FinancialSnapshot, question: str) -> ReasoningFinding | None: ...


@dataclass(frozen=True)
class SimpleRule:
    rule_id: str
    module_id: str
    topics: tuple[str, ...]
    phrases: tuple[str, ...] = ()
    always: bool = False

    def matches(self, snapshot: FinancialSnapshot, question: str) -> bool:
        if self.always:
            return True
        q = question.lower()
        if self.phrases and any(p in q for p in self.phrases):
            return True
        return False

    def analyze(self, snapshot: FinancialSnapshot, question: str) -> ReasoningFinding | None:
        return None


class RuleRegistry:
    def __init__(self) -> None:
        self._rules: list[DecisionRule] = []

    def register(self, rule: DecisionRule) -> None:
        self._rules.append(rule)

    def rules_for_module(self, module_id: str) -> tuple[DecisionRule, ...]:
        return tuple(r for r in self._rules if r.module_id == module_id)

    def matching_rules(
        self, module_id: str, snapshot: FinancialSnapshot, question: str
    ) -> tuple[DecisionRule, ...]:
        out = []
        for rule in self.rules_for_module(module_id):
            if rule.matches(snapshot, question):
                out.append(rule)
        return tuple(out)


GLOBAL_RULE_REGISTRY = RuleRegistry()
