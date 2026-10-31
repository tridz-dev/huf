"""Test-run data for the chat trigger nodes: a sample message and "the last real message", numbers masked. Never sends.

* ``get_gateway_sample(flow_id, node_id)``: the registry's example message for this node (nothing real).
* ``get_last_gateway_message(flow_id, node_id)``: the newest message that really started this flow from this node's
  channel, trimmed (``redact_sample``) and with phone numbers masked to their last four digits.

Only people who can edit the flow may ask. Testing creates no Gateway Event and no Flow Run (see ``step_test_api``).
"""

from __future__ import annotations

import json

import frappe
from frappe import _

from huf.ai.flow.gateways.registry import GATEWAY_NODE_TYPES, get_gateway_trigger_spec
from huf.ai.flow.gateways.phone_mask import mask_sample
from huf.ai.flow.support.trigger_sample import redact_sample

SCAN_RUNS = 25
_DROP = ("_trigger", "gateway_event", "attachments")


def safe_message(payload) -> dict:
	"""A real message made safe to show a flow editor: no record ids or files, secrets hidden, numbers masked."""
	payload = payload if isinstance(payload, dict) else {"payload": payload}
	return mask_sample(redact_sample({k: v for k, v in payload.items() if k not in _DROP}))


def sample_for_node(node: dict) -> dict:
	"""The registry's example message for ``node`` (provider-specific for the dedicated nodes), channel name filled in."""
	provider = frappe.db.get_value("Gateway", (node.get("config") or {}).get("gateway"), "provider") if (node.get("config") or {}).get("gateway") else None
	spec = get_gateway_trigger_spec(provider, node.get("type"))
	sample = dict(spec["sample_payload"])
	if (node.get("config") or {}).get("gateway"):
		sample["gateway"] = node["config"]["gateway"]
	return mask_sample(sample)


def _gateway_node(flow_id: str, node_id: str) -> dict:
	from huf.ai.flow.testrun import step_test as st

	if not flow_id or not frappe.db.exists("Flow Definition", flow_id):
		frappe.throw(_("Flow not found"), frappe.DoesNotExistError)
	if not frappe.has_permission("Flow Definition", "write", doc=flow_id):
		frappe.throw(_("Only people who can edit this flow can use its messages."), frappe.PermissionError)
	node = st.find_node(st.load_graph(flow_id), node_id)
	if node.get("type") not in GATEWAY_NODE_TYPES:
		frappe.throw(_("This step is not a chat trigger."), frappe.ValidationError)
	return node


@frappe.whitelist()
def get_gateway_sample(flow_id: str, node_id: str) -> dict:
	"""``{found: True, sample, real: False}``: an invented example for the node; nothing is sent."""
	node = _gateway_node(flow_id, node_id)
	return {"found": True, "sample": sample_for_node(node), "real": False}


@frappe.whitelist()
def get_last_gateway_message(flow_id: str, node_id: str) -> dict:
	"""``{found, sample, received_at, real: True}``: the newest real message for this node's channel, numbers masked."""
	node = _gateway_node(flow_id, node_id)
	gateway = str((node.get("config") or {}).get("gateway") or "")
	if not gateway:
		return {"found": False, "sample": None, "received_at": None, "real": True}
	if not frappe.has_permission("Gateway", "read", doc=gateway):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	rows = frappe.get_all(
		"Flow Run",
		filters={"flow_id": flow_id, "trigger_type": "Gateway"},
		fields=["trigger_payload", "creation"],
		order_by="creation desc",
		limit_page_length=SCAN_RUNS,
		ignore_permissions=True,
	)
	for row in rows:
		payload = row.get("trigger_payload")
		if isinstance(payload, str):
			try:
				payload = json.loads(payload)
			except ValueError:
				continue
		if isinstance(payload, dict) and payload.get("gateway") == gateway:
			return {"found": True, "sample": safe_message(payload), "received_at": str(row.get("creation")), "real": True}
	return {"found": False, "sample": None, "received_at": None, "real": True}
