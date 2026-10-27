"""Proactive Microsoft Teams notifications to a linked Huf user (WP T11).

Rules (SPEC section 15): the target is always a Huf *user* with a Linked Teams identity on the
gateway (never a raw Entra id, never an email). The bot can only reach people who installed
the app (personal scope) or already messaged it. No new group chats are ever created.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from typing import Any

import frappe
from frappe import _

from huf.ai.gateways import teams_api, teams_outbox, teams_refs, teams_tenant
from huf.ai.gateways import teams_contract as tc
from huf.ai.gateways.teams_contract import TeamsMeta

LINK_DOCTYPE = "Gateway Identity Link"
REF_DOCTYPE = teams_refs.DOCTYPE
MAX_TEXT = 3000
MAX_CARD_BYTES = 20000
CARD_CONTENT_TYPE = "application/vnd.microsoft.card.adaptive"
DEDUPE_PREFIX = "teams:notify:"
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class NotifyError(Exception):
	"""User-facing, plain-language failure."""


def _cache():
	return frappe.cache()


# --------------------------------------------------------------------------- lookups
def _linked_identity(gateway: str, user: str) -> dict | None:
	rows = frappe.get_all(
		LINK_DOCTYPE,
		filters={"gateway": gateway, "provider": tc.PROVIDER_LABEL, "user": user, "state": "Linked"},
		fields=["team_id", "external_id"],
		order_by="modified desc",
		limit=1,
	)
	return rows[0] if rows else None


def _known_service_url(gateway: str, tenant_id: str) -> str | None:
	rows = frappe.get_all(
		REF_DOCTYPE,
		filters={"gateway": gateway, "tenant_id": tenant_id, "service_url": ["is", "set"]},
		fields=["service_url", "tenant_id"],
		order_by="last_seen_at desc",
		limit=1,
	)
	for row in rows:
		if row.get("tenant_id") == tenant_id and row.get("service_url"):
			return row["service_url"]
	return None


def teams_user_reference(gateway: str, user: str) -> dict | None:
	"""Reusable: ``{tenant_id, aad_id, reference}`` for a linked Huf user, else None.

	``reference`` is the installed personal-chat reference (same tenant only) or None.
	"""
	link = _linked_identity(gateway, user)
	if not link:
		return None
	tenant, aad = link.get("team_id"), link.get("external_id")
	if not (tenant and aad):
		return None
	ref = teams_refs.get_personal_reference(gateway, tenant, aad)
	if ref and ref.get("tenant_id") != tenant:  # defence in depth: never cross tenants
		ref = None
	return {"tenant_id": tenant, "aad_id": aad, "reference": ref}


# --------------------------------------------------------------------------- content
def clean_text(text: Any) -> str:
	value = _CTRL.sub("", str(text or "")).strip()
	return value[:MAX_TEXT]


def build_activity(text: str | None = None, card: Any = None) -> dict:
	if card is not None:
		if not isinstance(card, dict) or card.get("type") != "AdaptiveCard":
			raise NotifyError(_("The card must be an Adaptive Card object."))
		try:
			size = len(json.dumps(card).encode("utf-8"))
		except (TypeError, ValueError):
			raise NotifyError(_("The card could not be serialised."))
		if size > MAX_CARD_BYTES:
			raise NotifyError(_("The card is too large."))
		activity = {
			"type": "message",
			"attachments": [{"contentType": CARD_CONTENT_TYPE, "content": card}],
		}
		body = clean_text(text)
		if body:
			activity["text"] = body
			activity["textFormat"] = "plain"
		return activity
	body = clean_text(text)
	if not body:
		raise NotifyError(_("Provide text or a card to send."))
	return {"type": "message", "text": body, "textFormat": "plain"}


# --------------------------------------------------------------------------- permissions
def _check_caller(gateway: str, user: str) -> None:
	caller = frappe.session.user
	if not caller or caller == "Guest":
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	if caller == user or "System Manager" in (frappe.get_roles() or []):
		return
	if frappe.has_permission("Gateway", "write", gateway):
		return
	frappe.throw(_("Not permitted"), frappe.PermissionError)


def _load_gateway(name: str):
	if not name or not frappe.db.exists("Gateway", name):
		raise NotifyError(_("Gateway not found."))
	gw = frappe.get_doc("Gateway", name)
	if getattr(gw, "provider", None) != tc.PROVIDER_LABEL:
		raise NotifyError(_("This gateway is not a Microsoft Teams gateway."))
	if not getattr(gw, "is_enabled", 0):
		raise NotifyError(_("This Microsoft Teams gateway is disabled."))
	return gw


# --------------------------------------------------------------------------- conversation
def _create_conversation(gw, tenant: str, aad: str) -> dict:
	service_url = _known_service_url(gw.name, tenant)
	if not service_url:
		raise NotifyError(
			_("This user has not messaged or installed the Teams app yet, so Huf cannot reach them.")
		)
	creds = {k: teams_tenant.get_gateway_credential(gw, k) for k in ("app_id", "app_password", "tenant_id")}
	if not all(creds.values()):
		raise NotifyError(_("The gateway credentials are incomplete."))
	provider = teams_api.make_token_provider(creds, gateway_name=gw.name)
	try:
		conv_id = teams_api.create_personal_conversation(
			service_url, tenant, creds["app_id"], aad, token=provider
		)
	except teams_api.TeamsApiError as exc:
		raise NotifyError(
			_("Teams refused to start a chat with this user (the app may not be installed for them): {0}").format(
				str(exc)[:200]
			)
		)
	teams_refs.upsert_reference(
		gw.name,
		TeamsMeta(
			tenant_id=tenant,
			service_url=service_url,
			conversation_type="personal",
			conversation_id=conv_id,
			user_aad_id=aad,
			bot_id=creds["app_id"],
		),
	)
	return {"conversation_id": conv_id, "service_url": service_url, "tenant_id": tenant, "name": None}


def _idempotency_key(gateway: str, tenant: str, aad: str, dedupe_key: str | None) -> str:
	if dedupe_key:
		raw = f"{gateway}|{tenant}|{aad}|{dedupe_key}"
		return "teams-notify-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()
	return "teams-notify-" + uuid.uuid4().hex


# --------------------------------------------------------------------------- API
@frappe.whitelist(methods=["POST"])
def send_teams_notification(
	gateway: str,
	user: str,
	text: str | None = None,
	card: Any = None,
	dedupe_key: str | None = None,
	dedupe_hours: int | float = 24,
) -> dict:
	_check_caller(gateway, user)
	claim = None
	try:
		if isinstance(card, str) and card:
			try:
				card = json.loads(card)
			except ValueError:
				raise NotifyError(_("The card must be valid JSON."))
		gw = _load_gateway(gateway)
		info = teams_user_reference(gateway, user)
		if not info:
			raise NotifyError(_("This user has not linked a Microsoft Teams identity on this gateway."))
		tenant, aad, ref = info["tenant_id"], info["aad_id"], info["reference"]
		activity = build_activity(text, card)
		snapshot = None
		if ref and ref.get("conversation_id") and ref.get("service_url"):
			snapshot = {
				"conversation_ref": ref.get("name"),
				"conversation_id": ref["conversation_id"],
				"service_url": ref["service_url"],
				"tenant_id": tenant,
			}
		key = _idempotency_key(gateway, tenant, aad, dedupe_key)
		if dedupe_key:
			cache_key = DEDUPE_PREFIX + key
			if _cache().get_value(cache_key):
				return {"success": True, "outbox": None, "deduped": True}
			hours = max(float(dedupe_hours or 24), 0.01)
			_cache().set_value(cache_key, 1, expires_in_sec=int(hours * 3600))
			claim = cache_key
		if snapshot is None:
			snapshot = _create_conversation(gw, tenant, aad)
		name = teams_outbox.enqueue(gateway, snapshot, "proactive", {"activity": activity}, key)
		return {"success": True, "outbox": name, "deduped": False}
	except NotifyError as exc:
		_release(claim)
		return {"success": False, "outbox": None, "deduped": False, "error": str(exc)}
	except Exception:
		_release(claim)
		try:
			frappe.log_error(title="Teams notification failed")
		except Exception:
			pass
		return {
			"success": False,
			"outbox": None,
			"deduped": False,
			"error": _("The notification could not be queued."),
		}


def _release(cache_key: str | None) -> None:
	if cache_key:
		try:
			_cache().delete_value(cache_key)
		except Exception:
			pass
