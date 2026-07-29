# AMI analytical benchmark evaluation

Improve synthesis **from observed answers**, not speculative architecture changes.

## Architecture baseline (stable)

The pipeline below is **frozen** unless benchmark evidence proves a fundamental gap:

| Component | Version / ID |
|-----------|----------------|
| Mode router | `p4-phase1-v2` |
| PortfolioAnalysisBrief | `2.1.0` (schema `2.1`) |
| Analytical synthesis | Phase 4; prompt `SYNTHESIS_PROMPT_VERSION` |
| Evaluation | B1–B6 + reasoning laboratory |

Progress = iterative refinement, not redesign. Each archived run stores `architecture_baseline` in `docs/eval/benchmark_run_index.json`.

## Scientific optimization loop

Every change needs a **hypothesis** before re-run:

> *I believe changing **X** will improve **Y** because …*

1. Run benchmark suite (live for quality; `--mock` for CI structure).  
2. Review analyst scorecards (Q1–Q8).  
3. Identify lowest scores → **root cause**.  
4. Change **exactly one lever** (priority: prompt → fact use → grounding → brief → architecture).  
5. Re-run with `--hypothesis` and `--lever`; optional `--scores-file`.  
6. Compare to previous run in `docs/eval/BENCHMARK_RUN_HISTORY.md`.  
7. **Keep** if quality improves; **revert** if not (note in `--notes`).

## Benchmark run history

Each run archives to `docs/eval/runs/` and updates:

- `docs/eval/benchmark_run_index.json`  
- `docs/eval/BENCHMARK_RUN_HISTORY.md`

```bash
python scripts/run_ami_analytical_benchmark_eval.py \
  --hypothesis "Question_tag rubrics will improve Q1 on B2 because ..." \
  --lever prompt \
  --scores-file docs/eval/scorecard_live.json
```

Optional scores JSON: per `B1`…`B6` keys with `Q1`…`Q8` (1–5) and optional `overall`.

## North star (the only metric that matters)

Structural checks (routing, grounding pass, citation count) are **guardrails**, not success.

Success is when a user reads the response and thinks:

> *This feels like an experienced investment professional analyzed my portfolio.*

Every iteration should make the **analysis itself** noticeably better—not the elegance of the prompt or the complexity of the system.

**Treat the current architecture as stable** unless live benchmark evidence shows something fundamental is missing.

---

## Run the benchmark harness

**Structural + routing (CI / no API key):**

```bash
python scripts/run_ami_analytical_benchmark_eval.py --mock
```

**Live analyst-quality review:**

```powershell
$env:INVESTMENT_AMI_ANALYTICAL_SYNTHESIS="1"
$env:OPENAI_API_KEY="sk-..."
# Do not set INVESTMENT_AMI_SYNTHESIS_MOCK
python scripts/run_ami_analytical_benchmark_eval.py
```

Reports:

- `docs/eval/ami_analytical_benchmark_latest.json`
- `docs/eval/ami_analytical_benchmark_latest.md`

Copy reports to dated files after each live run (e.g. `ami_analytical_benchmark_2026-07-28_live.md`) so scores and answers are comparable across prompt versions.

---

## Benchmarks (B1–B6)

Shared context: `IPA_BENCH_EVAL_CONTEXT` in `investment_ami/evaluation/benchmark_suite.py` (55% VOO / 45% BND + health + macro).

| ID | Question | Expected tag |
|----|----------|--------------|
| B1 | Critique as institutional PM | `critique` |
| B2 | Five biggest risks | `ranked_risks` |
| B3 | Argue against | `devils_advocate` |
| B4 | Ray Dalio lens | `philosophy_lens` |
| B5 | vs university endowment | `peer_compare` |
| B6 | Inflation elevated 5y — changes | `conditional_macro` |

---

## Analyst scorecard (live responses only)

Score each benchmark **1–5** (1 = poor, 5 = excellent). Add one sentence of evidence per row.

| Question | What you're judging |
|----------|---------------------|
| **Q1. Direct answer** | Did it directly answer the question asked? |
| **Q2. Portfolio-specific** | Did it make observations tied to *this* portfolio (holdings, sleeves, facts)? |
| **Q3. Non-obvious insight** | Did it surface insights the user might not have thought of immediately? |
| **Q4. Why, not just what** | Did it explain reasoning, not only list metrics or labels? |
| **Q5. Trade-offs & uncertainty** | Did it discuss trade-offs and uncertainty (including brief limitations)? |
| **Q6. Non-generic** | Did it avoid advice that could apply to any portfolio without change? |
| **Q7. Coherence** | Did it read coherently from beginning to end (one thread, not boilerplate)? |
| **Q8. Actionable credibility** | Would you *consider* acting on this analysis (not “follow orders,” but trust the reasoning)? |

**Initial bar:** median ≥ **4** on Q1, Q2, Q4, Q7 across B1–B6; no benchmark below **3** on Q1 or Q7.

**Overall pass (human judgment):** Would you describe this answer as “an experienced investment professional analyzed my portfolio”? Yes / Partial / No.

---

## Before changing anything: root cause

If any score is ≤ 3, write **one paragraph**:

1. What failed (quote the answer + benchmark ID).  
2. What the model had available (check reasoning laboratory: facts used vs ignored).  
3. **Root cause hypothesis** (pick primary):

| Hypothesis | Typical signal |
|------------|----------------|
| **Prompt** | Wrong structure, generic tone, ignored question_tag, didn’t use facts in brief |
| **Fact use** | Facts existed in brief but answer ignored them (prompt or input layout) |
| **Grounding** | Wrong numbers, invented holdings, invalid citations |
| **Brief gap** | Answer needed a fact that truly wasn’t in `facts` / `limitations` (name the missing `fact_id` you wanted) |
| **Architecture** | Rare: routing wrong, brief not built, synthesis not invoked |

Only then apply a fix using the **lever order** below—**one lever per iteration**.

---

## Lever order (strict priority)

1. **Prompt improvement** — question_tag rubrics, tone, fact-use instructions, anti-generic rules.  
2. **Better use of existing facts** — input shaping, summaries highlighted in user prompt, without new brief fields.  
3. **Grounding / validation** — citation requirements, fail-soft messaging, stricter checks.  
4. **PortfolioAnalysisBrief enhancements** — **only** when root cause is a documented missing fact.  
5. **Architecture changes** — **only** if benchmark evidence shows the pipeline cannot deliver (e.g. systematic routing failure).

Do **not** expand the brief or the system because a response “feels thin” if the brief already contained usable facts the model skipped.

---

## Symptom → first lever (quick reference)

| Observation | Try first (lever #) |
|-------------|---------------------|
| Same outline for every question | 1 Prompt (`question_tag` rubric) |
| B2 ≠ five distinct risks | 1 Prompt |
| B4/B5 costume philosophy / endowment | 1 Prompt + 2 cite existing macro/allocation facts |
| B6 ignores inflation conditional | 1 Prompt + 2 `scenario.summary` / macro facts in prompt emphasis |
| Generic “diversify / talk to advisor” | 1 Prompt denylist |
| Good prose, wrong numbers | 3 Grounding, then 1 Prompt cite rules |
| Correct facts in brief, unused in answer | 2 Fact use in prompt / input |
| Repeated “I don’t know X” and X absent from brief | 4 Brief (named gap only) |

Prompt version: `SYNTHESIS_PROMPT_VERSION` in `investment_ami/pipeline/synthesis_prompts.py` — bump when prompt text changes.

---

## Developer mode: reasoning laboratory

After an analytical submit (dev tools on), sidebar **“AMI reasoning laboratory”**:

1. Routing  
2. PortfolioAnalysisBrief  
3. Synthesis (prompts, input, raw, parsed, citations, timing, tokens, grounding)  
4. Final rendered answer  

Use the laboratory to **verify root cause** before changing prompt vs brief.

---

## Iteration loop

1. Live benchmark run → save dated report + laboratory JSON per benchmark if needed.  
2. Fill **analyst scorecard** + overall pass judgment.  
3. For lowest scores, write **root cause** paragraph.  
4. Apply **one** change at the top applicable lever (1→5).  
5. Re-run → compare scores and side-by-side answers.  

Goal: each cycle improves what the user **reads**, not what the repo **contains**.
