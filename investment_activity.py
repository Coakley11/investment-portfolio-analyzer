"""
Command Center activity hooks for Investment Portfolio Analyzer.

Every event says which portfolio it is about (``metrics.portfolio_kind``):

* ``real``     — the My Portfolio ledger (what you actually own: deposits, withdrawals,
                 purchases and sales you recorded). Real events never carry the
                 planning holdings.
* ``planning`` — the hypothetical portfolio in Portfolio Inputs and the analyses run on it.
                 Changing it to 100% VTI is a plan, not a purchase.

Every event also carries ``metrics.event_key``, a stable identity for the confirmed
action (a transaction id, a contribution id, a planning-allocation fingerprint + day).
Storage drops an event whose key was already recorded for the account, so reruns,
refreshes, new sessions and other devices never duplicate it.

Continue: ``track_resume_position`` keeps one "where you left off" item per account
(page + subtab + a one-line context), written only when the position changes.
"""

from __future__ import annotations

import datetime as dt
import hashlib
from typing import Any

APP = "investment"
REAL = "real"
PLANNING = "planning"

RESUME_POSITION_KEY = "portfolio:resume"
_RESUME_POS_SESSION_KEY = "_suite_inv_cc_resume_position"
_PENDING_PLANNING_KEY = "_suite_inv_cc_pending_planning"
_LAST_PLANNING_FP_KEY = "_suite_inv_cc_last_planning_fp"
_LAST_ALLOC_KEY = "_suite_inv_cc_last_alloc"

# Canonical page labels (independent of Beginner / Advanced mode) used in Continue links.
PAGE_IDS: dict[str, str] = {
    "getting_started": "Getting Started Guide",
    "overview": "Overview",
    "portfolio": "Portfolio Inputs",
    "analytics": "Portfolio Analytics",
    "health": "Portfolio Health",
    "explain": "Explain This Portfolio",
    "macro": "Forward Macro Analysis",
    "monte_carlo": "Monte Carlo",
    "optimization": "Optimization",
    "frontier": "Efficient Frontier",
    "etf_explorer": "ETF Holdings Explorer",
    "my_portfolio": "My Portfolio",
}


# ── helpers ───────────────────────────────────────────────────────────────────


def _today() -> str:
    try:
        from activity_time import to_display_local, utc_now_iso

        return to_display_local(utc_now_iso()).date().isoformat()
    except Exception:
        return dt.date.today().isoformat()


def _digest(*parts: Any) -> str:
    return hashlib.sha256("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:16]


def _money(x: float) -> str:
    return f"${x:,.2f}"


def _shares(x: float) -> str:
    try:
        import portfolio_engine as pe

        return pe.format_shares(x)
    except Exception:
        return f"{x:g} shares"


def _goal(st: Any) -> str:
    objective = str(st.session_state.get("health_objective") or "").strip()
    return str(st.session_state.get("guide_goal_choice") or objective).strip()


def planning_allocation(st: Any) -> list[tuple[str, float]]:
    """``[(ticker, weight_pct)]`` of the planning portfolio, normalized to 100."""
    df = st.session_state.get("holdings_df")
    rows: list[tuple[str, float]] = []
    if df is not None and hasattr(df, "iterrows"):
        for _, row in df.iterrows():
            t = str(row.get("Ticker") or "").strip().upper()
            if not t or t == "NAN":
                continue
            try:
                w = float(row.get("Weight (%)") or 0.0)
            except (TypeError, ValueError):
                w = 0.0
            if w != w:  # NaN
                w = 0.0
            rows.append((t, max(w, 0.0)))
    total = sum(w for _, w in rows)
    if total > 0:
        rows = [(t, w * 100.0 / total) for t, w in rows]
    return rows


def describe_allocation(alloc: list[tuple[str, float]], *, limit: int = 4) -> str:
    if not alloc:
        return "no holdings"
    parts = [f"{w:.0f}% {t}" for t, w in sorted(alloc, key=lambda x: -x[1])[:limit]]
    if len(alloc) > limit:
        parts.append(f"+{len(alloc) - limit} more")
    return ", ".join(parts)


def _planning_fp(alloc: list[tuple[str, float]]) -> str:
    return _digest(*[f"{t}:{w:.1f}" for t, w in sorted(alloc)])


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


def _planning_metrics(st: Any) -> dict[str, Any]:
    alloc = planning_allocation(st)
    objective = str(st.session_state.get("health_objective") or "").strip()
    return {
        "portfolio_kind": PLANNING,
        "goal": _goal(st),
        "objective": objective,
        "risk_profile": objective,
        "tickers": [t for t, _ in alloc],
        "holdings_count": len(alloc),
        "weights": {t: round(w, 2) for t, w in alloc},
        "allocation_label": describe_allocation(alloc),
        "holdings_fingerprint": _holdings_fingerprint_from_session(st),
    }


def _real_snapshot(transactions: list[Any]) -> dict[str, Any]:
    """Ledger-derived facts only (no live prices, no planning data)."""
    try:
        import portfolio_engine as pe

        cash = pe.compute_cash_ledger_summary(transactions)
        held: dict[str, float] = {}
        for t in transactions:
            sym = str(getattr(t, "ticker", "") or "").upper()
            if not sym:
                continue
            q = float(getattr(t, "quantity", 0.0) or 0.0)
            if t.action == "buy":
                held[sym] = held.get(sym, 0.0) + q
            elif t.action == "sell":
                held[sym] = held.get(sym, 0.0) - q
        held = {k: v for k, v in held.items() if v > 1e-12}
        return {
            "real_cash_balance": round(cash.net_cash, 2),
            "real_total_deposits": round(cash.total_deposits, 2),
            "real_tickers": sorted(held),
            "real_positions_count": len(held),
            "real_transaction_count": len(transactions),
        }
    except Exception:
        return {"real_transaction_count": len(transactions)}


def _resume_title(page: str, subtab: str = "") -> str:
    return f"{page} → {subtab}" if subtab else page


def _record(
    event: str,
    *,
    st: Any,
    kind: str,
    event_key: str,
    page: str,
    subtab: str = "",
    metrics: dict[str, Any] | None = None,
    summary: str = "",
    resume_key: str = "",
    resume_title: str = "",
    resume_subtitle: str = "",
) -> None:
    try:
        from suite_activity_client import record_activity

        base = _planning_metrics(st) if kind == PLANNING else {"portfolio_kind": REAL, "goal": _goal(st)}
        merged = {**base, **(metrics or {})}
        merged["portfolio_kind"] = kind
        merged["event_key"] = event_key
        merged["resume_page"] = page
        if subtab:
            merged["resume_subtab"] = subtab
        record_activity(
            APP,
            event,
            page=page,
            metrics=merged,
            summary=summary,
            resume_key=resume_key or RESUME_POSITION_KEY,
            resume_title=resume_title or _resume_title(page, subtab),
            resume_subtitle=resume_subtitle or summary,
        )
        st.session_state.pop(_RESUME_POS_SESSION_KEY, None)  # re-assert position after the event
    except Exception:
        pass


# ── planning portfolio (hypothetical) ─────────────────────────────────────────


def log_goal_selected(st: Any, *, goal_title: str, objective: str = "") -> None:
    """A goal the user chose (callers must not log the automatic first-render default)."""
    _record(
        "investment_goal_selected",
        st=st,
        kind=PLANNING,
        event_key=f"goal:{_digest(goal_title)}:{_today()}",
        page=PAGE_IDS["getting_started"],
        metrics={"goal_title": goal_title, "objective": objective or goal_title},
        summary=f"Set investment goal: {goal_title}",
    )


def log_portfolio_created(st: Any, *, preset: str = "", holdings_count: int | None = None) -> None:
    alloc = planning_allocation(st)
    count = holdings_count if holdings_count is not None else len(alloc)
    st.session_state[_LAST_PLANNING_FP_KEY] = _planning_fp(alloc)
    st.session_state.pop(_PENDING_PLANNING_KEY, None)
    remember_planning_baseline(st)
    _record(
        "portfolio_created",
        st=st,
        kind=PLANNING,
        event_key=f"planning_created:{_planning_fp(alloc)}:{_today()}",
        page=PAGE_IDS["portfolio"],
        metrics={"preset": preset, "holdings_count": count},
        summary=f"Built planning portfolio — {describe_allocation(alloc)}" + (f" ({preset})" if preset else ""),
    )


def remember_planning_baseline(st: Any) -> None:
    st.session_state[_LAST_ALLOC_KEY] = [list(x) for x in planning_allocation(st)]


def note_planning_edit(st: Any) -> None:
    """Holdings editor rendered: remember an edit; it is logged once confirmed."""
    alloc = planning_allocation(st)
    fp = _planning_fp(alloc)
    last = st.session_state.get(_LAST_PLANNING_FP_KEY)
    if last is None:
        st.session_state[_LAST_PLANNING_FP_KEY] = fp  # first render seeds the baseline, no event
        remember_planning_baseline(st)
        return
    if fp == last:
        st.session_state.pop(_PENDING_PLANNING_KEY, None)
        return
    pending = st.session_state.get(_PENDING_PLANNING_KEY)
    if not isinstance(pending, dict):
        pending = {"before": list(st.session_state.get(_LAST_ALLOC_KEY) or [])}
    pending["fp"] = fp
    st.session_state[_PENDING_PLANNING_KEY] = pending


def flush_planning_change(st: Any, *, reason: str = "") -> bool:
    """Log a pending planning edit as one ``holdings_updated`` (left the editor / ran an analysis)."""
    pending = st.session_state.get(_PENDING_PLANNING_KEY)
    if not isinstance(pending, dict):
        return False
    st.session_state.pop(_PENDING_PLANNING_KEY, None)
    alloc = planning_allocation(st)
    fp = _planning_fp(alloc)
    if fp == st.session_state.get(_LAST_PLANNING_FP_KEY):
        return False
    before = {str(t) for t, *_ in (pending.get("before") or [])}
    after = {t for t, _ in alloc}
    added, removed = sorted(after - before), sorted(before - after)
    detail = []
    if added:
        detail.append("added " + ", ".join(added))
    if removed:
        detail.append("removed " + ", ".join(removed))
    st.session_state[_LAST_PLANNING_FP_KEY] = fp
    remember_planning_baseline(st)
    _record(
        "holdings_updated",
        st=st,
        kind=PLANNING,
        event_key=f"planning:{fp}:{_today()}",
        page=PAGE_IDS["portfolio"],
        metrics={"added": added, "removed": removed, "confirmed_by": reason or "navigation"},
        summary=f"Updated planning portfolio — {describe_allocation(alloc)}"
        + (f" ({'; '.join(detail)})" if detail else ""),
    )
    return True


def log_holdings_updated(st: Any, *, tickers: list[str] | None = None) -> None:
    """Backward-compatible entry point: records a pending edit (never one event per keystroke)."""
    note_planning_edit(st)


def log_portfolio_health_checked(st: Any, *, score: float, score_label: str, tickers: list[str]) -> None:
    flush_planning_change(st, reason="health_check")
    hfp = _holdings_fingerprint_from_session(st)
    _record(
        "portfolio_health_checked",
        st=st,
        kind=PLANNING,
        event_key=f"health:{_digest(hfp, round(float(score), 1))}:{_today()}",
        page=PAGE_IDS["health"],
        metrics={"review_type": score_label, "score": float(score), "tickers": list(tickers)},
        summary=f"Completed portfolio health evaluation — {score_label} ({float(score):.0f})",
        resume_key="portfolio:health",
        resume_title="Review portfolio health results",
        resume_subtitle=f"{score_label} · {describe_allocation(planning_allocation(st))}",
    )


def log_risk_profile_changed(st: Any, *, profile: str) -> None:
    _record(
        "risk_profile_changed",
        st=st,
        kind=PLANNING,
        event_key=f"risk_profile:{_digest(profile)}:{_today()}",
        page=PAGE_IDS["health"],
        metrics={"risk_profile": profile, "objective": profile},
        summary=f"Changed investment strategy — {profile.replace('_', ' ').title()}",
    )


def _analysis(
    st: Any,
    event: str,
    page_id: str,
    summary: str,
    *,
    extra: dict[str, Any] | None = None,
    key: str = "",
) -> None:
    flush_planning_change(st, reason=event)
    hfp = _holdings_fingerprint_from_session(st)
    _record(
        event,
        st=st,
        kind=PLANNING,
        event_key=f"{event}:{_digest(hfp, key)}:{_today()}",
        page=PAGE_IDS[page_id],
        metrics=dict(extra or {}),
        summary=f"{summary} — {describe_allocation(planning_allocation(st))}",
    )


def log_allocation_reviewed(st: Any) -> None:
    _analysis(st, "allocation_reviewed", "health", "Reviewed allocation drift")


def log_optimizer_run(st: Any) -> None:
    _analysis(st, "optimizer_run", "optimization", "Ran portfolio optimization")


def log_frontier_viewed(st: Any) -> None:
    _analysis(st, "frontier_viewed", "frontier", "Built efficient frontier")


def log_macro_environment_applied(st: Any, *, context: str = "") -> None:
    _analysis(
        st,
        "macro_environment_applied",
        "macro",
        "Ran forward-looking macro analysis" + (f" ({context})" if context else ""),
        extra={"context": context},
        key=context,
    )


def log_scenario_run(st: Any, *, context: str = "Monte Carlo", detail: str = "") -> None:
    monte_carlo = context == "Monte Carlo"
    _analysis(
        st,
        "scenario_run",
        "monte_carlo" if monte_carlo else "analytics",
        "Ran Monte Carlo simulation" if monte_carlo else f"Ran {context}",
        extra={"scenario_type": context, "detail": detail},
        key=f"{context}:{detail}",
    )


def log_risk_analysis_run(st: Any) -> None:
    _analysis(st, "risk_analysis_completed", "analytics", "Completed portfolio risk analysis")


def log_ticker_analyzed(st: Any, *, ticker: str) -> None:
    sym = ticker.upper()
    _record(
        "ticker_analyzed",
        st=st,
        kind=PLANNING,
        event_key=f"ticker:{sym}:{_today()}",
        page=PAGE_IDS["portfolio"],
        metrics={"ticker": sym},
        summary=f"Added {sym} to the planning portfolio",
    )


def log_rebalance_reviewed(st: Any) -> None:
    _analysis(st, "rebalance_reviewed", "health", "Reviewed rebalance guidance")


# ── real portfolio (My Portfolio ledger) ──────────────────────────────────────


def log_real_transaction_recorded(st: Any, txn: Any, *, transactions_after: list[Any]) -> None:
    """One confirmed, persisted ledger transaction (deposit / withdrawal / buy / sell)."""
    action = str(getattr(txn, "action", "") or "")
    qty = float(getattr(txn, "quantity", 0.0) or 0.0)
    price = float(getattr(txn, "execution_price", 0.0) or 0.0)
    sym = str(getattr(txn, "ticker", "") or "").upper()
    txn_id = str(getattr(txn, "id", ""))
    metrics: dict[str, Any] = {
        "transaction_id": txn_id,
        "transaction_action": action,
        "transaction_date": str(getattr(txn, "date", "")),
        **_real_snapshot(transactions_after),
    }
    if action in ("cash_deposit", "cash_withdrawal"):
        amount = qty if qty > 0 else price
        metrics["amount"] = round(amount, 2)
        if action == "cash_deposit":
            event, summary = "real_cash_deposited", f"Added {_money(amount)} to real portfolio cash"
        else:
            event, summary = "real_cash_withdrawn", f"Withdrew {_money(amount)} from real portfolio cash"
    else:
        cost = qty * price
        prior = [t for t in transactions_after if str(getattr(t, "id", "")) != txn_id]
        first_overall = action == "buy" and not any(t.action == "buy" for t in prior)
        first_of_ticker = action == "buy" and not any(
            t.action == "buy" and str(t.ticker or "").upper() == sym for t in prior
        )
        metrics.update(
            {
                "ticker": sym,
                "shares": qty,
                "price": price,
                "amount": round(cost, 2),
                "first_real_purchase": first_overall,
                "first_purchase_of_ticker": first_of_ticker,
            }
        )
        if action == "buy":
            event = "real_investment_purchased"
            lead = f"Recorded first real {sym} purchase" if first_of_ticker else f"Recorded real {sym} purchase"
        else:
            event = "real_investment_sold"
            lead = f"Recorded real {sym} sale"
        summary = f"{lead} — {_shares(qty)} at {_money(price)} ({_money(cost)})"
    _record(
        event,
        st=st,
        kind=REAL,
        event_key=f"txn:{txn_id}",
        page=PAGE_IDS["my_portfolio"],
        subtab="Transactions",
        metrics=metrics,
        summary=summary,
    )


def log_real_transaction_removed(st: Any, txn: Any, *, transactions_after: list[Any]) -> None:
    sym = str(getattr(txn, "ticker", "") or "").upper() or "cash"
    action = str(getattr(txn, "action", "") or "").replace("_", " ")
    _record(
        "real_transaction_removed",
        st=st,
        kind=REAL,
        event_key=f"txn_removed:{getattr(txn, 'id', '')}",
        page=PAGE_IDS["my_portfolio"],
        subtab="Transactions",
        metrics={
            "transaction_id": str(getattr(txn, "id", "")),
            "transaction_action": str(getattr(txn, "action", "")),
            **_real_snapshot(transactions_after),
        },
        summary=f"Removed a {action} ({sym}) from the real portfolio ledger",
    )


def log_real_contribution_recorded(
    st: Any,
    *,
    application_id: str,
    amount: float,
    purchases: list[dict[str, Any]],
    transactions_after: list[Any],
) -> None:
    tickers = [str(p.get("ticker") or "").upper() for p in purchases if p.get("ticker")]
    _record(
        "real_contribution_recorded",
        st=st,
        kind=REAL,
        event_key=f"contribution:{application_id}",
        page=PAGE_IDS["my_portfolio"],
        subtab="Allocate New Money",
        metrics={
            "application_id": application_id,
            "amount": round(float(amount), 2),
            "purchases": purchases,
            "purchase_count": len(purchases),
            **_real_snapshot(transactions_after),
        },
        summary=f"Recorded {_money(float(amount))} contribution — {len(purchases)} purchase(s)"
        + (f": {', '.join(tickers)}" if tickers else ""),
    )


def log_real_strategy_target_saved(st: Any, *, weights: dict[str, float]) -> None:
    alloc = sorted(((str(k).upper(), float(v)) for k, v in (weights or {}).items()), key=lambda x: -x[1])
    total = sum(w for _, w in alloc)
    scale = 100.0 if 0 < total <= 1.0001 else 1.0
    label = ", ".join(f"{w * scale:.0f}% {t}" for t, w in alloc[:4]) or "cleared"
    _record(
        "real_strategy_target_saved",
        st=st,
        kind=REAL,
        event_key=f"strategy:{_digest(*[f'{t}:{w:.4f}' for t, w in alloc])}:{_today()}",
        page=PAGE_IDS["my_portfolio"],
        subtab="Allocate New Money",
        metrics={"strategy_target_weights": {t: w for t, w in alloc}},
        summary=f"Saved real-portfolio strategy target — {label}",
    )


# ── Continue: where you left off ─────────────────────────────────────────────


def _active_position(st: Any) -> tuple[str, str]:
    """(canonical page label, subtab label) of the current view."""
    ss = st.session_state
    tab = str(ss.get("investment_active_tab") or "").strip()
    try:
        from components.beginner_navigation import canonical_tab_label

        page = canonical_tab_label(tab)
    except Exception:
        page = tab
    subtab = ""
    if page == PAGE_IDS["my_portfolio"]:
        subtab = str(ss.get("real_portfolio_subtab") or "Dashboard")
    elif page == PAGE_IDS["overview"]:
        subtab = str(ss.get("overview_subtab") or "")
    elif page == PAGE_IDS["health"]:
        subtab = str(ss.get("health_subtab") or "")
    return page, subtab


def _position_context(st: Any, page: str) -> tuple[str, dict[str, Any]]:
    if page == PAGE_IDS["my_portfolio"]:
        try:
            from components.real_portfolio import get_portfolio_transactions

            snap = _real_snapshot(get_portfolio_transactions())
        except Exception:
            snap = {}
        n = int(snap.get("real_transaction_count") or 0)
        if n:
            held = ", ".join(snap.get("real_tickers") or []) or "cash only"
            line = f"Real portfolio: {n} transaction{'s' if n != 1 else ''} · {held}"
            if "real_cash_balance" in snap:
                line += f" · {_money(float(snap['real_cash_balance']))} cash"
        else:
            line = "Real portfolio: no transactions yet"
        return line, {"portfolio_kind": REAL, **snap}
    alloc = planning_allocation(st)
    goal = _goal(st)
    line = f"Planning portfolio: {describe_allocation(alloc)}" + (f" · {goal}" if goal else "")
    return line, {"portfolio_kind": PLANNING, "tickers": [t for t, _ in alloc]}


def track_resume_position(st: Any) -> bool:
    """Keep Continue pointed at the current page + subtab. Writes only when it changes."""
    page, subtab = _active_position(st)
    if not page:
        return False
    if page != PAGE_IDS["portfolio"]:
        flush_planning_change(st, reason="navigation")
    context, ctx_metrics = _position_context(st, page)
    signature = f"{page}|{subtab}|{context}"
    if st.session_state.get(_RESUME_POS_SESSION_KEY) == signature:
        return False
    try:
        from suite_storage_config import cloud_storage_enabled

        if not cloud_storage_enabled():
            return False
        from suite_deep_links import build_resume_action_url
        from suite_storage_supabase import upsert_resume_item

        metrics: dict[str, Any] = {**ctx_metrics, "resume_page": page}
        if subtab:
            metrics["resume_subtab"] = subtab
        try:
            from suite_workspace import get_active_workspace_id

            metrics["workspace_id"] = get_active_workspace_id(st)
        except Exception:
            pass
        url = build_resume_action_url(APP, resume_key=RESUME_POSITION_KEY, page=page, metrics=metrics)
        upsert_resume_item(
            APP,
            RESUME_POSITION_KEY,
            title=_resume_title(page, subtab),
            subtitle=context,
            action_url=url,
        )
        st.session_state[_RESUME_POS_SESSION_KEY] = signature
        return True
    except Exception:
        return False
