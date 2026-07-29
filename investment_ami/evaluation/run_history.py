"""Persist benchmark evaluation runs for longitudinal analyst-quality tracking."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Frozen baseline — change only with explicit architecture milestone + doc update.
ARCHITECTURE_BASELINE = {
    "label": "AMI analytical pipeline baseline",
    "mode_router": "p4-phase1-v2",
    "portfolio_brief": "2.1.0",
    "brief_schema": "2.1",
    "synthesis_pipeline": "phase4",
    "evaluation_process": "2026-07-28",
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _git_commit_short() -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=_repo_root(),
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return out.strip()
    except Exception:
        return "unknown"


def _prompt_version() -> str:
    try:
        from investment_ami.pipeline.synthesis_prompts import SYNTHESIS_PROMPT_VERSION

        return str(SYNTHESIS_PROMPT_VERSION)
    except ImportError:
        return "unknown"


def _index_path(eval_dir: Path) -> Path:
    return eval_dir / "benchmark_run_index.json"


def load_run_index(eval_dir: Path) -> list[dict[str, Any]]:
    path = _index_path(eval_dir)
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return list(data.get("runs") or [])
    except json.JSONDecodeError:
        return []


def save_run_index(eval_dir: Path, runs: list[dict[str, Any]]) -> None:
    eval_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "architecture_baseline": ARCHITECTURE_BASELINE,
        "runs": runs,
    }
    _index_path(eval_dir).write_text(json.dumps(payload, indent=2), encoding="utf-8")


def render_run_history_markdown(runs: list[dict[str, Any]]) -> str:
    lines = [
        "# AMI benchmark run history",
        "",
        "Longitudinal record of evaluation runs. See `docs/AMI_BENCHMARK_EVALUATION.md` for the workflow.",
        "",
        f"**Architecture baseline:** `{ARCHITECTURE_BASELINE['label']}` "
        f"(router `{ARCHITECTURE_BASELINE['mode_router']}`, brief `{ARCHITECTURE_BASELINE['portfolio_brief']}`).",
        "",
        "| Run ID | When (UTC) | Mode | Prompt | Lever | Hypothesis (short) | Structural | Cross-sim | Score summary | Artifacts |",
        "|--------|------------|------|--------|-------|-------------------|------------|-----------|---------------|-----------|",
    ]
    for row in reversed(runs[-40:]):
        hyp = str(row.get("hypothesis") or "").replace("|", "/")[:60]
        score = str(row.get("score_summary") or "—")
        struct = "OK" if row.get("structural_all_ok") else "issues"
        lines.append(
            "| {id} | {ts} | {mode} | {pv} | {lev} | {hyp} | {struct} | {sim} | {score} | `{json}` |".format(
                id=row.get("run_id", ""),
                ts=row.get("timestamp_utc", "")[:19],
                mode=row.get("synthesis_mode", ""),
                pv=row.get("prompt_version", ""),
                lev=row.get("lever_changed") or "—",
                hyp=hyp or "—",
                struct=struct,
                sim=row.get("cross_question_similarity_max", ""),
                score=score,
                json=row.get("artifact_json", ""),
            )
        )
    lines.extend(
        [
            "",
            "## How to add a run",
            "",
            "```bash",
            'python scripts/run_ami_analytical_benchmark_eval.py --hypothesis "..." --lever prompt',
            "```",
            "",
            "Optional: `--scores-file docs/eval/my_scores.json` with analyst Q1–Q8 per benchmark.",
            "",
        ]
    )
    return "\n".join(lines)


def record_benchmark_run(
    report: Any,
    *,
    eval_dir: Path | None = None,
    hypothesis: str = "",
    lever_changed: str = "",
    notes: str = "",
    scores: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Archive report JSON/Markdown under ``docs/eval/runs/`` and append to the run index.
    """
    root = _repo_root()
    eval_dir = eval_dir or (root / "docs" / "eval")
    runs_dir = eval_dir / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc)
    run_id = now.strftime("%Y%m%dT%H%M%SZ")
    mode = str(getattr(report, "synthesis_mode", "") or "unknown")
    pv = _prompt_version()
    stem = f"{run_id}_{mode}_{pv}"

    report_dict = report.to_dict() if hasattr(report, "to_dict") else dict(report)
    meta = {
        "run_id": run_id,
        "timestamp_utc": now.isoformat(),
        "architecture_baseline": ARCHITECTURE_BASELINE,
        "prompt_version": pv,
        "git_commit": _git_commit_short(),
        "synthesis_mode": mode,
        "hypothesis": hypothesis.strip(),
        "lever_changed": lever_changed.strip(),
        "notes": notes.strip(),
        "cross_question_similarity_max": report_dict.get("cross_question_similarity_max"),
        "cross_question_similarity_pair": report_dict.get("cross_question_similarity_pair"),
        "structural_all_ok": all(
            not (r.get("structural_issues") or []) for r in (report_dict.get("runs") or [])
        ),
        "scores": scores or {},
        "score_summary": _summarize_scores(scores),
    }
    payload = {"meta": meta, "report": report_dict}

    json_name = f"{stem}.json"
    json_path = runs_dir / json_name
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    from investment_ami.evaluation.benchmark_eval import format_report_markdown

    md_body = format_report_markdown(report)
    if hypothesis:
        md_body = f"**Hypothesis:** {hypothesis}\n\n**Lever changed:** {lever_changed or '—'}\n\n{md_body}"
    md_name = f"{stem}.md"
    (runs_dir / md_name).write_text(md_body, encoding="utf-8")

    meta["artifact_json"] = f"runs/{json_name}"
    meta["artifact_md"] = f"runs/{md_name}"

    index = load_run_index(eval_dir)
    index.append({k: v for k, v in meta.items() if k != "scores"})
    save_run_index(eval_dir, index)
    (eval_dir / "BENCHMARK_RUN_HISTORY.md").write_text(
        render_run_history_markdown(index),
        encoding="utf-8",
    )
    return meta


def _summarize_scores(scores: dict[str, Any] | None) -> str:
    if not scores:
        return ""
    totals: list[float] = []
    for bid in ("B1", "B2", "B3", "B4", "B5", "B6"):
        block = scores.get(bid)
        if not isinstance(block, dict):
            continue
        vals = [float(block[k]) for k in block if k.startswith("Q") and _is_num(block[k])]
        if vals:
            totals.append(sum(vals) / len(vals))
    if not totals:
        overall = scores.get("overall")
        return str(overall) if overall else ""
    return f"avg Q {sum(totals)/len(totals):.2f} ({len(totals)} benches)"


def _is_num(val: Any) -> bool:
    try:
        float(val)
        return True
    except (TypeError, ValueError):
        return False
