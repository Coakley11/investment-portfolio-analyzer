"""AppTest: AMI cold-start Forward metrics without visiting Forward Macro."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from streamlit.testing.v1 import AppTest

_APP = ROOT / "tests" / "_ami_forward_cold_start_apptest_app.py"


def _text_map(at: AppTest) -> dict[str, str]:
    out: dict[str, str] = {}
    blocks = list(at.markdown) + list(getattr(at, "text", []))
    for attr in ("write", "caption", "code"):
        blocks.extend(list(getattr(at, attr, []) or []))
    for block in blocks:
        val = str(getattr(block, "value", block))
        if "=" in val:
            k, _, v = val.partition("=")
            out[k] = v
    return out


class TestAmiForwardColdStartAppTest(unittest.TestCase):
    def test_cold_start_no_typeerror_and_forward_metrics(self) -> None:
        at = AppTest.from_file(str(_APP), default_timeout=60)
        at.run()
        self.assertFalse(at.exception, msg=str(at.exception))
        vals = _text_map(at)
        self.assertEqual(vals.get("ok"), "1")
        self.assertEqual(vals.get("has_forward"), "True")
        self.assertEqual(vals.get("answer_has_forward"), "True")
        self.assertEqual(vals.get("engine_inputs_materialized"), "True")
        self.assertTrue(vals.get("ret"))
        self.assertTrue(vals.get("vol"))
        self.assertTrue(vals.get("sharpe"))
        # No Forward page visit; resolver materializes engine inputs from holdings.
        self.assertIn("forward_projection", at.session_state)
        self.assertIn("_forward_engine_inputs", at.session_state)


if __name__ == "__main__":
    unittest.main()
