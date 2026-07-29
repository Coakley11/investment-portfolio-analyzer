#!/usr/bin/env python3
"""Run AMI analytical benchmark evaluation and write a report."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from investment_ami.evaluation.benchmark_eval import format_report_markdown, run_benchmark_evaluation
from investment_ami.evaluation.run_history import record_benchmark_run


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate AMI analytical synthesis benchmarks (evaluation-driven workflow)."
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Set INVESTMENT_AMI_SYNTHESIS_MOCK=1 and INVESTMENT_AMI_ANALYTICAL_SYNTHESIS=1",
    )
    parser.add_argument(
        "--hypothesis",
        type=str,
        default="",
        help='Scientific hypothesis: "I believe changing X will improve Y because..."',
    )
    parser.add_argument(
        "--lever",
        type=str,
        default="",
        choices=["", "prompt", "fact_use", "grounding", "brief", "architecture", "baseline"],
        help="Single lever changed this iteration (or baseline for first recorded run).",
    )
    parser.add_argument(
        "--notes",
        type=str,
        default="",
        help="Optional notes (e.g. revert decision, reviewer).",
    )
    parser.add_argument(
        "--scores-file",
        type=Path,
        default=None,
        help="JSON file with analyst scorecard Q1–Q8 per B1–B6 after live review.",
    )
    parser.add_argument(
        "--out-json",
        type=Path,
        default=ROOT / "docs" / "eval" / "ami_analytical_benchmark_latest.json",
    )
    parser.add_argument(
        "--out-md",
        type=Path,
        default=ROOT / "docs" / "eval" / "ami_analytical_benchmark_latest.md",
    )
    args = parser.parse_args()

    if args.mock:
        os.environ["INVESTMENT_AMI_ANALYTICAL_SYNTHESIS"] = "1"
        os.environ["INVESTMENT_AMI_SYNTHESIS_MOCK"] = "1"
    elif os.environ.get("INVESTMENT_AMI_ANALYTICAL_SYNTHESIS") != "1":
        print(
            "Tip: pass --mock for CI-style structural eval, or set "
            "INVESTMENT_AMI_ANALYTICAL_SYNTHESIS=1 + OPENAI_API_KEY for live eval."
        )

    scores: dict | None = None
    if args.scores_file and args.scores_file.is_file():
        scores = json.loads(args.scores_file.read_text(encoding="utf-8"))

    report = run_benchmark_evaluation(synthesis_mode="mock" if args.mock else "live")
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    md = format_report_markdown(report)
    if args.hypothesis:
        md = (
            f"**Hypothesis:** {args.hypothesis}\n\n"
            f"**Lever:** {args.lever or '—'}\n\n"
            f"{md}"
        )
    args.out_md.write_text(md, encoding="utf-8")

    meta = record_benchmark_run(
        report,
        hypothesis=args.hypothesis or "Baseline / exploratory run (no hypothesis recorded).",
        lever_changed=args.lever or ("baseline" if not args.hypothesis else ""),
        notes=args.notes,
        scores=scores,
    )
    print(md)
    print(f"\nWrote latest: {args.out_json} and {args.out_md}")
    print(f"Archived run {meta['run_id']} -> docs/eval/{meta['artifact_json']}")
    print("Updated docs/eval/BENCHMARK_RUN_HISTORY.md and benchmark_run_index.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
