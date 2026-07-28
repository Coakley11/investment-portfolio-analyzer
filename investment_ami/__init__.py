"""Investment AMI decision-support architecture (P1+)."""

from investment_ami.assembly.legacy_adapter import (
    attach_routing_metadata,
    solver_result_from_legacy,
)
from investment_ami.catalog.registry import (
    all_question_definitions,
    get_question_definition,
    question_for_intent,
)
from investment_ami.integration.instant_solver_facade import solve_instant_insight
from investment_ami.models.question import AmiCategory, AmiQuestionDefinition
from investment_ami.models.routing import RoutedQuestion
from investment_ami.pipeline.instant import run_instant_engine
from investment_ami.routing.router import route_instant_question

__all__ = (
    "AmiCategory",
    "AmiQuestionDefinition",
    "RoutedQuestion",
    "all_question_definitions",
    "attach_routing_metadata",
    "get_question_definition",
    "question_for_intent",
    "route_instant_question",
    "run_instant_engine",
    "solve_instant_insight",
    "solver_result_from_legacy",
)
