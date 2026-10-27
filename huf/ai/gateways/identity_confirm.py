"""Two-way proof for self-links: the Slack user being linked must confirm in Slack.

``identity.confirm_self_link`` creates the link as ``Pending`` and calls
:func:`send_confirmation`, which DMs the Slack user a Block Kit message with
"Yes, link it" / "No" buttons backed by a Gateway Action Session of kind ``idlink:``
(``intended_slack_user`` = that Slack user, payload ``{"link": <link name>}``).

The click handler flips Pending -> Linked only when the clicker is that same Slack user in
the same workspace; "No" revokes. Pending links never resolve to a user. The mechanism is
provider-neutral except for the Slack DM transport (``_send_dm``).
"""

from __future__ import annotations

import frappe

from huf.ai.gateways import blocks as bk
from huf.ai.gateways import identity
from huf.ai.gateways import slack_interactivity as si

KIND = "idlink:"
DOCTYPE = "Gateway Identity Link"
SESSION_TTL_SECONDS = 15 * 60

MSG_LINKED = "Done: your Slack account is now linked."
MSG_REVOKED = "Okay, nothing was linked."
MSG_INVALID = "This link request is no longer valid."


def _display_name(user: str) -> str:
	try:
		return frappe.db.get_value("User", user, "full_name") or user
	except Exception:
		return user


def _send_dm(gateway, external_id: str, text: str, blocks: list) -> None:
	from huf.ai.gateways.slack_context import get_slack_api

	api = get_slack_api(gateway)
	channel = api.conversations_open([external_id])
	if not channel:
		raise ValueError("could not open a direct message with the Slack user")
	api.post_message(channel, text=text, blocks=blocks)


def send_confirmation(gateway, link_name: str, team_id: str, external_id: str, huf_user: str) -> str:
	"""DM the Slack user and return the action session name. Raises if the DM cannot be sent."""
	session = si.create_action_session(
		gateway,
		KIND,
		{"link": link_name, "team_id": team_id},
		intended_slack_user=external_id,
		ttl_seconds=SESSION_TTL_SECONDS,
	)
	name = _display_name(huf_user)
	card = bk.approval_card(
		f"Did you just connect your Slack account to Huf user {name}?",
		"If not, ignore this.",
		session,
		approve_label="Yes, link it",
		reject_label="No",
	)
	_send_dm(gateway, external_id, card.fallback, card.blocks)
	return session


def _flip(link_name: str, slack_user: str, team_id: str, gateway_name: str, approve: bool) -> bool:
	row = frappe.db.get_value(
		DOCTYPE, link_name, ["name", "gateway", "team_id", "external_id", "state", "user"], as_dict=True
	)
	if not row or row.state != "Pending" or row.gateway != gateway_name:
		return False
	if row.external_id != slack_user or (team_id and row.team_id != team_id):
		return False
	if not approve:
		frappe.db.set_value(DOCTYPE, link_name, "state", "Revoked")
		return True
	lock = identity.key_lock(gateway_name, row.team_id, row.external_id)
	if not lock:
		return False
	try:
		if identity._find_link(gateway_name, row.team_id, row.external_id):
			frappe.db.set_value(DOCTYPE, link_name, "state", "Revoked")
			return False
		if not identity._usable(row.user, "Self link"):
			frappe.db.set_value(DOCTYPE, link_name, "state", "Revoked")
			return False
		frappe.db.set_value(
			DOCTYPE, link_name, {"state": "Linked", "linked_at": frappe.utils.now()}
		)
	finally:
		identity.release_key_lock(lock)
	return True


def handle_click(gateway, session, actor_user, payload) -> dict:
	"""Registered for ``idlink:``. ``actor_user`` is None (the clicker has no link yet)."""
	user = payload.get("user") or {}
	slack_user = str(user.get("id") or "")
	team = str((payload.get("team") or {}).get("id") or user.get("team_id") or "")
	data = session.get("payload") or {}
	if not slack_user or not team or slack_user != session.get("intended_slack_user"):
		return {"text": MSG_INVALID}
	if data.get("team_id") and data.get("team_id") != team:
		return {"text": MSG_INVALID}
	approve = session.get("choice") == "approve"
	ok = _flip(str(data.get("link") or ""), slack_user, team, gateway.name, approve)
	if not ok:
		return {"text": MSG_INVALID}
	return {"text": MSG_LINKED if approve else MSG_REVOKED}


si.register_action_handler(KIND, handle_click, requires_actor=False)
