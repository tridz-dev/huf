"""Keep a flow's webhook secret away from people who may read a flow but not change it.

The secret in ``trigger.webhook`` ``config.secret`` is a credential: whoever has it can start the flow. Flow Definition
read access (Huf User, Huf Viewer) is wider than write access (Huf Manager, System Manager), so every path that hands a
definition to a user redacts the secret unless that user can write the flow.

Redaction is a copy: the stored definition is never touched, and the engine, the webhook check and the editors of the
flow keep working with the real value.
"""

import copy
import json

import frappe

WEBHOOK_TYPE = "trigger.webhook"


def _nodes(graph) -> list[dict]:
	nodes = graph.get("nodes") if isinstance(graph, dict) else None
	if isinstance(nodes, dict):
		nodes = list(nodes.values())
	return [n for n in (nodes or []) if isinstance(n, dict)]


def _webhook_configs(graph) -> list[dict]:
	return [n["config"] for n in _nodes(graph) if n.get("type") == WEBHOOK_TYPE and isinstance(n.get("config"), dict)]


def hide_webhook_secrets(graph):
	"""A copy of ``graph`` where every webhook secret is ``None`` and flagged ``secret_hidden: true``."""
	if not isinstance(graph, dict):
		return graph
	redacted = copy.deepcopy(graph)
	for config in _webhook_configs(redacted):
		if config.get("secret"):
			config["secret"] = None
			config["secret_hidden"] = True
	return redacted


def drop_webhook_secrets(graph):
	"""A copy of ``graph`` without webhook secrets. For snapshots a run keeps: the run never needs the caller's password."""
	if not isinstance(graph, dict):
		return graph
	stripped = copy.deepcopy(graph)
	for config in _webhook_configs(stripped):
		config.pop("secret", None)
	return stripped


def pinned_json(version) -> str:
	"""The snapshot a run keeps of its definition (``PinnedVersion.to_json`` without the webhook secrets).

	Flow Run is readable by every flow user and a run never needs the caller's password: the trigger check reads the flow itself.
	"""
	return type(version)(graph=drop_webhook_secrets(version.graph), fingerprint=version.fingerprint).to_json()


def can_see_secrets(doc) -> bool:
	"""Only people who may change the flow see its secrets (the same check that guards saving it)."""
	return bool(frappe.has_permission("Flow Definition", "write", doc=doc))


def definition_for_user(doc) -> dict:
	"""The flow's graph as the current user may see it."""
	graph = json.loads(doc.definition_json) if isinstance(doc.definition_json, str) else doc.definition_json
	return graph if can_see_secrets(doc) else hide_webhook_secrets(graph)
