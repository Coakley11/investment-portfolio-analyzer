"""Smoke tests: persistence helpers are always bound in streamlit_app."""

from __future__ import annotations

from pathlib import Path

import investment_persistent_state as ips


REPO_ROOT = Path(__file__).resolve().parents[1]
STREAMLIT_APP = REPO_ROOT / "streamlit_app.py"


def test_investment_persistent_state_exports_sync_experience_after_widget() -> None:
    assert callable(ips.sync_experience_after_widget)


def test_streamlit_app_binds_sync_experience_before_import_try() -> None:
    source = STREAMLIT_APP.read_text(encoding="utf-8")
    pre_try = source.split("try:\n    from investment_persistent_state import", 1)[0]
    assert "sync_experience_after_widget = _fallback_sync_experience_after_widget" in pre_try
    assert "def _fallback_sync_experience_after_widget" in pre_try


def test_streamlit_app_imports_sync_experience_from_persistent_state() -> None:
    source = STREAMLIT_APP.read_text(encoding="utf-8")
    assert "sync_experience_after_widget," in source
