"""Beginner-friendly tab labels, sidebar checklist, and next-step coaching."""

from __future__ import annotations

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
    ("analyze", "Step 3 — Analyze Portfolio"),
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


def _portfolio_built() -> bool:
    if st.session_state.get("preset_applied") or st.session_state.get("guide_portfolio_loaded"):
        return True
    df = st.session_state.get("holdings_df")
    if df is None or df.empty:
        return False
    default_fp = _holdings_fingerprint(pd.DataFrame(core.DEFAULT_HOLDINGS))
    return _holdings_fingerprint(df) != default_fp


def mark_portfolio_built() -> None:
    st.session_state.portfolio_built = True


def _checklist_state() -> dict[str, bool]:
    goal_done = bool(st.session_state.get("guide_goal_choice")) or bool(
        st.session_state.get("beginner_goal_card")
    )
    portfolio_done = _portfolio_built() or bool(st.session_state.get("portfolio_built"))
    analyze_done = bool(st.session_state.get("portfolio_analyzed"))
    health_done = bool(st.session_state.get("portfolio_health_reviewed"))
    rec_done = bool(st.session_state.get("recommendations_displayed"))
    return {
        "goal": goal_done,
        "portfolio": portfolio_done,
        "analyze": analyze_done,
        "health": health_done,
        "recommendations": rec_done,
    }


def _current_step_index() -> int:
    state = _checklist_state()
    for i, (key, _) in enumerate(CHECKLIST_STEPS):
        if not state[key]:
            return i
    return len(CHECKLIST_STEPS) - 1


def get_recommended_next_step() -> tuple[str, str, str]:
    state = _checklist_state()
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
            f"Open **{tab}** and click **Analyze Portfolio** (top of that tab).",
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
    st.sidebar.caption("Steps 1–5 are required · Tabs ⑦–⑩ are optional.")
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
    if all(state.values()):
        st.sidebar.success("All main steps complete!")
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
        elif not state["portfolio"]:
            clicked = st.button(f"Go to {STEP_TAB_LABEL['portfolio']}", type="primary", use_container_width=True, key="cta_portfolio")
        elif not state["analyze"]:
            if st.button(f"Go to {STEP_TAB_LABEL['analyze']}", type="primary", use_container_width=True, key="cta_analyze"):
                st.session_state.run_health = True
                st.session_state.portfolio_analyzed = True
                clicked = True
        elif not state["health"]:
            clicked = st.button(f"Go to {STEP_TAB_LABEL['health']}", type="primary", use_container_width=True, key="cta_health")
        elif not state["recommendations"]:
            clicked = st.button(f"Go to {STEP_TAB_LABEL['health']}", type="primary", use_container_width=True, key="cta_rec")
    return clicked
