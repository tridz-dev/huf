"""Approvals in Microsoft Teams: Adaptive Card to each approver's personal chat, decided AS THE CLICKER.

``on_approval_inserted`` (doc_events) enqueues ``notify_approvers_job``; each approver with a linked
Teams identity and an installed personal chat gets one card holding one Teams Action Session
(opaque; payload = approval kind + name only). The invoke handler is a ``pre_ingest_filter`` for
``card_action`` activities: the clicker comes ONLY from the verified activity (tenant + aadObjectId ->
Huf user), the session must match gateway / tenant / conversation, the first valid click wins with
ONE conditional UPDATE (Open -> Decided), and the existing Agent Execution Approval API runs under
``frappe.set_user(clicker)`` so the system's own permission checks apply. The synchronous invoke
answer is handed to ``handle_gateway_webhook`` via ``frappe.local.gateway_response_override``.
Slice 1 handles Agent Execution Approval only.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

import frappe

from huf.ai.gateways import hooks
from huf.ai.gateways import teams_cards as cards
from huf.ai.gateways import teams_contract as tc
from huf.ai.gateways import teams_identity, teams_notify, teams_outbox, teams_refs

DOCTYPE = "Teams Action Session"
APPROVAL_DOCTYPE = "Agent Execution Approval"
KIND_EXECUTION = "approval:execution"
HOOK_PROVIDER = tc.PROVIDER_LABEL.lower()
DEFAULT_TTL = 24 * 3600
NOTIFIED_PREFIX = "huf_teams_approval_notified:"
NOTIFIED_TTL = 7 * 24 * 3600
SKIP_USERS = {"Administrator", "Guest"}
COMMENT = "Decided via Microsoft Teams"
MAX_SESSION_NAME = 140

MSG_UNLINKED = "Your Teams account is not connected to Huf. Send connect in a personal chat with me."
MSG_UNAVAILABLE = "This action is not available."
MSG_DENIED = "You are not permitted to decide this approval."
MSG_FAILED = "Sorry, that approval could not be recorded."
MSG_DECIDED = "This approval was already decided."
MSG_EXPIRED = "This approval has expired."
MSG_NOT_PENDING = "This approval is no longer pending."


def _log(title) -> None:
	try:
		frappe.log_error(title=title)
	except Exception:
		pass


def _s(value: Any) -> str:
	return str(value) if value else ""


# ----------------------------------------------------------------------------- notify
def on_approval_inserted(doc, method=None) -> None:
	"""doc_events after_insert wrapper: defer to a worker after commit; never raises into creation."""
	try:
		frappe.enqueue(
			"huf.ai.gateways.teams_actions.notify_approvers_job",
			approval_name=doc.name,
			enqueue_after_commit=True,
		)
	except Exception:
		_log("Teams approval enqueue failed")


def notify_approvers_job(approval_name: str) -> None:
	try:
		notify_approvers(frappe.get_doc(APPROVAL_DOCTYPE, approval_name))
	except Exception:
		_log("Teams approval notify job failed")


def notify_approvers(approval_doc) -> int:
	"""Send the approval card to every approver reachable in Teams. Returns the number queued."""
	try:
		if str(getattr(approval_doc, "status", "Pending") or "Pending") != "Pending":
			return 0
		sent = 0
		for user in _execution_approvers(approval_doc):
			try:
				sent += 1 if create_approval_card(approval_doc, user) else 0
			except Exception:
				_log("Teams approval card failed")
		return sent
	except Exception:
		_log("Teams approval notify failed")
		return 0


def create_approval_card(approval, approver_user: str) -> int:
	"""Queue the approval card to ``approver_user``'s personal chat on every enabled Teams gateway.

	Returns the number of cards queued (0 when the approver has no linked identity or no installed
	personal chat: they still have the web UI). ``approval`` is a doc or a name.
	"""
	if not approver_user or approver_user in SKIP_USERS:
		return 0
	doc = frappe.get_doc(APPROVAL_DOCTYPE, approval) if isinstance(approval, str) else approval
	title, facts = _approval_text(doc)
	ttl = _ttl(getattr(doc, "expires_on", None))
	queued = 0
	for gateway in _teams_gateways():
		if _queue_one(gateway, doc, approver_user, title, facts, ttl):
			queued += 1
	return queued


def _queue_one(gateway, doc, user, title, facts, ttl) -> bool:
	key = f"{NOTIFIED_PREFIX}{gateway}:{doc.name}:{user}"
	if frappe.cache().get_value(key):
		return False
	info = teams_notify.teams_user_reference(gateway, user)
	ref = (info or {}).get("reference")
	if not (info and ref and ref.get("conversation_id") and ref.get("service_url")):
		return False
	tenant = info["tenant_id"]
	session = create_action_session(gateway, KIND_EXECUTION, {"kind": KIND_EXECUTION, "name": doc.name},
		intended_user=user, tenant_id=tenant, conversation_id=ref["conversation_id"], ttl_seconds=ttl)
	card, fallback = cards.approval_card(session, title, facts)
	activity = cards.activity_with_card(card, fallback)
	snapshot = {
		"conversation_ref": ref.get("name"),
		"conversation_id": ref["conversation_id"],
		"service_url": ref["service_url"],
		"tenant_id": tenant,
	}
	idem = "teams-approval-" + hashlib.sha256(f"{gateway}|{session}".encode()).hexdigest()[:32]
	teams_outbox.enqueue(gateway, snapshot, "card", {"activity": activity}, idem)
	frappe.cache().set_value(key, 1, expires_in_sec=NOTIFIED_TTL)
	return True


def record_card_activity(session_name: str, activity_id: str) -> None:
	"""Remember the Teams activity id of the delivered card (for later card updates)."""
	if session_name and activity_id:
		frappe.db.set_value(DOCTYPE, session_name, "card_activity_id", str(activity_id)[:140])


def _teams_gateways() -> list:
	return frappe.get_all("Gateway", filters={"provider": tc.PROVIDER_LABEL, "is_enabled": 1}, pluck="name")


def _execution_approvers(doc) -> list:
	users = [getattr(r, "user", None) for r in (getattr(doc, "approver_users", None) or [])]
	if getattr(doc, "approver_role", None):
		users += _role_users(doc.approver_role)
	requester = getattr(doc, "requested_by", None)
	return [u for u in dict.fromkeys(users) if u and u != requester and u not in SKIP_USERS]


def _role_users(role) -> list:
	names = frappe.get_all("Has Role", filters={"role": role, "parenttype": "User"}, pluck="parent")
	if not names:
		return []
	return frappe.get_all("User", filters={"name": ["in", names], "enabled": 1}, pluck="name")


def _approval_text(doc):
	kind = str(getattr(doc, "execution_kind", None) or "code_execution").replace("_", " ")
	facts = [("Kind", kind)]
	for label, field in (("Capability", "requested_capability"), ("Reference", "code_ref"),
		("Expires", "expires_on")):
		value = getattr(doc, field, None)
		if value:
			facts.append((label, str(value)[:200]))
	return "Approval requested", facts


def _ttl(expires_on) -> int:
	try:
		secs = int((frappe.utils.get_datetime(expires_on) - frappe.utils.now_datetime()).total_seconds())
		return secs if secs > 0 else DEFAULT_TTL
	except Exception:
		return DEFAULT_TTL


# ----------------------------------------------------------------------------- sessions
def create_action_session(gateway, kind, payload=None, intended_user=None, tenant_id=None,
		conversation_id=None, ttl_seconds=DEFAULT_TTL) -> str:
	expires = frappe.utils.add_to_date(frappe.utils.now_datetime(), seconds=int(ttl_seconds or DEFAULT_TTL))
	doc = frappe.get_doc({
		"doctype": DOCTYPE,
		"gateway": gateway,
		"kind": kind,
		"state": "Open",
		"expires_at": expires,
		"intended_user": intended_user,
		"tenant_id": tenant_id,
		"conversation_id": teams_refs._base_conversation_id(conversation_id or ""),
		"payload": json.dumps(payload or {}),
	})
	doc.insert(ignore_permissions=True)
	return doc.name


def _rowcount() -> int:
	cursor = getattr(frappe.db, "_cursor", None)
	return int(getattr(cursor, "rowcount", 0) or 0)


def consume_session(name: str, actor: str) -> str:
	"""Atomically move Open -> Decided for ``actor``. Returns ok | decided | expired | unknown."""
	now = frappe.utils.now()
	frappe.db.sql(
		f"UPDATE `tab{DOCTYPE}` SET state='Decided', decided_by=%s "
		"WHERE name=%s AND state='Open' AND expires_at > %s",
		(actor, name, now),
	)
	if _rowcount() == 1:
		return "ok"
	state = frappe.db.get_value(DOCTYPE, name, "state")
	if state is None:
		return "unknown"
	if state == "Decided":
		return "decided"
	if state == "Open":
		frappe.db.sql(f"UPDATE `tab{DOCTYPE}` SET state='Expired' WHERE name=%s AND state='Open'", (name,))
	return "expired"


def release_session(name: str, actor: str) -> bool:
	"""Re-open a session this request consumed (still undecided: no decision recorded)."""
	frappe.db.sql(
		f"UPDATE `tab{DOCTYPE}` SET state='Open', decided_by=NULL "
		"WHERE name=%s AND state='Decided' AND decided_by=%s AND (decision IS NULL OR decision='')",
		(name, actor),
	)
	return _rowcount() == 1


def _load_session(name: str) -> dict | None:
	row = frappe.db.get_value(
		DOCTYPE, name,
		["name", "gateway", "kind", "state", "intended_user", "tenant_id", "conversation_id", "payload",
			"expires_at"],
		as_dict=True,
	)
	return dict(row) if row else None


# ----------------------------------------------------------------------------- invoke
def _set_response(body: dict) -> None:
	frappe.local.gateway_response_override = {
		"status": 200,
		"body": json.dumps(body),
		"content_type": "application/json",
	}


def _refuse(text: str) -> dict:
	"""Message to the clicker only; the original card stays untouched."""
	return cards.invoke_message_response(text)


def _replace(text: str, title: str = "Approval") -> dict:
	card, _fallback = cards.notice_card(text, title)
	return cards.invoke_card_response(card)


def pre_ingest_card_action(gateway, context) -> bool:
	"""Handle ONLY card_action activities; everything else passes through (True)."""
	activity = teams_refs._activity_of(context)
	if activity.get("huf_kind") != tc.TeamsActivityKind.CARD_ACTION.value:
		return True
	try:
		body = _handle(gateway, activity)
	except Exception:
		_log("Teams card action failed")
		body = _refuse(MSG_FAILED)
	_set_response(body)
	return False


def _action_parts(activity: dict):
	value = activity.get("value")
	action = value.get("action") if isinstance(value, dict) else None
	if not isinstance(action, dict):
		return "", ""
	data = action.get("data")
	session = data.get("session") if isinstance(data, dict) else ""
	verb = action.get("verb")
	session = session if isinstance(session, str) and 0 < len(session) <= MAX_SESSION_NAME else ""
	return (verb if isinstance(verb, str) else ""), session


def _gateway_name(gateway) -> str:
	name = getattr(gateway, "name", None)
	if name is None and isinstance(gateway, dict):
		name = gateway.get("name")
	return _s(name)


def _tenant_ok(gateway, tenant_id) -> bool:
	"""``teams_tenant.is_tenant_allowed``; fails closed when it is missing or raises."""
	try:
		from huf.ai.gateways import teams_tenant

		return bool(tenant_id) and bool(teams_tenant.is_tenant_allowed(gateway, tenant_id))
	except Exception:
		return False


def _handle(gateway, activity: dict) -> dict:
	meta = teams_refs.parse_meta(activity)
	if not _tenant_ok(gateway, meta.tenant_id):  # defence in depth: never act for a foreign tenant
		return _refuse(MSG_UNAVAILABLE)
	verb, session_name = _action_parts(activity)
	if verb not in cards.VERBS or not session_name:
		return _refuse(MSG_UNAVAILABLE)
	gw = _gateway_name(gateway)
	clicker = teams_identity.resolve_user(gw, meta.tenant_id, meta.user_aad_id) if (
		meta.tenant_id and meta.user_aad_id) else None
	if not clicker:
		return _refuse(MSG_UNLINKED)
	session = _load_session(session_name)
	if (not session or session.get("gateway") != gw or session.get("kind") != KIND_EXECUTION
			or _s(session.get("tenant_id")) != meta.tenant_id
			or _s(session.get("conversation_id")) != teams_refs._base_conversation_id(meta.conversation_id)):
		return _refuse(MSG_UNAVAILABLE)
	state = session.get("state")
	if state == "Decided":
		return _replace(MSG_DECIDED)
	if state != "Open":
		return _replace(MSG_EXPIRED)
	payload = session.get("payload")
	try:
		payload = json.loads(payload) if isinstance(payload, str) else payload
	except ValueError:
		payload = {}
	approval = _s((payload or {}).get("name")) if isinstance(payload, dict) else ""
	if not approval:
		return _refuse(MSG_UNAVAILABLE)
	if session.get("intended_user") != clicker and not _may_decide(approval, clicker):
		return _refuse(MSG_DENIED)
	outcome = consume_session(session_name, clicker)
	if outcome == "decided":
		return _replace(MSG_DECIDED)
	if outcome == "expired":
		return _replace(MSG_EXPIRED)
	if outcome != "ok":
		return _refuse(MSG_UNAVAILABLE)
	return _decide(session_name, approval, clicker, verb)


def _may_decide(approval: str, user: str) -> bool:
	"""Does the existing approval API consider ``user`` an approver? Fails closed."""
	try:
		from huf.huf.doctype.agent_execution_approval import agent_execution_approval as mod

		return bool(mod._can_decide(frappe.get_doc(APPROVAL_DOCTYPE, approval), user))
	except Exception:
		return False


def _decision_fn(verb: str):
	from huf.huf.doctype.agent_execution_approval import agent_execution_approval as mod

	return mod.approve_execution if verb == cards.VERB_APPROVE else mod.reject_execution


def _decide(session_name: str, approval: str, actor: str, verb: str) -> dict:
	previous = frappe.session.user
	frappe.set_user(actor)
	try:
		_decision_fn(verb)(approval, COMMENT)
	except Exception as exc:
		frappe.set_user(previous)
		if "PermissionError" in type(exc).__name__:
			release_session(session_name, actor)
			return _refuse(MSG_DENIED)
		status = _approval_status(approval)
		if status and status != "Pending":  # decided or lapsed elsewhere: close the session
			_record_decision(session_name, "superseded")
			return _replace(MSG_NOT_PENDING)
		release_session(session_name, actor)
		return _refuse(MSG_FAILED)
	finally:
		if frappe.session.user != previous:
			frappe.set_user(previous)
	choice = "approve" if verb == cards.VERB_APPROVE else "reject"
	_record_decision(session_name, choice)
	word = "Approved" if choice == "approve" else "Rejected"
	card, _fallback = cards.decided_card(word, _display_name(actor), frappe.utils.now())
	return cards.invoke_card_response(card)


def _approval_status(approval: str):
	try:
		return frappe.db.get_value(APPROVAL_DOCTYPE, approval, "status")
	except Exception:
		return None


def _record_decision(session_name: str, decision: str) -> None:
	try:
		frappe.db.set_value(DOCTYPE, session_name, "decision", decision)
	except Exception:
		_log("Teams action session decision write failed")


def _display_name(user: str) -> str:
	try:
		return _s(frappe.db.get_value("User", user, "full_name")) or user
	except Exception:
		return user


def register() -> None:
	hooks.register(
		hooks.PRE_INGEST_FILTER, pre_ingest_card_action, provider=HOOK_PROVIDER,
		priority=tc.HOOK_PRIORITY_CARD_ACTION,
	)


register()
