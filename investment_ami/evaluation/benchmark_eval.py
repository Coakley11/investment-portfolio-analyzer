"""Run analytical benchmarks and produce structured evaluation reports."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from difflib import SequenceMatcher
from typing import Any

from investment_ami.evaluation.benchmark_suite import (
    ANALYTICAL_BENCHMARKS,
    IPA_BENCH_EVAL_CONTEXT,
    AnalyticalBenchmark,
)
from investment_ami.pipeline.analytical_synthesis import synthesize_with_diagnostics
from investment_ami.routing.mode_router import mode_routing_diagnostics_dict, route_investment_response_mode


@dataclass
class BenchmarkRunResult:
    benchmark_id: str
    question: str
    expected_tag: str
    routing: dict[str, Any] = field(default_factory=dict)
    routing_ok: bool = False
    synthesis_enabled: bool = False
    pipeline_step: str = ""
    answer_preview: str = ""
    answer_length: int = 0
    grounding_ok: bool | None = None
    citation_count: int = 0
    fact_count: int = 0
    limitation_count: int = 0
    timing_ms: dict[str, float] = field(default_factory=dict)
    token_usage: dict[str, Any] = field(default_factory=dict)
    structural_issues: list[str] = field(default_factory=list)
    qualitative_notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BenchmarkEvaluationReport:
    eval_context_fingerprint: str
    synthesis_mode: str
    runs: list[BenchmarkRunResult] = field(default_factory=list)
    cross_question_similarity_max: float = 0.0
    cross_question_similarity_pair: str = ""
    summary: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "eval_context_fingerprint": self.eval_context_fingerprint,
            "synthesis_mode": self.synthesis_mode,
            "runs": [r.to_dict() for r in self.runs],
            "cross_question_similarity_max": self.cross_question_similarity_max,
            "cross_question_similarity_pair": self.cross_question_similarity_pair,
            "summary": list(self.summary),
        }


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def run_single_benchmark(
    bench: AnalyticalBenchmark,
    context: dict[str, Any] | None = None,
) -> tuple[BenchmarkRunResult, Any]:
    ctx = dict(context or IPA_BENCH_EVAL_CONTEXT)
    q = bench.question
    mode = route_investment_response_mode(q, ctx)
    result_row = BenchmarkRunResult(
        benchmark_id=bench.benchmark_id,
        question=q,
        expected_tag=bench.expected_question_tag,
        routing=mode_routing_diagnostics_dict(mode),
    )
    result_row.routing_ok = (
        mode.response_mode == "analytical_synthesis"
        and mode.question_tag == bench.expected_question_tag
    )
    if not result_row.routing_ok:
        result_row.structural_issues.append(
            f"Routing mismatch: got {mode.response_mode}/{mode.question_tag}, "
            f"expected analytical_synthesis/{bench.expected_question_tag}"
        )

    _route, result, diag = synthesize_with_diagnostics(q, ctx, mode)
    computed = dict(getattr(result, "computed", None) or {})
    brief = computed.get("portfolio_analysis_brief") if isinstance(computed.get("portfolio_analysis_brief"), dict) else {}
    result_row.synthesis_enabled = bool(diag.synthesis_enabled)
    result_row.pipeline_step = str(computed.get("ami_pipeline_step") or "")
    answer = str(diag.validated_answer_markdown or result.short_answer or "")
    result_row.answer_preview = answer[:500]
    result_row.answer_length = len(answer)
    result_row.grounding_ok = (diag.grounding or {}).get("ok") if diag.grounding else None
    parsed = diag.parsed_response if isinstance(diag.parsed_response, dict) else {}
    cites = parsed.get("citations") if isinstance(parsed.get("citations"), list) else []
    result_row.citation_count = len(cites)
    result_row.fact_count = len(brief.get("facts") or {})
    result_row.limitation_count = len(brief.get("limitations") or [])
    result_row.timing_ms = dict(diag.timing_ms or {})
    result_row.token_usage = dict(diag.token_usage or {})

    if not diag.synthesis_enabled:
        result_row.structural_issues.append("Synthesis disabled — enable INVESTMENT_AMI_ANALYTICAL_SYNTHESIS=1 for eval.")
    if diag.mock_mode:
        result_row.qualitative_notes.append(
            "Mock LLM — qualitative analyst-quality review requires live model (unset INVESTMENT_AMI_SYNTHESIS_MOCK)."
        )
    if result_row.answer_length < 120:
        result_row.structural_issues.append("Answer very short — may not satisfy benchmark depth.")
    if result_row.grounding_ok is False:
        result_row.structural_issues.append("Grounding validation failed (invalid fact_id citations).")
    if result_row.citation_count < 1 and diag.synthesis_enabled and not diag.mock_mode:
        result_row.structural_issues.append("No structured citations in parsed response.")

    return result_row, diag


def run_benchmark_evaluation(
    *,
    context: dict[str, Any] | None = None,
    synthesis_mode: str = "",
) -> BenchmarkEvaluationReport:
    import os

    mode_label = synthesis_mode or (
        "mock" if os.environ.get("INVESTMENT_AMI_SYNTHESIS_MOCK") else "live_or_placeholder"
    )
    report = BenchmarkEvaluationReport(
        eval_context_fingerprint=str((context or IPA_BENCH_EVAL_CONTEXT).get("holdings_fingerprint") or "default"),
        synthesis_mode=mode_label,
    )
    answers: list[tuple[str, str]] = []
    for bench in ANALYTICAL_BENCHMARKS:
        row, _diag = run_single_benchmark(bench, context)
        report.runs.append(row)
        answers.append((bench.benchmark_id, row.answer_preview))

    max_sim = 0.0
    max_pair = ""
    for i in range(len(answers)):
        for j in range(i + 1, len(answers)):
            sim = _similarity(answers[i][1], answers[j][1])
            if sim > max_sim:
                max_sim = sim
                max_pair = f"{answers[i][0]} vs {answers[j][0]}"
    report.cross_question_similarity_max = round(max_sim, 3)
    report.cross_question_similarity_pair = max_pair
    if max_sim > 0.55:
        report.summary.append(
            f"High cross-question similarity ({max_sim:.2f} on {max_pair}) — answers may feel templated."
        )

    routing_fail = [r.benchmark_id for r in report.runs if not r.routing_ok]
    if routing_fail:
        report.summary.append(f"Routing failures: {', '.join(routing_fail)}")

    struct_fail = [r.benchmark_id for r in report.runs if r.structural_issues]
    if struct_fail:
        report.summary.append(
            f"Structural issues on {len(struct_fail)} benchmark(s) — see per-run structural_issues."
        )
    else:
        report.summary.append("All benchmarks passed structural routing + pipeline checks.")

    if mode_label == "mock":
        report.summary.append(
            "Next step: run with OPENAI_API_KEY and INVESTMENT_AMI_ANALYTICAL_SYNTHESIS=1 "
            "(no MOCK) and score answers with the qualitative rubric in docs/AMI_BENCHMARK_EVALUATION.md."
        )

    return report


def format_report_markdown(report: BenchmarkEvaluationReport) -> str:
    lines = [
        "# AMI analytical benchmark evaluation",
        "",
        f"- Context: `{report.eval_context_fingerprint}`",
        f"- Synthesis mode: `{report.synthesis_mode}`",
        f"- Max cross-question similarity: **{report.cross_question_similarity_max}** ({report.cross_question_similarity_pair})",
        "",
        "## Summary",
    ]
    for s in report.summary:
        lines.append(f"- {s}")
    lines.append("")
    lines.append("## Per benchmark")
    for run in report.runs:
        lines.append(f"### {run.benchmark_id}")
        lines.append(f"- Question: {run.question}")
        lines.append(f"- Routing OK: {run.routing_ok} (tag `{run.routing.get('question_tag')}`)")
        lines.append(f"- Pipeline: `{run.pipeline_step}` | facts: {run.fact_count} | limitations: {run.limitation_count}")
        lines.append(f"- Grounding OK: {run.grounding_ok} | citations: {run.citation_count}")
        lines.append(f"- Timing ms: {run.timing_ms}")
        if run.structural_issues:
            lines.append("- Structural issues:")
            for issue in run.structural_issues:
                lines.append(f"  - {issue}")
        if run.qualitative_notes:
            lines.append("- Notes:")
            for n in run.qualitative_notes:
                lines.append(f"  - {n}")
    lines.append("")
    lines.append("## Analyst scorecard (fill after live run — see docs/AMI_BENCHMARK_EVALUATION.md)")
    lines.append("")
    lines.append("| ID | Q1 Direct | Q2 Specific | Q3 Insight | Q4 Why | Q5 Trade-offs | Q6 Non-generic | Q7 Coherent | Q8 Actionable | Overall Y/P/N |")
    lines.append("|----|-----------|-------------|------------|--------|---------------|----------------|-------------|---------------|---------------|")
    for run in report.runs:
        lines.append(
            f"| {run.benchmark_id} | | | | | | | | | |"
        )
    lines.append("")
    lines.append("_Root cause + single lever changed this iteration:_")
    lines.append("")
    return "\n".join(lines)


def build_reasoning_laboratory_snapshot(
    *,
    question: str,
    submit_diagnostics: dict[str, Any] | None,
    brief_dict: dict[str, Any] | None,
    synthesis_diagnostics: dict[str, Any] | None,
    final_answer: str,
) -> dict[str, Any]:
    """Single JSON artifact for dev-mode inspection of one submit."""
    return {
        "question": question,
        "routing": dict(submit_diagnostics or {}),
        "portfolio_analysis_brief": brief_dict,
        "analytical_synthesis": synthesis_diagnostics,
        "final_rendered_answer": final_answer,
    }
