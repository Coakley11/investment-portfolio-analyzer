# Investment date range / horizon audit (2026-06-07)

**Scope:** Code-level audit only — no formula changes. Clarifies what controls mean today and proposed UI wording.

## Two different concepts (currently conflated in UI)

| Concept | Current controls | Meaning |
|---------|------------------|---------|
| **Historical lookback** | Sidebar `analysis_start_date` / `analysis_end_date` (defaults: 5 years ago → today) | Window of **past market data** used to estimate return, volatility, correlations, drawdown, Sharpe, efficient frontier inputs |
| **Forward investment horizon** | Monte Carlo slider `Forward projection horizon (years)`; beginner goal wizard `Years until you need the money`; planning tab sliders | **Future** projection length — how far ahead to simulate growth / plan contributions |

Users asking “I want to invest for 10 years” may set lookback dates incorrectly unless we label them separately.

---

## Section-by-section

### Overview / Portfolio summary metrics

| Item | Historical or forward? | Date control | Macro effect |
|------|------------------------|--------------|--------------|
| Annual return, volatility, Sharpe, max drawdown | **Historical** over lookback | `analysis_start_date` → `analysis_end_date` | **No** — uses price history only |
| Growth chart / benchmark comparison | **Historical** | Same lookback | **No** |
| Dollar allocation tables | **Current weights** | N/A (uses sidebar portfolio value) | **No** |

**User should set:** lookback start/end for “use this much history to describe the portfolio.”  
**Proposed labels:** `Historical lookback start` / `Historical lookback end` + caption: “Used for return, volatility, Sharpe, and correlations.”

### Portfolio Health

| Item | Historical or forward? | Date control | Macro effect |
|------|------------------------|--------------|--------------|
| Headline return/vol in health tables | **Historical** (lookback) | Lookback dates | **No** on headline metrics |
| Health score / stress framing | **Forward-leaning interpretation** | Lookback for base stats | **Yes** — macro scenario inputs adjust health score and narrative |
| Optimizer suggestion | Mixed | Lookback for cov/returns; macro for forward stress | **Yes** on health score path |

**User should set:** lookback for historical base; macro panel for “what environment are we in?”  
**Proposed copy:** “Historical return/volatility below use the selected lookback period. Health score and forward stress also use macro assumptions.”

### Efficient Frontier

| Item | Historical or forward? | Date control | Macro effect |
|------|------------------------|--------------|--------------|
| Frontier points, recommended mix along frontier | **Historical** | Lookback dates (mean returns + cov from daily returns in window) | **No** on geometry; macro not in frontier math today |

**User should set:** lookback wide enough for stable cov estimates (often 3–10 years).  
**Proposed caption:** “Built from historical returns and correlations over the selected lookback period.”

### Monte Carlo

| Item | Historical or forward? | Date control | Macro effect |
|------|------------------------|--------------|--------------|
| Simulated paths | **Forward projection** | `Forward projection horizon (years)` slider (Overview/advanced MC section) | **Partial** — assumptions mode; macro can influence forward return assumptions in MC panel |
| Volatility/return inputs to MC | **Historical baseline** | Lookback dates feed underlying analytics load | Indirect |

**User should set:** lookback for historical vol/return inputs; **separate** horizon slider for “project next N years.”  
**Proposed labels:** keep MC slider as `Investment horizon (years)`; do not use lookback dates as forward horizon.

### Optimizer (Portfolio Health optimizer / guided adjustment)

| Item | Historical or forward? | Date control | Macro effect |
|------|------------------------|--------------|--------------|
| Suggested weights | **Historical** inputs + health objective | Lookback | **Yes** via health/macro path for scoring, not for raw return series |

### Recommendations / Rebalancing

| Item | Historical or forward? | Date control | Macro effect |
|------|------------------------|--------------|--------------|
| Action cards, rebalance deltas | **Based on last health/analytics run** | Whatever lookback was active at Analyze/Health time | **Yes** if health run used macro-adjusted score |

### Beginner mode

Same engine as Advanced: lookback dates in sidebar (may be hidden/simplified). Goal cards use **horizon slider** (`Years until you need the money`) for **recommended preset** — that is a **planning horizon**, not the historical lookback.  
**Risk:** beginner sets goal horizon thinking it changes charts; it mainly affects goal recommendation preset unless they also change lookback.

---

## What “expected return / volatility” means today

- **Not** “next 1 year forward” by default.
- **Is** annualized statistics from **daily returns between lookback start and end** for current holdings.
- **Not** fixed 1y/5y/10y unless user sets lookback to that window.
- **Macro** adjusts health score, forward narrative, and some forward sections — **does not** rewrite historical return/vol series (per macro audit).

---

## Recommended UI wording (no formula change)

1. Rename sidebar dates → **Historical lookback start / end** with one-line help.
2. Add read-only summary under dates: “Analyzing SPY/BND from {start} to {end}.”
3. Monte Carlo / planning: **Investment horizon (years)** — never reuse lookback date pickers.
4. Per-metric footnotes on Overview: “Based on selected historical lookback and current weights.”
5. Beginner: short callout separating “How much history to analyze” vs “When you need the money.”

---

## Next step (future, not this pass)

Implement copy/label changes from `investment-ui-transparency-mockups.md` aligned with this audit.
