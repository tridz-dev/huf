"""What the "Use data" picker lists for one step of a flow: the steps before it and their fields, with real examples.

``get_data_catalog(flow_id, node_id)`` answers for people who can edit the flow (samples are request data, the same rule
as ``node._sample``). Examples come, best first, from: the sample saved on the step (``_sample``), the latest successful
run (else the latest run), the last request a webhook received, and the document type of a data trigger (field names plus one
recent record the user may read). Nothing is invented: a step with no example says so and the picker offers to get one.
"""

from __future__ import annotations

import json

import frappe
from frappe import _

from huf.ai.flow.catalog import fields as cat
from huf.ai.flow.catalog import doc_fields
from huf.ai.flow.support.trigger_sample import redact_sample

NODE_OUTPUTS_KEY = "__node_outputs__"
DOC_EVENT = "trigger.doc-event"
WEBHOOK = "trigger.webhook"

#: Step names for a flow written outside the editor (no ``_label``).
TYPE_TITLES = {
	"agent.run": "Run agent", "tool.call": "Call tool", "router.llm": "Choose a path with AI", "condition": "Check a condition",
	"foreach": "Loop", "human.approval": "Wait for approval", "output": "End", "transform": "Change data", "code.run": "Run code",
	"state.get": "Use saved data", "state.set": "Save data for later", "state.delete": "Forget saved data", "doc.create": "Create a record",
	"trigger.webhook": "Webhook", "trigger.schedule": "Schedule", "trigger.doc-event": "A document changes", "trigger.unset": "Trigger",
}
TRIGGER_WORDS = {WEBHOOK: "webhook", "trigger.schedule": "schedule", DOC_EVENT: "doc-event"}


def _json(raw):
	if isinstance(raw, (dict, list)):
		return raw
	try:
		return json.loads(raw) if raw else None
	except (TypeError, ValueError):
		return None


def _title(node: dict) -> str:
	return node.get("_label") or TYPE_TITLES.get(node.get("type")) or node["id"]


def _step_tool(node: dict) -> str | None:
	config = node.get("config") or {}
	return config.get("tool_id") if node.get("type") == "tool.call" else None


def _latest_run(flow_id: str) -> dict | None:
	for filters in ({"flow_id": flow_id, "status": "Success"}, {"flow_id": flow_id}):
		rows = frappe.get_all(
			"Flow Run",
			filters=filters,
			fields=["name", "creation", "trigger_payload", "context_json", "trigger_type"],
			order_by="creation desc",
			limit_page_length=1,
			ignore_permissions=True,
		)
		if rows:
			return rows[0]
	return None


def _run_payload(run: dict | None) -> dict | None:
	payload = _json(run.get("trigger_payload")) if run else None
	if isinstance(payload, dict):
		payload = {k: v for k, v in payload.items() if k != "_trigger"}
		return payload or None
	return None


def _run_outputs(run: dict | None) -> dict:
	ctx = _json(run.get("context_json")) if run else None
	outputs = ctx.get(NODE_OUTPUTS_KEY) if isinstance(ctx, dict) else None
	return outputs if isinstance(outputs, dict) else {}


def _meta_fields(doctype: str) -> list:
	return list(frappe.get_meta(doctype).fields)


def _doctype_fields(doctype: str, payload: dict | None) -> tuple[list[dict], dict | None, str]:
	"""Fields of a data trigger's document type, the record the examples come from and where it came from."""
	if not frappe.db.exists("DocType", doctype):
		return [], None, "none"
	record, source = payload, "last_run"
	if not record and frappe.has_permission(doctype, "read"):
		meta = frappe.get_meta(doctype)
		readable = [
			f.fieldname for f in meta.fields
			if doc_fields.kind_of(f.fieldtype) not in (None, "list") and f.fieldtype != "Password"
		]
		rows = frappe.get_list(doctype, fields=["name", "creation", "modified", "owner", *readable], order_by="modified desc", limit_page_length=1)
		record, source = (rows[0] if rows else None), "doctype"
	record = redact_sample(record) if isinstance(record, dict) else None
	link_meta = lambda dt: _meta_fields(dt) if frappe.has_permission(dt, "read") else []  # noqa: E731
	fields = doc_fields.doctype_fields(_meta_fields(doctype), record, child_fields=_meta_fields, link_meta=link_meta)
	return fields, record, ("last_run" if payload else source if record else "doctype")


def _trigger_step(graph: dict, flow_id: str, run: dict | None) -> dict | None:
	nodes = cat.graph_nodes(graph)
	triggers = [n for n in nodes if str(n.get("type", "")).startswith("trigger.")]
	if not triggers:
		return None
	entry = [t for t in triggers if t["id"] in (graph.get("entry") if isinstance(graph.get("entry"), list) else [graph.get("entry")])]
	pool = entry or triggers
	node = next((t for t in pool if isinstance(t.get("_sample"), dict)), pool[0])
	kind = TRIGGER_WORDS.get(node.get("type"), "unset")
	pinned = node.get("_sample") if isinstance(node.get("_sample"), dict) else None
	payload = _run_payload(run)
	step = {
		"id": node["id"], "title": _title(node), "type": node.get("type"), "kind": kind, "is_trigger": True,
		"source": "none", "ran_at": None, "fields": [], "has_sample": False,
		"last_request_available": False, "doctype": None,
	}
	if node.get("type") == DOC_EVENT:
		doctype = (node.get("config") or {}).get("doctype")
		step["doctype"] = doctype
		if doctype:
			fields, record, source = _doctype_fields(doctype, pinned or payload)
			step.update(fields=fields, has_sample=bool(record), source="pinned" if pinned else source)
			step["ran_at"] = str(run["creation"]) if run and source == "last_run" else None
		return step
	if pinned:
		step.update(fields=cat.infer_fields(pinned, "input", root_label="What the trigger sent"), source="pinned", has_sample=True)
	elif payload:
		step.update(
			fields=cat.infer_fields(redact_sample(payload), "input", root_label="What the trigger sent"),
			source="last_run", has_sample=True, ran_at=str(run["creation"]),
		)
	if node.get("type") == WEBHOOK:
		step["last_request_available"] = bool(frappe.db.exists("Flow Run", {"flow_id": flow_id, "trigger_type": "Webhook"}))
	return step


def build_catalog(graph: dict, node_id: str, flow_id: str, run: dict | None) -> dict:
	"""The picker's data for ``node_id`` (separate from the whitelist wrapper so it is easy to test with a fake run)."""
	nodes = cat.graph_nodes(graph)
	by_id = {n["id"]: n for n in nodes}
	outputs = _run_outputs(run)
	depth = cat.depth_from_entry(graph)
	steps: list[dict] = []
	for pid in cat.guaranteed_predecessors(graph, node_id):
		node = by_id.get(pid)
		if not node or str(node.get("type", "")).startswith("trigger."):
			continue
		pinned = node.get("_sample") if isinstance(node.get("_sample"), dict) else None
		output = outputs.get(pid)
		sample = pinned if pinned is not None else output
		fields = cat.infer_fields(redact_sample(sample), pid) if sample not in (None, "") else []
		steps.append(
			{
				"id": pid, "title": _title(node), "type": node.get("type"), "tool_id": _step_tool(node), "is_trigger": False,
				"source": "pinned" if pinned is not None else ("last_run" if fields else "none"),
				"ran_at": str(run["creation"]) if run and pid in outputs else None,
				"fields": fields, "has_sample": bool(fields),
			}
		)
	steps.sort(key=lambda s: -depth.get(s["id"], 0))  # closest to this step first
	trigger = _trigger_step(graph, flow_id, run)
	loop = None
	loop_node = cat.enclosing_loop(graph, node_id)
	if loop_node:
		items = (loop_node.get("config") or {}).get("items")
		items_path = items.get("$from") if isinstance(items, dict) else None
		pool = [s for s in [trigger, *steps] if s]
		loop = {
			"id": loop_node["id"], "title": _title(loop_node), "items_path": items_path,
			"item_fields": cat.loop_item_fields(items_path, pool),
		}
	cat.trim_to_budget([s for s in [trigger, *steps] if s])
	return {"flow_id": flow_id, "node_id": node_id, "trigger": trigger, "steps": steps, "loop": loop}


@frappe.whitelist()
def get_data_catalog(flow_id: str, node_id: str) -> dict:
	"""Steps before ``node_id`` and the data each offers, for the "Use data" picker. Editors of the flow only."""
	if not flow_id or not frappe.db.exists("Flow Definition", flow_id):
		frappe.throw(_("Flow not found"), frappe.DoesNotExistError)
	if not frappe.has_permission("Flow Definition", "write", doc=flow_id):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	graph = _json(frappe.db.get_value("Flow Definition", flow_id, "definition_json"))
	if not isinstance(graph, dict):
		return {"flow_id": flow_id, "node_id": node_id, "trigger": None, "steps": [], "loop": None}
	return build_catalog(graph, node_id, flow_id, _latest_run(flow_id))
