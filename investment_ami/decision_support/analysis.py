"""Run matched rules and aggregate findings."""

from __future__ import annotations

from investment_ami.decision_support.models import DecisionSupportResponse, FinancialSnapshot, ReasoningFinding
from investment_ami.decision_support.rules import GLOBAL_RULE_REGISTRY


def run_financial_analysis(
    module_id: str,
    snapshot: FinancialSnapshot,
    question: str,
) -> list[ReasoningFinding]:
    findings: list[ReasoningFinding] = []
    seen: set[str] = set()
    for rule in GLOBAL_RULE_REGISTRY.matching_rules(module_id, snapshot, question):
        finding = rule.analyze(snapshot, question)
        if finding is None or finding.rule_id in seen:
            continue
        seen.add(finding.rule_id)
        findings.append(finding)
    return findings


def build_decision_support_response(
    module_id: str,
    snapshot: FinancialSnapshot,
    question: str,
    findings: list[ReasoningFinding],
) -> DecisionSupportResponse:
    facts: list[str] = []
    for k, v in snapshot.to_facts_dict().items():
        facts.append(f"{k.replace('_', ' ').title()}: {v}")

    observations = [f.observation for f in findings if f.observation]
    concerns = [f.concern for f in findings if f.concern]
    actions = [f.suggested_action for f in findings if f.suggested_action]
    trade_offs = [f.trade_off for f in findings if f.trade_off]

    confidences = [f.confidence for f in findings if f.confidence != "placeholder"]
    confidence = confidences[0] if len(confidences) == 1 else ("medium" if confidences else "placeholder")

    return DecisionSupportResponse(
        module_id=module_id,
        question=question,
        facts=facts,
        observations=observations,
        concerns=concerns,
        suggested_actions=actions,
        trade_offs=trade_offs,
        confidence=confidence,
        limitations=list(snapshot.limitations),
        findings=findings,
        applied_rule_ids=tuple(f.rule_id for f in findings),
    )
