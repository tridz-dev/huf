# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Who may publish a flow that reads documents, calls out to the web or starts from chat messages.

A flow always runs as its owner. Two kinds of step turn that into a way to move data out of the
system: a document-event trigger (the flow receives every matching document the owner can read) and
a web request step (``http_request``, or a tool of type GET / POST), and a chat trigger (messages from anyone who writes
to the channel start the flow). Publishing a flow that has one
of them therefore needs the ``flows.publish_sensitive`` capability, which Huf Manager and Huf Admin
(System Manager) hold by default. Other flows are published by anyone who may write flows.

Pure helpers first (no database), then the check the Flow Definition validator and ``publish_flow``
call.
"""

from __future__ import annotations

import json

import frappe
from frappe import _

from huf.ai.flow.gateways.registry import GATEWAY_NODE_TYPES

SENSITIVE_CAPABILITY = "flows.publish_sensitive"

DOC_EVENT_TYPE = "trigger.doc-event"
TOOL_CALL_TYPE = "tool.call"
HTTP_TOOL_ID = "http_request"
#: Agent Tool Function types that call a web address.
HTTP_TOOL_TYPES = ("GET", "POST")

CODE_RUN_TYPE = "code.run"

DOC_EVENT_LABEL = "a document-event trigger"
WEB_REQUEST_LABEL = "a web request step"
CODE_LABEL = "an Execute code step"
CHAT_LABEL = "a chat trigger"


def _is_web_tool(tool_id) -> bool:
	if not isinstance(tool_id, str) or not tool_id:
		return False
	if tool_id == HTTP_TOOL_ID:
		return True
	try:
		return frappe.db.get_value("Agent Tool Function", tool_id, "types") in HTTP_TOOL_TYPES
	except Exception:
		return False


def sensitive_nodes(defn) -> list[dict]:
	"""Nodes of ``defn`` that need the publish capability: ``[{"id", "label", "fingerprint"}]``."""
	found: list[dict] = []
	nodes = defn.get("nodes") if isinstance(defn, dict) else None
	for node in nodes or []:
		if not isinstance(node, dict):
			continue
		config = node.get("config") if isinstance(node.get("config"), dict) else {}
		if node.get("type") == DOC_EVENT_TYPE:
			label = DOC_EVENT_LABEL
			shape = {"doctype": config.get("doctype"), "event": config.get("event")}
		elif node.get("type") == TOOL_CALL_TYPE and _is_web_tool(config.get("tool_id")):
			label = WEB_REQUEST_LABEL
			shape = {"tool_id": config.get("tool_id"), "input": config.get("input")}
		elif node.get("type") in GATEWAY_NODE_TYPES:
			# Messages from strangers start the flow as its owner: same care as a document trigger.
			label = CHAT_LABEL
			shape = {"gateway": config.get("gateway"), "params": config.get("params")}
		elif node.get("type") == CODE_RUN_TYPE:
			from huf.ai.flow.code_node import fingerprint

			found.append({"id": node.get("id"), "label": CODE_LABEL, "fingerprint": fingerprint(node)})
			continue
		else:
			continue
		found.append(
			{
				"id": node.get("id"),
				"label": label,
				"fingerprint": json.dumps([node.get("id"), node.get("type"), shape], sort_keys=True, default=str),
			}
		)
	return found


def sensitive_labels(defn) -> list[str]:
	"""Distinct plain-language names of what in ``defn`` needs the capability (empty when nothing does)."""
	labels: list[str] = []
	for item in sensitive_nodes(defn):
		if item["label"] not in labels:
			labels.append(item["label"])
	return labels


def publish_denied_message(labels: list[str]) -> str:
	return _(
		"This flow has {0}. Only people who may publish flows that read documents or send web requests can "
		"publish it. Ask an admin to publish it for you."
	).format(" and ".join(labels))


def can_publish_sensitive(user: str | None = None) -> bool:
	from huf.permissions import has_capability

	return has_capability(user or frappe.session.user, SENSITIVE_CAPABILITY)


def check_can_publish(defn, previous_defn=None, user: str | None = None) -> None:
	"""Raise unless ``user`` may have ``defn`` Active.

	Nothing is required when the flow has no sensitive step, or when every sensitive step is exactly as
	it was in the already-Active version (``previous_defn``): editing an unrelated step of a published
	flow does not need the capability, adding or changing a sensitive one does.

	An Execute code step has its own rules on top (``huf.ai.flow.code_node.check_publish``): both code
	switches must be on, its settings sound, and a new or changed one needs ``flows.execute_code``.
	"""
	from huf.ai.flow import code_node

	code_node.check_publish(defn, previous_defn, user)
	from huf.ai.flow.gateways.authority import check_gateway_authority

	check_gateway_authority(defn, user)
	current = sensitive_nodes(defn)
	if not current:
		return
	if previous_defn is not None:
		before = {item["fingerprint"] for item in sensitive_nodes(previous_defn)}
		if all(item["fingerprint"] in before for item in current):
			return
	if can_publish_sensitive(user):
		return
	frappe.throw(publish_denied_message(sensitive_labels(defn)), frappe.PermissionError)
