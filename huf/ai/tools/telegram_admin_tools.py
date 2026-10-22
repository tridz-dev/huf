"""Telegram admin tools for HUF agents: group administration, bot profile and secretary (business) actions.

One consolidated tool (``telegram_admin``) with an ``action`` parameter. Everything here is OFF by default
and gated per action group by a flag on the run's own Gateway (read server-side, never from arguments):

- group admin  -> ``telegram_agent_allow_group_admin``
- profile      -> ``telegram_agent_allow_profile``
- business     -> ``telegram_agent_allow_business``

A run that is not inside an enabled Telegram gateway is always refused. Safety layers, in order:
scope (chat must be in the gateway's send scope), bot rights (getChatMember(bot) must show the needed admin
right), target protection (chat admins and the gateway's paired admins are never ban/restrict/demote targets,
and nobody can be given ``can_promote_members``), ``confirm=true`` for destructive actions in the owner's cockpit chat, and HUMAN approval (signed Approve/Reject
buttons sent to the gateway's Admin cockpit bindings) for every other run, a per-run cap and an audit entry per executed action.

Bot API verified against https://core.telegram.org/bots/api (Bot API 10.3).
"""

from __future__ import annotations

import hashlib
import json
import secrets
import threading
import time
from typing import Any, Optional

import frappe

logger = frappe.logger("huf")

from huf.ai import telegram_send_scope as scope
from huf.ai.gateway_adapters import telegram_admin_actions as aa
from huf.ai.gateway_adapters import telegram_business as biz
from huf.ai.gateway_adapters import telegram_commands as cmds
from huf.ai.gateway_adapters.telegram_client import TelegramApiError, TelegramBotClient

FLAGS = {
	"group": "telegram_agent_allow_group_admin",
	"profile": "telegram_agent_allow_profile",
	"business": "telegram_agent_allow_business",
}
# action -> (group, bot admin right required or None, state-changing (needs owner run + human approval), counts against the cap)
ACTIONS: dict[str, tuple[str, Optional[str], bool, bool]] = {
	"ban": ("group", "can_restrict_members", True, True),
	"unban": ("group", "can_restrict_members", True, True),
	"restrict": ("group", "can_restrict_members", True, True),
	"unrestrict": ("group", "can_restrict_members", True, True),
	"promote": ("group", "can_promote_members", True, True),
	"demote": ("group", "can_promote_members", True, True),
	"set_chat_title": ("group", "can_change_info", True, True),
	"set_chat_description": ("group", "can_change_info", True, True),
	"pin": ("group", "can_pin_messages", True, True),
	"unpin": ("group", "can_pin_messages", True, True),
	"delete_message": ("group", "can_delete_messages", True, True),
	"approve_join_request": ("group", "can_invite_users", True, True),
	"decline_join_request": ("group", "can_invite_users", True, True),
	"create_invite_link": ("group", "can_invite_users", True, True),
	"revoke_invite_link": ("group", "can_invite_users", True, True),
	"get_admins": ("group", None, False, False),
	"set_my_commands": ("profile", None, True, True),
	"set_my_name": ("profile", None, True, True),
	"set_my_description": ("profile", None, True, True),
	"set_my_short_description": ("profile", None, True, True),
	"set_chat_menu_button": ("profile", None, True, True),
	"get_business_connection": ("business", None, False, False),
	"send_business_message": ("business", None, True, True),
	"read_business_message": ("business", None, True, True),
	"delete_business_messages": ("business", None, True, True),
}
CHAT_ACTIONS = {a for a, v in ACTIONS.items() if v[0] == "group"}
TARGET_ACTIONS = {"ban", "restrict", "promote", "demote"}  # user_id must not be an admin / paired admin
DEFAULT_CAP = 5
CONFIRM_TTL = 300
_CONTROL_KEYS = ("action", "confirm", "confirmation_token")

# Restriction presets -> ChatPermissions (anything not listed stays allowed).
_ALL_PERMS = set(aa.CHAT_PERMISSIONS)
_MEDIA = {
	"can_send_audios", "can_send_documents", "can_send_photos", "can_send_videos", "can_send_video_notes",
	"can_send_voice_notes", "can_send_polls", "can_send_other_messages",
}
PRESETS: dict[str, set[str]] = {
	"mute": {"can_send_messages"} | _MEDIA,
	"no_media": set(_MEDIA),
	"no_links": {"can_add_web_page_previews"},
	"read_only": _ALL_PERMS,
	"no_invites_or_pins": {"can_invite_users", "can_pin_messages", "can_change_info", "can_manage_topics"},
}


class Refused(Exception):
	def __init__(self, error: str, message: str, **extra: Any) -> None:
		self.payload = {"success": False, "error": error, "message": message, **extra}
		super().__init__(message)


def _out(payload: dict) -> str:
	return json.dumps(payload, default=str)


# -- plumbing (patched in tests) ------------------------------------------------------------------


def _cache():
	return frappe.cache()


def _token() -> Optional[str]:
	from huf.ai.tools import telegram as tg_tool

	return tg_tool._token_for_run()


def _make_client(token: str, *, timeout: int = 30) -> TelegramBotClient:
	return TelegramBotClient(token, timeout=timeout)


def _flag(gateway: str, group: str) -> bool:
	try:
		return bool(frappe.db.get_value("Gateway", gateway, FLAGS[group]))
	except Exception:
		return False


def _cap_limit(gateway: str) -> int:
	try:
		value = int(frappe.db.get_value("Gateway", gateway, "agent_send_cap_per_run") or 0)
	except Exception:
		value = 0
	return value if value > 0 else DEFAULT_CAP


# Every state-changing action (anything not read-only get_*) needs a human Admin's signed Approve press, even in an
# owner run: a prompt-injected agent must not change anything with a mere ``confirm=true``.
ALWAYS_HUMAN_APPROVAL = frozenset(a for a, v in ACTIONS.items() if v[2])


def _is_owner_run(gateway: str, chat: str) -> bool:
	"""True when the run's chat is the private chat of a paired cockpit binding with role rank >= Admin.

	Viewer / Operator binding chats are NOT owner runs (same rank rule as ``telegram_admin.execute``).
	"""
	if not chat:
		return False
	from huf.ai import telegram_admin as ta

	try:
		role = frappe.db.get_value(
			"Telegram Admin Binding",
			{"gateway": gateway, "chat_id": str(chat), "is_active": 1},
			"role_scope",
		)
	except Exception:
		return False
	return ta.ROLE_RANK.get(role or "", 0) >= ta.ROLE_RANK["Admin"]


def _is_paired_admin(gateway: str, user_id: Any) -> bool:
	try:
		return bool(
			frappe.db.get_value(
				"Telegram Admin Binding", {"gateway": gateway, "telegram_user_id": str(user_id), "is_active": 1}, "name"
			)
		)
	except Exception:
		return False


# -- audit ---------------------------------------------------------------------------------------


def _audit(gateway: str, action: str, args: dict, result: str, detail: str = "") -> None:
	safe = {k: v for k, v in args.items() if k not in _CONTROL_KEYS}
	logger.info(f"telegram_admin gateway={gateway} action={action} result={result} args={json.dumps(safe, default=str)[:500]}")
	try:
		if not frappe.db.exists("DocType", "Telegram Admin Audit"):
			return
		frappe.get_doc(
			{
				"doctype": "Telegram Admin Audit",
				"telegram_user_id": "agent",
				"gateway": gateway,
				"action": f"agent:{action}"[:140],
				"arguments_json": json.dumps(safe, default=str)[:2000],
				"result": result[:140],
				"detail": detail[:1000],
				"ts": frappe.utils.now_datetime(),
			}
		).insert(ignore_permissions=True)
	except Exception as exc:  # audit must never break the action
		logger.warning(f"telegram_admin audit row failed: {type(exc).__name__}")


# -- caps and confirmation -----------------------------------------------------------------------


def _cap_key(gateway: str, run_id: str) -> str:
	return f"huf_tg_admin_run:{gateway}:{run_id}"


def _cap_count(gateway: str, run_id: str) -> int:
	try:
		return int(_cache().get_value(_cap_key(gateway, run_id)) or 0)
	except Exception:
		return 0


def _cap_atomic():
	try:
		c = _cache()
		if getattr(c, "make_key", None) and all(hasattr(c, n) for n in ("incrby", "decrby", "expire")):
			return c
	except Exception:
		pass
	return None


_CAP_LOCK = threading.Lock()


def _cap_claim(gateway: str, run_id: Optional[str]) -> None:
	if not run_id:
		return
	limit = _cap_limit(gateway)
	c = _cap_atomic()
	if c is not None:
		from huf.ai.telegram_send_scope import _incr

		try:
			key = c.make_key(_cap_key(gateway, run_id) + ":n")
			n = _incr(c, key)
		except Exception:
			c = None
		else:
			if n > limit:
				c.decrby(key, 1)
				raise Refused(
					"admin_cap_exceeded",
					f"This run already performed its limit of {limit} Telegram admin actions.",
					limit=limit,
				)
			return
	with _CAP_LOCK:
		count = _cap_count(gateway, run_id)
		if count >= limit:
			raise Refused(
				"admin_cap_exceeded",
				f"This run already performed its limit of {limit} Telegram admin actions.",
				limit=limit,
			)
		_cache().set_value(_cap_key(gateway, run_id), count + 1, expires_in_sec=24 * 3600)


def _cap_release(gateway: str, run_id: Optional[str]) -> None:
	if not run_id:
		return
	c = _cap_atomic()
	if c is not None:
		try:
			c.decrby(c.make_key(_cap_key(gateway, run_id) + ":n"), 1)
			return
		except Exception:
			pass
	with _CAP_LOCK:
		count = _cap_count(gateway, run_id)
		_cache().set_value(_cap_key(gateway, run_id), max(count - 1, 0), expires_in_sec=24 * 3600)


def _fingerprint(action: str, args: dict, gateway: str, chat: str) -> str:
	body = {k: v for k, v in args.items() if k not in _CONTROL_KEYS}
	raw = json.dumps({"a": action, "g": gateway, "c": chat, "args": body}, sort_keys=True, default=str)
	return hashlib.sha256(raw.encode()).hexdigest()


def _confirm_key(token: str) -> str:
	return f"huf_tg_admin_confirm:{token}"


def _describe(action: str, args: dict, chat: str) -> str:
	bits = {k: v for k, v in args.items() if k not in _CONTROL_KEYS and v not in (None, "")}
	return f"{action} in chat {chat or '(bot-wide)'} with {json.dumps(bits, default=str)[:300]}"


def _truthy(value: Any) -> bool:
	if isinstance(value, str):
		return value.strip().lower() in ("1", "true", "yes", "on")
	return bool(value)


APPROVAL_TTL = 600


def _gateway_token(gateway: str) -> Optional[str]:
	from huf.ai.tools import telegram as tg_tool

	return tg_tool._gateway_values(gateway).get("token") or None


def _callback_signer(gateway: str, chat_id: str):
	"""Sign callback_data with the gateway's own key (same derivation the adapter uses)."""
	from huf.ai.gateway_adapters.telegram_keyboards import derive_callback_key, sign_callback
	from huf.ai.tools import telegram as tg_tool

	secret = tg_tool._gateway_values(gateway).get("webhook_secret", "")
	if not secret:
		return None
	key = derive_callback_key(secret)
	return lambda payload: sign_callback(key, payload, context=str(chat_id))


def _admin_bindings(gateway: str) -> list[dict]:
	"""ACTIVE Admin-scope cockpit bindings of this gateway (live scope re-validated)."""
	from huf.ai import telegram_admin as ta

	try:
		rows = frappe.get_all(
			"Telegram Admin Binding",
			filters={"gateway": gateway, "is_active": 1, "role_scope": "Admin"},
			fields=["telegram_user_id"],
		)
	except Exception:
		rows = []
	out = []
	for row in rows:
		binding = ta.get_binding(row.get("telegram_user_id"), gateway)
		if binding and binding.get("role_scope") == "Admin" and binding.get("chat_id"):
			out.append(binding)
	return out


def _require_owner(gateway: str) -> None:
	if not _is_owner_run(gateway, scope.current_chat(scope.effective_run_id())):
		raise Refused(
			"owner_required",
			"State-changing Telegram admin actions can only be started from a bound admin's private cockpit chat. "
			"Do nothing here; ask a bound admin (Admin role in the Telegram cockpit) to request this action.",
		)


def _gate_destructive(action: str, args: dict, gateway: str, chat: str) -> Optional[dict]:
	"""Every state change needs an owner run (paired Admin+ binding chat) AND a human Approve button press.

	``confirm`` / ``confirmation_token`` supplied by the model are never approval and are ignored.
	"""
	_require_owner(gateway)
	if action not in ALWAYS_HUMAN_APPROVAL:
		return None
	if not _admin_bindings(gateway):
		raise Refused(
			"no_admin_available",
			"This action needs a human admin's approval, but this gateway has no active Admin-scope Telegram "
			"cockpit binding to ask. Nothing was done.",
		)
	body = {k: v for k, v in args.items() if k not in _CONTROL_KEYS}
	return {
		"op": "agent_action",
		"gateway": gateway,
		"chat": chat,
		"action": action,
		"args": body,
		"fp": _fingerprint(action, args, gateway, chat),
	}


def _request_human_approval(pending: dict, client) -> dict:
	"""Store the pending action and send signed Approve/Reject buttons to every active Admin binding."""
	from huf.ai import telegram_admin as ta
	from huf.ai.gateway_adapters import telegram_keyboards as kb

	gateway = pending["gateway"]
	cache = _cache()
	already = {"status": "pending_human_approval", "message": "An admin approval for this exact action is already pending."}
	if ta.agent_action_pending(pending["fp"], cache=cache):
		return already
	targets = _admin_bindings(gateway)
	if not targets:
		raise Refused("no_admin_available", "No active Admin-scope Telegram binding to ask. Nothing was done.")
	# Mark pending atomically BEFORE sending so a fast Approve is not 'expired' and a concurrent duplicate sends nothing.
	if not ta.agent_action_begin(pending["fp"], cache=cache, ttl=APPROVAL_TTL):
		return already
	text = "An agent requests approval:\n" + ta.describe(pending) + f"\nValid {APPROVAL_TTL // 60} minutes."
	delivered = 0
	for binding in targets:
		chat_id = str(binding["chat_id"])
		sign = _callback_signer(gateway, chat_id)
		if sign is None:
			continue
		rows = [[
			kb.callback_button("Approve", sign(ta.callback_payload(
				"c", ta.issue_nonce(binding["telegram_user_id"], chat_id, pending, cache=cache, ttl=APPROVAL_TTL)))),
			kb.callback_button("Reject", sign(ta.callback_payload(
				"x", ta.issue_nonce(binding["telegram_user_id"], chat_id, pending, cache=cache, ttl=APPROVAL_TTL)))),
		]]
		try:
			client.call("sendMessage", {"chat_id": aa._id(chat_id), "text": text[:4000], "reply_markup": kb.inline_keyboard(rows)})
			delivered += 1
		except Exception:
			continue
	if not delivered:
		ta.agent_action_clear(pending["fp"], cache=cache)
		raise Refused("no_admin_available", "Could not reach any admin to approve this action. Nothing was done.")
	return {
		"status": "pending_human_approval",
		"message": f"A human admin must approve this in Telegram ({delivered} admin(s) asked, valid "
		f"{APPROVAL_TTL // 60} minutes). Do not retry; tell the requester it is awaiting approval.",
		"effect": _describe(action=pending["action"], args=pending["args"], chat=pending["chat"]),
	}


def execute_approved(pending: dict) -> str:
	"""Run an admin-approved agent action (called ONLY from the admin's Approve button press)."""
	from huf.ai import telegram_admin as ta

	gateway = str(pending.get("gateway") or "")
	name = str(pending.get("action") or "")
	spec = ACTIONS.get(name)
	if not gateway or not spec or not spec[2]:
		raise ta.AdminError("Unknown action.")
	group, right, _destructive, _counted = spec
	args = dict(pending.get("args") or {})
	chat = str(pending.get("chat") or "")
	client = None
	try:
		if not _flag(gateway, group):
			raise Refused("action_not_permitted", f"This gateway no longer allows agents to use {group} actions.")
		token = _gateway_token(gateway)
		if not token:
			raise Refused("not_configured", "Telegram bot token not configured")
		client = _make_client(token)
		if name in CHAT_ACTIONS:
			_check_bot_rights(client, chat, right, name)
			if name in TARGET_ACTIONS:
				_check_target(client, gateway, chat, _int(args, "user_id"), name)
		elif group == "business":
			_connection(gateway, args)
		_execute(name, args, client, gateway, chat)
	except TelegramApiError as exc:
		raise ta.AdminError(f"Telegram error: {client.redact(exc.description) if client else exc.description}") from None
	except aa.AdminActionError as exc:
		raise ta.AdminError(str(exc)) from None
	except Refused as refusal:
		raise ta.AdminError(refusal.payload["message"]) from None
	except ValueError as exc:
		raise ta.AdminError(str(exc)) from None
	return f"Done: {name} " + (f"in chat {chat}" if chat else "(bot-wide)")


# -- checks --------------------------------------------------------------------------------------


def _call(client, method: str, payload: dict) -> Any:
	return aa._call(client, method, payload)


def _bot_id(client) -> int:
	me = client.call("getMe")
	return int((me or {}).get("id"))


def _check_bot_rights(client, chat: str, right: Optional[str], action: str) -> None:
	member = _call(client, "getChatMember", {"chat_id": aa._id(chat), "user_id": _bot_id(client)}) or {}
	status = member.get("status")
	if status == "creator":
		return
	if status != "administrator":
		raise Refused("bot_not_admin", f"The bot is not an administrator of chat {chat}, so {action} is not possible.")
	if right and not member.get(right):
		raise Refused(
			"bot_missing_right",
			f"The bot is an admin of chat {chat} but lacks the '{right}' right needed for {action}. "
			"A chat owner must grant it.",
			missing_right=right,
		)


def _check_target(client, gateway: str, chat: str, user_id: int, action: str) -> None:
	if _is_paired_admin(gateway, user_id):
		raise Refused("target_is_admin", "That user is a paired admin of this bot and cannot be targeted.")
	member = _call(client, "getChatMember", {"chat_id": aa._id(chat), "user_id": user_id}) or {}
	if member.get("status") in ("creator", "administrator"):
		if action == "demote" and member.get("status") == "administrator":
			return
		raise Refused("target_is_admin", f"That user is an administrator or owner of the chat; {action} is refused.")


def _int(args: dict, key: str, required: bool = True) -> Optional[int]:
	value = args.get(key)
	if value in (None, ""):
		if required:
			raise Refused("invalid_argument", f"{key} is required")
		return None
	try:
		return int(value)
	except (TypeError, ValueError):
		raise Refused("invalid_argument", f"{key} must be an integer") from None


def _until(args: dict) -> Optional[int]:
	if args.get("until_date"):
		return _int(args, "until_date")
	minutes = _int(args, "duration_minutes", required=False)
	return int(time.time()) + minutes * 60 if minutes else None


def _permissions(args: dict) -> dict:
	explicit = args.get("permissions")
	if isinstance(explicit, str):
		try:
			explicit = json.loads(explicit)
		except ValueError:
			explicit = None
	if isinstance(explicit, dict) and explicit:
		unknown = sorted(set(explicit) - _ALL_PERMS)
		if unknown:
			raise Refused("invalid_argument", f"unknown permission(s): {', '.join(unknown)}")
		return {k: bool(v) for k, v in explicit.items()}
	preset = str(args.get("preset") or "mute")
	if preset not in PRESETS:
		raise Refused("invalid_argument", f"preset must be one of {', '.join(sorted(PRESETS))} or pass permissions")
	denied = PRESETS[preset]
	return {k: (k not in denied) for k in aa.CHAT_PERMISSIONS}


def _rights(args: dict) -> dict:
	raw = args.get("rights")
	if isinstance(raw, str):
		try:
			raw = json.loads(raw)
		except ValueError:
			raw = [r.strip() for r in raw.split(",") if r.strip()]
	if not isinstance(raw, list) or not raw:
		raise Refused("invalid_argument", "rights must be a non-empty list of admin right names")
	unknown = sorted(set(raw) - set(aa.ADMIN_RIGHTS))
	if unknown:
		raise Refused("invalid_argument", f"unknown admin right(s): {', '.join(unknown)}")
	if "can_promote_members" in raw:
		raise Refused("right_not_grantable", "Agents may not grant can_promote_members (privilege escalation).")
	return {r: True for r in raw}


def _menu_button(args: dict) -> dict:
	raw = args.get("menu_button")
	if isinstance(raw, str):
		try:
			raw = json.loads(raw)
		except ValueError:
			raw = None
	if not isinstance(raw, dict) or raw.get("type") not in ("commands", "default", "web_app"):
		raise Refused("invalid_argument", "menu_button must be an object with type commands, default or web_app")
	if raw["type"] == "web_app":
		url = str(((raw.get("web_app") or {}).get("url")) or "")
		if not url.startswith("https://") or not str(raw.get("text") or "").strip():
			raise Refused("invalid_argument", "web_app menu button needs text and an https web_app.url")
		return {"type": "web_app", "text": str(raw["text"]), "web_app": {"url": url}}
	return {"type": raw["type"]}


def _text(args: dict, key: str, limit: int, required: bool = True) -> str:
	value = str(args.get(key) if args.get(key) is not None else "")
	if required and not value.strip():
		raise Refused("invalid_argument", f"{key} is required")
	if len(value) > limit:
		raise Refused("invalid_argument", f"{key} must be at most {limit} characters")
	return value


def _lang(args: dict) -> dict:
	code = args.get("language_code")
	return {"language_code": str(code)} if code else {}


def _connection(gateway: str, args: dict) -> dict:
	cid = str(args.get("business_connection_id") or "").strip()
	if not cid:
		raise Refused("invalid_argument", "business_connection_id is required")
	conn = biz.get_connection(cid)
	# Exact match only: a legacy/unbound connection (empty gateway) must not pass for every gateway.
	if not conn or not gateway or str(conn.get("gateway") or "") != gateway:
		raise Refused("unknown_connection", "This gateway does not know that business connection.")
	return conn


def _business_scope(action: str, args: dict, conn: dict, gateway: str, run_id: Optional[str]) -> None:
	"""Business actions obey the same recipient scope as every other agent send."""
	if action in ("send_business_message", "read_business_message"):
		chat = scope.normalize_chat(args.get("chat_id"))
		if not chat:
			raise Refused("invalid_argument", "chat_id is required (numeric chat id)")
	else:
		chat = scope.normalize_chat(args.get("chat_id")) or scope.current_chat(run_id)
		if args.get("chat_id") not in (None, "") and not scope.normalize_chat(args.get("chat_id")):
			raise Refused("invalid_argument", "chat_id must be a numeric chat id")
		if _truthy(args.get("all_messages")) and scope.settings(gateway)["scope"] != "Any number":
			raise Refused(
				"recipient_not_permitted",
				"Deleting other people's messages (all_messages) needs the gateway recipient scope 'Any number'.",
			)
	refusal = scope.check_recipient(gateway, run_id, chat)
	if refusal:
		raise Refused("recipient_not_permitted", json.loads(refusal)["message"])


# -- executors -----------------------------------------------------------------------------------


def _execute(action: str, args: dict, client, gateway: str, chat: str) -> Any:
	if action in ("ban", "unban", "restrict", "unrestrict", "promote", "demote"):
		uid = _int(args, "user_id")
		if action == "ban":
			return aa.ban_member(client, chat, uid, until_date=_until(args), revoke_messages=_truthy(args.get("revoke_messages")))
		if action == "unban":
			return aa.unban_member(client, chat, uid, only_if_banned=True)
		if action == "restrict":
			return aa.restrict_member(client, chat, uid, _permissions(args), until_date=_until(args))
		if action == "unrestrict":
			return aa.unrestrict_member(client, chat, uid)
		if action == "promote":
			return aa.promote_member(client, chat, uid, _rights(args))
		return aa.demote_member(client, chat, uid)
	if action == "set_chat_title":
		return aa.set_chat_title(client, chat, _text(args, "title", 128))
	if action == "set_chat_description":
		return aa.set_chat_description(client, chat, _text(args, "description", 255, required=False))
	if action == "pin":
		return aa.pin_message(client, chat, _int(args, "message_id"), silent=not _truthy(args.get("notify")))
	if action == "unpin":
		payload: dict = {"chat_id": aa._id(chat)}
		if args.get("message_id") not in (None, ""):
			payload["message_id"] = _int(args, "message_id")
		return _call(client, "unpinChatMessage", payload)
	if action == "delete_message":
		return aa.delete_message(client, chat, _int(args, "message_id"))
	if action == "approve_join_request":
		return aa.approve_join_request(client, chat, _int(args, "user_id"))
	if action == "decline_join_request":
		return aa.decline_join_request(client, chat, _int(args, "user_id"))
	if action == "create_invite_link":
		payload = {"chat_id": aa._id(chat)}
		if args.get("name"):
			payload["name"] = _text(args, "name", 32)
		if args.get("expire_date"):
			payload["expire_date"] = _int(args, "expire_date")
		if args.get("member_limit"):
			payload["member_limit"] = _int(args, "member_limit")
		if _truthy(args.get("creates_join_request")):
			if payload.get("member_limit"):
				raise Refused("invalid_argument", "member_limit cannot be combined with creates_join_request")
			payload["creates_join_request"] = True
		return _call(client, "createChatInviteLink", payload)
	if action == "revoke_invite_link":
		link = str(args.get("invite_link") or "").strip()
		if not link:
			raise Refused("invalid_argument", "invite_link is required")
		return _call(client, "revokeChatInviteLink", {"chat_id": aa._id(chat), "invite_link": link})
	if action == "get_admins":
		rows = aa.get_admins(client, chat, return_bots=_truthy(args.get("return_bots")))
		return [
			{
				"user_id": (r.get("user") or {}).get("id"),
				"username": (r.get("user") or {}).get("username"),
				"is_bot": (r.get("user") or {}).get("is_bot"),
				"status": r.get("status"),
				"custom_title": r.get("custom_title"),
			}
			for r in (rows if isinstance(rows, list) else [])
		]
	if action == "set_my_commands":
		commands = args.get("commands")
		if isinstance(commands, str):
			try:
				commands = json.loads(commands)
			except ValueError:
				commands = None
		kw = {"scope": str(args.get("command_scope") or "default"), "chat_id": args.get("chat_id"),
			"user_id": args.get("user_id"), "language_code": args.get("language_code") or None}
		try:
			return cmds.set_commands(client, commands or [], **kw)
		except ValueError as exc:
			raise Refused("invalid_argument", str(exc)) from None
	if action == "set_my_name":
		return client.call("setMyName", {"name": _text(args, "name", 64, required=False), **_lang(args)})
	if action == "set_my_description":
		return client.call("setMyDescription", {"description": _text(args, "description", 512, required=False), **_lang(args)})
	if action == "set_my_short_description":
		return client.call(
			"setMyShortDescription", {"short_description": _text(args, "short_description", 120, required=False), **_lang(args)}
		)
	if action == "set_chat_menu_button":
		payload = {"menu_button": _menu_button(args)}
		if args.get("chat_id") not in (None, ""):
			payload["chat_id"] = _int(args, "chat_id")
		return client.call("setChatMenuButton", payload)
	cid = str(args.get("business_connection_id") or "")
	if action == "get_business_connection":
		conn = _connection(gateway, args)
		return {k: conn.get(k) for k in ("id", "owner_id", "owner_name", "user_chat_id", "rights", "is_enabled")}
	try:
		if action == "send_business_message":
			text = _text(args, "text", 4096)
			return biz.reply_as_business(cid, _int(args, "chat_id"), text, sender=client, reply_to=args.get("reply_to_message_id"))
		if action == "read_business_message":
			return biz.mark_read(cid, _int(args, "chat_id"), _int(args, "message_id"), sender=client)
		ids = args.get("message_ids")
		if isinstance(ids, str):
			ids = [i for i in ids.replace(",", " ").split() if i]
		if not isinstance(ids, list) or not ids:
			raise Refused("invalid_argument", "message_ids must be a non-empty list")
		return biz.delete_messages(cid, [int(i) for i in ids], sender=client, own_only=not _truthy(args.get("all_messages")))
	except biz.BusinessReplyBlocked as exc:
		raise Refused("business_right_missing", str(exc), reason=exc.reason) from None
	except (TypeError, ValueError) as exc:
		raise Refused("invalid_argument", str(exc)) from None


# -- entrypoint ----------------------------------------------------------------------------------


def handle_action(action: str = "", **kwargs) -> str:
	action = str(action or "").strip()
	if action not in ACTIONS:
		return _out({"success": False, "error": "unknown_action", "message": f"Unknown action. Use one of: {', '.join(ACTIONS)}"})
	group, right, destructive, counted = ACTIONS[action]
	gateway = scope.run_gateway()
	run_id = scope.effective_run_id()
	args = dict(kwargs)
	counted_here = False
	send_claimed = False
	try:
		if not gateway:
			raise Refused("action_not_permitted", "Telegram admin actions are only available inside a Telegram gateway conversation.")
		if not _flag(gateway, group):
			raise Refused(
				"action_not_permitted",
				f"This gateway does not allow agents to use {group} actions ({FLAGS[group]} is off).",
			)
		if destructive:
			_require_owner(gateway)
		chat = ""
		if action in CHAT_ACTIONS:
			chat = scope.normalize_chat(args.get("chat_id")) or scope.current_chat(run_id)
			if not chat:
				raise Refused("invalid_argument", "chat_id is required")
			refusal = scope.check_recipient(gateway, run_id, chat)
			if refusal:
				raise Refused("action_not_permitted", json.loads(refusal)["message"])
			args["chat_id"] = chat
		if action == "set_my_commands" and str(args.get("command_scope") or "default") in ("chat", "chat_member", "chat_administrators"):
			target = scope.normalize_chat(args.get("chat_id"))
			if not target:
				raise Refused("invalid_argument", "chat_id is required for a chat-scoped command list")
			refusal = scope.check_recipient(gateway, run_id, target)
			if refusal:
				raise Refused("action_not_permitted", json.loads(refusal)["message"])
		if action == "set_chat_menu_button" and args.get("chat_id") not in (None, ""):
			target = scope.normalize_chat(args.get("chat_id"))
			if not target:
				raise Refused("invalid_argument", "chat_id must be a numeric chat id")
			refusal = scope.check_recipient(gateway, run_id, target)
			if refusal:
				raise Refused("action_not_permitted", json.loads(refusal)["message"])
		token = _token()
		if not token:
			raise Refused("not_configured", "Telegram bot token not configured")
		client = _make_client(token)
		try:
			if action in CHAT_ACTIONS:
				_check_bot_rights(client, chat, right, action)
				if action in TARGET_ACTIONS:
					_check_target(client, gateway, chat, _int(args, "user_id"), action)
			elif group == "business" and action != "get_business_connection":
				_business_scope(action, args, _connection(gateway, args), gateway, run_id)
			pending = _gate_destructive(action, args, gateway, chat) if destructive else None
			if counted:
				_cap_claim(gateway, run_id)
				counted_here = True
			if pending is not None:
				status = _request_human_approval(pending, client)
				_audit(gateway, action, args, "pending_human_approval")
				return _out({"success": True, **status})
			if action == "send_business_message":
				cap_refusal = scope.claim_send(gateway, run_id)
				if cap_refusal:
					raise Refused("send_cap_exceeded", json.loads(cap_refusal)["message"])
				send_claimed = True
			result = _execute(action, args, client, gateway, chat)
		except TelegramApiError as exc:
			raise Refused("telegram_error", f"Telegram error: {client.redact(exc.description)}") from None
		except aa.AdminActionError as exc:
			raise Refused(exc.code, str(exc)) from None
		except Refused:
			raise
		except ValueError as exc:
			raise Refused("invalid_argument", client.redact(exc)) from None
	except Refused as refusal:
		if counted_here:
			_cap_release(gateway, run_id)
		if send_claimed:
			scope.release_send(gateway, run_id)
		_audit(gateway, action, args, "refused", refusal.payload["error"])
		return _out(refusal.payload)
	_audit(gateway, action, args, "ok")
	return _out({"success": True, "action": action, "result": result})
