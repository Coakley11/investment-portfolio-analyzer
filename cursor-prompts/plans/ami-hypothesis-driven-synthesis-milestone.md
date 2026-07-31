# AMI milestone (post–Music): hypothesis-driven synthesis

**Status:** Planned — do not implement until benchmark-driven return from Music focus.  
**Baseline frozen:** intent-first routing (`p5-intent-v1`), analytical synthesis, B1 framework, **`p4-v4-cio-depth`**.

## Problem

Current single-shot contract encourages:

`pattern → thesis → defend thesis`

Target cognitive workflow:

`observe → competing hypotheses → evaluate → reject weak → select strongest → thesis → memo`

**Root cause:** thesis-first output shape + one completion doing explore and write together (not wording alone).

## Preferred first experiment: Option B (structured single call)

Add mandatory **`hypothesis_evaluation`** (or equivalent) **before** `investment_thesis` / memo body in the JSON contract.

- Prompt + validation enforce generation order.
- Memo section order: analytical reasoning (selected path) → investment thesis → IC structure.
- Re-benchmark on **B1** vs `p4-v4-cio-depth`; keep only if thinking quality improves (not length).

**Escalation:** Option C (two-pass: workbook then memo) only for critique-style tags if B1 still shows anchoring.

## Design goals (non-negotiable)

1. **Authentic hypotheses** — Real alternatives that could change the conclusion; not checklist filler.
2. **Willing to pivot** — Architecture must allow “first instinct was wrong” when evidence supports it.
3. **Earned recommendations** — Actions follow selected hypothesis + evidence, not predetermined narrative.
4. **Hidden vs visible** — Internal structure for quality; expose reasoning trace thoughtfully (e.g. Advanced Mode / reasoning lab), not necessarily full workbook in main answer.
5. **Latency** — Option B first; two-pass only with benchmark justification.

## Concentration nuance (brief + synthesis)

Distinguish security vs factor vs sector vs geographic vs macro vs valuation vs correlation concentration; bind “binding issue” to evidence, not largest-weight heuristic.

## Out of scope for this milestone

- More prompt-only iterations on v4/v5 adjectives.
- New routing infrastructure unless eval proves a gap.
- Longer memos or more sections for their own sake.

## Return checklist

1. Re-run B1 on deployed **`p4-v4-cio-depth`**; confirm keep/revert vs v3 (scorecard in `docs/eval/B1_CRITIQUE_SCORECARD.md`).
2. Spec JSON schema + validation + render for Option B.
3. One hypothesis recorded; one lever changed; compare B1 only.
4. Update `SYNTHESIS_PROMPT_VERSION` / diagnostics; document in benchmark run history.
