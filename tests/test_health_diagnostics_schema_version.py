"""Health diagnostics schema-version invalidation (startup-safe)."""

from __future__ import annotations

import math
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np

import portfolio_core as core


class TestNormalizeHealthDiagnosticsSchemaVersion(unittest.TestCase):
    def test_current_constant_exists_and_is_int(self) -> None:
        self.assertTrue(hasattr(core, "HEALTH_DIAGNOSTICS_SCHEMA_VERSION"))
        self.assertIsInstance(core.HEALTH_DIAGNOSTICS_SCHEMA_VERSION, int)
        self.assertGreaterEqual(core.HEALTH_DIAGNOSTICS_SCHEMA_VERSION, 1)

    def test_missing_and_malformed_normalize_to_none(self) -> None:
        self.assertIsNone(core.normalize_health_diagnostics_schema_version(None))
        self.assertIsNone(core.normalize_health_diagnostics_schema_version(""))
        self.assertIsNone(core.normalize_health_diagnostics_schema_version("  "))
        self.assertIsNone(core.normalize_health_diagnostics_schema_version("abc"))
        self.assertIsNone(core.normalize_health_diagnostics_schema_version(True))
        self.assertIsNone(core.normalize_health_diagnostics_schema_version(False))
        self.assertIsNone(core.normalize_health_diagnostics_schema_version(float("nan")))
        self.assertTrue(math.isnan(float("nan")))

    def test_numeric_and_string_forms(self) -> None:
        self.assertEqual(core.normalize_health_diagnostics_schema_version(3), 3)
        self.assertEqual(core.normalize_health_diagnostics_schema_version(3.0), 3)
        self.assertEqual(core.normalize_health_diagnostics_schema_version("3"), 3)
        self.assertEqual(core.normalize_health_diagnostics_schema_version("3.0"), 3)
        self.assertEqual(core.normalize_health_diagnostics_schema_version(2), 2)


class TestHealthDiagnosticsSchemaIsCurrent(unittest.TestCase):
    def test_fresh_session_no_schema_version(self) -> None:
        self.assertFalse(core.health_diagnostics_schema_is_current({}))
        self.assertFalse(core.health_diagnostics_schema_is_current(None))
        self.assertFalse(core.health_diagnostics_schema_is_current("not-a-dict"))

    def test_old_numeric_schema_version(self) -> None:
        self.assertFalse(
            core.health_diagnostics_schema_is_current({"_schema_version": 1})
        )
        self.assertFalse(
            core.health_diagnostics_schema_is_current({"_schema_version": 2.0})
        )

    def test_current_schema_version(self) -> None:
        cur = core.HEALTH_DIAGNOSTICS_SCHEMA_VERSION
        self.assertTrue(
            core.health_diagnostics_schema_is_current({"_schema_version": cur})
        )
        self.assertTrue(
            core.health_diagnostics_schema_is_current({"_schema_version": float(cur)})
        )
        self.assertTrue(
            core.health_diagnostics_schema_is_current({"_schema_version": str(cur)})
        )

    def test_malformed_string_schema_version(self) -> None:
        self.assertFalse(
            core.health_diagnostics_schema_is_current({"_schema_version": "v3"})
        )
        self.assertFalse(
            core.health_diagnostics_schema_is_current({"_schema_version": "n/a"})
        )


class TestGetHealthCacheStatusSchemaSafe(unittest.TestCase):
    """Startup path must not AttributeError/TypeError on schema checks."""

    def _call_status(self, session: dict) -> str:
        tickers = ["VTI", "BND"]
        weights = np.array([0.6, 0.4])
        fp = "VTI:0.6000|BND:0.4000"
        session.setdefault("health_result_fingerprint", fp)
        session.setdefault("health_settings_fingerprint", "settings-ok")

        fake_st = MagicMock()
        fake_st.session_state = session

        with patch("streamlit_app.st", fake_st), patch(
            "streamlit_app.health_settings_fingerprint", return_value="settings-ok"
        ), patch(
            "streamlit_app._portfolio_fingerprint", return_value=fp
        ):
            from streamlit_app import get_health_cache_status

            return get_health_cache_status(tickers, weights)

    def test_missing_health_result_is_missing(self) -> None:
        status = self._call_status({})
        self.assertEqual(status, "missing")

    def test_no_schema_version_invalidates(self) -> None:
        session = {
            "health_result": SimpleNamespace(health_diagnostics={}),
        }
        status = self._call_status(session)
        self.assertEqual(status, "missing")
        self.assertNotIn("health_result", session)

    def test_old_schema_invalidates(self) -> None:
        session = {
            "health_result": SimpleNamespace(
                health_diagnostics={"_schema_version": 1}
            ),
            "health_summary": {"score": 80},
        }
        status = self._call_status(session)
        self.assertEqual(status, "missing")
        self.assertNotIn("health_result", session)
        self.assertNotIn("health_summary", session)

    def test_current_schema_is_fresh(self) -> None:
        cur = core.HEALTH_DIAGNOSTICS_SCHEMA_VERSION
        session = {
            "health_result": SimpleNamespace(
                health_diagnostics={"_schema_version": cur}
            ),
        }
        status = self._call_status(session)
        self.assertEqual(status, "fresh")
        self.assertIn("health_result", session)

    def test_malformed_schema_invalidates_without_raising(self) -> None:
        session = {
            "health_result": SimpleNamespace(
                health_diagnostics={"_schema_version": "broken"}
            ),
        }
        status = self._call_status(session)
        self.assertEqual(status, "missing")

    def test_float_stored_current_schema_is_fresh(self) -> None:
        """Legacy sessions may have stored float(schema)."""
        cur = float(core.HEALTH_DIAGNOSTICS_SCHEMA_VERSION)
        session = {
            "health_result": SimpleNamespace(
                health_diagnostics={"_schema_version": cur}
            ),
        }
        status = self._call_status(session)
        self.assertEqual(status, "fresh")


if __name__ == "__main__":
    unittest.main()
