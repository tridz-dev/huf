"""Approvals in Slack: notify approvers with Approve/Reject buttons and decide AS THE CLICKER.

An approval (Agent Execution Approval, or a Flow Run waiting for approval) is announced to every
approver who has a Linked Slack identity on an enabled Slack gateway. The card holds one Gateway
Action Session (intended_user = approver, payload = kind + name only). On click, B1 verifies the
signed clicker, maps them to a Frappe user and consumes the session once; ``handle_click`` then
runs the EXISTING decision API with ``frappe.set_user(actor)`` so the system's own permission checks
apply. We never decide on behalf of another user and never swallow a permission error silently.
"""

from __future__ import annotations

import json

import frappe

from huf.ai.gateways.slack import blocks as bk
from huf.ai.gateways import slack_interactivity as si

KIND_PREFIX = "approval:"
KIND_EXECUTION = "approval:execution"
KIND_FLOW = "approval:flow"
APPROVAL_DOCTYPE = "Agent Execution Approval"
DEFAULT_TTL = 24 * 3600
NOTIFIED_PREFIX = "huf_slack_approval_notified:"
NOTIFIED_TTL = 7 * 24 * 3600
SKIP_USERS = {"Administrator", "Guest"}
MSG_DENIED = "You are not permitted to decide this approval."
MSG_FAILED = "Sorry, that approval could not be recorded."
COMMENT = "Decided via Slack"


# ----------------------------------------------------------------------------- notify
def notify_approvers_job(approval_name: str) -> None:
	"""Background entry point (enqueue target). Never raises."""
	try:
		notify_approvers(frappe.get_doc(APPROVAL_DOCTYPE, approval_name))
	except Exception:
		_log("Slack approval notify job failed")


def on_approval_inserted(doc, method=None) -> None:
	"""doc_events after_insert wrapper: defers to a worker after commit and never raises."""
	try:
		frappe.enqueue(
			"huf.ai.gateways.approvals.notify_approvers_job",
			approval_name=doc.name,
			enqueue_after_commit=True,
		)
	except Exception:
		_log("Slack approval enqueue failed")


def notify_approvers(approval_doc) -> int:
	"""Notify the approvers of an Agent Execution Approval. Returns the number of cards sent."""
	try:
		if str(getattr(approval_doc, "status", "Pending") or "Pending") != "Pending":
			return 0
		users = _execution_approvers(approval_doc)
		title, details = _execution_text(approval_doc)
		return _notify(KIND_EXECUTION, approval_doc.name, users, title, details,
			_ttl(getattr(approval_doc, "expires_on", None)))
	except Exception:
		_log("Slack approval notify failed")
		return 0


def notify_flow_run_approvers(flow_run) -> int:
	"""Notify the approvers of a Flow Run in "Waiting Approval". Never raises."""
	try:
		waiting = _waiting(flow_run)
		users = [u for u in (waiting.get("approver_users") or []) if isinstance(u, str)]
		role = waiting.get("approver_role")
		if role and waiting.get("approval_type", "role") == "role":
			users += _role_users(role)
		title = "Flow approval requested"
		details = f"Flow run {flow_run.name} is waiting for your approval."
		return _notify(KIND_FLOW, flow_run.name, users, title, details, DEFAULT_TTL)
	except Exception:
		_log("Slack flow approval notify failed")
		return 0


def _notify(kind, name, users, title, details, ttl) -> int:
	users = [u for u in dict.fromkeys(users) if u and u not in SKIP_USERS]
	if not users:
		return 0
	sent = 0
	for gateway in _slack_gateways():
		for user in users:
			try:
				sent += 1 if _notify_one(gateway, kind, name, user, title, details, ttl) else 0
			except Exception:
				_log("Slack approval card failed")
	return sent


def _notify_one(gateway, kind, name, user, title, details, ttl) -> bool:
	from huf.ai.gateways.slack import recipients
	from huf.ai.gateways.slack.context import get_slack_api

	key = f"{NOTIFIED_PREFIX}{gateway}:{kind}:{name}:{user}"
	if frappe.cache().get_value(key):
		return False
	slack_id = recipients.slack_id_for_user(gateway, user)
	if not slack_id:
		return False  # unlinked approver: they still have the web UI
	api = get_slack_api(gateway)
	channel = api.conversations_open([slack_id])
	if not channel:
		return False
	session = si.create_action_session(gateway, kind, {"kind": kind, "name": name},
		intended_user=user, intended_slack_user=slack_id, ttl_seconds=ttl)
	card = bk.approval_card(title, details, session)
	api.post_message(channel, text=card.fallback, blocks=card.blocks)
	frappe.cache().set_value(key, 1, expires_in_sec=NOTIFIED_TTL)
	return True


def _slack_gateways() -> list:
	return frappe.get_all("Gateway", filters={"provider": "Slack", "is_enabled": 1}, pluck="name")


def _execution_approvers(doc) -> list:
	users = [getattr(r, "user", None) for r in (getattr(doc, "approver_users", None) or [])]
	if getattr(doc, "approver_role", None):
		users += _role_users(doc.approver_role)
	requester = getattr(doc, "requested_by", None)
	return [u for u in users if u and u != requester]  # requester cannot decide by default


def _role_users(role) -> list:
	names = frappe.get_all("Has Role", filters={"role": role, "parenttype": "User"}, pluck="parent")
	if not names:
		return []
	return frappe.get_all("User", filters={"name": ["in", names], "enabled": 1}, pluck="name")


def _execution_text(doc):
	kind = str(getattr(doc, "execution_kind", None) or "code_execution").replace("_", " ")
	lines = [f"Kind: {kind}"]
	for label, field in (("Capability", "requested_capability"), ("Reference", "code_ref"),
		("Requested by", "requested_by"), ("Expires", "expires_on")):
		value = getattr(doc, field, None)
		if value:
			lines.append(f"{label}: {str(value)[:200]}")
	return "Approval requested", "\n".join(lines)


def _ttl(expires_on) -> int:
	try:
		secs = int((frappe.utils.get_datetime(expires_on) - frappe.utils.now_datetime()).total_seconds())
		return secs if secs > 0 else DEFAULT_TTL
	except Exception:
		return DEFAULT_TTL


def _waiting(flow_run) -> dict:
	raw = getattr(flow_run, "waiting", None)
	try:
		data = json.loads(raw) if isinstance(raw, str) else raw
	except (ValueError, TypeError):
		return {}
	return data if isinstance(data, dict) else {}


# ----------------------------------------------------------------------------- click
def handle_click(gateway, session, actor_user, payload=None) -> dict:
	"""Registered action handler. B1 already verified clicker == intended user and consumed the session."""
	data = session.get("payload") if hasattr(session, "get") else {}
	if isinstance(data, str):
		try:
			data = json.loads(data)
		except ValueError:
			data = {}
	data = data if isinstance(data, dict) else {}
	kind, name = str(session.get("kind") or data.get("kind") or ""), str(data.get("name") or "")
	choice = session.get("choice")
	if not actor_user or not name or choice not in ("approve", "reject") or kind not in (KIND_EXECUTION, KIND_FLOW):
		return {"text": MSG_FAILED}
	fn = _decision_fn(kind, choice)
	previous = frappe.session.user
	frappe.set_user(actor_user)
	try:
		fn(name, COMMENT)
	except Exception as exc:
		return {"text": _error_text(exc)}
	finally:
		frappe.set_user(previous)
	verb = "Approved" if choice == "approve" else "Rejected"
	label = "approval" if kind == KIND_EXECUTION else "flow approval"
	text = f"{verb} by {actor_user} at {frappe.utils.now()} ({label} {name})"
	return {"text": text, "blocks": bk.status_line(text, icon=":white_check_mark:" if choice == "approve"
		else ":no_entry_sign:").blocks}


def _decision_fn(kind, choice):
	if kind == KIND_EXECUTION:
		from huf.huf.doctype.agent_execution_approval import agent_execution_approval as mod

		return mod.approve_execution if choice == "approve" else mod.reject_execution
	from huf.ai.flow import api as flow_api

	return flow_api.approve_flow_run if choice == "approve" else flow_api.reject_flow_run


def _error_text(exc) -> str:
	if "PermissionError" in type(exc).__name__:
		return MSG_DENIED
	detail = " ".join(str(exc).split())[:200]
	return f"Could not record the decision: {detail}" if detail else MSG_FAILED


def _log(title) -> None:
	try:
		frappe.log_error(title=title)
	except Exception:
		pass


si.register_action_handler(KIND_PREFIX, handle_click)
