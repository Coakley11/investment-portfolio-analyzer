#!/usr/bin/env python3
"""Run B1 portfolio critique benchmark and write scorecard + full memo artifact."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from investment_ami.evaluation.b1_critique_scorecard import (
    B1_BENCHMARK_ID,
    B1_QUESTION,
    CRITIQUE_DIMENSIONS,
    compute_b1_structural_metrics,
    empty_human_scorecard,
)
from investment_ami.evaluation.benchmark_eval import run_single_benchmark
from investment_ami.evaluation.benchmark_suite import ANALYTICAL_BENCHMARKS, IPA_BENCH_EVAL_CONTEXT
from investment_ami.pipeline.synthesis_prompts import SYNTHESIS_PROMPT_VERSION


def main() -> int:
    parser = argparse.ArgumentParser(description="B1 critique / IC memo benchmark runner.")
    parser.add_argument("--mock", action="store_true", help="Use INVESTMENT_AMI_SYNTHESIS_MOCK=1")
    parser.add_argument(
        "--tag",
        type=str,
        default="",
        help="Artifact label, e.g. baseline or p4-v3-cio-thesis",
    )
    parser.add_argument(
        "--scores-json",
        type=Path,
        default=None,
        help="Optional human 1–5 scores per dimension (JSON object).",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=ROOT / "docs" / "eval" / "b1_runs",
    )
    args = parser.parse_args()

    if args.mock:
        os.environ["INVESTMENT_AMI_ANALYTICAL_SYNTHESIS"] = "1"
        os.environ["INVESTMENT_AMI_SYNTHESIS_MOCK"] = "1"
    elif os.environ.get("INVESTMENT_AMI_ANALYTICAL_SYNTHESIS") != "1":
        print("Set INVESTMENT_AMI_ANALYTICAL_SYNTHESIS=1 or pass --mock", file=sys.stderr)

    bench = next(b for b in ANALYTICAL_BENCHMARKS if b.benchmark_id == B1_BENCHMARK_ID)
    row, diag = run_single_benchmark(bench, IPA_BENCH_EVAL_CONTEXT)
    answer = str(diag.validated_answer_markdown or "")
    parsed = diag.parsed_response if isinstance(diag.parsed_response, dict) else {}

    metrics = compute_b1_structural_metrics(
        answer_markdown=answer,
        parsed_response=parsed,
        holdings=IPA_BENCH_EVAL_CONTEXT.get("current_weights"),
        synthesis_error=str(diag.error or ""),
    )

    human = empty_human_scorecard()
    if args.scores_json and args.scores_json.is_file():
        loaded = json.loads(args.scores_json.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            for k in CRITIQUE_DIMENSIONS:
                if k in loaded:
                    human[k] = loaded[k]

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    label = args.tag or SYNTHESIS_PROMPT_VERSION
    args.out_dir.mkdir(parents=True, exist_ok=True)
    base = args.out_dir / f"b1_{label}_{stamp}"
    base.with_suffix(".md").write_text(answer, encoding="utf-8")
    artifact = {
        "benchmark_id": B1_BENCHMARK_ID,
        "question": B1_QUESTION,
        "prompt_version": SYNTHESIS_PROMPT_VERSION,
        "run_label": label,
        "timestamp_utc": stamp,
        "routing": row.routing,
        "routing_ok": row.routing_ok,
        "synthesis_enabled": row.synthesis_enabled,
        "mock_mode": diag.mock_mode,
        "error": diag.error,
        "structural_metrics": metrics.to_dict(),
        "human_scores_1_to_5": human,
        "token_usage": row.token_usage,
        "timing_ms": row.timing_ms,
    }
    base.with_suffix(".json").write_text(json.dumps(artifact, indent=2), encoding="utf-8")

    print(f"# B1 critique benchmark — {label}")
    print(f"- Prompt: `{SYNTHESIS_PROMPT_VERSION}`")
    print(f"- Routing OK: {row.routing_ok}")
    print(f"- Mock: {diag.mock_mode} | answer chars: {metrics.answer_chars}")
    print(f"- Structural score (automated guardrail): **{metrics.structural_score}**")
    for n in metrics.notes:
        print(f"- Note: {n}")
    print(f"\nWrote:\n- {base.with_suffix('.md')}\n- {base.with_suffix('.json')}")
    if metrics.mock_or_error:
        print(
            "\nHuman 1–5 critique scores require a **live** run:\n"
            "  $env:INVESTMENT_AMI_ANALYTICAL_SYNTHESIS='1'\n"
            "  # OPENAI_API_KEY set; do not set MOCK\n"
            "  python scripts/run_b1_critique_benchmark.py --tag live-iterN "
            "--scores-json docs/eval/b1_human_scores.json"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
