"""Slack identity mapping: who is the person behind a Slack message?

Registered hooks (provider ``slack``, at import time):

- ``resolve_run_user``: find the Linked ``Gateway Identity Link`` for
  (gateway, team_id, sender). Linked => run as that Frappe user. Not linked =>
  optionally auto-map by verified email (site opt-in), else follow the gateway's
  ``unmapped_policy``: ask the person to link their account (denial with a user-visible
  reason holding a one-time link) or return None (gateway ``execution_user``).
- ``resolve_conversation_key``: per-user context in channels, per-thread in threads.
- ``on_run_success``: record the requester on the Agent Run / Flow Run.

Rules: identity is keyed on (team_id, user_id), never on email. Never returns Guest.
Auto-map is OFF unless the Integration Settings credential ``auto_link_by_email`` is "1";
it needs the Slack scope ``users:read.email`` (add it to the app manifest) and only maps
a human member of the gateway's own workspace (not a bot, deleted, guest or Slack Connect
user) to exactly one enabled Frappe user with that email.

Self-link token: stateless HMAC-SHA256 over a JSON payload using the site's
``encryption_key`` (never leaves the server, nothing to store for verification), plus a
random nonce kept in the cache for 15 minutes so the token is one-time. Nothing secret or
personal (no email) is in the URL. Confirmation is POST-only and requires a logged-in
non-Guest user; ``preview_self_link`` (GET) only shows what would be linked, so a link
clicked by mistake never links anything.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

import frappe
from frappe import _

from huf.ai.gateways import hooks as gw_hooks
from huf.ai.gateways.slack_context import get_gateway_credential, get_slack_api

DOCTYPE = "Gateway Identity Link"
TOKEN_TTL_SECONDS = 15 * 60
POLICY_ASK = "Ask to link account"
POLICY_SERVICE = "Use service user"
_NONCE_PREFIX = "huf_identity_link_nonce:"
_PROMPT_PREFIX = "huf_identity_link_prompt:"
PROMPT_THROTTLE_SECONDS = 2 * 60
_LABEL_MAX = 80
_UNSAFE_USERS = ("Guest", "Administrator")


# --------------------------------------------------------------------------- helpers
def _payload(event) -> dict:
	raw = getattr(event, "raw_payload", None)
	if isinstance(raw, str):
		try:
			raw = json.loads(raw)
		except ValueError:
			raw = None
	return raw if isinstance(raw, dict) else {}


def _team_id(event) -> str:
	payload = _payload(event)
	team = payload.get("team_id") or getattr(event, "team_id", None)
	return str(team or "")


def _slack_event(event) -> dict:
	inner = _payload(event).get("event")
	return inner if isinstance(inner, dict) else {}


def _find_link(gateway_name: str, team_id: str, external_id: str):
	return frappe.db.get_value(
		DOCTYPE,
		{"gateway": gateway_name, "team_id": team_id, "external_id": external_id, "state": "Linked"},
		["name", "user", "source"],
		as_dict=True,
	)


def _user_enabled(user: str) -> bool:
	return bool(user) and bool(frappe.db.get_value("User", user, "enabled"))


def _usable(user: str, source: str | None = None) -> bool:
	"""A user a run may execute as: enabled, never Guest; Administrator only via admin link."""
	if not user or user == "Guest" or not _user_enabled(user):
		return False
	if user == "Administrator" and source != "Admin":
		return False
	return True


def _create_link(gateway, team_id, external_id, user, source, label=None, linked_by=None):
	doc = frappe.get_doc(
		{
			"doctype": DOCTYPE,
			"gateway": gateway.name,
			"provider": getattr(gateway, "provider", None) or "slack",
			"team_id": team_id,
			"external_id": external_id,
			"user": user,
			"state": "Linked",
			"source": source,
			"display_label": label,
			"linked_at": frappe.utils.now(),
			"linked_by": linked_by,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc


# --------------------------------------------------------------------------- auto-map
def _auto_map(gateway, team_id: str, sender: str) -> str | None:
	if get_gateway_credential(gateway, "auto_link_by_email") != "1":
		return None
	from huf.ai.gateways.slack_api import inspect_token

	api = get_slack_api(gateway)
	workspace = (inspect_token(api) or {}).get("team_id")
	if not workspace or workspace != team_id:
		return None
	info = api.users_info(sender) or {}
	if info.get("team_id") != workspace:
		return None
	if info.get("is_bot") or info.get("deleted") or info.get("is_restricted") or info.get("is_ultra_restricted"):
		return None
	email = ((info.get("profile") or {}).get("email") or "").strip().lower()
	if not email:
		return None
	users = frappe.get_all("User", filters={"email": email, "enabled": 1}, pluck="name", limit=2)
	if len(users) != 1 or not _usable(users[0], "Auto email"):
		return None
	_create_link(gateway, team_id, sender, users[0], "Auto email")
	return users[0]


# --------------------------------------------------------------------------- self-link token
def _secret() -> bytes:
	key = (frappe.local.conf or {}).get("encryption_key") if frappe.local.conf else None
	if not key:
		raise ValueError("Site has no encryption_key; cannot sign self-link tokens")
	return str(key).encode()


def _b64(data: bytes) -> str:
	return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(text: str) -> bytes:
	return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sign(body: str) -> str:
	return hmac.new(_secret(), body.encode(), hashlib.sha256).hexdigest()


def _cache():
	cache = frappe.cache
	return cache() if callable(cache) and not hasattr(cache, "get_value") else cache


def create_self_link_token(gateway: str, team_id: str, external_id: str, label: str | None = None) -> str:
	"""Internal helper (not whitelisted): signed, 15-minute, one-time token.

	``label`` is an optional display name of the Slack person, shown on the confirm page.
	"""
	nonce = frappe.generate_hash(length=20)
	payload = {"g": gateway, "t": team_id, "x": external_id, "e": int(time.time()) + TOKEN_TTL_SECONDS, "n": nonce}
	if label:
		payload["l"] = str(label)[:_LABEL_MAX]
	body = _b64(json.dumps(payload, separators=(",", ":")).encode())
	_cache().set_value(_NONCE_PREFIX + nonce, 1, expires_in_sec=TOKEN_TTL_SECONDS)
	return f"{body}.{_sign(body)}"


def _verify_token(token: str) -> dict:
	"""Return the payload of a valid, unexpired, unused token or throw PermissionError."""
	bad = _("This link is invalid or has expired. Ask the bot for a new one in Slack.")
	try:
		body, sig = str(token or "").split(".", 1)
		if not hmac.compare_digest(sig, _sign(body)):
			frappe.throw(bad, frappe.PermissionError)
		data = json.loads(_unb64(body))
	except frappe.PermissionError:
		raise
	except Exception:
		frappe.throw(bad, frappe.PermissionError)
	if not isinstance(data, dict) or int(data.get("e") or 0) < time.time():
		frappe.throw(bad, frappe.PermissionError)
	if not _cache().get_value(_NONCE_PREFIX + str(data.get("n"))):
		frappe.throw(bad, frappe.PermissionError)
	return data


def _require_login() -> str:
	user = frappe.session.user
	if not user or user in _UNSAFE_USERS or not _user_enabled(user):
		frappe.throw(_("Log in to Huf with your own account to link it."), frappe.PermissionError)
	return user


def self_link_url(token: str) -> str:
	return f"{frappe.utils.get_url()}/huf/link-account?token={token}"


def _sender_label(event) -> str | None:
	"""Display name of the sender if the event already carries it (no Slack API call)."""
	profile = _slack_event(event).get("user_profile")
	if isinstance(profile, dict):
		return profile.get("display_name") or profile.get("real_name") or profile.get("name") or None
	return None


def _prompt_token(gateway: str, team_id: str, sender: str, label: str | None) -> str:
	"""At most one fresh token per sender per 2 minutes; within the window reuse the last one."""
	key = f"{_PROMPT_PREFIX}{gateway}:{team_id}:{sender}"
	cache = _cache()
	cached = cache.get_value(key)
	if cached:
		cached = cached.decode() if isinstance(cached, bytes) else str(cached)
		try:
			_verify_token(cached)
			return cached
		except Exception:
			pass
	token = create_self_link_token(gateway, team_id, sender, label)
	cache.set_value(key, token, expires_in_sec=PROMPT_THROTTLE_SECONDS)
	return token


@frappe.whitelist(methods=["GET"])
def preview_self_link(token: str) -> dict:
	"""Show which Slack person would be linked to the logged-in user. Changes nothing."""
	user = _require_login()
	data = _verify_token(token)
	return {
		"gateway": data["g"],
		"team_id": data["t"],
		"external_id": data["x"],
		"user": user,
		"slack_label": data.get("l") or data["x"],
		"workspace_label": data["g"],
	}


@frappe.whitelist(methods=["POST"])
def confirm_self_link(token: str) -> dict:
	"""Link the logged-in (non-Guest) user to the Slack identity in a valid one-time token."""
	user = _require_login()
	data = _verify_token(token)
	_cache().delete_value(_NONCE_PREFIX + str(data["n"]))
	gateway = frappe.get_doc("Gateway", data["g"])
	existing = _find_link(gateway.name, data["t"], data["x"])
	if existing and existing.user != user:
		frappe.throw(_("This Slack account is already linked to another user."), frappe.PermissionError)
	if not existing:
		_create_link(gateway, data["t"], data["x"], user, "Self link", linked_by=user)
	return {"linked": True, "user": user}


# --------------------------------------------------------------------------- admin APIs
def _require_admin(gateway: str | None = None) -> None:
	if frappe.session.user == "Guest":
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	if "System Manager" in (frappe.get_roles() or []):
		return
	if gateway and frappe.has_permission("Gateway", "write", gateway):
		return
	frappe.throw(_("Not permitted"), frappe.PermissionError)


@frappe.whitelist()
def list_identity_links(gateway: str) -> list:
	_require_admin(gateway)
	return frappe.get_all(
		DOCTYPE,
		filters={"gateway": gateway},
		fields=[
			"name", "gateway", "team_id", "external_id", "user", "state", "source",
			"display_label", "linked_at", "linked_by",
		],
		order_by="modified desc",
		limit_page_length=500,
	)


@frappe.whitelist(methods=["POST"])
def link_identity(gateway: str, team_id: str, external_id: str, user: str) -> dict:
	_require_admin(gateway)
	if not (team_id and external_id):
		frappe.throw(_("Workspace and person IDs are required."))
	if user == "Guest" or not _user_enabled(user):
		frappe.throw(_("Choose an enabled, non-Guest user."))
	gw = frappe.get_doc("Gateway", gateway)
	existing = _find_link(gateway, team_id, external_id)
	if existing:
		frappe.db.set_value(DOCTYPE, existing.name, {"user": user, "source": "Admin", "linked_by": frappe.session.user})
		return {"name": existing.name, "user": user}
	doc = _create_link(gw, team_id, external_id, user, "Admin", linked_by=frappe.session.user)
	return {"name": doc.name, "user": user}


@frappe.whitelist(methods=["POST"])
def unlink_identity(name: str) -> dict:
	gateway = frappe.db.get_value(DOCTYPE, name, "gateway")
	_require_admin(gateway)
	frappe.db.set_value(DOCTYPE, name, "state", "Revoked")
	return {"name": name, "state": "Revoked"}


# --------------------------------------------------------------------------- hooks
def resolve_run_user(gateway, event):
	team_id = _team_id(event)
	sender = str(getattr(event, "sender_id", "") or "")
	if not team_id or not sender:
		raise gw_hooks.GatewayHookDenied("Slack event has no workspace (team_id) or sender; cannot identify the person.")

	link = _find_link(gateway.name, team_id, sender)
	if link:
		if _usable(link.user, link.source):
			return link.user
		raise gw_hooks.GatewayHookDenied(
			gw_hooks.USER_VISIBLE_PREFIX + "Your linked Huf account is disabled. Please contact an administrator."
		)

	mapped = _auto_map(gateway, team_id, sender)
	if mapped:
		return mapped

	policy = getattr(gateway, "unmapped_policy", None) or POLICY_ASK
	if policy == POLICY_SERVICE:
		return None
	token = _prompt_token(gateway.name, team_id, sender, _sender_label(event))
	raise gw_hooks.GatewayHookDenied(
		gw_hooks.USER_VISIBLE_PREFIX
		+ "I don't know which Huf account is yours yet. Open this link (while logged in to Huf) "
		+ f"to connect your account; it works once and expires in 15 minutes: {self_link_url(token)}"
	)


def resolve_conversation_key(gateway, event):
	"""``{team or gateway}:{channel}:{thread_ts or sender}``.

	Threaded replies share one conversation per thread; un-threaded channel messages and DMs
	are per sender, so users never see each other's context.
	"""
	inner = _slack_event(event)
	channel = str(getattr(event, "conversation_id", "") or inner.get("channel") or "")
	thread_ts = str(inner.get("thread_ts") or "")
	sender = str(getattr(event, "sender_id", "") or "")
	if not channel or not (thread_ts or sender):
		return None
	return f"{_team_id(event) or gateway.name}:{channel}:{thread_ts or sender}"


def _record(doctype: str, name: str, values: dict) -> None:
	if name:
		frappe.db.set_value(doctype, name, values, update_modified=False)


def on_run_success(gateway, event, kind, response):
	try:
		sender = str(getattr(event, "sender_id", "") or "")
		link = _find_link(gateway.name, _team_id(event), sender)
		requester = link.user if link else frappe.session.user
		if kind == "flow":
			_record(
				"Flow Run",
				getattr(response, "name", None),
				{"gateway_event": event.name, "requester_external_id": sender, "requester_user": requester},
			)
		else:
			_record(
				"Agent Run",
				getattr(event, "agent_run", None),
				{
					"gateway": gateway.name,
					"gateway_event": event.name,
					"requester_external_id": sender,
					"requester_user": requester,
				},
			)
	except Exception:
		try:
			frappe.log_error(frappe.get_traceback(), "Gateway identity: record requester failed"[:140])
		except Exception:
			pass


gw_hooks.register(gw_hooks.RESOLVE_RUN_USER, resolve_run_user, provider="slack")
gw_hooks.register(gw_hooks.RESOLVE_CONVERSATION_KEY, resolve_conversation_key, provider="slack")
gw_hooks.register(gw_hooks.ON_RUN_SUCCESS, on_run_success, provider="slack")
