# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""WhatsApp Business Calling: webhook normalisation, Graph wrappers and call admission.

EXPERIMENTAL and OFF by default (``Gateway.calling_enabled``). Scope is a greeting-only
answer: no recording (call audio is never stored; only metadata is logged), unknown callers
are rejected. See docs/WHATSAPP_CALLING_DESIGN.md.

Nothing here talks to Meta unless a caller invokes a :class:`CallsGraph` method; the HTTP
transport is injectable so tests never touch the network.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from huf.ai.gateway_adapters import whatsapp_bridge as bridge
from huf.ai.gateway_adapters.whatsapp_bridge import BridgeError

CALL_ACTIONS = ("pre_accept", "accept", "reject", "terminate")
CALL_EVENTS = ("connect", "terminate", "status")
CALLING_STATUSES = ("ENABLED", "DISABLED")
ICON_VISIBILITY = ("DEFAULT", "DISABLE_ALL")
MAX_BIZ_OPAQUE = 512
MAX_PERMISSION_TEXT = 1024
USER_INITIATED = "USER_INITIATED"


# --------------------------------------------------------------------- normalisation
@dataclass(frozen=True)
class WhatsAppCall:
	"""One normalised ``calls`` webhook item (connect / terminate / call status)."""

	call_id: str
	event: str  # connect | terminate | status
	direction: str = ""
	caller: str = ""
	callee: str = ""
	status: str = ""  # terminate: COMPLETED|FAILED; status: RINGING|ACCEPTED|REJECTED
	timestamp: str = ""
	duration: int | None = None
	errors: tuple[dict, ...] = ()
	phone_number_id: str = ""
	display_name: str = ""
	# The SDP offer carries IPs/ICE data: kept in memory for the answer flow, never persisted/logged.
	sdp_offer: str = field(default="", repr=False)

	def public(self) -> dict[str, Any]:
		"""Metadata only: no SDP, no audio. This is what is stored on the Gateway Event."""
		out: dict[str, Any] = {
			"kind": "call",
			"call_id": self.call_id,
			"event": self.event,
			"direction": self.direction,
			"caller": self.caller,
			"callee": self.callee,
			"phone_number_id": self.phone_number_id,
		}
		for key in ("status", "timestamp"):
			if getattr(self, key):
				out[key] = getattr(self, key)
		if self.duration is not None:
			out["duration"] = self.duration
		if self.errors:
			out["errors"] = [dict(e) for e in self.errors][:5]
		return out


def _dict(value: Any) -> dict:
	return value if isinstance(value, dict) else {}


def _list(value: Any) -> list:
	return value if isinstance(value, list) else []


def _duration(value: Any) -> int | None:
	try:
		return max(int(value), 0)
	except (TypeError, ValueError):
		return None


def normalize_calls(value: Mapping[str, Any]) -> list[WhatsAppCall]:
	"""Normalise a ``calls`` change value (plus call-typed ``statuses``) into WhatsAppCall rows.

	Never raises on odd content; malformed items are skipped.
	"""
	metadata = _dict(value.get("metadata"))
	phone_id = str(metadata.get("phone_number_id") or "")
	contacts = [c for c in _list(value.get("contacts")) if isinstance(c, dict)]
	names = {bridge.normalize_phone(c.get("wa_id")): str(_dict(c.get("profile")).get("name") or "") for c in contacts}
	first_wa = bridge.normalize_phone(contacts[0].get("wa_id")) if contacts else ""
	out: list[WhatsAppCall] = []

	for item in _list(value.get("calls")):
		if not isinstance(item, dict):
			continue
		call_id = str(item.get("id") or "").strip()
		event = str(item.get("event") or "").strip().lower()
		if not call_id or event not in ("connect", "terminate"):
			continue
		direction = str(item.get("direction") or "").upper()
		# For a user-initiated call the caller is `from`; for a business-initiated call it is `to`.
		caller_raw = item.get("to") if direction == "BUSINESS_INITIATED" else item.get("from")
		caller = bridge.normalize_phone(caller_raw) or first_wa
		callee_raw = item.get("from") if direction == "BUSINESS_INITIATED" else item.get("to")
		out.append(
			WhatsAppCall(
				call_id=call_id,
				event=event,
				direction=direction,
				caller=caller,
				callee=bridge.normalize_phone(callee_raw),
				status=str(item.get("status") or "").upper(),
				timestamp=str(item.get("timestamp") or ""),
				duration=_duration(item.get("duration")),
				errors=tuple(e for e in _list(item.get("errors")) if isinstance(e, dict)),
				phone_number_id=phone_id,
				display_name=names.get(caller, ""),
				sdp_offer=str(_dict(item.get("session")).get("sdp") or "") if event == "connect" else "",
			)
		)

	for st in _list(value.get("statuses")):
		if isinstance(st, dict) and st.get("type") == "call" and st.get("id"):
			recipient = bridge.normalize_phone(st.get("recipient_id"))
			out.append(
				WhatsAppCall(
					call_id=str(st["id"]),
					event="status",
					direction=str(st.get("direction") or "BUSINESS_INITIATED").upper(),
					caller=recipient,
					status=str(st.get("status") or "").upper(),
					timestamp=str(st.get("timestamp") or ""),
					phone_number_id=phone_id,
					display_name=names.get(recipient, ""),
				)
			)
	return out


def is_call_status(status: Any) -> bool:
	"""True for a webhook ``statuses`` item that describes a call (not a message)."""
	return isinstance(status, dict) and status.get("type") == "call"


# --------------------------------------------------------------------- payload builders
def _clean_id(value: Any, label: str) -> str:
	text = str(value or "").strip()
	if not text:
		raise ValueError(f"{label} is required")
	return text


def call_action_payload(
	call_id: str, action: str, sdp: str | None = None, biz_opaque_callback_data: str | None = None
) -> dict[str, Any]:
	"""Body for ``POST /<PHONE_ID>/calls`` (pre_accept/accept carry the SDP answer; reject/terminate do not)."""
	if action not in CALL_ACTIONS:
		raise ValueError(f"Unknown call action: {action}")
	body: dict[str, Any] = {"messaging_product": "whatsapp", "call_id": _clean_id(call_id, "call_id"), "action": action}
	if action in ("pre_accept", "accept"):
		if not str(sdp or "").strip():
			raise ValueError(f"{action} requires an SDP answer")
		body["session"] = {"sdp_type": "answer", "sdp": sdp}
		if action == "accept" and biz_opaque_callback_data:
			body["biz_opaque_callback_data"] = str(biz_opaque_callback_data)[:MAX_BIZ_OPAQUE]
	elif sdp:
		raise ValueError(f"{action} does not take an SDP")
	return body


def calling_settings_payload(
	calls_status: str | None = None,
	call_icon_visibility: str | None = None,
	greeting_media_id: str | None = None,
	callback_permission_status: str | None = None,
) -> dict[str, Any]:
	"""Body for ``POST /<PHONE_ID>/settings``. The greeting is the voicemail announcement media id."""
	calling: dict[str, Any] = {}
	if calls_status is not None:
		status = str(calls_status).upper()
		if status not in CALLING_STATUSES:
			raise ValueError("calls_status must be ENABLED or DISABLED")
		calling["status"] = status
	if call_icon_visibility is not None:
		vis = str(call_icon_visibility).upper()
		if vis not in ICON_VISIBILITY:
			raise ValueError("call_icon_visibility must be DEFAULT or DISABLE_ALL")
		calling["call_icon_visibility"] = vis
	if callback_permission_status is not None:
		cb = str(callback_permission_status).upper()
		if cb not in CALLING_STATUSES:
			raise ValueError("callback_permission_status must be ENABLED or DISABLED")
		calling["callback_permission_status"] = cb
	if greeting_media_id:
		calling["voicemail"] = {
			"status": "ENABLED",
			"triggers": ["REJECT", "TIMEOUT"],
			"audio": {"default": {"announcement_media_id": str(greeting_media_id)}},
		}
	if not calling:
		raise ValueError("Nothing to change")
	return {"calling": calling}


def permission_request_payload(to: str, body_text: str) -> dict[str, Any]:
	"""``call_permission_request`` interactive message (asks the user to allow business calls).

	[U] Shape recalled from Meta's call-permissions docs (the page was not fetchable on 2026-10-21).
	"""
	phone = bridge.normalize_phone(to)
	if not phone:
		raise ValueError("A recipient phone number is required")
	text = " ".join(str(body_text or "").split())
	if not text:
		raise ValueError("Permission request text is required")
	if len(text) > MAX_PERMISSION_TEXT:
		raise ValueError(f"Permission request text is limited to {MAX_PERMISSION_TEXT} characters")
	return {
		"messaging_product": "whatsapp",
		"recipient_type": "individual",
		"to": phone,
		"type": "interactive",
		"interactive": {
			"type": "call_permission_request",
			"action": {"name": "call_permission_request"},
			"body": {"text": text},
		},
	}


# --------------------------------------------------------------------- Graph wrappers
class CallsGraph:
	"""Thin Graph wrapper for one account dict (``bridge.resolve_account`` shape). Not invoked live by tests."""

	def __init__(self, account: Mapping[str, Any], http_post: Callable[..., Any] | None = None, http_get: Callable[..., Any] | None = None):
		self._acct = account
		self._post = http_post or bridge._default_post
		self._get = http_get or _default_get

	def _url(self, path: str) -> str:
		a = self._acct
		return f"{a['url']}/{a['version']}/{a['phone_id']}/{path}"

	def _headers(self) -> dict[str, str]:
		return {"Authorization": f"Bearer {self._acct['token']}", "Content-Type": "application/json"}

	def _finish(self, resp: Any) -> dict[str, Any]:
		status = getattr(resp, "status_code", 200)
		if isinstance(status, int) and status >= 400:
			raise BridgeError({**bridge._graph_err("call_failed", resp), "message": bridge.graph_error_message(resp)})
		try:
			body = resp.json()
		except Exception as exc:
			raise BridgeError(bridge._err("call_failed", message="Unexpected response from WhatsApp.")) from exc
		return body if isinstance(body, dict) else {"result": body}

	def _do(self, method: Callable[..., Any], path: str, **kw: Any) -> dict[str, Any]:
		try:
			resp = method(self._url(path), headers=self._headers(), timeout=bridge._HTTP_TIMEOUT, **kw)
		except Exception as exc:
			raise BridgeError({**bridge._graph_err("call_failed", exc), "message": bridge._redact(exc)}) from exc
		return self._finish(resp)

	def action(self, call_id: str, action: str, sdp: str | None = None, biz_opaque: str | None = None) -> dict[str, Any]:
		return self._do(self._post, "calls", json=call_action_payload(call_id, action, sdp, biz_opaque))

	def pre_accept(self, call_id: str, sdp: str) -> dict[str, Any]:
		return self.action(call_id, "pre_accept", sdp)

	def accept(self, call_id: str, sdp: str, biz_opaque: str | None = None) -> dict[str, Any]:
		return self.action(call_id, "accept", sdp, biz_opaque)

	def reject(self, call_id: str) -> dict[str, Any]:
		return self.action(call_id, "reject")

	def terminate(self, call_id: str) -> dict[str, Any]:
		return self.action(call_id, "terminate")

	def get_settings(self) -> dict[str, Any]:
		return self._do(self._get, "settings", params={"fields": "calling"})

	def set_settings(self, payload: dict[str, Any]) -> dict[str, Any]:
		return self._do(self._post, "settings", json=payload)

	def send_permission_request(self, to: str, body_text: str) -> dict[str, Any]:
		return self._do(self._post, "messages", json=permission_request_payload(to, body_text))


def _default_get(*args: Any, **kwargs: Any) -> Any:
	import requests

	return requests.get(*args, **kwargs)


# --------------------------------------------------------------------- admission and events
def call_admission(gateway: Any, caller: str) -> tuple[bool, str]:
	"""Strict call admission: only an approved Sender access entry is answered.

	Deliberately stricter than message admission: ``Open`` and ``Pairing`` policies do NOT admit a
	caller (no pairing request is created for a call), and opted-out/blocked senders are refused.
	"""
	from huf.ai import gateway_service as gs

	if not caller:
		return False, "Caller identity unknown"
	negative = gs._sender_negative_state(gateway, caller)
	if negative:
		return False, f"Caller is blocked ({negative})"
	if gs._has_access_entry(gateway, "Sender", caller):
		return True, ""
	return False, "Caller is not on the allow list"


def calling_enabled(gateway: Any) -> bool:
	return bool(getattr(gateway, "calling_enabled", 0))


def _event_key(gateway_name: str, call_id: str) -> str:
	from huf.ai.gateway_service import _idempotency_key

	return _idempotency_key(gateway_name, f"call:{call_id}")


SDP_CACHE_TTL_SECONDS = 120


def _sdp_cache_key(gateway_name: str, call_id: str) -> str:
	return f"huf_call_sdp:{gateway_name}:{call_id}"


def stash_sdp_offer(gateway_name: str, call_id: str, sdp: str) -> str:
	"""Keep the SDP offer in a short-TTL cache entry so it never lands in RQ job kwargs."""
	import frappe

	key = _sdp_cache_key(gateway_name, call_id)
	frappe.cache.set_value(key, sdp or "", expires_in_sec=SDP_CACHE_TTL_SECONDS)
	return key


def take_sdp_offer(key: str) -> str:
	import frappe

	sdp = frappe.cache.get_value(key) or ""
	try:
		frappe.cache.delete_value(key)
	except Exception:
		pass
	return sdp


def _call_event_exists(gateway_name: str, call_id: str) -> bool:
	import frappe

	return bool(frappe.db.get_value("Gateway Event", {"idempotency_key": _event_key(gateway_name, call_id)}, "name"))


def record_call_event(gateway_name: str, call: WhatsAppCall, status: str, note: str = "", actions: list | None = None) -> dict:
	"""Create (or fetch) the Gateway Event for a call. Metadata only: never SDP or audio."""
	import frappe
	from frappe.utils import now_datetime

	key = _event_key(gateway_name, call.call_id)
	existing = frappe.db.get_value("Gateway Event", {"idempotency_key": key}, "name")
	if existing:
		return {"duplicate": True, "event_name": existing}
	payload = {"call": call.public(), "kind": "call", "actions": list(actions or [])}
	event = frappe.get_doc(
		{
			"doctype": "Gateway Event",
			"gateway": gateway_name,
			"idempotency_key": key,
			"provider_event_id": f"call:{call.call_id}",
			"status": status,
			"received_at": now_datetime(),
			"verified_sender": 1,
			"sender_id": call.caller,
			"conversation_id": call.caller,
			"message_text": f"[Call {call.direction.lower() or 'event'}]",
			"raw_payload": payload,
			"error_message": note,
		}
	)
	try:
		event.insert(ignore_permissions=True)
	except (frappe.DuplicateEntryError, frappe.UniqueValidationError):
		return {"duplicate": True, "event_name": frappe.db.get_value("Gateway Event", {"idempotency_key": key}, "name")}
	return {"event_name": event.name, "status": status}


def update_call_event(gateway_name: str, call: WhatsAppCall, status: str | None = None, note: str = "", action: dict | None = None) -> str | None:
	"""Merge terminate/status metadata and recorded actions into an existing call event."""
	import json

	import frappe

	name = frappe.db.get_value("Gateway Event", {"idempotency_key": _event_key(gateway_name, call.call_id)}, "name")
	if not name:
		return None
	raw = frappe.db.get_value("Gateway Event", name, "raw_payload") or {}
	if isinstance(raw, str):
		try:
			raw = json.loads(raw)
		except ValueError:
			raw = {}
	raw = dict(raw)
	raw.setdefault("call", {}).update(call.public())
	history = list(raw.get("history") or [])
	history.append({"event": call.event, "status": call.status})
	raw["history"] = history[-20:]
	if action:
		raw["actions"] = [*list(raw.get("actions") or []), action]
	values: dict[str, Any] = {"raw_payload": raw}
	if status:
		values["status"] = status
	if note:
		values["error_message"] = note
	frappe.db.set_value("Gateway Event", name, values)
	return name


def handle_call(gateway: Any, call: WhatsAppCall, *, graph: CallsGraph | None = None, enqueue: Callable[..., Any] | None = None) -> dict[str, Any]:
	"""Route one normalised call item. Never starts an agent run.

	* Gateway ``calling_enabled`` off (default): metadata event only, NO Graph call.
	* Unknown/blocked caller (calling on): ``reject`` action sent + recorded, event Rejected.
	* Approved caller: event Received, greeting job enqueued.
	"""
	name = gateway.name
	if call.event == "terminate":
		status = "Succeeded" if call.status == "COMPLETED" else ("Failed" if call.status == "FAILED" else None)
		note = "; ".join(str(e.get("message") or e.get("code") or "") for e in call.errors)[:300] if status == "Failed" else ""
		return {"call_id": call.call_id, "event": "terminate", "event_name": update_call_event(name, call, status, note)}
	if call.event == "status":
		return {"call_id": call.call_id, "event": "status", "event_name": update_call_event(name, call)}
	if call.direction != USER_INITIATED:
		return {"call_id": call.call_id, "ignored": "unsupported direction"}

	if not calling_enabled(gateway):
		rec = record_call_event(name, call, "Rejected", "Calling is not enabled for this gateway")
		return {"call_id": call.call_id, "outcome": "disabled", **rec}

	admitted, reason = call_admission(gateway, call.caller)
	if not admitted:
		if _call_event_exists(name, call.call_id):
			# webhook retry: the reject was already sent and recorded
			rec = record_call_event(name, call, "Rejected", reason)
			return {"call_id": call.call_id, "outcome": "duplicate", **rec}
		action = {"action": "reject", "reason": reason, "ok": False}
		try:
			(graph or CallsGraph(bridge.resolve_account(bridge.gateway_account(name)) or {})).reject(call.call_id)
			action["ok"] = True
		except Exception as exc:
			action["error"] = bridge._redact(exc)[:200]
		rec = record_call_event(name, call, "Rejected", reason, [action])
		return {"call_id": call.call_id, "outcome": "rejected", "reject_action": action, **rec}

	rec = record_call_event(name, call, "Received", "")
	if rec.get("duplicate"):
		return {"call_id": call.call_id, "outcome": "duplicate", **rec}
	if enqueue is None:
		import frappe

		enqueue = frappe.enqueue
	enqueue(
		"huf.ai.gateway_adapters.whatsapp_call_flow.answer_inbound_call_job",
		queue="short",
		timeout=120,
		gateway_name=name,
		call_id=call.call_id,
		caller=call.caller,
		sdp_key=stash_sdp_offer(name, call.call_id, call.sdp_offer),
		enqueue_after_commit=True,
	)
	return {"call_id": call.call_id, "outcome": "queued", **rec}
