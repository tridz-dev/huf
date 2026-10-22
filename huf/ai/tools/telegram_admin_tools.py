"""Telegram admin tools for HUF agents: group administration, bot profile and secretary (business) actions.

One consolidated tool (``telegram_admin``) with an ``action`` parameter. Everything here is OFF by default
and gated per action group by a flag on the run's own Gateway (read server-side, never from arguments):

- group admin  -> ``telegram_agent_allow_group_admin``
- profile      -> ``telegram_agent_allow_profile``
- business     -> ``telegram_agent_allow_business``

A run that is not inside an enabled Telegram gateway is always refused. Safety layers, in order:
scope (chat must be in the gateway's send scope), bot rights (getChatMember(bot) must show the needed admin
right), target protection (chat admins and the gateway's paired admins are never ban/restrict/demote targets,
and nobody can be given ``can_promote_members``), a two-step ``confirm`` for destructive actions (a one-time
token bound to action+args+gateway+chat, 5 minutes, required when the trigger is not the cockpit owner),
a per-run cap and an audit entry per executed action.

Bot API verified against https://core.telegram.org/bots/api (Bot API 10.3).
"""

from __future__ import annotations

import hashlib
import json
import secrets
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
# action -> (group, bot admin right required or None, destructive, counts against the cap)
ACTIONS: dict[str, tuple[str, Optional[str], bool, bool]] = {
	"ban": ("group", "can_restrict_members", True, True),
	"unban": ("group", "can_restrict_members", False, True),
	"restrict": ("group", "can_restrict_members", True, True),
	"unrestrict": ("group", "can_restrict_members", False, True),
	"promote": ("group", "can_promote_members", True, True),
	"demote": ("group", "can_promote_members", False, True),
	"set_chat_title": ("group", "can_change_info", False, True),
	"set_chat_description": ("group", "can_change_info", False, True),
	"pin": ("group", "can_pin_messages", False, True),
	"unpin": ("group", "can_pin_messages", False, True),
	"delete_message": ("group", "can_delete_messages", True, True),
	"approve_join_request": ("group", "can_invite_users", False, True),
	"decline_join_request": ("group", "can_invite_users", False, True),
	"create_invite_link": ("group", "can_invite_users", False, True),
	"revoke_invite_link": ("group", "can_invite_users", False, True),
	"get_admins": ("group", None, False, False),
	"set_my_commands": ("profile", None, True, True),
	"set_my_name": ("profile", None, False, True),
	"set_my_description": ("profile", None, False, True),
	"set_my_short_description": ("profile", None, False, True),
	"set_chat_menu_button": ("profile", None, False, True),
	"get_business_connection": ("business", None, False, False),
	"send_business_message": ("business", None, False, True),
	"read_business_message": ("business", None, False, True),
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


def _is_owner_run(gateway: str, chat: str) -> bool:
	"""True when the run's chat is the private chat of a paired cockpit admin of this gateway."""
	if not chat:
		return False
	try:
		return bool(
			frappe.db.get_value(
				"Telegram Admin Binding", {"gateway": gateway, "chat_id": str(chat), "is_active": 1}, "name"
			)
		)
	except Exception:
		return False


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


def _cap_claim(gateway: str, run_id: Optional[str]) -> None:
	if not run_id:
		return
	limit = _cap_limit(gateway)
	count = _cap_count(gateway, run_id)
	if count >= limit:
		raise Refused(
			"admin_cap_exceeded",
			f"This run already performed its limit of {limit} Telegram admin actions.",
			limit=limit,
		)
	_cache().set_value(_cap_key(gateway, run_id), count + 1, expires_in_sec=24 * 3600)


def _cap_release(gateway: str, run_id: Optional[str]) -> None:
	if run_id:
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


def _gate_destructive(action: str, args: dict, gateway: str, chat: str) -> None:
	owner = _is_owner_run(gateway, scope.current_chat(scope.effective_run_id()))
	fingerprint = _fingerprint(action, args, gateway, chat)
	confirmed = _truthy(args.get("confirm"))
	token = str(args.get("confirmation_token") or "")
	if owner:
		if not confirmed:
			raise Refused(
				"needs_confirmation",
				f"This is destructive: {_describe(action, args, chat)}. Call again with confirm=true to proceed.",
				effect=_describe(action, args, chat),
			)
		return
	if token:
		stored = None
		try:
			stored = _cache().get_value(_confirm_key(token))
			_cache().delete_value(_confirm_key(token))  # single use, consumed even on mismatch
		except Exception:
			stored = None
		if not stored or stored.get("exp", 0) < time.time():
			raise Refused("confirmation_invalid", "The confirmation token is unknown, expired or already used.")
		if stored.get("fingerprint") != fingerprint:
			raise Refused(
				"confirmation_mismatch",
				"The confirmation token was issued for different arguments, gateway or chat. Start again.",
			)
		if not confirmed:
			raise Refused("needs_confirmation", "Pass confirm=true together with the confirmation_token.")
		return
	new_token = secrets.token_urlsafe(16)
	_cache().set_value(
		_confirm_key(new_token), {"fingerprint": fingerprint, "exp": time.time() + CONFIRM_TTL}, expires_in_sec=CONFIRM_TTL
	)
	raise Refused(
		"needs_confirmation",
		f"This is destructive: {_describe(action, args, chat)}. Ask the requester to approve, then call again with "
		f"the same arguments, confirm=true and this confirmation_token (valid 5 minutes, single use).",
		effect=_describe(action, args, chat),
		confirmation_token=new_token,
		expires_in=CONFIRM_TTL,
	)


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
	if not conn or (conn.get("gateway") and conn["gateway"] != gateway):
		raise Refused("unknown_connection", "This gateway does not know that business connection.")
	return conn


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
	try:
		if not gateway:
			raise Refused("action_not_permitted", "Telegram admin actions are only available inside a Telegram gateway conversation.")
		if not _flag(gateway, group):
			raise Refused(
				"action_not_permitted",
				f"This gateway does not allow agents to use {group} actions ({FLAGS[group]} is off).",
			)
		chat = ""
		if action in CHAT_ACTIONS:
			chat = scope.normalize_chat(args.get("chat_id")) or scope.current_chat(run_id)
			if not chat:
				raise Refused("invalid_argument", "chat_id is required")
			refusal = scope.check_recipient(gateway, run_id, chat)
			if refusal:
				raise Refused("action_not_permitted", json.loads(refusal)["message"])
			args["chat_id"] = chat
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
				_connection(gateway, args)
			if destructive:
				_gate_destructive(action, args, gateway, chat)
			if counted:
				_cap_claim(gateway, run_id)
				counted_here = True
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
		if refusal.payload["error"] != "needs_confirmation":
			_audit(gateway, action, args, "refused", refusal.payload["error"])
		return _out(refusal.payload)
	_audit(gateway, action, args, "ok")
	return _out({"success": True, "action": action, "result": result})
