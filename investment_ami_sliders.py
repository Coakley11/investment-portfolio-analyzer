"""Phase 2c assumption sliders — question → assumption → updated AMI analysis."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

_EQUAL_REALLOC = "__equal__"
_PROPORTIONAL_REALLOC = "__proportional__"
_CASH_TICKERS = frozenset({"BIL", "SHV", "SGOV", "BILS", "TBIL"})

_SLIDER_PROBLEM_TYPES = frozenset(
    {
        "scenario_stress",
        "macro_rates",
        "macro_recession",
        "macro_inflation",
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


def _portfolio_label(rows: list[tuple[str, float]]) -> str:
    if not rows:
        return "(empty)"
    return ", ".join(f"**{t}** {p:.1f}%" for t, p in rows)


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
    if pt == "macro_inflation":
        return [
            SliderSpec(
                key="inflation_pct",
                label="Inflation assumption (%)",
                kind="int_slider",
                default=4,
                minimum=2,
                maximum=10,
                step=1,
                help_text="2% = stable; 4% = elevated; 6%+ = high inflation stress on real returns.",
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
        for ticker, wt in tickers[:4]:
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
                    help_text=f"Set a new target for {ticker}. If you reduce this sleeve, choose where the freed weight goes.",
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


def _detect_weight_reductions(
    baseline: dict[str, float],
    overrides: dict[str, float],
) -> list[tuple[str, float]]:
    """Return (ticker, freed_pct) for each sleeve reduced vs baseline."""
    cuts: list[tuple[str, float]] = []
    for ticker, new_w in overrides.items():
        sym = str(ticker).upper()
        base = baseline.get(sym, 0.0)
        if new_w < base - 0.01:
            cuts.append((sym, base - new_w))
    return cuts


def _detect_weight_increases(
    baseline: dict[str, float],
    overrides: dict[str, float],
) -> list[tuple[str, float]]:
    """Return (ticker, extra_pct) for each sleeve increased vs baseline."""
    boosts: list[tuple[str, float]] = []
    for ticker, new_w in overrides.items():
        sym = str(ticker).upper()
        base = baseline.get(sym, 0.0)
        if new_w > base + 0.01:
            boosts.append((sym, new_w - base))
    return boosts


def _funding_capacity(baseline: dict[str, float], exclude_ticker: str) -> float:
    """Total weight available from sleeves other than exclude_ticker."""
    exclude = str(exclude_ticker or "").upper()
    return sum(float(w) for t, w in baseline.items() if str(t).upper() != exclude)


def _valid_funding_source_options(
    baseline: dict[str, float],
    all_tickers: list[str],
    exclude_ticker: str,
    extra_needed: float,
) -> tuple[list[str], float]:
    """
    Funding sources that keep all sleeves >= 0%.
    Single-source options only when source weight >= extra_needed.
    """
    exclude = str(exclude_ticker or "").upper()
    total_avail = _funding_capacity(baseline, exclude)
    options: list[str] = []
    for ticker in all_tickers:
        sym = str(ticker).upper()
        if sym == exclude:
            continue
        if float(baseline.get(sym, 0.0)) >= extra_needed - 0.01:
            options.append(sym)
    for cash in sorted(_CASH_TICKERS):
        if cash in all_tickers and cash not in options and cash != exclude:
            if float(baseline.get(cash, 0.0)) >= extra_needed - 0.01:
                options.append(cash)
    if total_avail >= extra_needed - 0.01:
        options.append("Proportional distribution across other sleeves")
        options.append("Equal distribution across other sleeves")
    return options, total_avail


def _funding_source_options(all_tickers: list[str], exclude_ticker: str) -> list[str]:
    """Legacy helper — prefer _valid_funding_source_options with baseline + amount."""
    options = [t for t in all_tickers if t != exclude_ticker]
    for cash in sorted(_CASH_TICKERS):
        if cash in all_tickers and cash not in options:
            options.append(cash)
    options.append("Equal distribution across other sleeves")
    return options


def format_net_allocation_changes(
    base_rows: list[tuple[str, float]],
    prop_rows: list[tuple[str, float]],
) -> str:
    baseline = {t: p for t, p in base_rows}
    proposed = {t: p for t, p in prop_rows}
    tickers = sorted(set(baseline) | set(proposed), key=lambda t: baseline.get(t, proposed.get(t, 0)), reverse=True)
    lines: list[str] = []
    for ticker in tickers:
        delta = float(proposed.get(ticker, 0.0)) - float(baseline.get(ticker, 0.0))
        if abs(delta) < 0.01:
            lines.append(f"- **{ticker}**: 0%")
        elif delta > 0:
            lines.append(f"- **{ticker}**: +{delta:.1f}%")
        else:
            lines.append(f"- **{ticker}**: {delta:.1f}%")
    return "\n".join(lines)


def build_scenario_params_from_sliders(
    specs: list[SliderSpec],
    values: dict[str, Any],
    *,
    problem_type: str,
    weight_baseline: dict[str, float] | None = None,
    reallocations: list[dict[str, Any]] | None = None,
    increase_funding: list[dict[str, Any]] | None = None,
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
    if problem_type in ("allocation_recommendation", "rebalance_allocation"):
        params["allocation_overrides"] = dict(overrides)
        params["allocation_reallocations"] = list(reallocations or [])
        params["allocation_increase_funding"] = list(increase_funding or [])
    elif overrides:
        params["allocation_overrides"] = overrides
    if reallocations and problem_type not in ("allocation_recommendation", "rebalance_allocation"):
        params["allocation_reallocations"] = list(reallocations)
    if increase_funding and problem_type not in ("allocation_recommendation", "rebalance_allocation"):
        params["allocation_increase_funding"] = list(increase_funding)
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


def _stable_slider_scope_id(insight_data: dict[str, Any]) -> str:
    """Stable id for slider widget keys — must not change when conclusion text updates."""
    qid = str(insight_data.get("question_id") or "").strip()
    if qid:
        return qid
    return str(insight_data.get("insight_id") or "pending").strip() or "pending"


def _insight_context_from_data(insight_data: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    kn = insight_data.get("key_numbers") if isinstance(insight_data.get("key_numbers"), dict) else {}
    ctx: dict[str, Any] = {
        "experience_mode": insight_data.get("experience_mode") or "Advanced Mode",
        "scenario_params": dict(params),
        "objective": kn.get("objective") or insight_data.get("objective") or "",
        "rebalance_drift": kn.get("rebalance_drift") or insight_data.get("rebalance_drift"),
    }
    weights = kn.get("holdings_weights")
    if isinstance(weights, dict) and weights:
        ctx["current_weights"] = {str(t).upper(): float(w) for t, w in weights.items()}
    return ctx


def _refresh_via_lightweight_solver(
    insight_data: dict[str, Any],
    params: dict[str, Any],
) -> Any | None:
    """Re-solve on AMI or Investment without full applied_math_context when possible."""
    question = str(insight_data.get("question") or "").strip()
    problem_type = resolve_problem_type(insight_data)
    ctx = _insight_context_from_data(insight_data, params)
    beginner = "beginner" in str(ctx.get("experience_mode") or "").lower()

    if problem_type in ("allocation_recommendation", "rebalance_allocation"):
        from investment_ami_allocation import allocation_recommendation_answer

        return allocation_recommendation_answer(ctx, beginner=beginner, question=question)

    phase2 = {
        "scenario_stress",
        "macro_rates",
        "macro_recession",
        "macro_inflation",
        "portfolio_concentration",
        "portfolio_risk",
        "etf_overlap",
        "diversification",
        "valuation",
    }
    if problem_type in phase2:
        from investment_ami_phase2_solvers import solve_phase2_or_structured

        pair = solve_phase2_or_structured(problem_type, ctx, beginner=beginner, question=question)
        if pair:
            return pair[1]
    return None


def _stage_refreshed_insight(
    st: Any,
    *,
    insight_data: dict[str, Any],
    params: dict[str, Any],
    result: Any,
    page: str,
    route: Any | None = None,
    context: dict[str, Any] | None = None,
) -> bool:
    """Build payload from a solve result and restage without losing slider identity."""
    try:
        from applied_math_return_insight import (
            build_return_insight_payload,
            stage_pending_insight,
            store_applied_math_insight,
        )
        from investment_ami_instant_solver import INVESTMENT_AMI_BUILD_ID
    except ImportError:
        return False

    question = str(insight_data.get("question") or "").strip()
    preserved_iid = str(insight_data.get("insight_id") or "").strip()
    preserved_qid = str(insight_data.get("question_id") or "").strip()
    new_insight = build_return_insight_payload(
        question=question,
        source_app="investment",
        source_page=page,
        question_id=preserved_qid,
        route=route,
        result=result,
        full_analysis_url=str(insight_data.get("full_analysis_url") or ""),
        context=context or _insight_context_from_data(insight_data, params),
        resume_key=str(insight_data.get("resume_key") or ""),
    )
    payload = new_insight.to_dict()
    if preserved_iid:
        payload["insight_id"] = preserved_iid
    if preserved_qid:
        payload["question_id"] = preserved_qid
    payload["problem_type"] = str(
        getattr(route, "problem_type", "") or getattr(result, "problem_type", "") or resolve_problem_type(insight_data)
    )
    payload["experience_mode"] = str(
        (context or {}).get("experience_mode") or insight_data.get("experience_mode") or ""
    )
    prior_kn = insight_data.get("key_numbers") if isinstance(insight_data.get("key_numbers"), dict) else {}
    kn = dict(payload.get("key_numbers") or {})
    if isinstance(prior_kn, dict):
        if isinstance(prior_kn.get("holdings_weights"), dict):
            kn["holdings_weights"] = dict(prior_kn["holdings_weights"])
        for field in ("objective", "rebalance_drift", "problem_type"):
            if prior_kn.get(field) not in (None, "") and field not in kn:
                kn[field] = prior_kn[field]
    kn["scenario_params"] = dict(params)
    payload["key_numbers"] = kn
    payload["scenario_params"] = dict(params)
    payload["solver_build_id"] = INVESTMENT_AMI_BUILD_ID
    payload["canonical_instant"] = True
    payload["scenario_refreshed_at"] = datetime.now(timezone.utc).isoformat()
    if payload.get("problem_type") in ("allocation_recommendation", "rebalance_allocation"):
        try:
            from investment_ami_allocation import build_allocation_engine_diag

            diag_ctx = context or _insight_context_from_data(insight_data, params)
            payload["allocation_engine_diag"] = build_allocation_engine_diag(diag_ctx)
        except Exception:
            pass

    ss = st.session_state
    stage_pending_insight(st, payload)
    ss["_ami_scenario_params"] = dict(params)
    ss["_ami_force_insight_render"] = True
    ss["_ami_investment_instant_canonical"] = {
        **dict(ss.get("_ami_investment_instant_canonical") or {}),
        **payload,
        "problem_type": payload["problem_type"],
        "solver_build_id": INVESTMENT_AMI_BUILD_ID,
        "analyst_sections": payload.get("analyst_sections"),
        "conclusion": payload.get("conclusion"),
    }
    try:
        store_applied_math_insight(payload, st=st)
    except Exception:
        pass
    qid = str(preserved_qid or payload.get("question_id") or "").strip()
    if qid:
        try:
            from suite_analytical_question import sync_analytical_question_instant_insight

            sync_analytical_question_instant_insight(qid, payload)
        except Exception:
            pass
    try:
        from investment_persistent_state import notify_pending_insight_change

        notify_pending_insight_change(st, source="slider_refresh", trigger_save=True)
    except ImportError:
        pass
    return bool(payload.get("conclusion"))


def refresh_investment_insight_from_params(st: Any, insight_data: dict[str, Any], params: dict[str, Any]) -> bool:
    """Re-run local solver with updated scenario params and restage insight."""
    question = str(insight_data.get("question") or "").strip()
    if not question:
        return False

    ss = st.session_state
    page = str(insight_data.get("source_page") or ss.get("_ami_last_submit_source_page") or "").strip()
    problem_type = resolve_problem_type(insight_data)

    if problem_type in ("allocation_recommendation", "rebalance_allocation"):
        result = _refresh_via_lightweight_solver(insight_data, params)
        if result is not None:
            return _stage_refreshed_insight(
                st,
                insight_data=insight_data,
                params=params,
                result=result,
                page=page,
            )

    try:
        from applied_math_context import build_investment_applied_math_context
        from investment_ami_instant_solver import solve_instant_investment_insight

        ctx = build_investment_applied_math_context(page, ss)
        merged = dict(ctx.get("scenario_params") or {})
        merged.update(params)
        ctx["scenario_params"] = merged
        insight_ctx = _insight_context_from_data(insight_data, params)
        if insight_ctx.get("current_weights"):
            ctx["current_weights"] = dict(insight_ctx["current_weights"])
        solved = solve_instant_investment_insight(question, ctx)
        if solved:
            route, result = solved
            return _stage_refreshed_insight(
                st,
                insight_data=insight_data,
                params=params,
                result=result,
                page=page,
                route=route,
                context=ctx,
            )
    except ImportError:
        pass

    result = _refresh_via_lightweight_solver(insight_data, params)
    if result is None:
        return False
    return _stage_refreshed_insight(
        st,
        insight_data=insight_data,
        params=params,
        result=result,
        page=page,
    )


def _render_reallocation_controls(
    st: Any,
    *,
    insight_id: str,
    baseline: dict[str, float],
    overrides: dict[str, float],
    all_tickers: list[str],
) -> list[dict[str, Any]]:
    """Option B: ask where freed allocation goes when a sleeve is reduced."""
    cuts = _detect_weight_reductions(baseline, overrides)
    if not cuts:
        return []

    reallocations: list[dict[str, Any]] = []
    st.markdown("**Where should freed allocation go?**")
    st.caption("Portfolios must total 100%. Choose an explicit destination for each reduction.")

    for from_ticker, freed in cuts:
        options = [t for t in all_tickers if t != from_ticker]
        options.append("Equal distribution across remaining sleeves")
        dest_key = f"ami_realloc_dest_{insight_id}_{from_ticker}"
        widget_key = f"ami_realloc_sel_{insight_id}_{from_ticker}"
        legacy_key = f"ami_realloc_{insight_id}_{from_ticker}"

        if widget_key not in st.session_state:
            seed = st.session_state.get(dest_key) or st.session_state.get(legacy_key)
            default_idx = 0
            if seed == _EQUAL_REALLOC:
                default_idx = len(options) - 1
            elif seed in options:
                default_idx = options.index(seed)
            elif seed:
                upper = str(seed).upper()
                if upper in options:
                    default_idx = options.index(upper)
            st.session_state[widget_key] = options[default_idx]

        choice = st.selectbox(
            f"Allocate freed **{freed:.1f}%** from **{from_ticker}** to",
            options,
            key=widget_key,
        )
        to_ticker = _EQUAL_REALLOC if choice == "Equal distribution across remaining sleeves" else str(choice).upper()
        st.session_state[dest_key] = to_ticker
        reallocations.append(
            {
                "from_ticker": from_ticker,
                "amount_pct": round(freed, 2),
                "to_ticker": to_ticker,
            }
        )
    return reallocations


def _render_increase_funding_controls(
    st: Any,
    *,
    insight_id: str,
    baseline: dict[str, float],
    overrides: dict[str, float],
    all_tickers: list[str],
) -> list[dict[str, Any]]:
    """Option B mirror: ask where extra weight comes from when a sleeve is increased."""
    boosts = _detect_weight_increases(baseline, overrides)
    if not boosts:
        return []

    funding: list[dict[str, Any]] = []
    st.markdown("**Where should extra allocation come from?**")
    st.caption("Portfolios must total 100%. Choose an explicit source for each increase.")

    for to_ticker, extra in boosts:
        options, total_avail = _valid_funding_source_options(baseline, all_tickers, to_ticker, extra)
        dest_key = f"ami_fund_src_{insight_id}_{to_ticker}"
        widget_key = f"ami_fund_sel_{insight_id}_{to_ticker}"

        if total_avail + 0.01 < extra:
            st.error(
                f"This increase is too large unless multiple sleeves are reduced. "
                f"Need **{extra:.1f}%** but only **{total_avail:.1f}%** is available from other sleeves."
            )
            continue

        if not options:
            st.warning(
                f"No valid funding source for **{extra:.1f}%** to **{to_ticker}**. "
                "Lower the target weight or reduce another sleeve first."
            )
            continue

        if widget_key not in st.session_state:
            seed = st.session_state.get(dest_key)
            default_idx = 0
            if seed == _PROPORTIONAL_REALLOC:
                prop_label = "Proportional distribution across other sleeves"
                default_idx = options.index(prop_label) if prop_label in options else 0
            elif seed == _EQUAL_REALLOC:
                eq_label = "Equal distribution across other sleeves"
                default_idx = options.index(eq_label) if eq_label in options else 0
            elif seed in options:
                default_idx = options.index(seed)
            elif seed:
                upper = str(seed).upper()
                if upper in options:
                    default_idx = options.index(upper)
            st.session_state[widget_key] = options[default_idx]
        elif st.session_state[widget_key] not in options:
            st.session_state[widget_key] = options[0]

        if extra > total_avail * 0.85 and len([o for o in options if o not in (
            "Proportional distribution across other sleeves",
            "Equal distribution across other sleeves",
        )]) == 0:
            st.info(
                f"No single sleeve can fund **{extra:.1f}%** — use proportional or equal distribution."
            )

        choice = st.selectbox(
            f"Take additional **{extra:.1f}%** for **{to_ticker}** from",
            options,
            key=widget_key,
        )
        if choice == "Proportional distribution across other sleeves":
            from_ticker = _PROPORTIONAL_REALLOC
        elif choice == "Equal distribution across other sleeves":
            from_ticker = _EQUAL_REALLOC
        else:
            from_ticker = str(choice).upper()
        st.session_state[dest_key] = from_ticker
        funding.append(
            {
                "to_ticker": to_ticker,
                "amount_pct": round(extra, 2),
                "from_ticker": from_ticker,
            }
        )
    return funding


def _format_net_allocation_changes(
    baseline: dict[str, float],
    proposed: dict[str, float],
) -> str:
    tickers = sorted(set(baseline) | set(proposed), key=lambda t: baseline.get(t, proposed.get(t, 0)), reverse=True)
    lines: list[str] = []
    for ticker in tickers:
        delta = float(proposed.get(ticker, 0.0)) - float(baseline.get(ticker, 0.0))
        if abs(delta) < 0.01:
            lines.append(f"- **{ticker}**: 0%")
        elif delta > 0:
            lines.append(f"- **{ticker}**: +{delta:.1f}%")
        else:
            lines.append(f"- **{ticker}**: {delta:.1f}%")
    return "\n".join(lines)


def _preview_portfolios(
    st: Any,
    baseline: dict[str, float],
    params: dict[str, Any],
) -> None:
    try:
        from investment_ami_allocation import _apply_explicit_reallocation

        overrides = params.get("allocation_overrides") if isinstance(params.get("allocation_overrides"), dict) else {}
        realloc = params.get("allocation_reallocations") if isinstance(params.get("allocation_reallocations"), list) else []
        funding = params.get("allocation_increase_funding") if isinstance(params.get("allocation_increase_funding"), list) else []
        proposed = _apply_explicit_reallocation(baseline, overrides, realloc, funding)
        prop_rows = sorted(
            set(baseline) | set(proposed),
            key=lambda t: proposed.get(t, 0.0),
            reverse=True,
        )
        prop_rows = [(t, float(proposed.get(t, 0.0))) for t in prop_rows]
        base_rows = sorted(baseline.items(), key=lambda x: x[1], reverse=True)
        if prop_rows == base_rows:
            return
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Current portfolio**")
            st.markdown(_portfolio_label(base_rows))
        with c2:
            st.markdown("**Proposed portfolio**")
            st.markdown(_portfolio_label(prop_rows))
        net = _format_net_allocation_changes(baseline, proposed)
        if net:
            st.markdown("**Net allocation changes**")
            st.markdown(net)
        try:
            from investment_ami_allocation import format_funding_breakdown

            fb = format_funding_breakdown(baseline, overrides, params)
            if fb:
                st.markdown("**Funding breakdown**")
                st.markdown(fb)
        except ImportError:
            pass
        if any(w < -0.01 for w in proposed.values()):
            st.error("Proposed portfolio contains negative weights — adjust funding sources.")
        total = sum(proposed.values())
        if abs(total - 100) > 0.5:
            st.warning(
                f"Proposed weights sum to **{total:.1f}%** — pick sources/destinations for all allocation changes."
            )
    except ImportError:
        pass


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

    slider_scope_id = _stable_slider_scope_id(insight_data)
    params: dict[str, Any] = dict(st.session_state.get("_ami_scenario_params") or {})
    applied_key = f"_ami_slider_applied_{slider_scope_id}"

    st.markdown("**Explore assumptions**")
    exp = str(insight_data.get("experience_mode") or "").lower()
    if "beginner" not in exp:
        st.caption("Adjust assumptions to explore how recommendations and portfolio metrics change.")

    new_values: dict[str, Any] = {}
    cols = st.columns(min(len(specs), 2))
    for idx, spec in enumerate(specs):
        with cols[idx % len(cols)]:
            new_values[spec.key] = _read_slider_value(st, spec, params.get(spec.key, spec.default))

    weight_baseline = {t: w for t, w in _holdings_from_insight(insight_data)}
    alloc_specs = [s for s in specs if s.key.startswith("alloc_")]
    overrides: dict[str, float] = {}
    for spec in alloc_specs:
        val = new_values.get(spec.key, spec.default)
        ticker = spec.key.replace("alloc_", "", 1).upper()
        try:
            wt = float(val)
        except (TypeError, ValueError):
            continue
        base = weight_baseline.get(ticker)
        if base is not None and abs(wt - base) >= 0.01:
            overrides[ticker] = wt

    reallocations: list[dict[str, Any]] = []
    increase_funding: list[dict[str, Any]] = []
    if overrides and problem_type in ("allocation_recommendation", "rebalance_allocation"):
        reallocations = _render_reallocation_controls(
            st,
            insight_id=slider_scope_id,
            baseline=weight_baseline,
            overrides=overrides,
            all_tickers=list(weight_baseline.keys()),
        )
        increase_funding = _render_increase_funding_controls(
            st,
            insight_id=slider_scope_id,
            baseline=weight_baseline,
            overrides=overrides,
            all_tickers=list(weight_baseline.keys()),
        )

    merged = build_scenario_params_from_sliders(
        specs,
        new_values,
        problem_type=problem_type,
        weight_baseline=weight_baseline,
        reallocations=reallocations,
        increase_funding=increase_funding,
    )
    _preview_portfolios(st, weight_baseline, merged)

    prev = st.session_state.get(applied_key)
    if prev is None:
        st.session_state[applied_key] = dict(merged)
        st.session_state["_ami_scenario_params"] = {**dict(st.session_state.get("_ami_scenario_params") or {}), **merged}
        return False
    if merged != prev:
        if refresh_investment_insight_from_params(st, insight_data, merged):
            st.session_state[applied_key] = dict(merged)
            return True
        st.warning("Could not refresh the analysis with those allocation assumptions. Showing the last result.")
    return False
