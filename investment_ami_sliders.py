"""Phase 2c assumption sliders — question → assumption → updated AMI analysis."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

_SLIDER_PROBLEM_TYPES = frozenset(
    {
        "scenario_stress",
        "macro_rates",
        "macro_recession",
        "allocation_recommendation",
        "rebalance_allocation",
    }
)


@dataclass(frozen=True)
class SliderSpec:
    key: str
    label: str
    kind: str  # int_slider, float_slider, select_slider
    default: Any
    minimum: Any | None = None
    maximum: Any | None = None
    step: Any | None = None
    options: tuple[str, ...] = ()
    help_text: str = ""
    format_fn: Callable[[Any], str] | None = None


def resolve_problem_type(insight_data: dict[str, Any]) -> str:
    pt = str(insight_data.get("problem_type") or "").strip()
    if pt:
        return pt
    kn = insight_data.get("key_numbers")
    if isinstance(kn, dict):
        pt = str(kn.get("problem_type") or "").strip()
        if pt:
            return pt
    return ""


def _holdings_from_insight(insight_data: dict[str, Any]) -> list[tuple[str, float]]:
    kn = insight_data.get("key_numbers")
    if isinstance(kn, dict):
        hw = kn.get("holdings_weights")
        if isinstance(hw, dict) and hw:
            rows = []
            for t, w in hw.items():
                try:
                    rows.append((str(t).upper(), float(w)))
                except (TypeError, ValueError):
                    pass
            if rows:
                return sorted(rows, key=lambda x: x[1], reverse=True)
        recs = kn.get("recommendations")
        if isinstance(recs, list) and recs:
            rows = []
            for r in recs:
                if isinstance(r, dict) and r.get("ticker"):
                    try:
                        rows.append((str(r["ticker"]).upper(), float(r.get("weight_pct") or 0)))
                    except (TypeError, ValueError):
                        pass
            if rows:
                return sorted(rows, key=lambda x: x[1], reverse=True)
    return []


def slider_specs_for(problem_type: str, insight_data: dict[str, Any]) -> list[SliderSpec]:
    pt = str(problem_type or "").strip()
    if pt == "scenario_stress":
        return [
            SliderSpec(
                key="tech_drawdown_pct",
                label="Tech decline (%)",
                kind="int_slider",
                default=20,
                minimum=10,
                maximum=50,
                step=5,
                help_text="Shock size applied to direct + embedded technology exposure.",
            ),
        ]
    if pt == "macro_rates":
        return [
            SliderSpec(
                key="rate_rise_pct",
                label="Rate increase (pp)",
                kind="float_slider",
                default=2.0,
                minimum=0.0,
                maximum=5.0,
                step=0.5,
                help_text="Illustrative parallel rate rise in percentage points.",
            ),
        ]
    if pt == "macro_recession":
        return [
            SliderSpec(
                key="recession_severity",
                label="Recession severity",
                kind="select_slider",
                default="Moderate",
                options=("Mild", "Moderate", "Severe"),
                help_text="Scales earnings drag and volatility in the recession stress model.",
            ),
        ]
    if pt in ("allocation_recommendation", "rebalance_allocation"):
        specs: list[SliderSpec] = [
            SliderSpec(
                key="risk_tolerance",
                label="Risk tolerance",
                kind="select_slider",
                default="Moderate",
                options=("Conservative", "Moderate", "Aggressive"),
                help_text="Changes concentration and tech exposure comfort bands.",
            ),
        ]
        tickers = _holdings_from_insight(insight_data)
        seen: set[str] = set()
        for ticker, wt in tickers[:3]:
            if ticker in seen:
                continue
            seen.add(ticker)
            specs.append(
                SliderSpec(
                    key=f"alloc_{ticker}",
                    label=f"{ticker} target weight (%)",
                    kind="int_slider",
                    default=int(wt) if wt else 0,
                    minimum=0,
                    maximum=60,
                    step=5,
                    help_text=f"Test a new target weight for {ticker}; other sleeves renormalize to 100%.",
                )
            )
        return specs
    return []


def _severity_scale(raw: Any) -> float:
    text = str(raw or "Moderate").strip().lower()
    if "mild" in text:
        return 0.55
    if "severe" in text:
        return 1.45
    return 1.0


def parse_recession_severity(params: dict[str, Any]) -> float:
    raw = params.get("recession_severity")
    if raw in (None, ""):
        raw = params.get("recession_severity_pct")
        try:
            val = float(raw)
            return max(0.3, min(1.6, val / 100.0 if val > 3 else val))
        except (TypeError, ValueError):
            return 1.0
    return _severity_scale(raw)


def build_scenario_params_from_sliders(
    specs: list[SliderSpec],
    values: dict[str, Any],
    *,
    problem_type: str,
    weight_baseline: dict[str, float] | None = None,
) -> dict[str, Any]:
    params: dict[str, Any] = {}
    overrides: dict[str, float] = {}
    baseline = {str(k).upper(): float(v) for k, v in (weight_baseline or {}).items()}
    for spec in specs:
        val = values.get(spec.key, spec.default)
        if spec.key.startswith("alloc_") and spec.kind == "int_slider":
            ticker = spec.key.replace("alloc_", "", 1).upper()
            try:
                wt = float(val)
            except (TypeError, ValueError):
                continue
            base = baseline.get(ticker)
            if base is not None and abs(wt - base) < 0.01:
                continue
            if wt >= 0:
                overrides[ticker] = wt
            continue
        params[spec.key] = val
    if overrides:
        params["allocation_overrides"] = overrides
    if problem_type == "macro_recession":
        params["recession_severity_scale"] = parse_recession_severity(params)
    return params


def _read_slider_value(st: Any, spec: SliderSpec, current: Any) -> Any:
    key = f"ami_slider_{spec.key}"
    if spec.kind == "select_slider":
        opts = list(spec.options) or [str(spec.default)]
        idx = opts.index(current) if current in opts else (opts.index(spec.default) if spec.default in opts else 0)
        return st.select_slider(spec.label, options=opts, value=opts[idx], key=key, help=spec.help_text or None)
    if spec.kind == "float_slider":
        try:
            val = float(current)
        except (TypeError, ValueError):
            val = float(spec.default)
        return st.slider(
            spec.label,
            float(spec.minimum or 0),
            float(spec.maximum or 100),
            val,
            float(spec.step or 1),
            key=key,
            help=spec.help_text or None,
        )
    try:
        val = int(current)
    except (TypeError, ValueError):
        val = int(spec.default)
    return st.slider(
        spec.label,
        int(spec.minimum or 0),
        int(spec.maximum or 100),
        val,
        int(spec.step or 1),
        key=key,
        help=spec.help_text or None,
    )


def refresh_investment_insight_from_params(st: Any, insight_data: dict[str, Any], params: dict[str, Any]) -> bool:
    """Re-run local solver with updated scenario params and restage insight."""
    question = str(insight_data.get("question") or "").strip()
    if not question:
        return False
    try:
        from applied_math_context import build_investment_applied_math_context
        from applied_math_return_insight import build_return_insight_payload, stage_pending_insight
        from investment_ami_instant_solver import INVESTMENT_AMI_BUILD_ID, solve_instant_investment_insight
    except ImportError:
        return False

    ss = st.session_state
    ss["_ami_scenario_params"] = dict(params)
    page = str(insight_data.get("source_page") or ss.get("_ami_last_submit_source_page") or "").strip()
    ctx = build_investment_applied_math_context(page, ss)
    merged = dict(ctx.get("scenario_params") or {})
    merged.update(params)
    ctx["scenario_params"] = merged

    solved = solve_instant_investment_insight(question, ctx)
    if not solved:
        return False
    route, result = solved
    new_insight = build_return_insight_payload(
        question=question,
        source_app="investment",
        source_page=page,
        question_id=str(insight_data.get("question_id") or ""),
        route=route,
        result=result,
        full_analysis_url=str(insight_data.get("full_analysis_url") or ""),
        context=ctx,
        resume_key=str(insight_data.get("resume_key") or ""),
    )
    payload = new_insight.to_dict()
    payload["problem_type"] = str(getattr(route, "problem_type", "") or "")
    payload["experience_mode"] = str(ctx.get("experience_mode") or insight_data.get("experience_mode") or "")
    stage_pending_insight(st, payload)
    ss["_ami_investment_instant_canonical"] = {
        **dict(ss.get("_ami_investment_instant_canonical") or {}),
        "problem_type": payload["problem_type"],
        "solver_build_id": INVESTMENT_AMI_BUILD_ID,
        "analyst_sections": payload.get("analyst_sections"),
        "conclusion": payload.get("conclusion"),
    }
    return True


def render_ami_assumption_controls(st: Any, insight_data: dict[str, Any]) -> bool:
    """
    Render assumption sliders for supported problem types.
    Returns True if insight was refreshed this run.
    """
    problem_type = resolve_problem_type(insight_data)
    if problem_type not in _SLIDER_PROBLEM_TYPES:
        return False
    specs = slider_specs_for(problem_type, insight_data)
    if not specs:
        return False

    insight_id = str(insight_data.get("insight_id") or "pending")
    params: dict[str, Any] = dict(st.session_state.get("_ami_scenario_params") or {})
    applied_key = f"_ami_slider_applied_{insight_id}"

    st.markdown("**Explore assumptions**")
    exp = str(insight_data.get("experience_mode") or "").lower()
    if "beginner" not in exp:
        st.caption("Adjust an assumption to see how the analysis and recommendations change.")

    new_values: dict[str, Any] = {}
    cols = st.columns(min(len(specs), 2))
    for idx, spec in enumerate(specs):
        with cols[idx % len(cols)]:
            new_values[spec.key] = _read_slider_value(st, spec, params.get(spec.key, spec.default))

    weight_baseline = {t: w for t, w in _holdings_from_insight(insight_data)}
    merged = build_scenario_params_from_sliders(
        specs,
        new_values,
        problem_type=problem_type,
        weight_baseline=weight_baseline,
    )
    prev = st.session_state.get(applied_key)
    if prev is None:
        st.session_state[applied_key] = dict(merged)
        st.session_state["_ami_scenario_params"] = {**dict(st.session_state.get("_ami_scenario_params") or {}), **merged}
        return False
    if merged != prev:
        st.session_state[applied_key] = dict(merged)
        if refresh_investment_insight_from_params(st, insight_data, merged):
            return True
    return False
