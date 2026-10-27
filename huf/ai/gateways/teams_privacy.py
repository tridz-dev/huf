"""Microsoft Teams private output classification and per-user conversation key (WP T9).

Two hooks for the Teams provider:

- ``resolve_conversation_key``: in rooms (channel / group chat) every person gets their own
  context (``teams:{tenant}:{conversation_root}:{aad}``); personal chats key on the conversation.
- ``resolve_reply_target``: deterministic (no LLM) classification. In a room the answer is sent
  to the asker's personal chat when the tenant policy is "Always private", or "Private when
  records touched" and the run called any tool outside a small allowlist, or the run/event was
  flagged with :func:`mark_sensitive`. Personal chats never change.

Fail closed: ``hooks`` treats ``None`` as "no change", which would post the answer into the room.
Once a private reply is required this handler never raises and never returns ``None``. When a
personal conversation cannot be obtained it posts a neutral note and returns ``UNUSABLE_TARGET``,
a conversation id with no stored reference: the adapter's ``send_reply`` then fails, so the answer
is never posted to the channel.
"""

from __future__ import annotations

import json
from typing import Any

import frappe

from huf.ai.gateways import hooks, teams_api, teams_identity, teams_outbox, teams_refs, teams_tenant
from huf.ai.gateways import teams_contract as tc

HOOK_PROVIDER = teams_refs.HOOK_PROVIDER

ALWAYS_PRIVATE = "Always private"
PRIVATE_WHEN_RECORDS = "Private when records touched"
CHANNEL = "Channel"

UNUSABLE_TARGET = "teams-private-unavailable"
ACK_TEXT = "I sent you the answer in a private chat."
UNAVAILABLE_TEXT = 'Open a private chat with me and send "hi" so I can reply privately.'

SENSITIVE_TTL_SECONDS = 3600
_KEY = "huf:teams:sensitive:"
_THREAD_MARK = ";messageid="
_ROOM_TYPES = ("channel", "groupChat")

# Tools that neither read nor write Frappe documents. Everything else counts as touching records.
SAFE_TOOLS = frozenset(
	{
		"calculator",
		"calculate",
		"get_current_time",
		"get_current_datetime",
		"current_datetime",
		"search_knowledge",
		"knowledge_search",
	}
)


# ---- sensitivity marking -----------------------------------------------------------------
def _cache():
	return frappe.cache()


def _ids(obj) -> list[str]:
	if not obj:
		return []
	if isinstance(obj, str):
		return [obj]
	return [str(v) for v in (getattr(obj, "name", None), getattr(obj, "agent_run", None)) if v]


def mark_sensitive(event_or_name_or_run, reason: str | None = None) -> None:
	"""Flag a gateway event (or agent run) as sensitive; short-lived. Never raises."""
	try:
		for ident in _ids(event_or_name_or_run):
			_cache().set_value(_KEY + ident, reason or "sensitive", expires_in_sec=SENSITIVE_TTL_SECONDS)
	except Exception:
		pass


def is_marked_sensitive(event) -> bool:
	try:
		return any(_cache().get_value(_KEY + i) for i in _ids(event))
	except Exception:
		return False


def clear_sensitive(event_or_name_or_run) -> None:
	try:
		for ident in _ids(event_or_name_or_run):
			_cache().delete_value(_KEY + ident)
	except Exception:
		pass


# ---- activity helpers --------------------------------------------------------------------
def _activity(event) -> dict:
	raw = event.get("raw_payload") if isinstance(event, dict) else getattr(event, "raw_payload", None)
	if isinstance(raw, str):
		try:
			raw = json.loads(raw)
		except Exception:
			return {}
	return raw if isinstance(raw, dict) else {}


def _meta(event) -> tc.TeamsMeta:
	try:
		return teams_refs.parse_meta(_activity(event))
	except Exception:
		return tc.TeamsMeta()


def _base(conversation_id: str) -> str:
	return (conversation_id or "").split(_THREAD_MARK, 1)[0]


def is_room(event) -> bool:
	"""True for channels and group chats; unknown shapes count as rooms (fail closed)."""
	return _meta(event).conversation_type != "personal"


# ---- conversation key --------------------------------------------------------------------
def resolve_conversation_key(gateway, event) -> str | None:
	try:
		m = _meta(event)
		if not (m.tenant_id and m.conversation_id):
			return None
		if m.conversation_type == "personal":
			return f"teams:{m.tenant_id}:{m.conversation_id}"
		if m.conversation_type in _ROOM_TYPES and m.user_aad_id:
			root = m.root_id or _base(m.conversation_id)
			return f"teams:{m.tenant_id}:{root}:{m.user_aad_id}"
	except Exception:
		pass
	return None


# ---- classification ----------------------------------------------------------------------
def run_touched_records(agent_run) -> bool:
	"""True when the run called any tool outside ``SAFE_TOOLS``. Conservative: a failed lookup
	counts as touched. A missing run has no tool calls."""
	if not agent_run:
		return False
	try:
		rows = frappe.get_all("Agent Tool Call", filters={"agent_run": agent_run}, fields=["tool"], limit=500)
	except Exception:
		return True
	for row in rows or []:
		name = str((row.get("tool") if isinstance(row, dict) else getattr(row, "tool", "")) or "").strip()
		if name.lower() not in SAFE_TOOLS:
			return True
	return False


def _policy(gateway) -> str:
	try:
		name = getattr(gateway, "name", None) or (gateway.get("name") if isinstance(gateway, dict) else "")
		return teams_tenant.get_settings(name).get("private_output_policy") or PRIVATE_WHEN_RECORDS
	except Exception:
		return ALWAYS_PRIVATE  # cannot read the policy: be private


def needs_private_reply(gateway, event) -> bool:
	if not is_room(event):
		return False
	if is_marked_sensitive(event):
		return True
	policy = _policy(gateway)
	if policy == ALWAYS_PRIVATE:
		return True
	if policy == CHANNEL:
		return False
	return run_touched_records(getattr(event, "agent_run", None))  # default policy


# ---- redirect ----------------------------------------------------------------------------
def _gname(gateway) -> str:
	return getattr(gateway, "name", None) or (gateway.get("name") if isinstance(gateway, dict) else "") or ""


def _note(gateway, event, meta: tc.TeamsMeta, text: str, kind: str) -> None:
	"""Neutral note in the originating channel thread via the outbox; never raises, never the answer."""
	try:
		gname = _gname(gateway)
		base = _base(meta.conversation_id)
		thread = getattr(event, "thread_id", None) or meta.root_id
		target = f"{base}{_THREAD_MARK}{thread}" if (thread and meta.conversation_type == "channel") else base
		ref = teams_refs._find(gname, meta.tenant_id, base)
		snapshot = {
			"conversation_ref": ref,
			"conversation_id": target,
			"service_url": meta.service_url,
			"tenant_id": meta.tenant_id,
		}
		activity = {"type": "message", "text": text, "textFormat": "markdown"}
		key = f"privnote:{gname}:{getattr(event, 'name', '') or meta.conversation_id}:{kind}"
		teams_outbox.enqueue(gname, snapshot, "reply", {"activity": activity}, key)
	except Exception:
		pass


def _service_url(gname: str, meta: tc.TeamsMeta) -> str:
	if meta.service_url:
		return meta.service_url
	try:
		rows = frappe.get_all(
			teams_refs.DOCTYPE,
			filters={"gateway": gname, "tenant_id": meta.tenant_id},
			fields=["service_url"],
			order_by="last_seen_at desc",
			limit=5,
		)
		for row in rows or []:
			if row.get("service_url"):
				return row["service_url"]
	except Exception:
		pass
	return ""


def _token_provider(gateway):
	creds = {k: teams_tenant.get_gateway_credential(gateway, k) for k in ("app_id", "app_password", "tenant_id")}
	return teams_api.make_token_provider(creds, gateway_name=_gname(gateway) or None)


def _personal_conversation(gateway, meta: tc.TeamsMeta) -> str | None:
	gname = _gname(gateway)
	ref = teams_refs.get_personal_reference(gname, meta.tenant_id, meta.user_aad_id)
	if ref and ref.get("conversation_id"):
		return ref["conversation_id"]
	# No reference: create one, only for a linked user and a known service URL.
	if not teams_identity.resolve_user(gname, meta.tenant_id, meta.user_aad_id):
		return None
	service_url = _service_url(gname, meta)
	if not (service_url and meta.bot_id):
		return None
	conv_id = teams_api.create_personal_conversation(
		service_url, meta.tenant_id, meta.bot_id, meta.user_aad_id, token=_token_provider(gateway)
	)
	if not conv_id:
		return None
	teams_refs.upsert_reference(
		gname,
		tc.TeamsMeta(
			tenant_id=meta.tenant_id,
			service_url=service_url,
			conversation_type="personal",
			conversation_id=conv_id,
			user_aad_id=meta.user_aad_id,
			bot_id=meta.bot_id,
		),
		installed=True,
	)
	return conv_id


def _fail_closed(gateway, event, meta: tc.TeamsMeta):
	_note(gateway, event, meta, UNAVAILABLE_TEXT, "unavailable")
	try:
		event.thread_id = None
	except Exception:
		pass
	return UNUSABLE_TARGET


def resolve_reply_target(gateway, event, reply_text):
	try:
		if not needs_private_reply(gateway, event):
			return None
	except Exception:
		pass  # classification itself failed: fall through to the private path (fail closed)
	else:
		if not is_room(event):
			return None
	meta = _meta(event)
	try:
		if not (meta.tenant_id and meta.user_aad_id):
			return _fail_closed(gateway, event, meta)
		conv_id = _personal_conversation(gateway, meta)
		if not conv_id:
			return _fail_closed(gateway, event, meta)
		_note(gateway, event, meta, ACK_TEXT, "ack")
		event.thread_id = None
		return conv_id
	except Exception:
		return _fail_closed(gateway, event, meta)


def register() -> None:
	hooks.register(hooks.RESOLVE_CONVERSATION_KEY, resolve_conversation_key, provider=HOOK_PROVIDER)
	hooks.register(hooks.RESOLVE_REPLY_TARGET, resolve_reply_target, provider=HOOK_PROVIDER)


register()
