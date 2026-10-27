"""Two-way proof for Teams self-links: the Teams person being linked must confirm in Teams.

``teams_identity.confirm_teams_link`` creates the link as ``Pending`` and calls
:func:`send_confirmation`, which queues an Adaptive Card to that person's PERSONAL chat
("Did you just connect your Teams account to Huf user <name>? If not, ignore this.") with
Yes / No ``Action.Execute`` buttons backed by a Teams Action Session of kind ``idlink``
(payload = the link name only; the intended principal is the link's tenant + Entra object id).

The click handler (:func:`handle_click`, dispatched by ``teams_actions``) flips Pending -> Linked
ONLY when the clicker's verified (tenant, aadObjectId) is the link's own; "No" revokes. Pending
rows never resolve a user. If the card cannot be queued the caller revokes the row.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

import frappe

from huf.ai.gateways import teams_cards as cards
from huf.ai.gateways import teams_outbox, teams_refs

KIND = "idlink"
DOCTYPE = "Gateway Identity Link"
SESSION_TTL_SECONDS = 15 * 60

MSG_LINKED = "Done: your Teams account is now connected to Huf."
MSG_REVOKED = "Okay, nothing was connected."
MSG_INVALID = "This connection request is no longer valid."


class ConfirmationUnavailable(Exception):
	"""No way to ask the Teams person (no installed personal chat). Fail closed."""


def _s(value: Any) -> str:
	return str(value) if value else ""


def _display_name(user: str) -> str:
	try:
		return _s(frappe.db.get_value("User", user, "full_name")) or user
	except Exception:
		return user


def confirmation_card(session: str, huf_name: str) -> tuple[dict, str]:
	question = f"Did you just connect your Teams account to Huf user {huf_name}?"
	body = [
		cards._title("Connect your Huf account"),
		{"type": "TextBlock", "text": cards.clean(question, cards.MAX_NOTICE), "wrap": True},
		{"type": "TextBlock", "text": "If not, ignore this.", "wrap": True},
	]
	actions = [
		cards._action("Yes, connect it", cards.VERB_APPROVE, session, "positive"),
		cards._action("No", cards.VERB_REJECT, session, "destructive"),
	]
	return cards._card(body, actions), question + " If not, ignore this."


def send_confirmation(gateway_name: str, link_name: str, tenant_id: str, aad_id: str, huf_user: str) -> str:
	"""Queue the confirmation card to the person's personal chat; returns the session name.

	Raises (so the caller revokes the pending link) when there is no installed personal chat
	for exactly this (tenant, aadObjectId) or the outbox refuses the row.
	"""
	from huf.ai.gateways import teams_actions

	ref = teams_refs.get_personal_reference(gateway_name, tenant_id, aad_id)
	if not (ref and ref.get("conversation_id") and ref.get("service_url")) or ref.get("tenant_id") != tenant_id:
		raise ConfirmationUnavailable("no installed personal chat for this Teams user")
	session = teams_actions.create_action_session(
		gateway_name,
		KIND,
		{"link": link_name},
		tenant_id=tenant_id,
		conversation_id=ref["conversation_id"],
		ttl_seconds=SESSION_TTL_SECONDS,
	)
	card, fallback = confirmation_card(session, _display_name(huf_user))
	snapshot = {
		"conversation_ref": ref.get("name"),
		"conversation_id": ref["conversation_id"],
		"service_url": ref["service_url"],
		"tenant_id": tenant_id,
	}
	idem = "teams-idlink-" + hashlib.sha256(f"{gateway_name}|{session}".encode()).hexdigest()[:32]
	teams_outbox.enqueue(
		gateway_name,
		snapshot,
		"card",
		{"activity": cards.activity_with_card(card, fallback), "action_session": session},
		idem,
	)
	return session


def _revoke(link_name: str) -> None:
	frappe.db.set_value(DOCTYPE, link_name, "state", "Revoked")


def _flip(link_name: str, meta, gateway_name: str, approve: bool) -> bool:
	row = frappe.db.get_value(
		DOCTYPE, link_name, ["name", "gateway", "team_id", "external_id", "state", "user"], as_dict=True
	)
	if not row or row.get("state") != "Pending" or row.get("gateway") != gateway_name:
		return False
	if row.get("team_id") != meta.tenant_id or row.get("external_id") != meta.user_aad_id:
		return False
	if not approve:
		_revoke(link_name)
		return True
	from huf.ai.gateways import teams_identity

	if teams_identity._find_link(gateway_name, row["team_id"], row["external_id"]):
		_revoke(link_name)
		return False
	mine = teams_identity._user_link_in_tenant(gateway_name, row["team_id"], row["user"])
	if (mine and mine.get("external_id") != row["external_id"]) or not teams_identity._usable(
		row["user"], "Self link"
	):
		_revoke(link_name)
		return False
	frappe.db.set_value(DOCTYPE, link_name, {"state": "Linked", "linked_at": frappe.utils.now()})
	return True


def handle_click(gateway_name: str, session_name: str, session: dict, meta, verb: str) -> dict:
	"""``idlink`` handler: an Adaptive Card invoke body. Never raises for bad input."""
	from huf.ai.gateways import teams_actions

	payload = session.get("payload")
	try:
		payload = json.loads(payload) if isinstance(payload, str) else payload
	except ValueError:
		payload = {}
	link_name = _s((payload or {}).get("link")) if isinstance(payload, dict) else ""
	row = frappe.db.get_value(DOCTYPE, link_name, ["external_id", "team_id", "user"], as_dict=True) if link_name else None
	# Only the very (tenant, aad) being linked may answer; anyone else changes nothing.
	if (
		not row
		or not meta.user_aad_id
		or row.get("external_id") != meta.user_aad_id
		or row.get("team_id") != meta.tenant_id
		or _s(session.get("tenant_id")) != meta.tenant_id
	):
		return teams_actions._refuse(MSG_INVALID)
	if teams_actions.consume_session(session_name, row.get("user") or "Guest") != "ok":
		return teams_actions._replace(MSG_INVALID, "Connect your Huf account")
	approve = verb == cards.VERB_APPROVE
	if not _flip(link_name, meta, gateway_name, approve):
		return teams_actions._replace(MSG_INVALID, "Connect your Huf account")
	teams_actions._record_decision(session_name, "approve" if approve else "reject")
	return teams_actions._replace(MSG_LINKED if approve else MSG_REVOKED, "Connect your Huf account")


def register() -> None:
	from huf.ai.gateways import teams_actions

	teams_actions.register_action_handler(KIND, handle_click)


register()
