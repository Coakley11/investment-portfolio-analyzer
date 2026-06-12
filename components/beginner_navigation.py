"""Beginner-friendly tab labels, sidebar checklist, and next-step coaching."""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

import portfolio_core as core

# Same count/order as ADVANCED_TAB_LABELS — wording matches the beginner workflow.
BEGINNER_TAB_LABELS = [
    "① Choose Goal",
    "② Overview",
    "③ Build Portfolio",
    "④ Analyze Portfolio",
    "⑤ Portfolio Health",
    "⑥ Explain Portfolio",
    "⑦ Macro (Optional)",
    "⑧ Scenarios (Optional)",
    "⑨ Optimizer (Optional)",
    "⑩ Frontier (Optional)",
]

ADVANCED_TAB_LABELS = [
    "Getting Started Guide",
    "Overview",
    "Portfolio Inputs",
    "Portfolio Analytics",
    "Portfolio Health",
    "Explain This Portfolio",
    "Forward Macro Analysis",
    "Monte Carlo",
    "Optimization",
    "Efficient Frontier",
]

STEP_TAB_LABEL: dict[str, str] = {
    "goal": "① Choose Goal",
    "portfolio": "③ Build Portfolio",
    "analyze": "④ Analyze Portfolio",
    "health": "⑤ Portfolio Health",
    "recommendations": "⑤ Portfolio Health",
}

CHECKLIST_STEPS = [
    ("goal", "Step 1 — Choose Goal"),
    ("portfolio", "Step 2 — Build Portfolio"),
    ("analyze", "Step 3 — Run Portfolio Analysis"),
    ("health", "Step 4 — Review Portfolio Health"),
    ("recommendations", "Step 5 — Review Recommendations"),
]

OBJECTIVE_TO_PRESET: dict[str, str] = {
    "capital preservation": "Conservative",
    "balanced growth": "Balanced",
    "aggressive growth": "Aggressive",
    "income": "Dividend Income",
    "retirement": "Retirement",
    "short-term cash management": "Conservative",
}

PRESET_DISPLAY: dict[str, dict[str, str]] = {
    "Conservative": {
        "tab": "Conservative",
        "tagline": "Lower bumps, more bonds and cash-like funds.",
        "characteristics": "Smoother ride, slower growth potential.",
    },
    "Balanced": {
        "tab": "Balanced",
        "tagline": "Mix of stocks, bonds, and real estate.",
        "characteristics": "Common long-term starting point.",
    },
    "Aggressive": {
        "tab": "Growth",
        "tagline": "Heavy stock exposure including growth (QQQ).",
        "characteristics": "Higher growth potential, bigger swings.",
    },
    "Dividend Income": {
        "tab": "Income",
        "tagline": "Dividend ETFs, REITs, and bonds.",
        "characteristics": "Income-oriented, moderate growth.",
    },
    "Retirement": {
        "tab": "Retirement",
        "tagline": "Diversified mix with more bonds than balanced.",
        "characteristics": "Built for long-term saving with stability.",
    },
}


try:
    from investment_workflow import WORKFLOW_UI_BUILD as GOAL_WORKFLOW_DEBUG_BUILD
except ImportError:
    GOAL_WORKFLOW_DEBUG_BUILD = "2026-06-03-goal-change-fix"

# Beginner and advanced main tabs share the same index order (10 tabs).
_TAB_INDEX_BY_BEGINNER = {label: i for i, label in enumerate(BEGINNER_TAB_LABELS)}
_TAB_INDEX_BY_ADVANCED = {label: i for i, label in enumerate(ADVANCED_TAB_LABELS)}


def normalize_tab_label_for_mode(label: str, *, beginner: bool) -> str:
    """Map a saved tab from the other experience mode to the active label set."""
    cleaned = str(label or "").strip()
    if not cleaned:
        return BEGINNER_TAB_LABELS[0] if beginner else ADVANCED_TAB_LABELS[0]
    if beginner:
        if cleaned in BEGINNER_TAB_LABELS:
            return cleaned
        if cleaned in ADVANCED_TAB_LABELS:
            return BEGINNER_TAB_LABELS[ADVANCED_TAB_LABELS.index(cleaned)]
    else:
        if cleaned in ADVANCED_TAB_LABELS:
            return cleaned
        if cleaned in BEGINNER_TAB_LABELS:
            return ADVANCED_TAB_LABELS[BEGINNER_TAB_LABELS.index(cleaned)]
    return BEGINNER_TAB_LABELS[0] if beginner else ADVANCED_TAB_LABELS[0]


def _sess(st_obj: Any | None = None):
    if st_obj is not None:
        return st_obj.session_state
    return st.session_state


def sync_beginner_goal_keys_from_portfolio(st: Any) -> bool:
    """
    Align checklist goal keys with restored or preset-loaded portfolio state.

    Returns True when goal keys were inferred and written.
    """
    ss = _sess(st)
    if ss.get("guide_goal_choice") or ss.get("beginner_goal_card"):
        return False
    preset = str(ss.get("preset_applied") or "").strip()
    objective = str(ss.get("health_objective") or "").strip()
    if not preset and not objective:
        return False
    try:
        from components.beginner_coach import GOAL_CARDS
    except ImportError:
        return False
    preset_to_card_id = {
        "Conservative": "preservation",
        "Balanced": "balanced",
        "Aggressive": "growth",
        "Dividend Income": "income",
        "Retirement": "retirement",
    }
    preferred_id = preset_to_card_id.get(preset)
    if preferred_id:
        for card in GOAL_CARDS:
            if card.get("id") == preferred_id:
                ss.beginner_goal_card = card["id"]
                ss.guide_goal_choice = card["goal_key"]
                return True
    if preset and objective:
        for card in GOAL_CARDS:
            if card.get("preset") == preset and card.get("objective") == objective:
                ss.beginner_goal_card = card["id"]
                ss.guide_goal_choice = card["goal_key"]
                return True
    for card in GOAL_CARDS:
        if preset and card.get("preset") == preset:
            ss.beginner_goal_card = card["id"]
            ss.guide_goal_choice = card["goal_key"]
            return True
    for card in GOAL_CARDS:
        if objective and card.get("objective") == objective:
            ss.beginner_goal_card = card["id"]
            ss.guide_goal_choice = card["goal_key"]
            return True
    return False


def _goal_step_complete(st_obj: Any | None = None) -> bool:
    ss = _sess(st_obj)
    if ss.get("guide_goal_choice") or ss.get("beginner_goal_card"):
        return True
    preset = ss.get("preset_applied")
    objective = ss.get("health_objective")
    if preset and objective:
        return True
    if preset and _portfolio_built(st_obj):
        return True
    return False


def _holdings_fingerprint(df: pd.DataFrame) -> str:
    if df is None or df.empty:
        return ""
    rows = []
    for _, row in df.iterrows():
        ticker = str(row.get("Ticker", "")).strip().upper()
        weight = float(row.get("Weight (%)", 0) or 0)
        atype = str(row.get("Asset Type", "")).strip()
        rows.append((ticker, round(weight, 2), atype))
    rows.sort(key=lambda x: x[0])
    return "|".join(f"{t}:{w}:{a}" for t, w, a in rows)


def _portfolio_built(st_obj: Any | None = None) -> bool:
    """Portfolio step is complete only after explicit user confirmation."""
    return bool(_sess(st_obj).get("portfolio_built"))


def mark_portfolio_built(st_obj: Any | None = None, *, holdings_df: pd.DataFrame | None = None) -> None:
    try:
        from investment_workflow import confirm_portfolio_step

        df = holdings_df
        if df is None:
            ss = _sess(st_obj)
            raw = ss.get("holdings_df")
            if isinstance(raw, pd.DataFrame):
                df = raw
        confirm_portfolio_step(st_obj, holdings_df=df)
    except ImportError:
        _sess(st_obj).portfolio_built = True


def _checklist_state(st_obj: Any | None = None) -> dict[str, bool]:
    try:
        from investment_workflow import workflow_checklist

        return workflow_checklist(st_obj)
    except ImportError:
        ss = _sess(st_obj)
        goal_done = _goal_step_complete(st_obj)
        portfolio_done = _portfolio_built(st_obj) or bool(ss.get("portfolio_built"))
        return {
            "goal": goal_done,
            "portfolio": portfolio_done,
            "analyze": bool(ss.get("portfolio_analyzed")),
            "health": bool(ss.get("portfolio_health_reviewed")),
            "recommendations": bool(ss.get("recommendations_displayed")),
        }


def _current_step_index(st_obj: Any | None = None) -> int:
    state = _checklist_state(st_obj)
    for i, (key, _) in enumerate(CHECKLIST_STEPS):
        if not state[key]:
            return i
    return len(CHECKLIST_STEPS) - 1


def get_recommended_next_step(st_obj: Any | None = None) -> tuple[str, str, str]:
    state = _checklist_state(st_obj)
    total = len(CHECKLIST_STEPS)
    if not state["goal"]:
        tab = STEP_TAB_LABEL["goal"]
        return (f"Step 1 of {total}", tab, f"Open **{tab}** and choose a goal card.")
    if not state["portfolio"]:
        tab = STEP_TAB_LABEL["portfolio"]
        return (f"Step 2 of {total}", tab, f"Open **{tab}** and confirm your holdings.")
    if not state["analyze"]:
        tab = STEP_TAB_LABEL["analyze"]
        return (
            f"Step 3 of {total}",
            tab,
            f"Open **{tab}** and click **Run Portfolio Analysis** (top of that tab).",
        )
    if not state["health"]:
        tab = STEP_TAB_LABEL["health"]
        return (
            f"Step 4 of {total}",
            tab,
            f"Open **{tab}** and click **Refresh Portfolio Health**.",
        )
    if not state["recommendations"]:
        tab = STEP_TAB_LABEL["recommendations"]
        return (
            f"Step 5 of {total}",
            tab,
            f"Open **{tab}** → **Recommendations** sub-tab and read each suggestion.",
        )
    return ("All done", STEP_TAB_LABEL["health"], "Great work! Optional tabs ⑦–⑩ are extra tools.")


def render_beginner_sidebar_checklist() -> None:
    st.sidebar.markdown("### Your journey")
    st.sidebar.caption("Matches the workflow bar above the main area.")
    try:
        from investment_workflow import workflow_step_visual_states

        active = st.session_state.get("investment_active_tab")
        visuals = workflow_step_visual_states(st, beginner=True, active_tab=active)
        icons = {"complete": "✓", "current": "▶", "stale": "⚠", "available": "○"}
        for key, label in CHECKLIST_STEPS:
            vis = visuals.get(key, "available")
            icon = icons.get(vis, "○")
            if vis == "complete":
                style = "color:#86efac;font-weight:500;"
            elif vis == "current":
                style = "color:#4da3ff;font-weight:600;font-size:0.95rem;"
            elif vis == "stale":
                style = "color:#fbbf24;font-weight:500;"
            else:
                style = "color:#64748b;"
            st.sidebar.markdown(
                f'<div style="{style}line-height:1.65;margin:0.2rem 0;">{icon} {label}</div>',
                unsafe_allow_html=True,
            )
        if all(_checklist_state().values()):
            st.sidebar.success("All main steps complete!")
    except ImportError:
        state = _checklist_state()
        current = _current_step_index()
        for i, (key, label) in enumerate(CHECKLIST_STEPS):
            done = state[key]
            is_current = i == current and not done
            if done:
                icon, style = "✅", "color:#86efac;font-weight:500;"
            elif is_current:
                icon, style = "👉", "color:#4da3ff;font-weight:600;font-size:0.95rem;"
            else:
                icon, style = "⬜", "color:#64748b;"
            st.sidebar.markdown(
                f'<div style="{style}line-height:1.65;margin:0.2rem 0;">{icon} {label}</div>',
                unsafe_allow_html=True,
            )
    st.sidebar.divider()


def render_next_step_banner() -> None:
    step_label, tab_label, message = get_recommended_next_step()
    st.markdown(
        f"""
        <div style="background:linear-gradient(90deg,rgba(77,163,255,0.18) 0%,rgba(20,28,43,0.92) 100%);
        border:1px solid rgba(77,163,255,0.45);border-left:5px solid #4da3ff;border-radius:12px;
        padding:0.9rem 1.15rem;margin:0 0 0.85rem 0;">
        <div style="font-size:0.72rem;text-transform:uppercase;letter-spacing:0.1em;color:#4da3ff;
        font-weight:600;margin-bottom:0.35rem;">{step_label} · Start here</div>
        <span style="font-weight:700;color:#f1f5f9;font-size:1.05rem;">Go to {tab_label}</span>
        <span style="color:#cbd5e1;font-size:0.92rem;"> — {message}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _workflow_redirect_reason(*, tab_labels: list[str] | None = None, st_obj: Any | None = None) -> str:
    """Human-readable reason the coach banner points at Step 1 (Choose Goal)."""
    ss = _sess(st_obj)
    state = _checklist_state(st_obj)
    if state["goal"]:
        return "goal step complete — no redirect to Choose Goal"
    parts: list[str] = []
    if not ss.get("guide_goal_choice"):
        parts.append("guide_goal_choice missing")
    if not ss.get("beginner_goal_card"):
        parts.append("beginner_goal_card missing")
    preset = ss.get("preset_applied")
    objective = ss.get("health_objective")
    if preset:
        parts.append(f"preset_applied={preset!r} (counts toward goal if objective set)")
    if objective:
        parts.append(f"health_objective={objective!r}")
    if preset and not objective:
        parts.append("preset without health_objective — goal still incomplete")
    active = ss.get("investment_active_tab")
    labels = tab_labels or BEGINNER_TAB_LABELS
    if active and active not in labels:
        mapped = normalize_tab_label_for_mode(str(active), beginner=True)
        parts.append(
            f"active tab {active!r} invalid for beginner — would reset to {mapped!r}"
        )
    return "; ".join(parts) if parts else "unknown"


def goal_workflow_debug_lines(st_obj: Any, *, tab_labels: list[str] | None = None) -> list[str]:
    ss = _sess(st_obj)
    state = _checklist_state(st_obj)
    step_idx = _current_step_index(st_obj)
    step_key, step_label = (
        CHECKLIST_STEPS[step_idx] if step_idx < len(CHECKLIST_STEPS) else ("done", "complete")
    )
    labels = tab_labels or BEGINNER_TAB_LABELS
    active = ss.get("investment_active_tab")
    goal_valid = state["goal"]
    return [
        f"build: {GOAL_WORKFLOW_DEBUG_BUILD}",
        f"selected goal (guide_goal_choice): {ss.get('guide_goal_choice')!r}",
        f"goal card id (beginner_goal_card): {ss.get('beginner_goal_card')!r}",
        f"preset_applied: {ss.get('preset_applied')!r}",
        f"health_objective: {ss.get('health_objective')!r}",
        f"workflow step: {step_key!r} ({step_label})",
        f"checklist goal valid: {goal_valid!r}",
        f"investment_active_tab: {active!r}",
        f"tab valid for current labels: {(active in labels) if active else False!r}",
        f"redirect reason: {_workflow_redirect_reason(tab_labels=labels, st_obj=st_obj)}",
    ]


def render_recommended_next_step_card() -> bool:
    step_label, tab_label, message = get_recommended_next_step()
    state = _checklist_state()
    st.markdown(
        f"""
        <div style="background:linear-gradient(135deg,#0f2847 0%,#141c2b 100%);
        border:2px solid rgba(77,163,255,0.5);border-radius:14px;padding:1.15rem 1.25rem;margin-bottom:1rem;">
        <div style="font-size:0.75rem;text-transform:uppercase;color:#4da3ff;font-weight:700;">{step_label}</div>
        <div style="font-size:1.15rem;font-weight:700;color:#f1f5f9;margin:0.5rem 0;">Go to {tab_label}</div>
        <div style="color:#cbd5e1;font-size:0.95rem;line-height:1.55;">{message}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    c1, _c2 = st.columns([1, 1])
    clicked = False
    with c1:
        if not state["goal"]:
            clicked = st.button(f"Go to {STEP_TAB_LABEL['goal']}", type="primary", use_container_width=True, key="cta_goal")
            if clicked:
                try:
                    from investment_workflow import request_core_step_navigation

                    request_core_step_navigation("goal", beginner=True)
                except ImportError:
                    st.session_state["_pending_investment_tab"] = STEP_TAB_LABEL["goal"]
        elif not state["portfolio"]:
            clicked = st.button(f"Go to {STEP_TAB_LABEL['portfolio']}", type="primary", use_container_width=True, key="cta_portfolio")
            if clicked:
                try:
                    from investment_workflow import begin_portfolio_rebuild_workflow

                    begin_portfolio_rebuild_workflow(st, beginner=True)
                except ImportError:
                    st.session_state["_pending_investment_tab"] = STEP_TAB_LABEL["portfolio"]
        elif not state["analyze"]:
            if st.button(f"Go to {STEP_TAB_LABEL['analyze']}", type="primary", use_container_width=True, key="cta_analyze"):
                try:
                    from investment_workflow import request_core_step_navigation

                    request_core_step_navigation("analyze", beginner=True)
                except ImportError:
                    st.session_state["_pending_investment_tab"] = STEP_TAB_LABEL["analyze"]
                st.session_state.run_health = True
                clicked = True
        elif not state["health"]:
            clicked = st.button(f"Go to {STEP_TAB_LABEL['health']}", type="primary", use_container_width=True, key="cta_health")
            if clicked:
                try:
                    from investment_workflow import request_core_step_navigation

                    request_core_step_navigation("health", beginner=True)
                except ImportError:
                    st.session_state["_pending_investment_tab"] = STEP_TAB_LABEL["health"]
        elif not state["recommendations"]:
            clicked = st.button(f"Go to {STEP_TAB_LABEL['health']}", type="primary", use_container_width=True, key="cta_rec")
            if clicked:
                try:
                    from investment_workflow import request_core_step_navigation

                    request_core_step_navigation("health", beginner=True)
                except ImportError:
                    st.session_state["_pending_investment_tab"] = STEP_TAB_LABEL["health"]
    return clicked
