"""Resume URL import path and Investment instant insight staging."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from music_resume_payload import decode_payload_b64, encode_payload_b64
from suite_analytical_question import (
    _stage_investment_instant_insight,
    build_applied_math_resume_url,
    build_question_payload,
)


class TestMusicResumePayload(unittest.TestCase):
    def test_roundtrip_encode_decode(self) -> None:
        payload = {"resume_kind": "backing", "pick_key": "abc123", "bpm": 120}
        encoded = encode_payload_b64(payload)
        self.assertTrue(encoded)
        restored = decode_payload_b64(encoded)
        self.assertEqual(restored.get("pick_key"), "abc123")
        self.assertEqual(restored.get("resume_kind"), "backing")


class TestInvestmentResumeUrl(unittest.TestCase):
    def test_build_applied_math_resume_url_imports_without_music_failure(self) -> None:
        payload = build_question_payload(
            source_app="investment",
            source_page="Portfolio Health",
            question="What happens if rates rise?",
            context={"page": "Portfolio Health"},
        )
        url = build_applied_math_resume_url(payload)
        self.assertIn("applied-mathematical-intelligence", url)
        self.assertIn("suite_", url)


class TestInvestmentStageAfterResumeUrl(unittest.TestCase):
    def test_stage_creates_pending_insight_for_macro(self) -> None:
        st = MagicMock()
        ss: dict = {}
        st.session_state = ss
        st.columns = lambda n: [MagicMock() for _ in range(max(int(n), 1))]
        ctx = {
            "page": "Portfolio Health",
            "experience_mode": "Advanced Mode",
            "current_weights": {"VOO": "50%", "BND": "50%"},
        }
        pre = build_question_payload(
            source_app="investment",
            source_page="Portfolio Health",
            question="What happens if rates rise?",
            context=ctx,
        )
        url = build_applied_math_resume_url(pre)
        with patch("applied_math_return_insight.store_applied_math_insight"):
            ok = _stage_investment_instant_insight(
                st,
                ss,
                question=pre["question"],
                source_app="investment",
                source_page="Portfolio Health",
                submit_ctx=ctx,
                submit_source_state={},
                pre_payload=pre,
                action_url_pre=url,
            )
        self.assertTrue(ok)
        pending = ss.get("_ami_pending_insight")
        self.assertIsInstance(pending, dict)
        conclusion = str(pending.get("conclusion") or "")
        self.assertTrue(conclusion)
        self.assertIn("Macro Outlook", conclusion)


if __name__ == "__main__":
    unittest.main()
