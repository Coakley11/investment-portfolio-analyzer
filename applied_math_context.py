"""Page-specific Applied Math context extractors for Investment."""

from __future__ import annotations

from typing import Any


def cache_investment_context(session_state: dict[str, Any], ctx: dict[str, Any]) -> None:
    if ctx:
        session_state["_ami_investment_context"] = dict(ctx)


def build_investment_applied_math_context(page: str, session_state: dict[str, Any]) -> dict[str, Any]:
    tab = str(session_state.get("investment_active_tab") or page or "").strip()
    ctx: dict[str, Any] = {"page": tab}

    exp = session_state.get("investment_experience") or session_state.get("experience_mode")
    if exp:
        ctx["experience_mode"] = str(exp)

    objective = str(
        session_state.get("portfolio_objective") or session_state.get("investment_objective") or ""
    ).strip()
    if objective:
        ctx["objective"] = objective

    pv = session_state.get("sidebar_portfolio_value")
    if pv:
        try:
            ctx["portfolio_value"] = f"${int(float(pv)):,}"
        except (TypeError, ValueError):
            ctx["portfolio_value"] = str(pv)

    hr = session_state.get("health_result")
    if hr is not None:
        score = getattr(hr, "score", None) if not isinstance(hr, dict) else hr.get("score")
        if score is not None:
            ctx["health_score"] = round(float(score), 1) if isinstance(score, (int, float)) else score
        for attr, key, fmt in (
            ("expected_return", "expected_return", "{:.1f}%"),
            ("volatility", "volatility", "{:.1f}%"),
            ("sharpe", "sharpe_ratio", "{:.2f}"),
            ("max_drawdown", "max_drawdown", "{:.1f}%"),
            ("risk_level", "risk_level", "{}"),
        ):
            val = getattr(hr, attr, None) if not isinstance(hr, dict) else hr.get(attr)
            if val is not None and val != "":
                try:
                    ctx[key] = fmt.format(float(val)) if fmt != "{}" else str(val)
                except (TypeError, ValueError):
                    ctx[key] = str(val)
        ctx.setdefault(
            "context_note_historical",
            "expected_return/volatility/sharpe/max_drawdown are historical unless labeled forward",
        )

    df = session_state.get("holdings_df")
    try:
        import pandas as pd

        if isinstance(df, pd.DataFrame) and not df.empty and "Ticker" in df.columns:
            tickers = [str(t).strip() for t in df["Ticker"].dropna().tolist() if str(t).strip()]
            if tickers:
                ctx["holdings"] = tickers[:12]
            if "Weight" in df.columns:
                weights = {}
                for _, row in df.iterrows():
                    t = str(row.get("Ticker") or "").strip()
                    w = row.get("Weight")
                    if t and w is not None:
                        try:
                            weights[t] = f"{float(w):.1f}%"
                        except (TypeError, ValueError):
                            weights[t] = str(w)
                if weights:
                    ctx["current_weights"] = weights
    except Exception:
        pass

    target = session_state.get("target_weights") or session_state.get("portfolio_target_weights")
    if isinstance(target, dict) and target:
        ctx["target_weights"] = {str(k): str(v) for k, v in list(target.items())[:12]}

    drift = session_state.get("rebalance_drift") or session_state.get("_ami_rebalance_drift")
    if isinstance(drift, dict) and drift:
        ctx["rebalance_drift"] = drift

    if "macro" in tab.lower():
        ctx["workflow"] = "Macro analysis"
        try:
            from components.macro_engine import macro_assumption_summary

            macro = macro_assumption_summary()
            if macro:
                ctx["macro_summary"] = macro
                ctx["macro_outlook"] = macro
                ctx["context_note_forward"] = "Macro outlook affects forward projections and health recommendations, not historical return/volatility"
        except Exception:
            pass

    extra = session_state.get("_ami_investment_context")
    if isinstance(extra, dict):
        for k, v in extra.items():
            if v is not None and v != "":
                ctx[k] = v
    return ctx
