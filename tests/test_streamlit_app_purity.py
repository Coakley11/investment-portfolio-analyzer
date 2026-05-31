"""Regression: streamlit_app.py must not call unrelated project UI."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
STREAMLIT_APP = REPO_ROOT / "streamlit_app.py"

FORBIDDEN_TOKENS = (
    "render_problem_solving_lab",
    "render_thinking_lab",
    "render_thinking_topics_panel",
    "from components.problem_solving",
    "from components.thinking_lab",
    "import problem_solving",
    "import thinking_lab",
    "math_lab",
    "applied_mathematical_intelligence",
    "tab_problem_lab",
    "Math Problem Solving Lab",
    "Mathematical Problem Solving Lab",
)


def test_streamlit_app_has_no_foreign_lab_references() -> None:
    source = STREAMLIT_APP.read_text(encoding="utf-8")
    hits = [token for token in FORBIDDEN_TOKENS if token in source]
    assert not hits, (
        "streamlit_app.py references non-investment UI: "
        + ", ".join(repr(h) for h in hits)
    )
