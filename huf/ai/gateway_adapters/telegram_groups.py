# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Join requests, Guard mode and group membership events for Telegram (WP-8c).

Bot API findings (core.telegram.org/bots/api, Bot API 10.3, checked 2026):

* There is NO separate guard-mode update type. Guard mode is delivered as an ordinary ``chat_join_request``
  update whose ``ChatJoinRequest`` carries an extra ``query_id`` (only for the bot assigned as the chat's
  guard; ``User.supports_join_request_queries`` in getMe, ``ChatFullInfo.guard_bot``). When ``query_id`` is
  present the bot MUST answer within 10 seconds, either directly with
  ``answerChatJoinRequestQuery(chat_join_request_query_id, result)`` where ``result`` is ``approve`` |
  ``decline`` | ``queue`` (queue = leave it to the other administrators), or first show a Mini App with
  ``sendChatJoinRequestWebApp(chat_join_request_query_id, web_app_url)`` and answer later.
* Without ``query_id`` (plain join-request chat) the decision is ``approveChatJoinRequest`` /
  ``declineChatJoinRequest`` (``chat_id``, ``user_id``); both need the ``can_invite_users`` admin right.
  Not deciding leaves the request pending for human admins. ``user_chat_id`` is usable to DM the user for
  5 minutes.
* ``chat_join_request``, ``chat_member`` (admin only) and ``my_chat_member`` must be in ``allowed_updates``
  (they are in ``telegram_client.ALLOWED_UPDATES``). ``ChatMemberUpdated`` has chat, from (actor), date,
  old/new_chat_member, invite_link, via_join_request.

Policy: ``register_join_policy(fn)`` where ``fn(ctx) -> "approve" | "decline" | "queue"``. Default and
fallback (policy error / invalid result) is ``queue``; the bot never auto-approves. A queued request is
recorded as a Pending Gateway Access Entry (``entry_type`` "Room", ``external_id`` ``join:<chat>:<user>``,
PAIR- code, gateway pairing TTL) using the pairing helpers; the ``join:`` id matches no real room so
approving it grants nothing. No one is notified.

Service messages: ``new_chat_members`` / ``left_chat_member`` arrive as ordinary ``message`` updates and are
handled here (welcome once per member, departures logged) and not forwarded to the agent. A welcome is deduped
per gateway + chat + user within the welcome cooldown, so a ``chat_member`` update and a ``new_chat_members``
message for the same join never welcome twice. Telegram only delivers service messages to a bot that can see
group messages (group privacy mode off, or the bot is an admin); with privacy mode on they may not arrive and
the ``chat_member`` update (bot must be an admin) is the only trigger.

Membership: changes are logged; the bot being removed from a non-private chat marks the chat unsendable via
the same opted-out access-entry state private blocks use (``apply_membership_change``).
"""

from __future__ import annotations

from typing import Any, Callable

import frappe

from huf.ai.gateway_adapters import telegram_admin_actions as admin

DECISIONS = admin.JOIN_RESULTS
_policy: Callable[[dict], str] | None = None


def _gateway_policy(ctx: dict) -> str:
	from huf.ai import telegram_guard

	return telegram_guard.gateway_policy(ctx)


def register_join_policy(fn: Callable[[dict], str] | None) -> None:
	"""Install the join decision function (None restores the default: queue)."""
	global _policy
	_policy = fn


def default_policy(ctx: dict) -> str:
	return "queue"


def decide(ctx: dict) -> str:
	try:
		decision = (_policy or _gateway_policy)(ctx)
	except Exception as exc:
		frappe.logger("huf").warning(f"Telegram join policy failed ({type(exc).__name__}); queueing")
		return "queue"
	decision = str(decision or "").strip().lower()
	return decision if decision in DECISIONS + ("defer",) else "queue"


def _ack(kind: str, note: str = "", **extra: Any) -> dict:
	return {"success": True, "ignored": kind, "note": note, **extra}


def join_request_ctx(raw: dict) -> dict | None:
	jr = raw.get("chat_join_request")
	if not isinstance(jr, dict):
		return None
	chat, user = jr.get("chat") or {}, jr.get("from") or {}
	if chat.get("id") is None or user.get("id") is None:
		return None
	return {
		"update_id": str(raw.get("update_id") or ""),
		"chat_id": str(chat["id"]),
		"chat_type": str(chat.get("type") or ""),
		"chat_title": str(chat.get("title") or ""),
		"user_id": str(user["id"]),
		"user_name": f"@{user['username']}" if user.get("username") else str(user.get("first_name") or ""),
		"is_bot": bool(user.get("is_bot")),
		"is_premium": bool(user.get("is_premium")),
		"user_chat_id": str(jr.get("user_chat_id") or ""),
		"bio": str(jr.get("bio") or ""),
		"date": jr.get("date"),
		"invite_link": (jr.get("invite_link") or {}).get("invite_link", ""),
		"query_id": str(jr.get("query_id") or ""),
	}


def record_pending_join(gateway, ctx: dict) -> str:
	"""Pending Gateway Access Entry for a queued request (deduplicated). Returns the entry name."""
	from frappe.utils import add_to_date, now_datetime

	from huf.ai import gateway_service as svc

	external_id = f"join:{ctx['chat_id']}:{ctx['user_id']}"
	existing = frappe.get_all(
		"Gateway Access Entry",
		filters={
			"gateway": gateway.name, "entry_type": "Room", "provider": gateway.provider,
			"external_id": external_id, "state": "Pending",
		},
		pluck="name",
		limit_page_length=1,
	)
	if existing:
		return existing[0]
	label = f"Join request: {ctx['user_name'] or ctx['user_id']} -> {ctx['chat_title'] or ctx['chat_id']}"
	doc = frappe.get_doc(
		{
			"doctype": "Gateway Access Entry",
			"gateway": gateway.name,
			"entry_type": "Room",
			"provider": gateway.provider,
			"external_id": external_id,
			"pairing_code": svc._new_unique_pairing_code(gateway.name),
			"state": "Pending",
			"expires_at": add_to_date(now_datetime(), minutes=int(gateway.get("pairing_ttl_minutes") or 60)),
			"display_label": label[:140],
			"notes": f"chat {ctx['chat_id']} user {ctx['user_id']} user_chat {ctx['user_chat_id']}",
		}
	).insert(ignore_permissions=True)
	return doc.name


def handle_join_request(gateway, adapter, parsed, request) -> dict | None:
	"""Decide a chat_join_request (plain or Guard-mode). Never raises; always acks."""
	ctx = join_request_ctx(parsed.raw)
	if ctx is None:
		return None
	ctx["gateway"] = gateway.name
	decision = decide(ctx)
	client = adapter.client
	error = ""
	if decision == "defer":  # a Guard Mini App challenge owns the answer (telegram_guard)
		frappe.logger("huf").info(f"Telegram gateway {gateway.name}: join request deferred to Guard Mini App")
		return _ack("chat_join_request", "defer", decision="defer")
	try:
		if decision == "queue":
			record_pending_join(gateway, ctx)
		if ctx["query_id"]:
			admin.answer_join_request_query(client, ctx["query_id"], decision)
		elif decision == "approve":
			admin.approve_join_request(client, ctx["chat_id"], ctx["user_id"])
		elif decision == "decline":
			admin.decline_join_request(client, ctx["chat_id"], ctx["user_id"])
	except admin.AdminActionError as exc:
		error = f"{exc.code}: {exc}"
		frappe.logger("huf").warning(f"Telegram gateway {gateway.name}: join request {decision} failed ({exc.code})")
	frappe.logger("huf").info(
		f"Telegram gateway {gateway.name}: join request chat={ctx['chat_id']} user={ctx['user_id']} "
		f"guard={bool(ctx['query_id'])} decision={decision}"
	)
	return _ack("chat_join_request", error or decision, decision=decision, **({"error": error} if error else {}))


# -- membership --------------------------------------------------------------------------------


def classify_transition(old: str, new: str) -> str:
	if new in ("kicked", "left"):
		return "removed"
	if old in ("kicked", "left", "") and new in ("member", "administrator", "restricted"):
		return "added"
	if new == "administrator" and old != "administrator":
		return "promoted"
	if old == "administrator" and new != "administrator":
		return "demoted"
	if new == "restricted" or old == "restricted":
		return "restricted"
	return "changed"


def apply_membership_change(gateway, parsed) -> dict:
	"""Log a (my_)chat_member change; bot removed from a room -> unsendable, re-added -> restored."""
	transition = classify_transition(parsed.member_old_status, parsed.member_new_status)
	about_bot = parsed.kind == "my_chat_member"
	frappe.logger("huf").info(
		f"Telegram gateway {gateway.name}: {parsed.kind} chat={parsed.chat_id} ({parsed.chat_type}) "
		f"{parsed.member_old_status}->{parsed.member_new_status} ({transition}) by={parsed.sender_id}"
	)
	if about_bot and parsed.is_room:
		from huf.ai import gateway_service as svc

		if transition == "removed":
			svc._record_room_opt_out(gateway, parsed.chat_id)
		elif transition == "added":
			svc._record_room_opt_in(gateway, parsed.chat_id)
	return _ack(parsed.kind, transition, transition=transition)


def _maybe_welcome(gateway, parsed) -> None:
	from huf.ai import telegram_guard

	telegram_guard.maybe_welcome(gateway, parsed)


def handle_membership(gateway, adapter, parsed, request) -> dict | None:
	if parsed.chat_type == "private":
		return None  # private block / unblock is handled by telegram_ingest
	ack = apply_membership_change(gateway, parsed)
	if parsed.kind == "chat_member" and ack.get("transition") == "added":
		try:
			_maybe_welcome(gateway, parsed)
		except Exception as exc:
			frappe.logger("huf").warning(f"Telegram welcome failed ({type(exc).__name__})")
	return ack


def migrate_room(gateway, old_id: str, new_id: str) -> bool:
	"""Basic group -> supergroup: re-key the approved Room entry to the new chat id. Idempotent; the old entry
	stays as Revoked with a note. Returns True when a new entry was created."""
	from frappe.utils import now_datetime

	from huf.ai import gateway_service as svc

	if not old_id or not new_id or old_id == new_id:
		return False
	if svc._has_access_entry(gateway, "Room", new_id):
		return False
	if not svc._has_access_entry(gateway, "Room", old_id):
		return False
	old = svc._live_room_entry(gateway, old_id)
	old_doc = frappe.get_doc("Gateway Access Entry", old["name"])
	frappe.get_doc(
		{
			"doctype": "Gateway Access Entry",
			"gateway": gateway.name,
			"entry_type": "Room",
			"provider": gateway.provider,
			"external_id": svc._normalize_sender_for_provider(gateway.provider, "Room", new_id),
			"state": "Approved",
			"display_label": old_doc.display_label,
			"expires_at": old_doc.expires_at,
			"approved_by": old_doc.approved_by,
			"approved_at": now_datetime(),
			"notes": f"Migrated from chat {old_id} (basic group promoted to supergroup)",
		}
	).insert(ignore_permissions=True)
	svc._save_entry(
		old_doc,
		{
			"state": svc.ENTRY_STATE_REVOKED,
			"revoked_at": now_datetime(),
			"notes": f"{old_doc.notes or ''}\nMigrated to supergroup {new_id}".strip(),
		},
	)
	frappe.logger("huf").info(f"Telegram gateway {gateway.name}: room {old_id} migrated to {new_id}")
	return True


def handle_service_message(gateway, adapter, parsed, request) -> dict | None:
	"""``new_chat_members`` / ``left_chat_member`` service messages in groups. None for any other message."""
	if parsed.kind != "message" or parsed.chat_type == "private":
		return None
	message = (parsed.raw or {}).get("message")
	if not isinstance(message, dict):
		return None
	old_id, new_id = message.get("migrate_from_chat_id"), message.get("migrate_to_chat_id")
	if old_id is not None or new_id is not None:
		# migrate_to arrives in the old chat, migrate_from in the new one; both name the pair.
		if new_id is not None:
			old_id = parsed.chat_id
		else:
			new_id = parsed.chat_id
		moved = migrate_room(gateway, str(old_id), str(new_id))
		return _ack("migrate_chat", "migrated" if moved else "nothing to migrate", old=str(old_id), new=str(new_id))
	if message.get("new_chat_members"):
		welcomed = 0
		try:
			from huf.ai import telegram_guard

			welcomed = telegram_guard.welcome_new_members(gateway, parsed)
		except Exception as exc:
			frappe.logger("huf").warning(f"Telegram welcome failed ({type(exc).__name__})")
		frappe.logger("huf").info(
			f"Telegram gateway {gateway.name}: new_chat_members chat={parsed.chat_id} "
			f"count={len(message['new_chat_members'])} welcomed={welcomed}"
		)
		return _ack("new_chat_members", "joined", welcomed=welcomed)
	left = message.get("left_chat_member")
	if isinstance(left, dict):
		frappe.logger("huf").info(
			f"Telegram gateway {gateway.name}: left_chat_member chat={parsed.chat_id} user={left.get('id')}"
		)
		return _ack("left_chat_member", "left", user_id=str(left.get("id") or ""))
	return None
