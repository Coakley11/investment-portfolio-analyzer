"""Portfolio capture performance helpers."""

from __future__ import annotations

import portfolio_polish as pp


class _FakeSt:
    def __init__(self):
        self.session_state = {}


def test_capture_perf_helpers():
    st = _FakeSt()
    st.session_state["portfolio_screenshot_mode"] = True
    assert pp.skip_heavy_work(st)
    assert pp.skip_api_refresh(st)


def test_capture_analytics_roundtrip():
    st = _FakeSt()
    fp = pp.capture_analytics_fingerprint(["AAPL", "MSFT"], [0.6, 0.4], "2020-01-01", None, "Overview")
    assert pp.restore_capture_analytics(st, fp) is None
    pp.store_capture_analytics(st, fp, prices="cached")
    bundle = pp.restore_capture_analytics(st, fp)
    assert bundle is not None
    assert bundle["prices"] == "cached"
