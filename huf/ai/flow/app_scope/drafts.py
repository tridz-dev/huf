"""The server path that saves an app editor's draft of an app-owned flow.

``definition_json`` is at permlevel 1 and app roles never get a DocPerm there. :func:`save_app_draft` is the one
way an app editor changes it: it lifts the permlevel check for that single field, and only after the submitted
graph passed a server-side allow-list. Every other check of a normal save still applies.

Allowed steps: the embed built-ins and the step types the flow's own app registers. So ``doc.create``,
``doc.update``, ``tool.call``, ``code.run`` and webhook or chat triggers are refused. A trigger may be chosen or
changed among the allowed types, but a save may not add triggers.
An Active flow's definition cannot change here at all.
"""

import json

import frappe
from frappe import _

from huf.ai.flow.catalog.node_registry import embed_builtin_types, registered_types


def save_app_draft(doc, definition_json: str) -> None:
	"""Save ``definition_json`` on the app flow ``doc`` for a non-privileged editor, or refuse it."""
	doc.check_permission("write")
	new = _parse(definition_json)
	old = _parse(doc.definition_json)
	if new == old:
		return
	if doc.status == "Active":
		_refuse(_("This flow is live. Only a draft can be changed."))
	_check_steps(doc.owner_app, _nodes(new))
	_check_triggers(_nodes(old), _nodes(new))
	doc.definition_json = definition_json
	doc.flags.ignore_permlevel_for_fields = ["definition_json"]
	doc.save()


def _refuse(message: str):
	frappe.throw(message, frappe.PermissionError)


def _parse(definition_json):
	try:
		return json.loads(definition_json) if isinstance(definition_json, str) else definition_json
	except json.JSONDecodeError:
		frappe.throw(_("Invalid JSON in definition"))


def _nodes(definition) -> list[dict]:
	nodes = definition.get("nodes") if isinstance(definition, dict) else None
	if not isinstance(nodes, list) or not all(
		isinstance(n, dict) and isinstance(n.get("type"), str) for n in nodes
	):
		_refuse(_("The flow's steps could not be read."))
	return nodes


def _check_steps(app: str, nodes: list[dict]) -> None:
	allowed = set(embed_builtin_types())
	allowed |= {type_id for type_id, node_type in registered_types().items() if node_type.app == app}
	for node in nodes:
		if node["type"] not in allowed:
			_refuse(_("Step type {0} cannot be used in this flow.").format(node["type"]))


def _check_triggers(old: list[dict], new: list[dict]) -> None:
	def count(nodes):
		return sum(n["type"].startswith("trigger.") for n in nodes)

	if count(new) > max(1, count(old)):
		_refuse(_("Triggers cannot be added to this flow."))
