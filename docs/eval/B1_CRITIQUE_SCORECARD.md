# B1 — Portfolio critique / IC memo scorecard

Benchmark question (B1):

> Critique my portfolio as an institutional portfolio manager.

Context: `IPA_BENCH_EVAL_CONTEXT` in `investment_ami/evaluation/benchmark_suite.py` (55% VOO / 45% BND + health + macro).

## Human dimensions (score 1–5 each)

| Dimension | What “5” looks like |
|-----------|---------------------|
| **Depth of reasoning** | Explains mechanisms and **why**; trade-offs; alternative views; explicit uncertainty |
| **Portfolio personalization** | Names **your** holdings/sleeves; priorities reflect **this** mix, not generic advice |
| **Macro analysis** | Coherent narrative linking inflation, rates, growth, valuations, regime → **your** exposures |
| **Scenario analysis** | Named scenarios; which holdings benefit/struggle **and why** |
| **Recommendation quality** | Ranked by impact, effort, conviction; specific actions for **this** portfolio |
| **Originality** | Does not feel like a template with numbers swapped in |
| **Institutional tone** | Reads like a CIO / IC memo, not retail blog or checklist |
| **Evidence & grounding** | Claims tied to brief facts / citations; limitations acknowledged |
| **Actionability** | Clear immediate vs monitor items; credible reasoning |
| **Overall usefulness** | Would an experienced PM say this was worth their time? |

PM litmus tests (use in written evidence):

- Genuinely insightful, not obvious?
- Connects ideas into one thread?
- Prioritizes what matters most?
- Teaches something non-obvious?
- Recommendations specific to **my** portfolio?

## Iteration log

| Iter | Prompt | Hypothesis | Human median | Structural score | Keep? |
|------|--------|------------|--------------|------------------|-------|
| 0 | `p4-v2-institutional` | Baseline | _(live run pending)_ | _(live run pending)_ | — |
| 1 | `p4-v3-cio-thesis` | Mandatory `investment_thesis` + section linkage improves coherence & originality | _(fill after live run)_ | _(from JSON artifact)_ | TBD |

### Iteration 1 (prompt lever)

**Change:** `SYNTHESIS_PROMPT_VERSION` → **`p4-v3-cio-thesis`**

- JSON field `investment_thesis` + ## Investment Thesis section
- CIO through-line rules; each section ties back to thesis
- Stronger B1 critique rubric (PM quality bar)

**Run:**

```powershell
$env:INVESTMENT_AMI_ANALYTICAL_SYNTHESIS="1"
# OPENAI_API_KEY required; unset MOCK
python scripts/run_b1_critique_benchmark.py --tag iter1-p4-v3
```

Optional human scores file (`docs/eval/b1_human_scores_iter1.json`):

```json
{
  "depth_of_reasoning": 4,
  "portfolio_personalization": 4,
  "macro_analysis": 3,
  "scenario_analysis": 3,
  "recommendation_quality": 4,
  "originality": 3,
  "institutional_tone": 4,
  "evidence_grounding": 4,
  "actionability": 3,
  "overall_usefulness": 4
}
```

Re-run with `--scores-json` to attach scores to the artifact under `docs/eval/b1_runs/`.

## Automated guardrail

`compute_b1_structural_metrics()` produces a **0–1 structural score** (length, sections, holdings mentioned, scenarios, reasoning markers, citations, thesis present). It does **not** replace human judgment; use it to compare **live** A/B runs on the same portfolio context.
