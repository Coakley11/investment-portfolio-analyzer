"""AppTest: shared macro valuation survives Health → navigate → return.

Reproduces the live failure mode the unit-only tests missed:

After a selectbox change, Streamlit updates ``_w_health_valuation`` immediately but
canonical ``health_valuation`` stays at Fair Value until Health controls commit.
If the post-select run skips Health (navigation / early rerun), Streamlit deletes
``_w_*`` at end-of-run and Valuation silently reverts to Fair Value.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from streamlit.testing.v1 import AppTest

_APP = ROOT / "tests" / "_shared_macro_apptest_app.py"


def _val_box(at: AppTest):
    return next(s for s in at.selectbox if "Valuation" in str(s.label))


def _text_map(at: AppTest) -> dict[str, str]:
    out: dict[str, str] = {}
    for block in list(at.markdown) + list(getattr(at, "text", [])):
        val = str(getattr(block, "value", block))
        if "=" in val:
            k, _, v = val.partition("=")
            out[k] = v
    return out


class TestSharedMacroAppTestPersistence(unittest.TestCase):
    def test_select_navigate_return_keeps_expensive(self) -> None:
        at = AppTest.from_file(str(_APP), default_timeout=30)
        at.run()
        self.assertFalse(at.exception)
        _val_box(at).select("Expensive")
        at.run()
        self.assertEqual(at.session_state["health_valuation"], "Expensive")

        at.radio[0].set_value("macro")
        at.run()
        self.assertEqual(at.session_state["health_valuation"], "Expensive")
        self.assertEqual(_text_map(at).get("forward"), "Expensive")

        at.radio[0].set_value("health")
        at.run()
        self.assertEqual(at.session_state["health_valuation"], "Expensive")
        self.assertEqual(_val_box(at).value, "Expensive")

    def test_immediate_skip_health_after_select_still_persists(self) -> None:
        """Selection event must commit even if the next run never re-renders Health."""
        at = AppTest.from_file(str(_APP), default_timeout=30)
        at.run()
        _val_box(at).select("Expensive")
        # Next rerun skips Health controls while `_w_*` still holds Expensive.
        at.session_state["_force_skip_health"] = True
        at.run()
        self.assertEqual(
            at.session_state["health_valuation"],
            "Expensive",
            "early harvest/on_change must commit before widget teardown",
        )
        at.session_state["_force_skip_health"] = False
        at.radio[0].set_value("macro")
        at.run()
        self.assertEqual(at.session_state["health_valuation"], "Expensive")
        self.assertEqual(_text_map(at).get("forward"), "Expensive")

    def test_other_macros_survive_navigation(self) -> None:
        at = AppTest.from_file(str(_APP), default_timeout=30)
        at.run()
        next(s for s in at.selectbox if "Interest Rate" in str(s.label)).select("Rising Rates")
        at.run()
        next(s for s in at.selectbox if "Inflation" in str(s.label)).select("High Inflation")
        at.run()
        next(s for s in at.selectbox if "Economic Regime" in str(s.label)).select("Stagflation")
        at.run()
        at.slider[0].set_value(70)
        at.run()

        self.assertEqual(at.session_state["health_rate_env"], "Rising Rates")
        self.assertEqual(at.session_state["health_inflation"], "High Inflation")
        self.assertEqual(at.session_state["health_regime"], "Stagflation")
        self.assertEqual(int(at.session_state["health_recession"]), 70)

        at.radio[0].set_value("macro")
        at.run()
        self.assertEqual(at.session_state["health_rate_env"], "Rising Rates")
        self.assertEqual(at.session_state["health_inflation"], "High Inflation")
        self.assertEqual(at.session_state["health_regime"], "Stagflation")
        self.assertEqual(int(at.session_state["health_recession"]), 70)

        at.radio[0].set_value("health")
        at.run()
        self.assertEqual(
            next(s for s in at.selectbox if "Interest Rate" in str(s.label)).value,
            "Rising Rates",
        )
        self.assertEqual(
            next(s for s in at.selectbox if "Inflation" in str(s.label)).value,
            "High Inflation",
        )
        self.assertEqual(
            next(s for s in at.selectbox if "Economic Regime" in str(s.label)).value,
            "Stagflation",
        )
        self.assertEqual(int(at.slider[0].value), 70)

    def test_changing_valuation_does_not_reset_rates(self) -> None:
        at = AppTest.from_file(str(_APP), default_timeout=30)
        at.run()
        next(s for s in at.selectbox if "Interest Rate" in str(s.label)).select("Falling Rates")
        at.run()
        _val_box(at).select("Bubble-like")
        at.run()
        self.assertEqual(at.session_state["health_rate_env"], "Falling Rates")
        self.assertEqual(at.session_state["health_valuation"], "Bubble-like")


if __name__ == "__main__":
    unittest.main()
