"""Suite resume launch public API (startup imports)."""

from __future__ import annotations

import importlib


def test_hydrate_applied_intelligence_from_url_is_exported() -> None:
    from suite_resume_launch import hydrate_applied_intelligence_from_url

    assert callable(hydrate_applied_intelligence_from_url)


def test_hydrate_canonical_module_matches_resume_reexport() -> None:
    from suite_ami_startup_hydrate import hydrate_applied_intelligence_from_url as canonical
    from suite_resume_launch import hydrate_applied_intelligence_from_url as reexported

    assert canonical is reexported


def test_probe_suite_resume_launch_compat() -> None:
    from suite_ami_startup_hydrate import probe_suite_resume_launch_compat

    probe = probe_suite_resume_launch_compat()
    assert probe.get("canonical_hydrate_callable") is True
    assert probe.get("suite_resume_launch_has_hydrate") is True
    assert importlib.util.find_spec("suite_resume_launch") is not None


def test_apply_suite_resume_launch_is_exported() -> None:
    from suite_resume_launch import apply_suite_resume_launch

    assert callable(apply_suite_resume_launch)
