"""Public endpoint that resumes a run parked on a wait step, by its single-use token."""

from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit


RESUME_RATE_LIMIT = 20
RESUME_RATE_WINDOW_SECONDS = 60


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(key="flow_run", limit=RESUME_RATE_LIMIT, seconds=RESUME_RATE_WINDOW_SECONDS)
def resume_waiting_run(flow_run: str | None = None, token: str | None = None, payload: str | dict | None = None) -> dict:
	"""Resume a run parked on a wait step, by its single-use token (no login needed).

	An unknown run, a run that is not waiting, and a wrong or missing token all get the same refusal. The token
	works once: the first call wakes the run, any later call is refused. ``payload`` (at most 64 KB) is handed to
	the run, with secrets masked. At most 20 calls a minute per caller address and run.
	"""
	from huf.ai.flow.app_scope.api_guards import guard_public
	guard_public()
	from huf.ai.flow.runs import park
	from huf.ai.secrets import redact

	refusal = _("This link has already been used or is not valid.")
	if not flow_run or not token or not frappe.db.exists("Agent Flow Run", flow_run):
		frappe.throw(refusal, frappe.PermissionError)
	run = frappe.get_doc("Agent Flow Run", flow_run)
	if run.status != park.WAIT_STATUS or not park.verify_token(run, token):
		frappe.throw(refusal, frappe.PermissionError)

	if isinstance(payload, str):
		try:
			payload = json.loads(payload)
		except ValueError:
			frappe.throw(_("The payload must be valid JSON."), frappe.ValidationError)
	if payload is not None:
		if len(json.dumps(payload, default=str).encode()) > park.MAX_PAYLOAD_BYTES:
			frappe.throw(_("The payload is larger than {0} KB.").format(park.MAX_PAYLOAD_BYTES // 1024), frappe.ValidationError)
		payload = redact(payload)
	if not park.wake_run(flow_run, "resumed", payload):
		frappe.throw(refusal, frappe.PermissionError)
	return {"status": "resumed"}
