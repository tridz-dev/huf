"""Whitelisted API of the Test tab: try one step with sample data (UX-16). Editors of the flow only.

* ``get_step_test_info(flow_id, node_id)``: how the step behaves when tested and the sample data it would receive.
* ``test_step(flow_id, node_id, sample_input=None)``: run it. See :mod:`huf.ai.flow.testrun.step_test` for the rules.
* ``list_recent_documents`` / ``get_document_sample``: a data trigger's "Pick a recent document".

Testing never creates a Flow Run, so nothing shows up in the run history. Result shape: FIELD_CONTRACT.md section 12.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

import frappe
from frappe import _

from huf.ai.flow.testrun import step_test as st
from huf.ai.flow.testrun.step_sample import SOURCE_NONE, build_sample_input, clean_sample_input, pin_value, redact_output

RECENT_DOCUMENTS = 5
_TRIGGER_KINDS = {"trigger.webhook": "webhook", "trigger.schedule": "schedule", "trigger.doc-event": "doc-event", "trigger.unset": "unset"}


def _editor_node(flow_id: str, node_id: str) -> tuple[dict, dict]:
	if not flow_id or not frappe.db.exists("Flow Definition", flow_id):
		frappe.throw(_("Flow not found"), frappe.DoesNotExistError)
	if not frappe.has_permission("Flow Definition", "write", doc=flow_id):
		frappe.throw(_("Only people who can edit this flow can test its steps."), frappe.PermissionError)
	graph = st.load_graph(flow_id)
	return graph, st.find_node(graph, node_id)


@frappe.whitelist()
def get_step_test_info(flow_id: str, node_id: str) -> dict:
	"""How the step behaves in a test (``effect``, ``calls_ai``, ``simulated``) and the data it would receive."""
	graph, node = _editor_node(flow_id, node_id)
	info = st.describe_step(node)
	out = {"flow_id": flow_id, "node_id": node_id, **info, "trigger_kind": _TRIGGER_KINDS.get(node.get("type")), "parts": [], "sample_input": {"input": {}, "steps": {}}}
	if info["trigger"]:
		out["doctype"] = (node.get("config") or {}).get("doctype")
		return out
	from huf.ai.flow.catalog.api import _latest_run

	built = build_sample_input(graph, node_id, _latest_run(flow_id), st.titles_of(graph))
	return {**out, **built}


@frappe.whitelist(methods=["POST"])
def test_step(flow_id: str, node_id: str, sample_input=None) -> dict:
	"""Run ONE step against sample data and return what it did. Nothing is sent or changed outside the flow."""
	graph, node = _editor_node(flow_id, node_id)
	st.check_rate()
	if str(node.get("type", "")).startswith("trigger."):
		return _test_trigger(flow_id, node, sample_input)
	return st.run_with_limit(flow_id, node_id, sample_input)


# --------------------------------------------------------------------------- triggers


def _trigger_result(node: dict, data, started: float, mode: str, summary: str | None, error: str | None = None) -> dict:
	meta = {"effect": "reads", "calls_ai": False, "mode": mode, "summary": summary, "preview": None, "goes_to": None, "branch": None}
	if error:
		return st._failure(node, error, started, **meta)
	return st._success(node, data, started, **meta)


def _test_trigger(flow_id: str, node: dict, sample_input) -> dict:
	started = time.monotonic()
	ntype = node.get("type")
	config = node.get("config") or {}
	try:
		given = clean_sample_input(sample_input)["input"] if sample_input is not None else None
	except ValueError as exc:
		return _trigger_result(node, None, started, "real", None, str(exc))
	if ntype == "trigger.schedule":
		now = datetime.now(timezone.utc).replace(second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
		tick = {"scheduled_for": now, "trigger_node": node["id"], "cron": config.get("cron", "")}
		return _trigger_result(node, given or tick, started, "simulated", "Pretending the schedule just fired")
	if ntype == "trigger.webhook":
		if given is None:
			from huf.ai.flow.trigger_samples_api import get_last_webhook_request

			last = get_last_webhook_request(flow_id)
			if not last.get("found"):
				return _trigger_result(node, None, started, "real", None, "No request has reached this web address yet. Send one to it, or use Wait for a test request.")
			given = last["sample"]
		return _trigger_result(node, given, started, "real", "The last request this flow received")
	if ntype == "trigger.doc-event":
		if given is None:
			docs = list_recent_documents(flow_id, node["id"])["documents"]
			if not docs:
				return _trigger_result(node, None, started, "real", None, "There are no documents of this type that you can open yet. Create one, then test again.")
			given = get_document_sample(flow_id, node["id"], docs[0]["name"])["sample"]
		return _trigger_result(node, given, started, "real", "A recent document, as this flow would receive it")
	return _trigger_result(node, None, started, "real", None, "Choose what starts this flow first, on the Setup tab.")


def _doc_trigger(flow_id: str, node_id: str) -> tuple[dict, str]:
	_, node = _editor_node(flow_id, node_id)
	doctype = (node.get("config") or {}).get("doctype")
	if node.get("type") != "trigger.doc-event" or not doctype or not frappe.db.exists("DocType", doctype):
		frappe.throw(_("Choose the kind of document this flow watches first, on the Setup tab."), frappe.ValidationError)
	return node, doctype


@frappe.whitelist()
def list_recent_documents(flow_id: str, node_id: str) -> dict:
	"""The five most recently changed documents of the watched type that the caller may open."""
	_, doctype = _doc_trigger(flow_id, node_id)
	if not frappe.has_permission(doctype, "read"):
		return {"doctype": doctype, "documents": []}
	title_field = frappe.get_meta(doctype).title_field
	fields = ["name", "modified"] + ([title_field] if title_field and title_field != "name" else [])
	rows = frappe.get_list(doctype, fields=fields, order_by="modified desc", limit_page_length=RECENT_DOCUMENTS)
	docs = [{"name": r["name"], "title": str(r.get(title_field) or r["name"]) if title_field else r["name"], "modified": str(r["modified"])} for r in rows]
	return {"doctype": doctype, "documents": docs}


@frappe.whitelist()
def get_document_sample(flow_id: str, node_id: str, docname: str) -> dict:
	"""One document as the flow would receive it when it changes (fields the caller may not read are left out)."""
	from huf.ai.flow.triggers import build_doc_event_payload

	node, doctype = _doc_trigger(flow_id, node_id)
	doc = frappe.get_doc(doctype, docname)
	doc.check_permission("read")
	payload = build_doc_event_payload(doc, frappe.session.user, (node.get("config") or {}).get("event"))
	payload.pop("_trigger", None)
	safe, shortened = redact_output(payload)
	return {"found": True, "sample": safe, "shortened": shortened, "doctype": doctype, "docname": docname}
