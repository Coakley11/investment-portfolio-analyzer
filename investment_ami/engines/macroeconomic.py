"""Macroeconomic instant reasoning engine (P2) — rates, recession, inflation."""

from __future__ import annotations

from typing import Any

from investment_ami.engines.base import InstantEngineRequest
from investment_ami_macro import (
    _macro_inflation_solve,
    _macro_rates_solve,
    _macro_recession_solve,
)

_MACRO_SOLVERS = {
    "macro_rates": _macro_rates_solve,
    "macro_recession": _macro_recession_solve,
    "macro_inflation": _macro_inflation_solve,
}


class MacroeconomicEngine:
    """Dispatches to legacy macro solve bodies without changing narratives."""

    def __init__(self, macro_intent: str) -> None:
        self.engine_id = str(macro_intent or "").strip()
        if self.engine_id not in _MACRO_SOLVERS:
            raise KeyError(f"unknown macro intent: {self.engine_id}")

    def solve(self, request: InstantEngineRequest) -> Any:
        solver = _MACRO_SOLVERS[self.engine_id]
        result = solver(
            dict(request.context or {}),
            beginner=bool(request.beginner),
            question=str(request.question or ""),
        )
        computed = dict(getattr(result, "computed", None) or {})
        computed["ami_engine_id"] = self.engine_id
        computed.setdefault("ami_macro_intent", self.engine_id)
        try:
            result.computed = computed
        except AttributeError:
            pass
        return result


_ENGINE_CACHE: dict[str, MacroeconomicEngine] = {}


def get_macroeconomic_engine(macro_intent: str) -> MacroeconomicEngine:
    key = str(macro_intent or "").strip()
    if key not in _ENGINE_CACHE:
        _ENGINE_CACHE[key] = MacroeconomicEngine(key)
    return _ENGINE_CACHE[key]
