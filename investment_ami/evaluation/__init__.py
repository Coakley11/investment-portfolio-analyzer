"""Evaluation package for AMI analytical benchmarks."""

from investment_ami.evaluation.benchmark_eval import (
    BenchmarkEvaluationReport,
    BenchmarkRunResult,
    build_reasoning_laboratory_snapshot,
    format_report_markdown,
    run_benchmark_evaluation,
    run_single_benchmark,
)
from investment_ami.evaluation.benchmark_suite import ANALYTICAL_BENCHMARKS, IPA_BENCH_EVAL_CONTEXT

__all__ = (
    "ANALYTICAL_BENCHMARKS",
    "IPA_BENCH_EVAL_CONTEXT",
    "BenchmarkEvaluationReport",
    "BenchmarkRunResult",
    "build_reasoning_laboratory_snapshot",
    "format_report_markdown",
    "run_benchmark_evaluation",
    "run_single_benchmark",
)
