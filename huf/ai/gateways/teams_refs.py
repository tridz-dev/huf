"""Teams conversation references and install lifecycle (WP T4).

Keeps one ``Teams Conversation Reference`` row per (gateway, tenant, conversation) so the
bot can message people proactively. Registers two hooks for the Teams provider:

- ``pre_ingest_filter`` at ``HOOK_PRIORITY_INSTALL`` (10, runs before the tenant check at 20):
  installationUpdate / conversationUpdate activities about the bot itself update the
  reference (installed 1/0) and are dropped (return False; reason ``install_event``).
- ``on_event_received``: real messages upsert the reference.

Because the install filter runs before the tenant allowlist, it re-checks the tenant through
an injectable callable (``set_tenant_allowed_check``) and never writes rows for foreign tenants.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Callable

import frappe
from frappe.utils import now_datetime

from huf.ai.gateways import hooks
from huf.ai.gateways import teams_contract as tc
from huf.ai.gateways.teams_contract import TeamsMeta

DOCTYPE = "Teams Conversation Reference"
INSTALL_EVENT_REASON = "install_event"
# hooks lowercases gateway.provider ("Microsoft Teams" -> "microsoft teams"), so the
# registration key is the lowercased label, not PROVIDER_ID ("microsoft_teams").
HOOK_PROVIDER = tc.PROVIDER_LABEL.lower()

_CONV_TYPES = ("personal", "channel", "groupChat")


def reference_name(gateway: str, tenant_id: str, conversation_id: str) -> str:
	"""Deterministic primary key: unique per (gateway, tenant_id, conversation_id)."""
	raw = "\x1f".join((gateway or "", tenant_id or "", conversation_id or ""))
	return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


def _s(value: Any) -> str:
	return str(value) if value else ""


def parse_meta(activity: dict) -> TeamsMeta:
	"""Extract routing metadata from a Bot Framework activity (missing parts become "")."""
	activity = activity if isinstance(activity, dict) else {}
	conv = activity.get("conversation") or {}
	data = activity.get("channelData") or {}
	tenant = _s((data.get("tenant") or {}).get("id")) or _s(conv.get("tenantId"))
	conv_id = _s(conv.get("id"))
	root = ""
	if ";messageid=" in conv_id:
		root = conv_id.split(";messageid=", 1)[1].split(";", 1)[0]
	ctype = _s(conv.get("conversationType"))
	team = data.get("team") or {}
	channel = data.get("channel") or {}
	return TeamsMeta(
		tenant_id=tenant,
		service_url=_s(activity.get("serviceUrl")),
		conversation_type=ctype,
		conversation_id=conv_id,
		root_id=root,
		user_aad_id=_s((activity.get("from") or {}).get("aadObjectId")),
		bot_id=_s((activity.get("recipient") or {}).get("id")),
		team_id=_s(team.get("id")),
		channel_id=_s(channel.get("id")),
	)


def _base_conversation_id(conversation_id: str) -> str:
	"""Reference key: the conversation without the channel-thread ``;messageid=`` suffix."""
	return (conversation_id or "").split(";messageid=", 1)[0]


def _find(gateway: str, tenant_id: str, conversation_id: str) -> str | None:
	return frappe.db.get_value(
		DOCTYPE,
		{"gateway": gateway, "tenant_id": tenant_id, "conversation_id": _base_conversation_id(conversation_id)},
		"name",
	)


def upsert_reference(gateway: str, meta: TeamsMeta, *, installed: bool = True) -> str:
	"""Insert or refresh the reference for this conversation; returns its name. Idempotent."""
	if not (meta.tenant_id and meta.conversation_id):
		raise ValueError("tenant_id and conversation_id are required for a conversation reference")
	values = {
		"conversation_type": meta.conversation_type if meta.conversation_type in _CONV_TYPES else "personal",
		"installed": 1 if installed else 0,
		"last_seen_at": now_datetime(),
	}
	for field, value in (
		("service_url", meta.service_url),
		("team_id", meta.team_id),
		("channel_id", meta.channel_id),
		("user_aad_id", meta.user_aad_id),
		("bot_id", meta.bot_id),
	):
		if value:  # never blank out a known value with a partial activity
			values[field] = value
	name = _find(gateway, meta.tenant_id, meta.conversation_id)
	if name:
		frappe.db.set_value(DOCTYPE, name, values)
		return name
	doc = frappe.get_doc(
		{
			"doctype": DOCTYPE,
			"gateway": gateway,
			"tenant_id": meta.tenant_id,
			"conversation_id": _base_conversation_id(meta.conversation_id),
			**values,
		}
	)
	try:
		doc.insert(ignore_permissions=True)
	except frappe.DuplicateEntryError:  # concurrent insert: the deterministic name collided
		name = _find(gateway, meta.tenant_id, meta.conversation_id)
		frappe.db.set_value(DOCTYPE, name, values)
		return name
	return doc.name


def mark_uninstalled(gateway: str, meta: TeamsMeta) -> str | None:
	"""Flip ``installed`` to 0. Creates no row when none exists; returns the name or None."""
	name = _find(gateway, meta.tenant_id, meta.conversation_id)
	if not name:
		return None
	frappe.db.set_value(DOCTYPE, name, {"installed": 0, "last_seen_at": now_datetime()})
	return name


def get_personal_reference(gateway: str, tenant_id: str, user_aad_id: str) -> dict | None:
	"""The installed personal-chat reference for this user in this tenant, else None."""
	if not (tenant_id and user_aad_id):
		return None
	rows = frappe.get_all(
		DOCTYPE,
		filters={
			"gateway": gateway,
			"tenant_id": tenant_id,
			"user_aad_id": user_aad_id,
			"conversation_type": "personal",
			"installed": 1,
		},
		fields=["*"],
		order_by="last_seen_at desc",
		limit=1,
	)
	return rows[0] if rows else None


# --- hooks -------------------------------------------------------------------------------

_TenantCheck = Callable[[Any, str], bool]
_tenant_allowed: _TenantCheck = lambda gateway, tenant_id: True  # noqa: E731


def set_tenant_allowed_check(fn: _TenantCheck | None) -> None:
	"""Inject the allowlist check ``(gateway, tenant_id) -> bool`` (default: allow all).
	The coordinator wires T5's allowlist here; None restores the default."""
	global _tenant_allowed
	_tenant_allowed = fn or (lambda gateway, tenant_id: True)


def _as_activity(value: Any) -> dict:
	if isinstance(value, str):
		try:
			value = json.loads(value)
		except Exception:
			return {}
	return value if isinstance(value, dict) else {}


def _activity_of(source: Any) -> dict:
	"""Raw activity from a filter context (dict) or a Gateway Event (attribute); defensive."""
	if isinstance(source, dict):
		raw = source.get("raw_payload")
	else:
		raw = getattr(source, "raw_payload", None)
	return _as_activity(raw)


def classify(activity: dict) -> str:
	"""One of TeamsActivityKind values, preferring the adapter's ``huf_kind`` tag."""
	tag = activity.get("huf_kind")
	if tag in {k.value for k in tc.TeamsActivityKind}:
		return tag
	kind = activity.get("type")
	if kind == "installationUpdate":
		return tc.TeamsActivityKind.UNINSTALL.value if activity.get("action") == "remove" else (
			tc.TeamsActivityKind.INSTALL.value
		)
	if kind == "conversationUpdate":
		bot = _s((activity.get("recipient") or {}).get("id"))
		added = [m.get("id") for m in activity.get("membersAdded") or [] if isinstance(m, dict)]
		removed = [m.get("id") for m in activity.get("membersRemoved") or [] if isinstance(m, dict)]
		if bot and bot in removed:
			return tc.TeamsActivityKind.UNINSTALL.value
		if bot and bot in added:
			return tc.TeamsActivityKind.INSTALL.value
		return tc.TeamsActivityKind.IGNORED.value
	if kind == "message":
		return tc.TeamsActivityKind.MESSAGE.value
	return tc.TeamsActivityKind.IGNORED.value


def _pre_ingest_install(gateway, context) -> bool:
	activity = _activity_of(context)
	if activity.get("type") not in ("installationUpdate", "conversationUpdate"):
		return True
	kind = classify(activity)
	meta = parse_meta(activity)
	name = getattr(gateway, "name", None) or (gateway.get("name") if isinstance(gateway, dict) else None)
	if meta.tenant_id and meta.conversation_id and _tenant_allowed(gateway, meta.tenant_id):
		if kind == tc.TeamsActivityKind.INSTALL.value:
			upsert_reference(name, meta, installed=True)
		elif kind == tc.TeamsActivityKind.UNINSTALL.value:
			mark_uninstalled(name, meta)
	return False  # install_event: never routed to an agent


def _on_event_received(gateway, event) -> None:
	activity = _activity_of(event)
	if classify(activity) != tc.TeamsActivityKind.MESSAGE.value:
		return
	meta = parse_meta(activity)
	if not (meta.tenant_id and meta.conversation_id) or not _tenant_allowed(gateway, meta.tenant_id):
		return
	upsert_reference(getattr(gateway, "name", None), meta, installed=True)


def register() -> None:
	hooks.register(
		hooks.PRE_INGEST_FILTER, _pre_ingest_install, provider=HOOK_PROVIDER, priority=tc.HOOK_PRIORITY_INSTALL
	)
	hooks.register(hooks.ON_EVENT_RECEIVED, _on_event_received, provider=HOOK_PROVIDER)


register()
