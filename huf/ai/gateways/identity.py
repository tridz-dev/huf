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
Auto-map is OFF unless the Integration Settings credential ``auto_link_by_email`` is "1"
(scope ``users:read.email``); it maps only a human member of the gateway's own workspace to
exactly one enabled Frappe user with that email.

Self-link token: stateless HMAC-SHA256 over a JSON payload keyed with the site's
``encryption_key``, plus a cache nonce (15 minutes) that makes it one-time; no secret or
personal data is in the URL. Confirmation is POST-only for a logged-in non-Guest user;
``preview_self_link`` (GET) only shows what would be linked.

Two-way proof: confirming on the web creates a ``Pending`` link and DMs the Slack user
(``identity_confirm``); only that user clicking "Yes, link it" makes it ``Linked``. Pending
links never resolve to a user. The token is delivered privately, never to the channel.

Concurrency: the nonce is consumed with an atomic cache claim and Linked-row creation is
serialised by a short per-(gateway, team, person) lock plus a re-check.
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
_ADMIN_SOURCES = ("Admin",)  # the only link source that may resolve to Administrator
# Only a System Manager may link an identity to Administrator or to a user holding one of these.
PRIVILEGED_ROLES = ("System Manager",)
_USED_PREFIX = "huf_identity_link_used:"
_LOCK_PREFIX = "huf_identity_link_lock:"
_LOCK_TTL = 30


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


def _has_revoked(gateway_name: str, team_id: str, external_id: str) -> bool:
	return bool(
		frappe.db.get_value(
			DOCTYPE,
			{"gateway": gateway_name, "team_id": team_id, "external_id": external_id, "state": "Revoked"},
			"name",
		)
	)


def _claim(key: str, ttl: int) -> bool:
	"""Atomically claim ``key`` (SET NX); False if already claimed. Same approach as gateway_send."""
	cache = _cache()
	try:
		return bool(cache.set(cache.make_key(key), 1, nx=True, ex=ttl))
	except (AttributeError, TypeError):
		if cache.get_value(key):
			return False
		cache.set_value(key, 1, expires_in_sec=ttl)
		return True


def _release(key: str) -> None:
	try:
		_cache().delete_value(key)
	except Exception:
		pass


def key_lock(gateway_name: str, team_id: str, external_id: str) -> str | None:
	"""Take the short per-person lock; returns the lock key or None if someone else holds it."""
	key = f"{_LOCK_PREFIX}{gateway_name}:{team_id}:{external_id}"
	return key if _claim(key, _LOCK_TTL) else None


def release_key_lock(key: str | None) -> None:
	if key:
		_release(key)


def _user_enabled(user: str) -> bool:
	return bool(user) and bool(frappe.db.get_value("User", user, "enabled"))


def _usable(user: str, source: str | None = None) -> bool:
	"""A user a run may execute as: enabled, never Guest; Administrator only via admin link."""
	if not user or user == "Guest" or not _user_enabled(user):
		return False
	if user == "Administrator" and source not in _ADMIN_SOURCES:
		return False
	return True


def _create_link(gateway, team_id, external_id, user, source, label=None, linked_by=None, state="Linked"):
	doc = frappe.get_doc(
		{
			"doctype": DOCTYPE,
			"gateway": gateway.name,
			"provider": getattr(gateway, "provider", None) or "slack",
			"team_id": team_id,
			"external_id": external_id,
			"user": user,
			"state": state,
			"source": source,
			"display_label": label,
			"linked_at": frappe.utils.now() if state == "Linked" else None,
			"linked_by": linked_by,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc


# --------------------------------------------------------------------------- auto-map
def _auto_map(gateway, team_id: str, sender: str) -> str | None:
	if get_gateway_credential(gateway, "auto_link_by_email") != "1":
		return None
	if _has_revoked(gateway.name, team_id, sender):
		return None  # an admin revoked this person: only an explicit re-link may restore it
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
	lock = key_lock(gateway.name, team_id, sender)
	if not lock:
		return None
	try:
		if _find_link(gateway.name, team_id, sender):
			return None
		_create_link(gateway, team_id, sender, users[0], "Auto email")
	finally:
		release_key_lock(lock)
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
	"""Internal helper: signed, 15-minute, one-time token (``label`` = display name for the confirm page)."""
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
	"""Create a ``Pending`` link and DM the Slack user; it resolves only once they click "Yes, link it"."""
	user = _require_login()
	data = _verify_token(token)
	if not _claim(_USED_PREFIX + str(data["n"]), TOKEN_TTL_SECONDS + 60):
		frappe.throw(_("This link is invalid or has expired. Ask the bot for a new one in Slack."), frappe.PermissionError)
	_cache().delete_value(_NONCE_PREFIX + str(data["n"]))
	gateway = frappe.get_doc("Gateway", data["g"])
	lock = key_lock(gateway.name, data["t"], data["x"])
	if not lock:
		frappe.throw(_("Another link attempt is in progress. Try again in a moment."), frappe.PermissionError)
	try:
		existing = _find_link(gateway.name, data["t"], data["x"])
		if existing and existing.user != user:
			frappe.throw(_("This Slack account is already linked to another user."), frappe.PermissionError)
		if existing:
			return {"linked": True, "pending": False, "user": user}
		doc = _create_link(gateway, data["t"], data["x"], user, "Self link", linked_by=user, state="Pending")
	finally:
		release_key_lock(lock)
	from huf.ai.gateways import identity_confirm

	try:
		identity_confirm.send_confirmation(gateway, doc.name, data["t"], data["x"], user)
	except Exception:
		frappe.db.set_value(DOCTYPE, doc.name, "state", "Revoked")
		try:
			frappe.log_error(frappe.get_traceback(), "Gateway identity: link confirmation DM failed"[:140])
		except Exception:
			pass
		frappe.throw(_("Could not send the confirmation message in Slack. Ask the bot for a new link."))
	return {"linked": False, "pending": True, "user": user}


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


def _is_privileged_user(user: str) -> bool:
	if user == "Administrator":
		return True
	roles = set(frappe.get_roles(user) or [])
	return bool(roles & set(PRIVILEGED_ROLES))


def _require_can_assign(user: str) -> None:
	"""Only a System Manager may map an identity to Administrator or a privileged user."""
	if "System Manager" in (frappe.get_roles() or []):
		return
	if _is_privileged_user(user):
		frappe.throw(_("Only a System Manager can link a person to a privileged user."), frappe.PermissionError)


@frappe.whitelist(methods=["POST"])
def link_identity(gateway: str, team_id: str, external_id: str, user: str) -> dict:
	_require_admin(gateway)
	if not (team_id and external_id):
		frappe.throw(_("Workspace and person IDs are required."))
	if user == "Guest" or not _user_enabled(user):
		frappe.throw(_("Choose an enabled, non-Guest user."))
	_require_can_assign(user)
	gw = frappe.get_doc("Gateway", gateway)
	existing = _find_link(gateway, team_id, external_id)
	if existing:
		_require_can_assign(existing.user)  # cannot take over a privileged user's link either
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
	"""``{team or gateway}:{channel}:{thread_ts or sender}``: per thread, else per sender (no shared context)."""
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

try:  # registers the "idlink:" button handler; a failure only leaves links Pending (fail closed)
	from huf.ai.gateways import identity_confirm  # noqa: F401
except Exception:
	try:
		frappe.log_error(frappe.get_traceback(), "Gateway identity: confirm handler not loaded"[:140])
	except Exception:
		pass
