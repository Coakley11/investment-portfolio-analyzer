"""Suite resume launch public API (startup imports)."""

from __future__ import annotations


def test_hydrate_applied_intelligence_from_url_is_exported() -> None:
    from suite_resume_launch import hydrate_applied_intelligence_from_url

    assert callable(hydrate_applied_intelligence_from_url)


def test_apply_suite_resume_launch_is_exported() -> None:
    from suite_resume_launch import apply_suite_resume_launch

    assert callable(apply_suite_resume_launch)
