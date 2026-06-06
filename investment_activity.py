"""
Command Center activity hooks for Investment Portfolio Analyzer.
"""

from __future__ import annotations

from typing import Any


def _metrics_from_session(st: Any) -> dict[str, Any]:
    objective = str(st.session_state.get("health_objective") or "").strip()
    goal = str(st.session_state.get("guide_goal_choice") or objective).strip()
    df = st.session_state.get("holdings_df")
    tickers: list[str] = []
    if df is not None and hasattr(df, "iterrows"):
        for _, row in df.iterrows():
            t = str(row.get("Ticker") or "").strip().upper()
            if t:
                tickers.append(t)
    return {
        "goal": goal,
        "objective": objective,
        "tickers": tickers,
        "holdings_count": len(tickers),
        "risk_profile": str(st.session_state.get("health_objective") or objective),
    }


def _record(
    event: str,
    *,
    st: Any,
    page: str = "",
    metrics: dict[str, Any] | None = None,
    summary: str = "",
    resume_key: str = "",
    resume_title: str = "",
    resume_subtitle: str = "",
) -> None:
    try:
        from suite_activity_client import record_activity

        base = _metrics_from_session(st)
        merged = {**base, **(metrics or {})}
        record_activity(
            "investment",
            event,
            page=page or "Investment Analytics",
            metrics=merged,
            summary=summary,
            resume_key=resume_key or "portfolio:main",
            resume_title=resume_title or "Continue portfolio review",
            resume_subtitle=resume_subtitle or merged.get("goal") or "Investment",
        )
    except Exception:
        pass


def log_goal_selected(st: Any, *, goal_title: str, objective: str = "") -> None:
    _record(
        "investment_goal_selected",
        st=st,
        page="Getting Started",
        metrics={"goal_title": goal_title, "objective": objective or goal_title},
        summary=f"Selected investment goal: {goal_title}",
    )


def log_portfolio_created(st: Any, *, preset: str = "", holdings_count: int | None = None) -> None:
    ctx = _metrics_from_session(st)
    count = holdings_count if holdings_count is not None else ctx["holdings_count"]
    _record(
        "portfolio_created",
        st=st,
        page="Portfolio Inputs",
        metrics={"preset": preset, "holdings_count": count},
        summary=f"Built portfolio with {count} holdings",
        resume_subtitle=f"{count} holdings",
    )


def log_holdings_updated(st: Any, *, tickers: list[str] | None = None) -> None:
    ctx = _metrics_from_session(st)
    tlist = tickers if tickers is not None else ctx["tickers"]
    sample = ", ".join(tlist[:6])
    if len(tlist) > 6:
        sample += f", +{len(tlist) - 6} more"
    _record(
        "holdings_updated",
        st=st,
        page="Portfolio Inputs",
        metrics={"tickers": tlist, "holdings_count": len(tlist)},
        summary=f"Updated holdings: {sample}" if sample else "Updated portfolio holdings",
    )


def _holdings_fingerprint_from_session(st: Any) -> str:
    try:
        import pandas as pd
        from components.beginner_navigation import _holdings_fingerprint

        df = st.session_state.get("holdings_df")
        if isinstance(df, pd.DataFrame) and not df.empty:
            return str(_holdings_fingerprint(df))
    except Exception:
        pass
    return ""


def log_portfolio_health_checked(
    st: Any,
    *,
    score: float,
    score_label: str,
    tickers: list[str],
) -> None:
    hfp = _holdings_fingerprint_from_session(st)
    _record(
        "portfolio_health_checked",
        st=st,
        page="Portfolio Health",
        metrics={
            "review_type": score_label,
            "score": float(score),
            "tickers": list(tickers),
            "holdings_fingerprint": hfp,
        },
        summary=f"Ran portfolio health check ({score_label})",
        resume_key="portfolio:health",
        resume_title="Continue portfolio review",
        resume_subtitle=score_label,
    )


def log_risk_profile_changed(st: Any, *, profile: str) -> None:
    _record(
        "risk_profile_changed",
        st=st,
        page="Portfolio Health",
        metrics={"risk_profile": profile, "objective": profile},
        summary=f"Risk profile: {profile.replace('_', ' ').title()}",
    )


def log_allocation_reviewed(st: Any) -> None:
    _record(
        "allocation_reviewed",
        st=st,
        page="Portfolio Health",
        summary="Reviewed allocation drift",
    )


def log_optimizer_run(st: Any) -> None:
    _record(
        "optimizer_run",
        st=st,
        page="Optimization",
        summary="Ran portfolio optimizer",
    )


def log_frontier_viewed(st: Any) -> None:
    _record(
        "frontier_viewed",
        st=st,
        page="Efficient Frontier",
        summary="Viewed efficient frontier",
    )


def log_macro_environment_applied(st: Any, *, context: str = "") -> None:
    _record(
        "macro_environment_applied",
        st=st,
        page="Macro Analysis",
        metrics={"context": context},
        summary="Applied current macro environment"
        + (f" ({context})" if context else ""),
    )


def log_scenario_run(st: Any, *, context: str = "Monte Carlo") -> None:
    _record(
        "scenario_run",
        st=st,
        page=context,
        metrics={"scenario_type": context},
        summary=f"Ran investment scenario ({context})",
    )


def log_ticker_analyzed(st: Any, *, ticker: str) -> None:
    _record(
        "ticker_analyzed",
        st=st,
        page="Portfolio Inputs",
        metrics={"ticker": ticker.upper()},
        summary=f"Analyzed ticker {ticker.upper()}",
    )


def log_rebalance_reviewed(st: Any) -> None:
    _record(
        "rebalance_reviewed",
        st=st,
        page="Rebalancing",
        summary="Reviewed rebalance guidance",
    )
