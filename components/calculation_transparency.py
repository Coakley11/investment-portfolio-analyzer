"""Advanced-mode methodology documentation for quantitative metrics."""

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

**Other columns in the health table**

- **Recommended (%)** — from the recommendation engine's type mix when available.
- **Optimizer (%)** — max-Sharpe weights when "Include optimizer in drift analysis" is on.

**Pre-investment:** With no deployed capital, the app labels this **Suggested Allocation Adjustment** rather than rebalancing.
"""

FORWARD_RETURN = """
**Forward expected return** (portfolio level):

`adjusted_return = historical_annual_return + ret_shift`

where `ret_shift` is the sum of allocation-weighted effects from:

- Rate environment (Falling / Rising / High / Stable)
- Inflation category (High / Moderate / Low / Deflation)
- Valuation (Cheap → Bubble-like)
- Economic regime (Expansion, Recession, Stagflation, etc.)
- Recession probability (0–100%): additional equity/bond/T-Bill shifts

Optional overrides replace or blend equity/bond returns or inflation/volatility numerically.

**Per-asset means** for optimizer/Monte Carlo: historical daily means × 252, plus `type_shifts` by asset type.
"""

INFLATION = """
**Inflation assumptions**

- **Category "High Inflation":** Reduces returns on bonds and equity, boosts T-Bills/real assets; `vol_mult ×= 1.28`.
- **Numeric override** (if > 4%): `inflation_excess = min(8%, override − 4%)` then  
  `adj_return −= inflation_excess × (1.20×bonds + 1.50×long_duration_bonds)` and  
  `adj_vol ×= 1 + 1.5 × inflation_excess`.

**Projected value** uses the inflation-adjusted `adjusted_return` in a deterministic compound formula (not Monte Carlo).
Real (inflation-adjusted) wealth is not separately modeled unless you lower return assumptions manually.
"""

FORWARD_VOLATILITY = """
**Forward volatility:**

`adjusted_volatility = max(0.001, historical_volatility × vol_mult)`

`vol_mult` is the product of multipliers from rate environment, inflation, valuation, regime, and recession probability  
(`vol_mult ×= 1 + recession_prob × 0.75`).

**Covariance for optimizer:** `adjusted_cov = historical_cov × (vol_scale²) × corr_stress`  
where `vol_scale = adjusted_vol / historical_vol` and `corr_stress = 1 + recession_prob × 0.30`.

Override volatility, if set, replaces `adjusted_volatility` directly.
"""

FORWARD_PROJECTED_VALUE = """
**Forward projected value** — deterministic, **not** Monte Carlo:

`projected_value = initial_value × (1 + adjusted_return) ^ years`

Uses macro-adjusted return and the horizon slider on the Forward Macro tab. This is a single-path compound growth estimate, not CAGR from simulated paths.
"""

FORWARD_DRAWDOWN = """
**Forward max drawdown:**

`adjusted_max_drawdown = historical_max_drawdown × drawdown_mult`

where `drawdown_mult = 1 + recession_probability × 0.90`.

Historical drawdown comes from the loaded price history of your current weights. It is **scaled**, not re-simulated under macro scenarios.
"""

FORWARD_SHARPE = """
**Forward Sharpe ratio:**

`adjusted_sharpe = (adjusted_return − risk_free_rate) / adjusted_volatility`

- **Risk-free rate:** Sidebar slider (same as historical Sharpe).
- **Return and volatility** both use macro-adjusted values above.
"""

OPTIMIZER = """
**Method:** Long-only **mean-variance** optimization with **SciPy `minimize` (SLSQP)**.

| Objective | Minimizes |
|-----------|-----------|
| Max Sharpe | `−(μ_p − r_f) / σ_p` |
| Min volatility | `σ_p` |

**Inputs:** Expected return vector `μ` and covariance `Σ` (annualized: daily mean × 252, daily cov × 252).  
Forward mode uses `adjusted_mean_returns` and `adjusted_cov` from macro projection.

**Portfolio stats:** `μ_p = w·μ`, `σ_p = √(wᵀ Σ w)`.

**Constraints:** Weights sum to 1; each weight ∈ [0, 1]. No sector caps beyond bond-min in health (optimizer itself is unconstrained except long-only).

**Recommendations:** Separate rule engine (`recommend_portfolio` / health evaluation); optimizer weights are optional drift reference only.
"""

EFFICIENT_FRONTIER = """
**Efficient frontier:** For each target return on a grid from min to max asset expected return, solve:

- Minimize `σ_p` subject to `w·μ = target`, `Σw = 1`, `w ≥ 0`.

Same SLSQP solver as the optimizer. Frontier points failing convergence are skipped.
"""

FUTURE_IMPROVEMENTS = """
**Simplified assumptions (future improvements)**

- Forward metrics are single-scenario adjustments, not a full macro simulation.
- Drawdown is scaled from history, not estimated from forward volatility.
- Correlation stress is a scalar multiplier, not a regime-dependent correlation matrix.
- Optimizer uses point estimates of μ and Σ without estimation error or robust optimization.
- No transaction costs, taxes, or rebalancing frictions in allocation guidance.
"""


def render_methodology_expander(title: str, body: str, *, expanded: bool = False, key: str | None = None) -> None:
    with st.expander(title, expanded=expanded):
        st.markdown(body.strip())


def render_how_calculated_section(topic: str, *, expanded: bool = False) -> None:
    """Render 'How These Numbers Are Calculated' for a given analytics topic."""
    topics = {
        "drift": ("Drift score & rebalancing", DRIFT_SCORE + "\n\n---\n\n" + REBALANCING),
        "forward_return": ("Forward expected return", FORWARD_RETURN),
        "forward_volatility": ("Forward volatility", FORWARD_VOLATILITY),
        "forward_sharpe": ("Forward Sharpe ratio", FORWARD_SHARPE),
        "forward_drawdown": ("Forward max drawdown", FORWARD_DRAWDOWN),
        "forward_projected": ("Forward projected value", FORWARD_PROJECTED_VALUE),
        "inflation": ("Inflation effects", INFLATION),
        "optimizer": ("Optimizer results", OPTIMIZER),
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


def render_methodology_footer() -> None:
    render_methodology_expander("Future model improvements", FUTURE_IMPROVEMENTS, expanded=False)
