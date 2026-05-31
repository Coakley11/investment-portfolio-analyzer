"""Beginner-friendly tab labels, sidebar checklist, and next-step coaching."""

from __future__ import annotations

import streamlit as st

BEGINNER_TAB_LABELS = [
    "🧭 Getting Started",
    "📋 Overview",
    "💼 Portfolio Inputs",
    "⚠️ Risk Analysis",
    "❤️ Portfolio Health",
    "📄 Explain Portfolio",
    "🌎 Macro Analysis",
    "🎲 Monte Carlo",
    "⚙️ Optimizer",
    "📈 Efficient Frontier",
    "🔬 Problem Lab",
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
    "Math Problem Solving Lab",
]

CHECKLIST_STEPS = [
    ("goal", "Step 1: Choose your goal"),
    ("portfolio", "Step 2: Load a suggested portfolio"),
    ("analyze", "Step 3: Click Analyze Portfolio"),
    ("health", "Step 4: Review Portfolio Health"),
    ("recommendations", "Step 5: Review Recommendations"),
    ("advanced", "Step 6: Explore advanced analysis"),
]

OBJECTIVE_TO_PRESET: dict[str, str] = {
    "capital preservation": "Conservative",
    "balanced growth": "Balanced",
    "aggressive growth": "Aggressive",
    "income": "Dividend Income",
    "retirement": "Retirement",
    "short-term cash management": "Conservative",
}


def _checklist_state() -> dict[str, bool]:
    goal_done = bool(st.session_state.get("guide_goal_choice"))
    portfolio_done = bool(st.session_state.get("preset_applied")) or st.session_state.get(
        "guide_portfolio_loaded", False
    )
    analyze_done = bool(st.session_state.get("run_health"))
    health_done = analyze_done
    rec_done = analyze_done and bool(st.session_state.get("health_result"))
    advanced_done = bool(
        st.session_state.get("visited_risk")
        or st.session_state.get("visited_explain")
        or st.session_state.get("visited_forward")
        or st.session_state.get("experience") == "Advanced Mode"
    )
    return {
        "goal": goal_done,
        "portfolio": portfolio_done,
        "analyze": analyze_done,
        "health": health_done,
        "recommendations": rec_done,
        "advanced": advanced_done,
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
    if not state["goal"]:
        return ("Step 1 of 6", "Getting Started", "Open the **🧭 Getting Started** tab and pick your goal.")
    if not state["portfolio"]:
        return ("Step 2 of 6", "Portfolio Inputs", "Confirm your portfolio in **💼 Portfolio Inputs**.")
    if not state["analyze"]:
        return ("Step 3 of 6", "Overview", "Open **📋 Overview** and click **Analyze Portfolio**.")
    if not state["health"]:
        return ("Step 4 of 6", "Portfolio Health", "Open **❤️ Portfolio Health** and review your score.")
    if not state["recommendations"]:
        return ("Step 5 of 6", "Overview", "Read **Recommendations & why** on Overview or Portfolio Health.")
    if not state["advanced"]:
        return ("Step 6 of 6", "Explain Portfolio", "Optional: read **📄 Explain Portfolio** when ready.")
    return ("All done", "Overview", "You're set! Revisit monthly: refresh market data and re-analyze.")


def render_beginner_sidebar_checklist() -> None:
    """Guided checklist in the sidebar for Beginner Mode."""
    st.sidebar.markdown("### Your checklist")
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
            if st.button("🧭 Open Getting Started", type="primary", use_container_width=True, key="cta_goal"):
                clicked = True
        elif not state["portfolio"]:
            if st.button("💼 Review Portfolio Inputs", type="primary", use_container_width=True, key="cta_portfolio"):
                clicked = True
        elif not state["analyze"]:
            if st.button("📋 Analyze Portfolio Now", type="primary", use_container_width=True, key="cta_analyze"):
                st.session_state.run_health = True
                st.session_state.health_refresh = st.session_state.get("health_refresh", 0) + 1
                clicked = True
        elif not state["recommendations"]:
            if st.button("❤️ Open Portfolio Health", type="primary", use_container_width=True, key="cta_health"):
                clicked = True
        else:
            if st.button("📄 Explain My Portfolio", type="secondary", use_container_width=True, key="cta_explain"):
                st.session_state.visited_explain = True
                clicked = True
    with c2:
        if not state["analyze"] and state["portfolio"]:
            st.caption("Tip: You can also click **Analyze Portfolio** on the Overview tab.")
        elif state["analyze"] and not state["advanced"]:
            st.caption("Optional — explore when you're comfortable with the basics.")
    return clicked
