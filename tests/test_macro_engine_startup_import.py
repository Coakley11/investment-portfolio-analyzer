"""Startup/import smoke: streamlit_app must resolve all macro_engine exports."""

from __future__ import annotations

import ast
import importlib
import sys
import types
import unittest
from pathlib import Path

from components.macro_engine_loader import (
    STREAMLIT_APP_MACRO_ENGINE_EXPORTS,
    load_macro_engine,
)


ROOT = Path(__file__).resolve().parents[1]


class TestMacroEngineStartupImport(unittest.TestCase):
    def test_macro_engine_defines_streamlit_exports(self) -> None:
        mod = importlib.import_module("components.macro_engine")
        missing = [n for n in STREAMLIT_APP_MACRO_ENGINE_EXPORTS if not hasattr(mod, n)]
        self.assertEqual(missing, [], f"macro_engine missing exports: {missing}")

    def test_streamlit_app_import_names_match_loader_contract(self) -> None:
        """Guard: streamlit_app must not add a direct from-import that bypasses the loader."""
        src = (ROOT / "streamlit_app.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        direct = []
        for node in tree.body:
            if isinstance(node, ast.ImportFrom) and node.module == "components.macro_engine":
                direct.extend(alias.name for alias in node.names)
        self.assertEqual(
            direct,
            [],
            "streamlit_app must use load_macro_engine(), not direct from-import "
            f"(found {direct})",
        )
        self.assertIn("load_macro_engine", src)
        for name in STREAMLIT_APP_MACRO_ENGINE_EXPORTS:
            self.assertIn(name, src)

    def test_stale_sys_modules_reload_recovers_new_symbols(self) -> None:
        """Reproduce Cloud partial-reload ImportError, then prove loader recovers."""
        stale = types.ModuleType("components.macro_engine")
        # Pre-8a85558 surface only — missing persistence exports.
        for name in (
            "get_forward_projection",
            "health_settings_fingerprint",
            "macro_assumption_summary",
            "macro_assumptions_from_session",
        ):
            setattr(stale, name, lambda *a, **k: None)
        sys.modules["components.macro_engine"] = stale

        with self.assertRaises(ImportError) as ctx:
            from components.macro_engine import ensure_shared_macro_session_defaults  # noqa: F401
        self.assertIn("ensure_shared_macro_session_defaults", str(ctx.exception))

        mod = load_macro_engine()
        self.assertTrue(hasattr(mod, "ensure_shared_macro_session_defaults"))
        self.assertTrue(hasattr(mod, "render_shared_macro_assumption_controls"))
        self.assertTrue(callable(mod.ensure_shared_macro_session_defaults))

    def test_streamlit_app_module_imports(self) -> None:
        # Drop any stale stub from prior tests before full app import.
        sys.modules.pop("components.macro_engine", None)
        sys.modules.pop("streamlit_app", None)
        mod = importlib.import_module("streamlit_app")
        for name in STREAMLIT_APP_MACRO_ENGINE_EXPORTS:
            self.assertTrue(callable(getattr(mod, name)), name)


if __name__ == "__main__":
    unittest.main()
