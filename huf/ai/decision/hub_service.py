"""Opt-in Hub ingress service for Decision Runtime routing."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Iterable

from huf.ai.decision.hub_routing import RouteableAgent, get_routeable_agents, resolve_hub_route
from huf.ai.decision.types import CandidateSource, DecisionRequest, Option, QuestionKind


def route_request(runtime: Any, request: DecisionRequest, backend: Any | str, authorized_agents: Iterable[Any]) -> tuple[dict[str, str], Any]:
	"""Route a Hub request using only the current authorized Agent candidates."""
	candidates = get_routeable_agents(authorized_agents)
	if not candidates:
		return {"route": "no-match", "reason": "no_authorized_agents"}, None
	options = tuple(Option(candidate.agent_name, candidate.display_name) for candidate in candidates)
	policy = replace(request.policy, questions=tuple(
		replace(question, options=options)
		if question.kind == QuestionKind.SELECT else question
		for question in request.policy.questions
	))
	request = replace(request, policy=policy, candidates=options, candidate_source=CandidateSource.AUTHORIZED_AGENTS, candidate_resolver_id="authorized_agent_resolver")
	response = runtime.evaluate(request, backend)
	return resolve_hub_route(response, candidates), response
