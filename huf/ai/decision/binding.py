"""Portable Agent Decision Binding resolution."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

# Surfaces that support Advise mode. Must match Agent Decision Binding surface options exactly.
ADVISE_SURFACES = {
	"Tool Selection",
	"Skill Selection",
	"Procedure Selection",
	"Agent Routing",
	"RAG Filter",
}


@dataclass(frozen=True, slots=True)
class ResolvedBinding:
	surface: str
	policy: str
	mode: str
	priority: int


def resolve_agent_decision_binding(agent_doc: Any, surface: str, *, requested_mode: str | None = None) -> ResolvedBinding | None:
	"""Resolve one enabled binding without coupling it to a provider.

	Bindings default to Off; callers must explicitly request Shadow or Enforce. The
	resolver returns the highest-priority matching binding and never infers one from
	the Agent's normal model/provider configuration.
	"""
	bindings: Iterable[Any] = getattr(agent_doc, "decision_bindings", None) or ()
	matches = []
	for binding in bindings:
		if not getattr(binding, "enabled", True) or getattr(binding, "surface", None) != surface:
			continue
		mode = getattr(binding, "mode", "Off") or "Off"
		if mode == "Advise" and surface not in ADVISE_SURFACES:
			mode = "Off"
		if mode == "Off" or (requested_mode is not None and mode != requested_mode):
			continue
		policy = getattr(binding, "policy", None)
		if not isinstance(policy, str) or not policy.strip():
			continue
		matches.append(ResolvedBinding(surface=surface, policy=policy, mode=mode, priority=max(0, int(getattr(binding, "priority", 100) or 0))))
	return min(matches, key=lambda item: (item.priority, item.policy)) if matches else None
