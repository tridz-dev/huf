# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""Copy a flow, or start a new one from a template (UX-11 / UX-20).

Both end in the same place: a NEW Draft flow that the caller owns, with

* a name nobody else uses ("Order alert (copy)", "Order alert (copy 2)"),
* a fresh webhook secret (a copy must never share the original's password),
* nothing carried over that belongs to the original (published state, run samples, procedure link),
* the steps that cannot work yet listed as ``needs_setup`` (an integration that is not connected, a step that has no
  agent), so the screen can say what is left to do.

The caller needs permission to create flows; copying also needs permission to read the source flow.

Run the tests with:
    bench --site <site> run-tests --app huf --module huf.ai.flow.tests.test_flow_ux11_clone
"""

from __future__ import annotations

import copy
import json
import re
import secrets
import time

import frappe
from frappe import _

from huf.ai.api_support import require_permission
from huf.ai.flow.integrations import FLOW_INTEGRATIONS, is_connected, service_for_tool

MAX_NAME = 140
MAX_DESCRIPTION = 1000


def unique_flow_name(base: str) -> str:
	"""``base`` when free, otherwise ``base 2``, ``base 3`` ... Names are compared without regard to capitals."""
	base = (base or "").strip()[:MAX_NAME] or "Untitled flow"
	taken = {n.lower() for n in frappe.get_all("Flow Definition", filters={"flow_name": ["like", f"{base}%"]}, pluck="flow_name")}
	if base.lower() not in taken:
		return base
	number = 2
	while f"{base} {number}".lower() in taken:
		number += 1
	return f"{base} {number}"


def copy_name(source_name: str) -> str:
	"""``X (copy)``, ``X (copy 2)``... The name of a copy of ``source_name``."""
	stem = (source_name or "Untitled flow").strip()
	stem = re.sub(r" \(copy( \d+)?\)$", "", stem)
	stem = stem[: MAX_NAME - 12]
	taken = {n.lower() for n in frappe.get_all("Flow Definition", filters={"flow_name": ["like", f"{stem}%"]}, pluck="flow_name")}
	candidate = f"{stem} (copy)"
	number = 2
	while candidate.lower() in taken:
		candidate = f"{stem} (copy {number})"
		number += 1
	return candidate


def _new_flow_id() -> str:
	flow_id = f"flow-{int(time.time() * 1000)}"
	while frappe.db.exists("Flow Definition", flow_id):
		flow_id = f"flow-{int(time.time() * 1000)}{secrets.token_hex(1)}"
	return flow_id


def _first_agent() -> str | None:
	rows = frappe.get_list("Agent", filters={"disabled": 0}, pluck="name", order_by="modified desc", limit_page_length=1)
	return rows[0] if rows else None


def prepare_graph(graph: dict, *, from_template: bool) -> tuple[dict, list[dict]]:
	"""A copy of ``graph`` that is safe to save as someone else's flow, and the steps that still need setup."""
	prepared = copy.deepcopy(graph)
	needs_setup: list[dict] = []
	nodes = prepared.get("nodes") if isinstance(prepared.get("nodes"), list) else []
	for node in nodes:
		if not isinstance(node, dict):
			continue
		node.pop("_sample", None)
		config = node.get("config") if isinstance(node.get("config"), dict) else {}
		node["config"] = config
		node_type = node.get("type")
		title = node.get("_label") or node.get("id")

		if node_type == "trigger.webhook":
			config.pop("secret_hidden", None)
			config["secret"] = secrets.token_hex(24)
		elif node_type == "agent.run" and from_template:
			agent = _first_agent()
			if not agent:
				frappe.throw(
					_("This template runs an AI agent. Create an agent first (Agents), then start from the template again."),
					title=_("No agent yet"),
				)
			config["agent"] = agent
			needs_setup.append({"node_id": node.get("id"), "title": title, "what": _("Check that this is the agent you want")})
		elif node_type == "tool.call":
			service = service_for_tool(str(config.get("tool_id") or ""))
			if service and not is_connected(service):
				label = FLOW_INTEGRATIONS[service][0]
				needs_setup.append({"node_id": node.get("id"), "title": title, "what": _("Connect {0}").format(label), "service": service})
			elif from_template and service and config.get("tool_id") == "gmail_send_email":
				needs_setup.append({"node_id": node.get("id"), "title": title, "what": _("Enter who to send it to")})
	return prepared, needs_setup


def _insert_flow(*, name: str, description: str, category: str, graph: dict) -> frappe.Document:
	doc = frappe.get_doc(
		{
			"doctype": "Flow Definition",
			"flow_id": _new_flow_id(),
			"flow_name": name,
			"description": (description or "")[:MAX_DESCRIPTION],
			"category": category or "",
			"status": "Draft",
			"definition_json": json.dumps(graph),
		}
	)
	doc.insert()
	return doc


def _result(doc: frappe.Document, needs_setup: list[dict]) -> dict:
	return {"flow_id": doc.flow_id, "flow_name": doc.flow_name, "needs_setup": needs_setup}


@frappe.whitelist(methods=["POST"])
def clone_flow(flow_id: str) -> dict:
	"""Copy a flow into a new Draft named "<name> (copy)". Returns ``{flow_id, flow_name, needs_setup}``."""
	require_permission(frappe.has_permission("Flow Definition", "create"), "You are not allowed to create flows")
	if not frappe.db.exists("Flow Definition", flow_id):
		frappe.throw(_("Flow {0} was not found").format(flow_id), frappe.DoesNotExistError)
	source = frappe.get_doc("Flow Definition", flow_id)
	require_permission(frappe.has_permission("Flow Definition", "read", doc=source), "Not permitted")

	raw = source.definition_json
	graph = json.loads(raw) if isinstance(raw, str) else (raw or {})
	prepared, needs_setup = prepare_graph(graph, from_template=False)
	doc = _insert_flow(
		name=copy_name(source.flow_name),
		description=source.description or "",
		category=source.category or "",
		graph=prepared,
	)
	return _result(doc, needs_setup)


@frappe.whitelist(methods=["POST"])
def create_flow_from_template(
	name: str, definition_json: str | dict, description: str = "", category: str = ""
) -> dict:
	"""Start a new Draft flow from a template's steps (the template catalog lives in the app, see flowTemplates.ts).

	The caller supplies the graph exactly like ``save_flow_definition`` does and it is checked the same way when saved;
	what this adds is the fresh secret, the unique name and the list of steps that still need setup.
	"""
	require_permission(frappe.has_permission("Flow Definition", "create"), "You are not allowed to create flows")
	graph = json.loads(definition_json) if isinstance(definition_json, str) else definition_json
	if not isinstance(graph, dict):
		frappe.throw(_("The template is not valid"))
	prepared, needs_setup = prepare_graph(graph, from_template=True)
	doc = _insert_flow(name=unique_flow_name(name), description=description, category=category, graph=prepared)
	return _result(doc, needs_setup)
