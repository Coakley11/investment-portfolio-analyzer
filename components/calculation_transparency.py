"""Advanced-mode methodology documentation and beginner-friendly plain-English helpers."""

from __future__ import annotations

import streamlit as st

DRIFT_SCORE = """
**Drift score (category drift)** measures how far your portfolio's **asset-type mix** is from the
**objective allocation** selected in Portfolio Health (e.g. Balanced Growth → 60% equity / 30% bonds / 10% T-Bills).

**Formula**

1. Compute category weights from holdings: `equity`, `bonds`, `tbills` (REITs count toward equity in the profile).
2. Look up objective targets from `OBJECTIVE_ALLOCATIONS` for your selected objective.
3. Per-category absolute drift: `|current_category − objective_category|`
4. **Average drift** (0–1 scale): `(eq_drift + bond_drift + tbill_drift) / 3`
5. **Objective Alignment subscore** (0–12 of 100 health points): `clip(12 − avg_drift × 30, 0, 12)`

**Not included in drift score**

- Per-ticker drift (shown separately in the rebalance table as `Drift vs Objective (%)`).
- Optimizer weights (optional second column `Drift vs Optimizer (%)` when enabled).
- Position-size weighting beyond your entered **Weight (%)** columns.

**Rebalance suggestions** compare **current weights vs objective mix** (not vs preset or optimizer by default).
Optimizer comparison is optional commentary when enabled.
"""

REBALANCING = """
**Baseline:** **Current portfolio weights** vs **objective mix** derived from your Portfolio Health objective.

**Objective per ticker:** Category targets (equity / bonds / T-Bills) are spread across holdings by asset type,
then normalized to sum to 100%.

**Suggested change:** `Change (pp) = Objective (%) − Current (%)`. Moves ≥ 1 percentage point appear in guidance.
Model notes use ±3 pp thresholds vs objective (or vs optimizer when objective drift is small).

**Pre-investment:** With no deployed capital, the app labels this **Suggested Allocation Adjustment** rather than rebalancing.
"""

FORWARD_RETURN = """
**Forward expected return** (portfolio level):

`adjusted_return = historical_annual_return + ret_shift`

where `ret_shift` is the sum of allocation-weighted effects from rate environment, inflation category,
valuation, economic regime, and recession probability.
"""

INFLATION = """
**Inflation assumptions**

- **Category "High Inflation":** Reduces returns on bonds and equity, boosts T-Bills/real assets; `vol_mult ×= 1.28`.
- **Numeric override** (if > 4%): additional bond drag and higher volatility scaling.

**Single-scenario projection** uses the inflation-adjusted `adjusted_return` in a deterministic compound formula.
Monte Carlo uses a separate simulation engine (see Monte Carlo tab).
"""

FORWARD_VOLATILITY = """
**Forward volatility:**

`adjusted_volatility = max(0.001, historical_volatility × vol_mult)`

`vol_mult` is the product of multipliers from rate environment, inflation, valuation, regime, and recession probability
(`vol_mult ×= 1 + recession_prob × 0.75`).

**Covariance for optimizer:** `adjusted_cov = historical_cov × (vol_scale²) × corr_stress`
where `vol_scale = adjusted_vol / historical_vol` and `corr_stress = 1 + recession_prob × 0.30`.
"""

FORWARD_PROJECTED_VALUE = """
### Single-Scenario Projection (deterministic)

`projected_value = initial_value × (1 + adjusted_return) ^ years`

This is **one compound-growth path** using macro-adjusted return and your horizon slider.
It is **not** a Monte Carlo median, confidence band, or probability-weighted outcome.

For a **range of outcomes**, use the **Monte Carlo** tab (percentiles, probability of loss, etc.).
"""

FORWARD_DRAWDOWN = """
### Stress-Adjusted Historical Drawdown Estimate

`adjusted_max_drawdown = historical_max_drawdown × drawdown_mult`

where `drawdown_mult = 1 + recession_probability × 0.90`.

Historical drawdown comes from loaded price history of your current weights.
The metric is **scaled** under recession stress — it is **not** a forward-simulated drawdown forecast.
"""

FORWARD_SHARPE = """
**Forward Sharpe ratio:**

`adjusted_sharpe = (adjusted_return − risk_free_rate) / adjusted_volatility`

Risk-free rate = sidebar slider (same as historical Sharpe).
Return and volatility both use macro-adjusted values above.
"""

OPTIMIZER = """
**Method:** Long-only **mean-variance** optimization with **SciPy `minimize` (SLSQP)**.

| Objective | Minimizes |
|-----------|-----------|
| Max Sharpe | `−(μ_p − r_f) / σ_p` |
| Min volatility | `σ_p` |

**Inputs:** Expected return vector `μ` and covariance `Σ` (annualized: daily mean × 252, daily cov × 252).
Forward mode uses `adjusted_mean_returns` and `adjusted_cov` from macro projection.

**Constraints:** Weights sum to 1; each weight ∈ [0, 1].
"""

OPTIMIZER_CONFIDENCE = """
### Optimizers are sensitive to assumptions

- Changing **expected returns** (historical vs forward macro) changes optimal weights.
- Changing **macro assumptions** (recession, inflation, rates) changes forward μ and Σ, which changes recommendations.
- Optimization finds a **mathematical optimum for your inputs** — not a forecast of future performance.
- There is **no confidence interval** around optimizer outputs in the current model.

Use optimizer results as **one scenario**, alongside your objective mix and qualitative judgment.
"""

EFFICIENT_FRONTIER = """
**Efficient frontier:** For each target return on a grid, minimize `σ_p` subject to `w·μ = target`, `Σw = 1`, `w ≥ 0`.
Same SLSQP solver as the optimizer.
"""

MACRO_WHY_RECESSION = """
#### Recession probability — why does this matter?

Higher recession probability in the model:

- **Lowers** expected returns (especially equity and REIT exposure)
- **Raises** portfolio volatility (`vol_mult` increases)
- **Widens** the stress-adjusted historical drawdown estimate
- **Increases** correlation stress in the covariance matrix used by optimizer and Monte Carlo (forward mode)

It does **not** predict whether a recession will occur — it stress-tests your portfolio under your assumption.
"""

MACRO_WHY_INFLATION = """
#### Inflation — why does this matter?

Higher inflation settings in the model:

- Can **hurt bonds** and long-duration assets (return drag)
- May **increase volatility** (especially in High Inflation category)
- Can **reduce real returns** unless offsets (e.g. T-Bill shifts) apply
- Feeds into forward return, volatility, and (when selected) Monte Carlo inputs

Numeric inflation overrides add extra bond drag above 4%.
"""

MACRO_WHY_RATES = """
#### Interest rates — why does this matter?

Rate environment affects the model through return shifts and volatility multipliers:

- **Rising / high rates:** Often pressure long-duration bonds and growth equities; **T-Bills** may benefit in the model
- **Falling rates:** Often help bonds; growth assets may see higher modeled returns
- **Stable rates:** Neutral baseline when unsure

Combined with inflation and recession settings, rates shape forward return, volatility, and optimization inputs.
"""

FUTURE_IMPROVEMENTS = """
### Current simplifications

- Single-scenario macro adjustments (not a full macro simulation engine)
- Drawdown = historical drawdown × stress multiplier (not forward path simulation)
- Correlation stress = scalar multiplier (not regime-dependent correlation matrix)
- No taxes, account types, or transaction costs in allocation guidance
- Optimizer uses point estimates of μ and Σ without estimation error or robust optimization
- Single-scenario forward projection is separate from Monte Carlo percentiles

### Future model improvements (possibilities)

- Regime-switching Monte Carlo
- Macro-driven return simulations with multiple scenarios
- Dynamic, state-dependent correlations
- Tax-aware and account-aware optimization
- Transaction cost and turnover modeling
- Confidence intervals and sensitivity bands around optimizer outputs
- Automated macro setting suggestions from live economic data
"""


def objective_alignment_plain_english(avg_drift: float, objective: str = "") -> str:
    """Plain-English summary of category drift vs objective (for Beginner Mode)."""
    obj = (objective or "your selected goal").replace("_", " ").strip()
    if avg_drift < 0.03:
        closeness = "close to"
    elif avg_drift < 0.06:
        closeness = "somewhat different from"
    else:
        closeness = "significantly different from"
    return (
        f"Your portfolio is **{closeness}** the allocation associated with "
        f"**{obj}**."
    )


def _is_advanced_mode() -> bool:
    return st.session_state.get("experience", "Beginner Mode") == "Advanced Mode"


def render_methodology_expander(title: str, body: str, *, expanded: bool = False, key: str | None = None) -> None:
    if not _is_advanced_mode():
        return
    with st.expander(title, expanded=expanded):
        st.markdown(body.strip())


def render_how_calculated_section(topic: str, *, expanded: bool = False) -> None:
    """Render methodology expanders — Advanced Mode only."""
    if not _is_advanced_mode():
        return
    topics = {
        "drift": ("Drift score & rebalancing", DRIFT_SCORE + "\n\n---\n\n" + REBALANCING),
        "forward_return": ("Forward expected return", FORWARD_RETURN),
        "forward_volatility": ("Forward volatility", FORWARD_VOLATILITY),
        "forward_sharpe": ("Forward Sharpe ratio", FORWARD_SHARPE),
        "forward_drawdown": ("Stress-adjusted historical drawdown", FORWARD_DRAWDOWN),
        "forward_projected": ("Single-scenario projection", FORWARD_PROJECTED_VALUE),
        "inflation": ("Inflation effects", INFLATION),
        "optimizer": ("Optimizer results", OPTIMIZER),
        "optimizer_confidence": ("Optimizer sensitivity", OPTIMIZER_CONFIDENCE),
        "frontier": ("Efficient frontier", EFFICIENT_FRONTIER),
        "macro_all": (
            "Forward macro methodology (summary)",
            FORWARD_RETURN
            + "\n\n"
            + INFLATION
            + "\n\n"
            + FORWARD_VOLATILITY
            + "\n\n"
            + FORWARD_PROJECTED_VALUE
            + "\n\n"
            + FORWARD_DRAWDOWN
            + "\n\n"
            + FORWARD_SHARPE,
        ),
    }
    label, body = topics.get(topic, ("Methodology", "Documentation not found for this topic."))
    render_methodology_expander(f"How these numbers are calculated — {label}", body, expanded=expanded)


def render_macro_why_it_matters() -> None:
    """Advanced Mode — how macro inputs affect model outputs."""
    if not _is_advanced_mode():
        return
    with st.expander("Why do these macro inputs matter?", expanded=False):
        st.markdown(MACRO_WHY_RECESSION.strip())
        st.markdown(MACRO_WHY_INFLATION.strip())
        st.markdown(MACRO_WHY_RATES.strip())
        st.caption(
            "These describe **model relationships**, not predictions. "
            "Change assumptions on this tab and re-run Forward Macro or Portfolio Health to see updated outputs."
        )


def render_optimizer_confidence() -> None:
    """Advanced Mode — optimizer sensitivity disclaimer."""
    if not _is_advanced_mode():
        return
    render_methodology_expander("Optimizer confidence & limitations", OPTIMIZER_CONFIDENCE, expanded=False)


def render_future_model_improvements(*, expanded: bool = False) -> None:
    """Dedicated Future Model Improvements section — Advanced Mode only."""
    if not _is_advanced_mode():
        return
    render_methodology_expander("Future model improvements", FUTURE_IMPROVEMENTS, expanded=expanded)


def render_methodology_footer() -> None:
    """Alias for the dedicated future-improvements section."""
    render_future_model_improvements(expanded=False)


def render_objective_alignment_summary(
    health_avg_drift: float,
    objective: str,
    *,
    show_formula: bool = True,
) -> None:
    """Plain-English alignment line; optional drift stats and formula expander (Advanced)."""
    st.markdown(objective_alignment_plain_english(health_avg_drift, objective))
    if show_formula and _is_advanced_mode():
        st.caption(
            f"Category drift (average across equity, bonds, T-Bills): "
            f"**{health_avg_drift * 100:.1f}** percentage points."
        )
        render_how_calculated_section("drift")
