"""Portable top-level Hub/Agent routing contract."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from huf.ai.decision.types import DecisionResponse, DecisionStatus


@dataclass(frozen=True, slots=True)
class RouteableAgent:
	agent_name: str
	display_name: str


def get_routeable_agents(authorized_agents: Iterable[Any]) -> tuple[RouteableAgent, ...]:
	"""Build candidates from an already authorized and visible Agent resolver."""
	result = []
	seen = set()
	for agent in authorized_agents:
		name = getattr(agent, "name", None) or getattr(agent, "agent_name", None)
		if not isinstance(name, str) or not name.strip() or name in seen:
			continue
		seen.add(name)
		result.append(RouteableAgent(name, getattr(agent, "agent_name", None) or name))
	return tuple(result)


def resolve_hub_route(
	response: DecisionResponse,
	candidates: Iterable[RouteableAgent],
	*,
	uncertain_route: str = "clarify",
) -> dict[str, str]:
	"""Resolve a bounded Hub route without changing direct Agent invocation semantics."""
	candidate_ids = {candidate.agent_name for candidate in candidates}
	if response.status != DecisionStatus.SUCCESS:
		return {"route": uncertain_route, "reason": response.error_code or "decision_failed"}
	answer = next(iter(response.answers.values()), None)
	selected = answer.value if answer and isinstance(answer.value, str) else None
	if selected not in candidate_ids:
		return {"route": uncertain_route, "reason": "invalid_or_missing_agent"}
	return {"route": selected, "reason": "agent_selected"}
