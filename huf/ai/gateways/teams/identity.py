"""Microsoft Teams identity linking: who is the Huf user behind a Teams message?

Reuses the shared ``Gateway Identity Link`` doctype (no new doctype): Teams tenant id =>
``team_id``, Entra object id (``aadObjectId``) => ``external_id``, provider "Microsoft Teams".
Nothing here imports the Slack identity module.

Registered hooks (provider ``microsoft teams``, at import time):

- ``resolve_run_user``: Linked => run as that user. Unlinked => denial with a one-time
  link. NEVER falls back to the gateway ``execution_user``. Guest / external Entra users
  and activities without an Entra object id are not linkable.
- ``on_run_success``: record the requester on the Agent Run / Flow Run.

Self-link token: stateless HMAC-SHA256 over a JSON payload (gateway, tenant, Entra id,
label, expiry) with the site ``encryption_key``, plus a random nonce in the cache so it is
single use. 10 minute expiry. Nothing secret or personal is in the URL. Confirmation is
POST-only and needs a logged-in non-Guest user; preview (GET) changes nothing, so a link
opened by mistake never links anything.
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
from huf.ai.gateways.teams import contract as tc
from huf.ai.gateways.teams.refs import parse_meta

DOCTYPE = "Gateway Identity Link"
HOOK_PROVIDER = tc.PROVIDER_LABEL.lower()
TOKEN_TTL_SECONDS = 10 * 60
PROMPT_THROTTLE_SECONDS = 2 * 60
_NONCE_PREFIX = "huf_teams_link_nonce:"
_PROMPT_PREFIX = "huf_teams_link_prompt:"
_LABEL_MAX = 80
_UNSAFE_USERS = ("Guest", "Administrator")
_FIELDS = ["name", "gateway", "team_id", "external_id", "user", "state", "source", "display_label", "linked_at"]


# --------------------------------------------------------------------------- helpers
def _user_enabled(user: str) -> bool:
	return bool(user) and bool(frappe.db.get_value("User", user, "enabled"))


def _usable(user: str, source: str | None = None) -> bool:
	"""A user a run may execute as: enabled, never Guest; Administrator only via admin link."""
	if not user or user == "Guest" or not _user_enabled(user):
		return False
	return not (user == "Administrator" and source != "Admin")


def _find_link(gateway: str, tenant_id: str, aad_id: str):
	return frappe.db.get_value(
		DOCTYPE,
		{"gateway": gateway, "team_id": tenant_id, "external_id": aad_id, "state": "Linked"},
		["name", "user", "source"],
		as_dict=True,
	)


def _user_link_in_tenant(gateway: str, tenant_id: str, user: str):
	return frappe.db.get_value(
		DOCTYPE,
		{"gateway": gateway, "team_id": tenant_id, "user": user, "state": "Linked"},
		["name", "external_id"],
		as_dict=True,
	)


def _create_link(gateway: str, tenant_id, aad_id, user, source, label=None, linked_by=None, state="Linked"):
	doc = frappe.get_doc(
		{
			"doctype": DOCTYPE,
			"gateway": gateway,
			"provider": tc.PROVIDER_LABEL,
			"team_id": tenant_id,
			"external_id": aad_id,
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


def resolve_user(gateway: str, tenant_id: str, user_aad_id: str) -> str | None:
	"""Huf user linked to (tenant, aadObjectId) on this gateway, else None. Never execution_user."""
	if not (gateway and tenant_id and user_aad_id):
		return None
	link = _find_link(gateway, tenant_id, user_aad_id)
	if link and _usable(link.user, link.source):
		return link.user
	return None


# --------------------------------------------------------------------------- token
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


def create_link_token(gateway: str, tenant_id: str, aad_id: str, label: str | None = None) -> str:
	"""Internal (not whitelisted): signed, 10-minute, single-use token."""
	nonce = frappe.generate_hash(length=20)
	payload = {"g": gateway, "t": tenant_id, "x": aad_id, "e": int(time.time()) + TOKEN_TTL_SECONDS, "n": nonce}
	if label:
		payload["l"] = str(label)[:_LABEL_MAX]
	body = _b64(json.dumps(payload, separators=(",", ":")).encode())
	_cache().set_value(_NONCE_PREFIX + nonce, 1, expires_in_sec=TOKEN_TTL_SECONDS)
	return f"{body}.{_sign(body)}"


def _verify_token(token: str) -> dict:
	bad = _("This link is invalid or has expired. Ask the bot for a new one in Teams.")
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


def link_url(token: str) -> str:
	return f"{frappe.utils.get_url()}/huf/link-account?p=teams&token={token}"


def _prompt_token(gateway: str, tenant_id: str, aad_id: str, label: str | None) -> str:
	"""At most one fresh token per (gateway, tenant, person) per 2 minutes; reuse inside it."""
	key = f"{_PROMPT_PREFIX}{gateway}:{tenant_id}:{aad_id}"
	cache = _cache()
	cached = cache.get_value(key)
	if cached:
		cached = cached.decode() if isinstance(cached, bytes) else str(cached)
		try:
			_verify_token(cached)
			return cached
		except Exception:
			pass
	token = create_link_token(gateway, tenant_id, aad_id, label)
	cache.set_value(key, token, expires_in_sec=PROMPT_THROTTLE_SECONDS)
	return token


@frappe.whitelist(methods=["GET"])
def preview_teams_link(token: str) -> dict:
	"""Show which Teams person would be linked to the logged-in user. Changes nothing.

	``tenant_id`` (the Microsoft tenant GUID) is the field to show prominently.
	``display_label_untrusted`` is the sender-chosen Teams display name: attacker-controlled, so
	only ever secondary text. ``person_label`` is kept for compatibility (same value).
	"""
	user = _require_login()
	data = _verify_token(token)
	label = data.get("l") or ""
	return {
		"gateway": data["g"],
		"team_id": data["t"],
		"tenant_id": data["t"],
		"external_id": data["x"],
		"user": user,
		"person_label": label or data["x"],
		"display_label_untrusted": label,
		"workspace_label": data["t"],
	}


def _huf_name(user: str) -> str:
	try:
		return str(frappe.db.get_value("User", user, "full_name") or user)
	except Exception:
		return user


def _supersede_pending(gateway: str, tenant_id: str, aad_id: str) -> None:
	"""Only the newest self-link attempt for a Teams person stays Pending."""
	rows = frappe.get_all(
		DOCTYPE,
		filters={"gateway": gateway, "team_id": tenant_id, "external_id": aad_id, "state": "Pending"},
		pluck="name",
	)
	for name in rows or []:
		frappe.db.set_value(DOCTYPE, name, "state", "Revoked")


@frappe.whitelist(methods=["POST"])
def confirm_teams_link(token: str) -> dict:
	"""Start linking the logged-in (non-Guest) user to the Teams identity in a valid one-time token.

	Two-way proof: the link is created as ``Pending`` and the Teams person is asked, in their
	personal chat, to confirm ("Did you just connect your Teams account to Huf user <name>?").
	Only that same (tenant, aadObjectId) clicking Yes flips it to ``Linked``. If the question
	cannot be sent the pending row is revoked (fail closed). Pending rows never resolve a user.
	"""
	user = _require_login()
	data = _verify_token(token)
	gateway, tenant, aad = data["g"], data["t"], data["x"]
	_cache().delete_value(_NONCE_PREFIX + str(data["n"]))
	existing = _find_link(gateway, tenant, aad)
	if existing and existing.user != user:
		frappe.throw(_("This Teams account is already linked to another user."), frappe.PermissionError)
	if existing:
		return {"linked": True, "pending": False, "user": user}
	mine = _user_link_in_tenant(gateway, tenant, user)
	if mine and mine.external_id != aad:
		frappe.throw(
			_("Your Huf account is already linked to another Teams account in this organisation."),
			frappe.PermissionError,
		)
	_supersede_pending(gateway, tenant, aad)
	doc = _create_link(
		gateway, tenant, aad, user, "Self link", label=data.get("l"), linked_by=user, state="Pending"
	)
	try:
		from huf.ai.gateways.teams import identity_confirm as teams_identity_confirm

		teams_identity_confirm.send_confirmation(gateway, doc.name, tenant, aad, user)
	except Exception:
		frappe.db.set_value(DOCTYPE, doc.name, "state", "Revoked")
		try:
			frappe.log_error(frappe.get_traceback(), "Teams identity: link confirmation failed"[:140])
		except Exception:
			pass
		frappe.throw(
			_("Could not send the confirmation message in Teams. Ask the bot for a new link."),
			frappe.ValidationError,
		)
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
def list_teams_links(gateway: str) -> list:
	_require_admin(gateway)
	return frappe.get_all(
		DOCTYPE,
		filters={"gateway": gateway, "provider": tc.PROVIDER_LABEL},
		fields=_FIELDS,
		order_by="modified desc",
		limit_page_length=500,
	)


@frappe.whitelist(methods=["POST"])
def link_teams_user(gateway: str, tenant_id: str, aad_object_id: str, user: str) -> dict:
	_require_admin(gateway)
	if not (tenant_id and aad_object_id):
		frappe.throw(_("Tenant and person IDs are required."))
	if user == "Guest" or not _user_enabled(user):
		frappe.throw(_("Choose an enabled, non-Guest user."))
	existing = _find_link(gateway, tenant_id, aad_object_id)
	other = _user_link_in_tenant(gateway, tenant_id, user)
	if other and other.external_id != aad_object_id:
		frappe.throw(_("This user is already linked to another Teams account in this organisation."))
	if existing:
		frappe.db.set_value(
			DOCTYPE, existing.name, {"user": user, "source": "Admin", "linked_by": frappe.session.user}
		)
		return {"name": existing.name, "user": user}
	doc = _create_link(gateway, tenant_id, aad_object_id, user, "Admin", linked_by=frappe.session.user)
	return {"name": doc.name, "user": user}


@frappe.whitelist(methods=["POST"])
def revoke_teams_link(name: str) -> dict:
	gateway = frappe.db.get_value(DOCTYPE, name, "gateway")
	_require_admin(gateway)
	frappe.db.set_value(DOCTYPE, name, "state", "Revoked")
	return {"name": name, "state": "Revoked"}


def disconnect_current(gateway: str, tenant_id: str, aad_object_id: str) -> bool:
	"""Revoke the link of exactly this principal (used by the 'disconnect' command)."""
	if not (gateway and tenant_id and aad_object_id):
		return False
	link = _find_link(gateway, tenant_id, aad_object_id)
	if not link:
		return False
	frappe.db.set_value(DOCTYPE, link.name, "state", "Revoked")
	return True


# --------------------------------------------------------------------------- hooks
def _activity(event) -> dict:
	raw = event.get("raw_payload") if isinstance(event, dict) else getattr(event, "raw_payload", None)
	if isinstance(raw, str):
		try:
			raw = json.loads(raw)
		except ValueError:
			raw = None
	return raw if isinstance(raw, dict) else {}


def _is_guest(activity: dict) -> bool:
	"""Guest / external / unverifiable sender. Conservative: any doubt means "not linkable".

	``from.userType`` is usually absent on message activities, so also deny when
	``from.aadObjectId`` is missing or any tenant claim on the activity (channelData tenant,
	conversation tenantId, ``from.tenantId`` / ``from.properties.tenantId|homeTenantId``) is
	not the conversation's tenant: a B2B guest's home tenant differs from the host tenant.
	TODO(roster): a guest of the HOST tenant carries the host tenant id and no userType, so it
	still looks like a member here; the follow-up is a ``teams.getMember`` roster check
	(TeamsChannelAccount.userRole/tenantId). Graph is deliberately not called from this module.
	"""
	sender = activity.get("from") if isinstance(activity.get("from"), dict) else {}
	props = sender.get("properties") if isinstance(sender.get("properties"), dict) else {}
	kind = sender.get("userType") or props.get("userType") or sender.get("role") or ""
	if str(kind).lower() in ("guest", "external"):
		return True
	if not str(sender.get("aadObjectId") or "").strip():
		return True
	channel_data = activity.get("channelData") if isinstance(activity.get("channelData"), dict) else {}
	conv = activity.get("conversation") if isinstance(activity.get("conversation"), dict) else {}
	tenant = channel_data.get("tenant") if isinstance(channel_data.get("tenant"), dict) else {}
	claims = [
		tenant.get("id"),
		conv.get("tenantId"),
		sender.get("tenantId"),
		props.get("tenantId"),
		props.get("homeTenantId"),
	]
	seen = {str(c).strip().lower() for c in claims if c}
	return len(seen) > 1


def _label(activity: dict) -> str | None:
	name = (activity.get("from") or {}).get("name")
	return str(name) if name else None


def resolve_run_user(gateway, event):
	activity = _activity(event)
	meta = parse_meta(activity)
	if _is_guest(activity) or not (meta.tenant_id and meta.user_aad_id):
		raise gw_hooks.GatewayHookDenied(
			gw_hooks.USER_VISIBLE_PREFIX
			+ "Guest and external Microsoft accounts are not supported. Ask a colleague from your "
			+ "organisation to help."
		)
	link = _find_link(gateway.name, meta.tenant_id, meta.user_aad_id)
	if link:
		if _usable(link.user, link.source):
			return link.user
		raise gw_hooks.GatewayHookDenied(
			gw_hooks.USER_VISIBLE_PREFIX + "Your linked Huf account is disabled. Please contact an administrator."
		)
	if meta.conversation_type != "personal":
		# Never mint a token or post a link where other people can see/click it.
		raise gw_hooks.GatewayHookDenied(
			gw_hooks.USER_VISIBLE_PREFIX
			+ "Connect your Huf account to use this bot. Open a personal chat with me and send connect."
		)
	token = _prompt_token(gateway.name, meta.tenant_id, meta.user_aad_id, _label(activity))
	raise gw_hooks.GatewayHookDenied(
		gw_hooks.USER_VISIBLE_PREFIX
		+ "Connect your Huf account to use this bot. Open this link while logged in to Huf; "
		+ f"it works once and expires in 10 minutes: {link_url(token)}"
	)


def _record(doctype: str, name: str, values: dict) -> None:
	if name:
		frappe.db.set_value(doctype, name, values, update_modified=False)


def on_run_success(gateway, event, kind, response):
	try:
		meta = parse_meta(_activity(event))
		link = _find_link(gateway.name, meta.tenant_id, meta.user_aad_id)
		requester = link.user if link else frappe.session.user
		if kind == "flow":
			_record(
				"Flow Run",
				getattr(response, "name", None),
				{"gateway_event": event.name, "requester_external_id": meta.user_aad_id, "requester_user": requester},
			)
		else:
			_record(
				"Agent Run",
				getattr(event, "agent_run", None),
				{
					"gateway": gateway.name,
					"gateway_event": event.name,
					"requester_external_id": meta.user_aad_id,
					"requester_user": requester,
				},
			)
	except Exception:
		try:
			frappe.log_error(frappe.get_traceback(), "Teams identity: record requester failed"[:140])
		except Exception:
			pass


gw_hooks.register(gw_hooks.RESOLVE_RUN_USER, resolve_run_user, provider=HOOK_PROVIDER)
gw_hooks.register(gw_hooks.ON_RUN_SUCCESS, on_run_success, provider=HOOK_PROVIDER)


try:  # registers the "idlink" card handler; a failure only leaves links Pending (fail closed)
	from huf.ai.gateways.teams import identity_confirm as teams_identity_confirm  # noqa: F401
except Exception:  # pragma: no cover
	pass
