"""Inbound pre-route hook pipeline.

Hooks run once per real inbound event, before the route (agent/Solution) is chosen.
Each hook is ``hook(context: dict) -> Decision | None``; the first Decision whose action is not
"continue" wins. With no hooks registered the pipeline returns None and routing is unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import frappe

ACTIONS = ("continue", "reply", "route", "handoff", "drop")

# Dotted paths of hook callables. Later WPs append here.
PRE_ROUTE_HOOKS: list[str] = [
	"huf.ai.channels.hours.business_hours_hook",
	"huf.ai.channels.rules.routing_rules_hook",
]


@dataclass
class Decision:
	action: str = "continue"
	payload: dict[str, Any] = field(default_factory=dict)


def _hook_paths() -> list[str]:
	paths = list(PRE_ROUTE_HOOKS)
	try:
		for entry in frappe.get_hooks("huf_channel_pre_route") or []:
			if entry not in paths:
				paths.append(entry)
	except Exception:
		pass
	return paths


def run_pre_route(context: dict) -> Decision | None:
	"""Run hooks in order; return the first non-"continue" Decision, else None."""
	for path in _hook_paths():
		try:
			hook = frappe.get_attr(path)
			decision = hook(context)
		except Exception:
			frappe.log_error(title=f"huf pre-route hook failed: {path}")
			continue
		if isinstance(decision, Decision) and decision.action in ACTIONS and decision.action != "continue":
			return decision
	return None
