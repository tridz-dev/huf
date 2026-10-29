"""What the Webhook panel needs to show "Use last received request": the most recent real call, trimmed and safe."""

import json

import frappe
from frappe import _

from huf.ai.flow.support.trigger_sample import redact_sample


@frappe.whitelist()
def get_last_webhook_request(flow_id: str) -> dict:
	"""The newest request a flow's webhook received, as a small safe sample: ``{found, sample, received_at}``.

	Only people who can edit the flow may look (the body can hold customer data); the secret and other credentials in the
	body are hidden, long text is shortened and the whole sample stays under 8 KB.
	"""
	if not flow_id or not frappe.db.exists("Flow Definition", flow_id):
		frappe.throw(_("Flow not found"), frappe.DoesNotExistError)
	if not frappe.has_permission("Flow Definition", "write", doc=flow_id):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	rows = frappe.get_all(
		"Flow Run",
		filters={"flow_id": flow_id, "trigger_type": "Webhook"},
		fields=["trigger_payload", "creation"],
		order_by="creation desc",
		limit_page_length=1,
		ignore_permissions=True,
	)
	if not rows:
		return {"found": False, "sample": None, "received_at": None}
	payload = rows[0].get("trigger_payload")
	if isinstance(payload, str):
		try:
			payload = json.loads(payload)
		except ValueError:
			payload = {"payload": payload}
	if not isinstance(payload, dict):
		payload = {"payload": payload}
	payload = {k: v for k, v in payload.items() if k not in ("_trigger",)}
	return {"found": True, "sample": redact_sample(payload), "received_at": str(rows[0].get("creation"))}
