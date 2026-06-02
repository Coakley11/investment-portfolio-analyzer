"""Apply beginner label + analyze tab edits to streamlit_app.py from HEAD."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
text = subprocess.check_output(["git", "show", "HEAD:streamlit_app.py"]).decode("utf-8")

if "render_goal_cards" not in text:
    text = text.replace(
        "from components.beginner_navigation import (",
        """from components.beginner_coach import (
    render_beginner_analyze_results,
    render_goal_cards,
)
from components.beginner_navigation import (""",
        1,
    )

old = """_tab_labels = BEGINNER_TAB_LABELS if beginner_mode else ADVANCED_TAB_LABELS
if len(_tab_labels) != len(ADVANCED_TAB_LABELS):
    raise ValueError(
        f"Tab label count mismatch: {len(_tab_labels)} labels vs "
        f"{len(ADVANCED_TAB_LABELS)} expected — fix BEGINNER_TAB_LABELS / ADVANCED_TAB_LABELS"
    )
(
    tab_guide,
    tab_overview,
    tab_inputs,
    tab_risk,
    tab_health,
    tab_explain,
    tab_forward,
    tab_mc,
    tab_opt,
    tab_frontier,
) = st.tabs(_tab_labels)

with tab_guide:
    section_header(
        "Getting Started Guide",
        "Your step-by-step coach — no finance background needed." if beginner_mode
        else f"Step-by-step tutorial. {APP_DISCLAIMER}",
    )
    render_getting_started_guide(beginner_mode=beginner_mode)"""

new = """(
    tab_guide,
    tab_overview,
    tab_inputs,
    tab_risk,
    tab_health,
    tab_explain,
    tab_forward,
    tab_mc,
    tab_opt,
    tab_frontier,
) = st.tabs(BEGINNER_TAB_LABELS if beginner_mode else ADVANCED_TAB_LABELS)

with tab_guide:
    if beginner_mode:
        st.markdown(
            f'<p style="color:#f5d08a;font-size:0.85rem;">{APP_DISCLAIMER}</p>',
            unsafe_allow_html=True,
        )
        render_goal_cards()
    else:
        section_header(
            "Getting Started Guide",
            f"Step-by-step tutorial. {APP_DISCLAIMER}",
        )
        render_getting_started_guide(beginner_mode=False)"""

if old not in text:
    raise SystemExit("tab block missing")
text = text.replace(old, new, 1)

old_risk = """with tab_risk:
    st.session_state.visited_risk = True
    section_header(
        "Risk Analysis",
        "See how bumpy each holding is and whether your mix is spread out enough." if beginner_mode
        else "Correlation, concentration, scenarios, and macro regimes.",
    )
    if beginner_mode:
        what_why_do(
            "Risk Analysis",
            "Tools that show how much investments move and whether one fund dominates your risk.",
            "Helps you avoid putting too many eggs in one basket.",
            "Switch to Advanced Mode when ready, or read suggestions on Overview and Portfolio Health.",
        )
        st.info(
            "Detailed risk charts are in **Advanced Mode**. Your Overview tab already highlights key suggestions."
        )
    else:
        if st.button("Run Risk & Macro Analysis", key="run_risk_macro_btn"):"""

new_risk = """with tab_risk:
    st.session_state.visited_risk = True
    if beginner_mode:
        section_header(
            "Analyze Portfolio",
            "Run a one-click checkup — then continue on **⑤ Portfolio Health**.",
        )
        if st.button("Analyze Portfolio", type="primary", key="beg_analyze", use_container_width=True):
            st.session_state.run_health = True
            st.session_state.health_refresh = st.session_state.get("health_refresh", 0) + 1
            st.session_state.portfolio_analyzed = True
            st.rerun()
        _beg_health = get_cached_health(tickers, weights)
        if _beg_health:
            st.session_state.portfolio_health_reviewed = True
            render_beginner_analyze_results(
                _beg_health,
                objective=st.session_state.get("health_objective", "balanced growth"),
            )
        else:
            st.info("Click **Analyze Portfolio** above.")
        st.caption("Tabs **⑦–⑩** are optional. Advanced Mode has full risk charts.")
    else:
        section_header(
            "Risk Analysis",
            "Correlation, concentration, scenarios, and macro regimes.",
        )
        if st.button("Run Risk & Macro Analysis", key="run_risk_macro_btn"):"""

if old_risk not in text:
    raise SystemExit("risk block missing")
text = text.replace(old_risk, new_risk, 1)

text = text.replace(
    '"Click Refresh below, then use the tabs for score, recommendations, and rebalancing."',
    '"Click **Refresh Portfolio Health** below, then open the **Recommendations** sub-tab."',
    1,
)

(ROOT / "streamlit_app.py").write_text(text, encoding="utf-8")
print("patched")
