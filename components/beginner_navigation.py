"""Beginner-friendly tab labels, sidebar checklist, and next-step coaching."""

from __future__ import annotations

import streamlit as st

BEGINNER_TAB_LABELS = [
    "🧭 Getting Started",
    "🏠 Overview",
    "💼 Portfolio Inputs",
    "⚠️ Risk Analysis",
    "❤️ Portfolio Health",
    "📄 Explain Portfolio",
    "🌎 Macro Analysis",
    "🎲 Monte Carlo",
    "⚙️ Optimizer",
    "📊 Efficient Frontier",
]

ADVANCED_TAB_LABELS = [
    "Getting Started Guide",
    "Overview",
    "Portfolio Inputs",
    "Risk Analysis",
    "Portfolio Health",
    "Explain This Portfolio",
    "Forward-Looking Macro Analysis",
    "Monte Carlo",
    "Optimization",
    "Efficient Frontier",
]

CHECKLIST_STEPS = [
    ("goal", "Step 1 — Choose Goal"),
    ("invest", "Step 2 — Determine How Much To Invest"),
    ("portfolio", "Step 3 — Build Portfolio"),
    ("analyze", "Step 4 — Analyze Portfolio"),
    ("health", "Step 5 — Review Health Score"),
    ("recommendations", "Step 6 — Review Recommendations"),
    ("implement", "Step 7 — Learn How To Implement"),
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


def _checklist_state() -> dict[str, bool]:
    goal_done = bool(st.session_state.get("guide_goal_choice"))
    invest_done = bool(st.session_state.get("investment_plan")) or bool(
        st.session_state.get("plan_total_cash")
    )
    portfolio_done = bool(st.session_state.get("preset_applied")) or st.session_state.get(
        "guide_portfolio_loaded", False
    )
    analyze_done = bool(st.session_state.get("run_health"))
    health_done = bool(st.session_state.get("health_result"))
    rec_done = health_done and bool(
        st.session_state.get("health_result") and st.session_state.get("run_health")
    )
    implement_done = bool(st.session_state.get("visited_implement"))
    return {
        "goal": goal_done,
        "invest": invest_done,
        "portfolio": portfolio_done,
        "analyze": analyze_done,
        "health": health_done,
        "recommendations": rec_done,
        "implement": implement_done,
    }


def _current_step_index() -> int:
    state = _checklist_state()
    for i, (key, _) in enumerate(CHECKLIST_STEPS):
        if not state[key]:
            return i
    return len(CHECKLIST_STEPS) - 1


def get_recommended_next_step() -> tuple[str, str, str]:
    """Return (step_label, tab_hint, action_message)."""
    state = _checklist_state()
    total = len(CHECKLIST_STEPS)
    if not state["goal"]:
        return (f"Step 1 of {total}", "Getting Started", "Open **🧭 Getting Started** and pick your goal.")
    if not state["invest"]:
        return (
            f"Step 2 of {total}",
            "Portfolio Inputs",
            "Open **💼 Portfolio Inputs** → **How Much to Invest** and set your cash amounts.",
        )
    if not state["portfolio"]:
        return (
            f"Step 3 of {total}",
            "Portfolio Inputs",
            "Confirm your portfolio mix in **💼 Portfolio Inputs** or load a preset in Getting Started.",
        )
    if not state["analyze"]:
        return (
            f"Step 4 of {total}",
            "Overview",
            "Open **🏠 Overview** and click **Analyze Portfolio**.",
        )
    if not state["health"]:
        return (
            f"Step 5 of {total}",
            "Portfolio Health",
            "Open **❤️ Portfolio Health** and review your health score.",
        )
    if not state["recommendations"]:
        return (
            f"Step 6 of {total}",
            "Overview",
            "Read **Recommendations & why** on Overview or Portfolio Health.",
        )
    if not state["implement"]:
        return (
            f"Step 7 of {total}",
            "Portfolio Inputs",
            "Open **💼 Portfolio Inputs** → **Implementation Guide** for how to invest in practice.",
        )
    return ("All done", "Overview", "You're set! Follow the monthly review checklist on Overview.")


def render_beginner_sidebar_checklist() -> None:
    """Guided checklist in the sidebar for Beginner Mode."""
    st.sidebar.markdown("### Your journey")
    st.sidebar.caption("Follow these steps in order.")
    state = _checklist_state()
    current = _current_step_index()
    for i, (key, label) in enumerate(CHECKLIST_STEPS):
        done = state[key]
        is_current = i == current and not done
        if done:
            icon = "✅"
            style = "color:#86efac;font-weight:500;"
        elif is_current:
            icon = "👉"
            style = "color:#4da3ff;font-weight:600;font-size:0.95rem;"
        else:
            icon = "⬜"
            style = "color:#64748b;"
        st.sidebar.markdown(
            f'<div style="{style}line-height:1.65;margin:0.2rem 0;">{icon} {label}</div>',
            unsafe_allow_html=True,
        )
    if all(state.values()):
        st.sidebar.success("All steps complete — great job!")
    st.sidebar.divider()


def render_next_step_banner() -> None:
    """Highlight the recommended next tab/action above the main tabs."""
    step_label, _tab_hint, message = get_recommended_next_step()
    st.markdown(
        f"""
        <div style="background:linear-gradient(90deg,rgba(77,163,255,0.18) 0%,rgba(20,28,43,0.92) 100%);
        border:1px solid rgba(77,163,255,0.45);border-left:5px solid #4da3ff;border-radius:12px;
        padding:0.9rem 1.15rem;margin:0 0 0.85rem 0;">
        <div style="font-size:0.72rem;text-transform:uppercase;letter-spacing:0.1em;color:#4da3ff;
        font-weight:600;margin-bottom:0.35rem;">{step_label}</div>
        <span style="font-weight:600;color:#f1f5f9;font-size:1.02rem;">👉 Recommended next step</span>
        <span style="color:#cbd5e1;font-size:0.92rem;"> — {message}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_recommended_next_step_card() -> bool:
    """
    Large CTA card with one-click action for the current step.
    Returns True if user clicked a CTA that triggers rerun.
    """
    step_label, _tab_hint, message = get_recommended_next_step()
    state = _checklist_state()

    st.markdown(
        f"""
        <div style="background:linear-gradient(135deg,#0f2847 0%,#141c2b 100%);
        border:2px solid rgba(77,163,255,0.5);border-radius:14px;padding:1.15rem 1.25rem;
        margin-bottom:1rem;box-shadow:0 4px 20px rgba(77,163,255,0.12);">
        <div style="font-size:0.75rem;text-transform:uppercase;letter-spacing:0.12em;
        color:#4da3ff;font-weight:700;margin-bottom:0.5rem;">{step_label}</div>
        <div style="font-size:1.15rem;font-weight:700;color:#f1f5f9;margin-bottom:0.4rem;">
        What to do next
        </div>
        <div style="color:#cbd5e1;font-size:0.95rem;line-height:1.55;">{message}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2 = st.columns([1, 1])
    clicked = False
    with c1:
        if not state["goal"]:
            if st.button("🧭 Choose Your Goal", type="primary", use_container_width=True, key="cta_goal"):
                clicked = True
        elif not state["invest"]:
            if st.button("💰 Set Investment Amounts", type="primary", use_container_width=True, key="cta_invest"):
                clicked = True
        elif not state["portfolio"]:
            if st.button("💼 Review Portfolio", type="primary", use_container_width=True, key="cta_portfolio"):
                clicked = True
        elif not state["analyze"]:
            if st.button("📋 Analyze Portfolio Now", type="primary", use_container_width=True, key="cta_analyze"):
                st.session_state.run_health = True
                st.session_state.health_refresh = st.session_state.get("health_refresh", 0) + 1
                clicked = True
        elif not state["health"]:
            if st.button("❤️ Open Portfolio Health", type="primary", use_container_width=True, key="cta_health"):
                clicked = True
        elif not state["recommendations"]:
            if st.button("📋 Read Recommendations", type="primary", use_container_width=True, key="cta_rec"):
                clicked = True
        elif not state["implement"]:
            if st.button("📘 Open Implementation Guide", type="primary", use_container_width=True, key="cta_impl"):
                st.session_state.visited_implement = True
                clicked = True
        else:
            if st.button("📅 View Monthly Routine", type="secondary", use_container_width=True, key="cta_monthly"):
                clicked = True
    with c2:
        if state["analyze"] and not state["implement"]:
            st.caption("Take your time — review suggestions before making any changes.")
        elif all(state.values()):
            st.caption("Revisit monthly: refresh data and re-analyze.")
    return clicked
