"""Activation-time integrity rules for Flow Definitions.

Pure functions over a parsed definition dict -- no DB, no frappe session -- so every
rule is unit-testable in isolation. Draft saves stay permissive about *semantic*
completeness (a half-built flow is a normal work-in-progress state); these rules gate
the transition to / state of ``status == "Active"``.

The shared graph-IR validator (huf.ai.graph.validator) still owns schema conformance.
"""

from __future__ import annotations

from collections import deque

from huf.ai.flow.gateways.registry import gateway_trigger_problems
from huf.ai.flow.support.schedule_rules import cron_problem, time_zone_problem
from huf.ai.graph.validator import _control_flow_targets, _entry_roots

UNSET_TRIGGER_TYPE = "trigger.unset"

# Required, non-blank string config keys per node type (mirrors graph_ir.schema.json).
REQUIRED_CONFIG_KEYS: dict[str, tuple[str, ...]] = {
	"trigger.webhook": ("method", "secret"),
	"trigger.schedule": ("cron",),
	"trigger.doc-event": ("doctype", "event"),
	"trigger.gateway": ("gateway",),
	"trigger.whatsapp": ("gateway",),
	"trigger.telegram": ("gateway",),
	"agent.run": ("agent", "prompt"),
	"tool.call": ("tool_id",),
	"router.llm": ("prompt",),
	"human.approval": ("message",),
	"condition": ("expression",),
}


def _is_blank(value) -> bool:
	return value is None or (isinstance(value, str) and not value.strip())


def entry_is_unset(defn: dict) -> bool:
	"""True if any entry root of ``defn`` is a ``trigger.unset`` node (unrunnable)."""
	nodes = {n.get("id"): n for n in (defn.get("nodes") or []) if isinstance(n, dict)}
	return any((nodes.get(root) or {}).get("type") == UNSET_TRIGGER_TYPE for root in _entry_roots(defn))


def collect_activation_problems(defn: dict) -> list[str]:
	"""Every reason ``defn`` cannot be Active, in one pass. Empty list means activatable."""
	if not isinstance(defn, dict):
		return ["definition is not a JSON object"]

	nodes = [n for n in (defn.get("nodes") or []) if isinstance(n, dict)]
	by_id = {n.get("id"): n for n in nodes}
	problems: list[str] = []

	triggers = [n for n in nodes if str(n.get("type", "")).startswith("trigger.")]
	if not triggers:
		problems.append("flow has no trigger node")
	for n in triggers:
		if n.get("type") == UNSET_TRIGGER_TYPE:
			problems.append(f"trigger {n.get('id')!r} is unset -- choose a trigger type")

	for n in nodes:
		config = n.get("config") or {}
		for key in REQUIRED_CONFIG_KEYS.get(n.get("type"), ()):
			if _is_blank(config.get(key)):
				problems.append(f"node {n.get('id')!r} ({n.get('type')}): required config {key!r} is empty")

	for n in nodes:
		if n.get("type") != "trigger.schedule":
			continue
		config = n.get("config") or {}
		# A blank cron is already reported above; only a malformed one needs its own sentence.
		issues = [] if _is_blank(config.get("cron")) else [cron_problem(config.get("cron"))]
		for issue in issues + [time_zone_problem(config.get("time_zone"))]:
			if issue:
				problems.append(f"node {n.get('id')!r} (trigger.schedule): {issue}")

	problems.extend(gateway_trigger_problems(defn))

	for n in nodes:
		for field, target in _control_flow_targets(n):
			if target not in by_id:
				problems.append(f"node {n.get('id')!r}: {field} points at nonexistent node {target!r}")
	for root in _entry_roots(defn):
		if root not in by_id:
			problems.append(f"entry points at nonexistent node {root!r}")

	seen: set = set()
	queue = deque(r for r in _entry_roots(defn) if r in by_id)
	while queue:
		nid = queue.popleft()
		if nid in seen:
			continue
		seen.add(nid)
		queue.extend(t for _, t in _control_flow_targets(by_id[nid]) if t in by_id and t not in seen)
	for n in nodes:
		if n.get("id") not in seen:
			problems.append(f"node {n.get('id')!r} is an orphan (unreachable from the entry)")

	return problems
