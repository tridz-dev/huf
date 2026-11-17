"""Confirm-before-send: park a ``requires_confirmation`` tool call until the requesting user approves.

Contract (frozen): Tracks/safwan-erooth.LoyaltyCRMEnablers/N06_CONTRACT.md.

Flow: ``tool_policy.check_tool_call`` calls :func:`park` for EVERY run (gateway, web, mobile) when a tool
is flagged ``requires_confirmation``. The call is stored in ``Agent Tool Confirmation`` (canonical args
hash, requesting user, 15 min expiry, single use) and a ``confirmation_request`` is returned to the model
instead of running the tool. :func:`decide` (whitelisted) lets ONLY the requesting user approve or deny;
on approve it re-verifies the hash, re-checks permission now, executes as that user and appends the result
to the conversation. The row doubles as the audit record (who / what / when / hash).
"""

from __future__ import annotations

import hashlib
import json

import frappe
from frappe import _
from frappe.utils import add_to_date, cint, get_datetime, now_datetime

DOCTYPE = "Agent Tool Confirmation"
EXPIRY_MINUTES = 15
_SAMPLE_LEN = 200
_TRANSIENT_ARGS = ("ignore_permissions",)


class ConfirmationError(frappe.ValidationError):
	code = "confirmation_error"
	http_status_code = 400

	def __init__(self, message=""):
		super().__init__(f"{self.code}: {message}" if message else self.code)


def _err(code: str, status: int, base=ConfirmationError):
	return type(code, (base,), {"code": code, "http_status_code": status})


NotFound = _err("confirmation_not_found", 404)
Forbidden = _err("confirmation_forbidden", 403)
Expired = _err("confirmation_expired", 410)
AlreadyDecided = _err("confirmation_already_decided", 409)
ArgsChanged = _err("confirmation_args_changed", 409)
RoleDenied = _err("confirmation_role_denied", 403)
ExecutionFailed = _err("confirmation_execution_failed", 500)


# ------------------------------------------------------------------ helpers
def canonical_args(args: dict | None) -> dict:
	out = dict(args or {})
	for k in _TRANSIENT_ARGS:
		out.pop(k, None)
	return out


def args_hash(args: dict | None) -> str:
	blob = json.dumps(canonical_args(args), sort_keys=True, separators=(",", ":"), default=str)
	return hashlib.sha256(blob.encode()).hexdigest()


def _first(args: dict, *keys):
	for k in keys:
		if args.get(k) not in (None, "", [], {}):
			return args[k]
	return None


def build_summary(tool: str, args: dict) -> dict:
	args = args or {}
	rec = _first(args, "recipients", "to", "phones", "phone_numbers", "contacts", "audience_members")
	if isinstance(rec, (list, tuple, set)):
		count = len(rec)
	elif rec is not None:
		count = 1
	else:
		count = cint(_first(args, "recipient_count", "count")) or None
	text = _first(args, "message", "body", "text", "content")
	channel = _first(args, "channel", "channel_type")
	if not channel:
		channel = next((c for c in ("whatsapp", "sms", "email", "slack") if c in tool.lower()), None)
	return {
		"action": str(_first(args, "action") or tool.replace("_", " ")),
		"recipient_count": count,
		"template": _first(args, "template", "template_name"),
		"channel": channel,
		"sample": str(text)[:_SAMPLE_LEN] if text is not None else None,
	}


def _redact(obj):
	try:
		from huf.ai.secrets import redact

		return redact(obj)
	except Exception:
		return {"redacted": True}


def _serialize(doc) -> dict:
	return {
		"type": "confirmation_request",
		"id": doc.name,
		"tool": doc.tool,
		"state": doc.state,
		"summary": json.loads(doc.summary or "{}"),
		"expires_at": str(doc.expires_at),
		"conversation": doc.conversation or None,
		"requires_confirmation": True,
		"denied": doc.state != "executed",
		"message": "Awaiting user approval. The action was not executed."
		if doc.state == "pending"
		else f"Confirmation {doc.state}.",
		**({"error": doc.error} if doc.error else {}),
	}


def _publish(event_type: str, doc, agent_run=None):
	if not doc.conversation:
		return
	try:
		frappe.publish_realtime(
			event=f"conversation:{doc.conversation}",
			message={
				"type": event_type,
				"conversation_id": doc.conversation,
				"agent_run_id": agent_run or doc.agent_run,
				"confirmation": _serialize(doc),
			},
			user=doc.user,
		)
	except Exception:
		frappe.log_error(title="tool_confirmation: realtime publish failed")


# ------------------------------------------------------------------ park
def park(tool_name: str, args: dict, agent_run_id=None, conversation_id=None, agent_name=None) -> dict:
	"""Store the call and return the ``confirmation_request`` dict. Raises on failure (caller fails closed)."""
	user = frappe.session.user
	if not user or user == "Guest":
		raise Forbidden("guests cannot approve tool calls")
	args = canonical_args(args)
	doc = frappe.get_doc(
		{
			"doctype": DOCTYPE,
			"user": user,
			"tool": tool_name,
			"state": "pending",
			"conversation": conversation_id or "",
			"agent_run": agent_run_id or "",
			"agent": agent_name or "",
			"expires_at": add_to_date(now_datetime(), minutes=EXPIRY_MINUTES),
			"args_hash": args_hash(args),
			"summary": json.dumps(build_summary(tool_name, args), default=str),
			"redacted_args": json.dumps(_redact(args), default=str),
			"raw_args": json.dumps(args, default=str),
		}
	).insert(ignore_permissions=True)
	_publish("approval-requested", doc, agent_run_id)
	return _serialize(doc)


# ------------------------------------------------------------------ permission
def assert_user_may_run(tool_name: str, user: str) -> None:
	"""Re-check, at approval time, that ``user`` may still run the tool."""
	from huf.ai.tools import registry

	tool_doc = frappe.db.get_value("Agent Tool Function", {"tool_name": tool_name}, "name")
	if not tool_doc:
		raise RoleDenied(f"tool '{tool_name}' no longer exists")
	try:
		registry.assert_tool_role(frappe.get_doc("Agent Tool Function", tool_doc), user)
	except frappe.PermissionError as e:
		raise RoleDenied(str(e)) from e
	if not registry.PermissionAwareToolRegistry._can_use_tool(frappe.get_doc("Agent Tool Function", tool_doc), user):
		raise RoleDenied(f"user '{user}' may no longer use '{tool_name}'")


def assert_agent_scope(doc, user: str) -> None:
	"""Re-apply agent-level scoping at approval time (tool still on the agent, user still allowed)."""
	agent = getattr(doc, "agent", None)
	if not agent:
		return
	if not frappe.db.exists("Agent", agent):
		raise RoleDenied(f"agent '{agent}' no longer exists")
	agent_doc = frappe.get_doc("Agent", agent)
	tool_names = {
		frappe.db.get_value("Agent Tool Function", row.tool, "tool_name") for row in (agent_doc.get("agent_tool") or [])
	}
	if doc.tool not in tool_names:
		raise RoleDenied(f"tool '{doc.tool}' is no longer enabled on agent '{agent}'")
	from huf.ai.agent.access import check_agent_access

	if not check_agent_access(agent_doc, user):
		raise RoleDenied(f"user '{user}' may no longer use agent '{agent}'")


def _execute(doc, args: dict):
	from huf.ai.tools.invocation import RunContext, invoke_tool_sync

	ctx = RunContext(
		conversation_id=doc.conversation or None,
		agent_run_id=doc.agent_run or None,
		user=doc.user,
	)
	# role already re-checked in decide(); skip the shared-path role check only for this resume call
	return invoke_tool_sync(doc.tool, args, ctx=ctx, _skip_role_check=True)


def _next_index(conversation: str) -> int:
	# FOR UPDATE serialises concurrent appenders on the conversation's last rows (race-safe index).
	row = frappe.db.sql(
		"select max(conversation_index) from (select conversation_index from `tabAgent Message` "
		"where conversation=%s order by conversation_index desc limit 1 for update) t",
		conversation,
	)
	return cint(row[0][0] if row and row[0] else 0) + 1


def _append_followup(doc, state: str, result):
	if not doc.conversation or not frappe.db.exists("Agent Conversation", doc.conversation):
		return
	payload = {"type": "confirmation_result", "id": doc.name, "tool": doc.tool, "state": state, "result": result}
	frappe.get_doc(
		{
			"doctype": "Agent Message",
			"conversation": doc.conversation,
			"conversation_index": _next_index(doc.conversation),
			"content": json.dumps(payload, default=str),
			"kind": "Tool Result",
			"role": "tool",
			"is_agent_message": 1,
		}
	).insert(ignore_permissions=True)


# ------------------------------------------------------------------ API
@frappe.whitelist()
def get_pending(conversation=None):
	filters = {"user": frappe.session.user, "state": "pending", "expires_at": (">", now_datetime())}
	if conversation:
		filters["conversation"] = conversation
	names = frappe.get_all(DOCTYPE, filters=filters, pluck="name", order_by="creation asc")
	return {"confirmations": [_serialize(frappe.get_doc(DOCTYPE, n)) for n in names]}


@frappe.whitelist(methods=["POST"])
def decide(id, approve):
	if isinstance(approve, str):
		approve = approve.strip().lower() in ("1", "true", "yes")
	approve = bool(approve)
	user = frappe.session.user
	if not frappe.db.exists(DOCTYPE, id):
		raise NotFound(str(id))
	doc = frappe.get_doc(DOCTYPE, id, for_update=True)
	if doc.user != user:
		raise Forbidden("only the requesting user may decide")
	if doc.state != "pending":
		if doc.state == "expired":
			raise Expired(id)
		raise AlreadyDecided(f"{id} is {doc.state}")
	if get_datetime(doc.expires_at) <= now_datetime():
		_close(doc, state="expired")
		frappe.db.commit()
		raise Expired(id)

	doc.decision = "Approved" if approve else "Denied"
	doc.decided_by, doc.decided_at = user, now_datetime()
	result = None
	if not approve:
		doc.state = "denied"
		_close(doc, clear_args=True)
		_append_followup(doc, "denied", None)
		_publish("approval-resolved", doc)
		return {"confirmation": _serialize(doc), "result": None}

	try:
		args = json.loads(doc.raw_args or "{}")
		if args_hash(args) != doc.args_hash:
			doc.state, doc.error = "failed", "args hash mismatch"
			_close(doc, clear_args=True)
			frappe.db.commit()
			raise ArgsChanged(id)
		assert_agent_scope(doc, user)
		assert_user_may_run(doc.tool, user)
	except RoleDenied:
		doc.state, doc.error = "failed", "permission re-check failed"
		_close(doc, clear_args=True)
		frappe.db.commit()
		raise

	# Single use: mark before executing so a crash/retry can never run it twice.
	doc.state = "approved"
	_close(doc)
	frappe.db.commit()
	try:
		res = _execute(doc, args)
		result = res.as_dict() if hasattr(res, "as_dict") else res
		ok = bool(getattr(res, "success", True))
		doc.state = "executed" if ok else "failed"
		doc.result = json.dumps(_redact(result), default=str)
		if not ok:
			doc.error = str(getattr(res, "error", "") or "")[:500]
	except Exception as e:
		doc.state, doc.error = "failed", str(e)[:500]
		frappe.log_error(title="tool_confirmation: execution failed")
	_close(doc, clear_args=True)
	_append_followup(doc, doc.state, _redact(result) if result is not None else {"error": doc.error})
	_publish("approval-resolved", doc)
	if doc.state == "failed":
		# Persist the failed state, cleared raw_args and the follow-up message: Frappe rolls the
		# request back when an exception is raised, which would revert the row to "approved".
		frappe.db.commit()
		raise ExecutionFailed(doc.error or id)
	return {"confirmation": _serialize(doc), "result": result}


def _close(doc, state=None, clear_args=False):
	if state:
		doc.state = state
	if clear_args:
		doc.raw_args = ""
	doc.save(ignore_permissions=True)


def sweep_expired() -> dict:
	"""Scheduler job: expire stale pending rows and clear raw_args from every non-pending row."""
	now = now_datetime()
	expired = frappe.db.get_all(
		DOCTYPE, filters={"state": "pending", "expires_at": ("<=", now)}, pluck="name"
	)
	for name in expired:
		frappe.db.set_value(DOCTYPE, name, {"state": "expired", "raw_args": ""}, update_modified=False)
	cleared = frappe.db.get_all(
		DOCTYPE, filters={"state": ("!=", "pending"), "raw_args": ("is", "set")}, pluck="name"
	)
	for name in cleared:
		frappe.db.set_value(DOCTYPE, name, "raw_args", "", update_modified=False)
	frappe.db.commit()
	return {"expired": len(expired), "cleared": len(cleared)}
