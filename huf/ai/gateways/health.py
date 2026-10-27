"""Gateway monitoring: health hooks, health summary API and read-only diagnosis.

Hooks (registered for every provider at import time):

- ``on_event_received``  -> ``Gateway.last_event_at`` (throttled).
- ``on_run_failure`` / ``on_event_rejected`` -> ``Gateway.last_error`` (redacted, short).
- ``on_run_success`` -> clears ``last_error`` if it was written by an earlier run failure.

``diagnose_event`` replays the admission / routing decisions for a stored event
without creating or changing any record.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any

import frappe
from frappe import _
from frappe.utils import now_datetime

from huf.ai.gateways import hooks
from huf.ai.gateways.identity_policy import is_identity_required

LAST_EVENT_THROTTLE_SECONDS = 5
LAST_ERROR_MAX_CHARS = 300
EVENT_ERROR_MAX_CHARS = 200
RECENT_EVENT_LIMIT = 20
_TS_FORMAT = "%Y-%m-%d %H:%M:%S"
_TAG_RUN_FAILED = "run failed"
_STATUSES = ("Received", "Rejected", "Unrouted", "Queued", "Running", "Succeeded", "Failed")

_SECRET_PATTERNS = (
	re.compile(r"xox[a-zA-Z]-[A-Za-z0-9-]{4,}"),
	re.compile(r"\bxapp-[A-Za-z0-9-]{4,}"),
	re.compile(r"\bsk-[A-Za-z0-9_-]{8,}"),
	re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{6,}"),
	re.compile(r"(?i)((?:access_?token|token|secret|signing_secret|api_?key|password|authorization)"
		r"[\"']?\s*[:=]\s*[\"']?)[^\s\"'&,;}]{4,}"),
	re.compile(r"(?i)([?&](?:token|key|secret|access_token)=)[^&\s]+"),
)


def redact(text: Any) -> str:
	"""Strip credentials from free text before it is stored or returned."""
	out = str(text or "")
	for index, pattern in enumerate(_SECRET_PATTERNS):
		if index in (4, 5):
			out = pattern.sub(r"\1[redacted]", out)
		else:
			out = pattern.sub("[redacted]", out)
	return out


def _clip(text: str, limit: int) -> str:
	text = " ".join(str(text or "").split())
	return text if len(text) <= limit else text[: limit - 1] + "…"


def _now() -> datetime:
	return now_datetime()


def _cache():
	cache = frappe.cache
	return cache() if callable(cache) else cache


def _gateway_name(gateway: Any) -> str | None:
	name = getattr(gateway, "name", None)
	if name is None and isinstance(gateway, dict):
		name = gateway.get("name")
	return name


# --------------------------------------------------------------------- hooks

def _on_event_received(gateway, event) -> None:
	try:
		name = _gateway_name(gateway)
		if not name:
			return
		key = f"gateway_health:last_event:{name}"
		cache = _cache()
		if cache.get_value(key):
			return
		cache.set_value(key, 1, expires_in_sec=LAST_EVENT_THROTTLE_SECONDS)
		frappe.db.set_value("Gateway", name, "last_event_at", _now(), update_modified=False)
	except Exception:
		pass


def _write_error(gateway, tag: str, event, text: Any) -> None:
	try:
		name = _gateway_name(gateway)
		if not name:
			return
		prefix = f"{_now().strftime(_TS_FORMAT)} | {tag} | {getattr(event, 'name', '') or '-'} | "
		room = max(LAST_ERROR_MAX_CHARS - len(prefix), 0)
		message = (prefix + _clip(redact(text), room))[:LAST_ERROR_MAX_CHARS]
		frappe.db.set_value("Gateway", name, "last_error", message, update_modified=False)
	except Exception:
		pass


def _on_run_failure(gateway, event, kind, error) -> None:
	_write_error(gateway, _TAG_RUN_FAILED, event, error)


def _on_event_rejected(gateway, event, status, reason) -> None:
	_write_error(gateway, str(status or "rejected").lower(), event, reason or "No reason recorded")


def _on_run_success(gateway, event, kind, response) -> None:
	try:
		name = _gateway_name(gateway)
		if not name:
			return
		current = frappe.db.get_value("Gateway", name, "last_error")
		if not current:
			return
		parts = str(current).split(" | ", 2)
		if len(parts) < 3 or parts[1] != _TAG_RUN_FAILED:
			return
		if datetime.strptime(parts[0], _TS_FORMAT) <= _now():
			frappe.db.set_value("Gateway", name, "last_error", None, update_modified=False)
	except Exception:
		pass


def register_hooks() -> None:
	hooks.register(hooks.ON_EVENT_RECEIVED, _on_event_received, priority=900)
	hooks.register(hooks.ON_RUN_FAILURE, _on_run_failure, priority=900)
	hooks.register(hooks.ON_EVENT_REJECTED, _on_event_rejected, priority=900)
	hooks.register(hooks.ON_RUN_SUCCESS, _on_run_success, priority=900)


register_hooks()


# ----------------------------------------------------------------- permission

def _require_access(gateway_name: str) -> None:
	if not gateway_name:
		frappe.throw(_("Gateway is required"), frappe.ValidationError)
	if "System Manager" in (frappe.get_roles() or []):
		return
	if frappe.has_permission("Gateway", "write", gateway_name):
		return
	frappe.throw(_("Not permitted"), frappe.PermissionError)


# --------------------------------------------------------------------- health

def _counts_since(gateway_name: str, since: datetime) -> dict[str, int]:
	rows = frappe.get_all(
		"Gateway Event",
		filters={"gateway": gateway_name, "received_at": [">=", since]},
		fields=["status", "count(name) as count"],
		group_by="status",
		limit_page_length=50,
	)
	counts = {status: 0 for status in _STATUSES}
	for row in rows:
		counts[row.get("status")] = int(row.get("count") or 0)
	counts["total"] = sum(v for k, v in counts.items() if k != "total")
	return counts


def _usage_since(gateway_name: str, since: datetime) -> dict[str, Any]:
	linked = frappe.get_all(
		"Gateway Event",
		filters={"gateway": gateway_name, "received_at": [">=", since]},
		fields=["agent_run", "flow_run"],
		limit_page_length=5000,
	)
	agent_runs = sorted({r["agent_run"] for r in linked if r.get("agent_run")})
	flow_runs = sorted({r["flow_run"] for r in linked if r.get("flow_run")})
	seen: dict[str, dict] = {}
	for field, names in (("name", agent_runs), ("flow_run", flow_runs)):
		for start in range(0, len(names), 500):
			rows = frappe.get_all(
				"Agent Run",
				filters={field: ["in", names[start : start + 500]]},
				fields=["name", "cost", "total_tokens", "input_tokens", "output_tokens"],
				limit_page_length=0,
			)
			for row in rows:
				seen[row["name"]] = row
	return {
		"runs": len(seen),
		"cost": round(sum(float(r.get("cost") or 0) for r in seen.values()), 6),
		"total_tokens": sum(int(r.get("total_tokens") or 0) for r in seen.values()),
		"input_tokens": sum(int(r.get("input_tokens") or 0) for r in seen.values()),
		"output_tokens": sum(int(r.get("output_tokens") or 0) for r in seen.values()),
	}


@frappe.whitelist()
def get_gateway_health(gateway_name: str) -> dict:
	"""Status, event counts, recent events and 7-day usage for one gateway."""
	_require_access(gateway_name)
	summary = frappe.db.get_value(
		"Gateway", gateway_name, ["is_enabled", "last_event_at", "last_error", "provider"], as_dict=True
	)
	if not summary:
		frappe.throw(_("Gateway not found"), frappe.DoesNotExistError)

	now = _now()
	events = frappe.get_all(
		"Gateway Event",
		filters={"gateway": gateway_name},
		fields=[
			"name", "status", "received_at", "sender_id", "conversation_id", "error_message",
			"agent_run", "flow_run", "target_type", "target_agent", "target_flow",
		],
		order_by="received_at desc",
		limit_page_length=RECENT_EVENT_LIMIT,
	)
	recent = [
		{
			"name": e["name"],
			"status": e.get("status"),
			"received_at": str(e["received_at"]) if e.get("received_at") else None,
			"sender": e.get("sender_id") or "",
			"conversation": e.get("conversation_id") or "",
			"error_message": _clip(redact(e.get("error_message")), EVENT_ERROR_MAX_CHARS),
			"agent_run": e.get("agent_run"),
			"flow_run": e.get("flow_run"),
			"target": e.get("target_agent") or e.get("target_flow") or "",
		}
		for e in events
	]
	return {
		"gateway": gateway_name,
		"status": {
			"enabled": bool(summary.get("is_enabled")),
			"provider": summary.get("provider"),
			"last_event_at": str(summary["last_event_at"]) if summary.get("last_event_at") else None,
			"last_error": redact(summary.get("last_error")) or None,
		},
		"counts": {
			"24h": _counts_since(gateway_name, now - timedelta(hours=24)),
			"7d": _counts_since(gateway_name, now - timedelta(days=7)),
		},
		"recent_events": recent,
		"usage_7d": _usage_since(gateway_name, now - timedelta(days=7)),
	}


# ------------------------------------------------------------------- diagnose

def _check(check: str, ok: bool, good: str, bad: str, fix: str) -> dict:
	return {
		"check": check,
		"ok": bool(ok),
		"plain_language_explanation": good if ok else bad,
		"how_to_fix": "" if ok else fix,
	}


def _event_context(gateway, event) -> dict[str, Any]:
	sender, conversation = str(event.sender_id or ""), str(event.conversation_id or "")
	text = str(event.message_text or "")
	if str(gateway.provider or "").lower() == "slack":
		is_room = bool(conversation) and not conversation.startswith("D")
		mentioned = "<@" in text
	else:
		is_room = bool(conversation) and conversation != sender
		mentioned = True
	return {
		"sender_id": sender,
		"conversation_id": conversation,
		"thread_id": str(event.thread_id or ""),
		"message_text": text,
		"is_room": is_room,
		"mentioned": mentioned,
	}


def _admission_check(gs, gateway, context: dict[str, Any]) -> dict:
	"""Pure re-implementation of ``gateway_service._admission`` (no pairing requests)."""
	sender, conversation = context["sender_id"], context["conversation_id"]
	name = "Sender or channel is allowed"
	if not context["is_room"]:
		policy = gateway.direct_policy or "Allow list"
		if policy == "Allow list" or policy == "Pairing":
			ok = gs._has_access_entry(gateway, "Sender", sender)
			if policy == "Pairing":
				bad = "This person has not been approved yet. They need to be approved from the pending requests list."
				fix = "Approve their pending access request, then ask them to message again."
			else:
				bad = "This person is not on the approved list for direct messages."
				fix = "Add this person to the approved list for this channel."
				if is_identity_required(getattr(gateway, "provider", "")):
					fix = (
						"Set the access policy to Open so this person can connect their own account "
						"(nothing runs until they do), or add them to the approved list."
					)
		elif policy == "Open":
			ok, bad, fix = True, "", ""
		else:
			ok = False
			bad = f"Direct messages are set to '{policy}', which does not let this person in."
			fix = "Change the direct message access to an approved list."
		return _check(name, ok, "This person is approved to message the gateway.", bad, fix)

	if gateway.mention_required and not context["mentioned"]:
		return _check(
			name, False, "", "The message did not mention the bot, and this channel only reacts to mentions.",
			"Mention the bot in the message, or turn off 'mention required' for this gateway.",
		)
	room_ok = gs._policy_admits(gateway.room_policy, gateway, "Room", conversation)
	sender_ok = gs._policy_admits(gateway.room_sender_policy, gateway, "Sender", sender)
	if room_ok and sender_ok:
		return _check(name, True, "This channel and person are both approved.", "", "")
	if not room_ok:
		return _check(name, False, "", "This channel is not approved for the gateway.",
			"Add the channel to the approved list or set channel access to open.")
	return _check(name, False, "", "This person is not approved to talk to the gateway in channels.",
		"Add the person to the approved list or set channel sender access to open.")


@frappe.whitelist()
def diagnose_event(event_name: str) -> list[dict]:
	"""Explain, read-only, why a stored event did or did not run."""
	event = frappe.get_doc("Gateway Event", event_name)
	_require_access(event.gateway)
	gateway = frappe.get_doc("Gateway", event.gateway)

	from huf.ai import gateway_service as gs

	results: list[dict] = []
	enabled = bool(gateway.is_enabled)
	results.append(_check(
		"Gateway is turned on", enabled, "The gateway is turned on.", "The gateway is turned off.",
		"Turn the gateway on in its settings.",
	))
	user = gateway.execution_user
	results.append(_check(
		"Run-as user is set", bool(user), "A run-as user is set.",
		"No run-as user is set, so nothing can be started.", "Choose a run-as user in the gateway settings.",
	))
	linked = bool(gateway.integration_settings)
	results.append(_check(
		"Credentials are connected", linked, "Credentials are connected.",
		"No credentials are connected to this gateway.", "Connect the channel credentials in the gateway settings.",
	))
	context = _event_context(gateway, event)
	results.append(_admission_check(gs, gateway, context))

	route = gs.resolve_gateway_route(gateway.name, context) if enabled else {"status": "Rejected"}
	if enabled:
		matched = route.get("status") == "Queued" and route.get("binding")
		results.append(_check(
			"A route matches this message",
			route.get("status") == "Queued",
			"A routing rule matches this message." if matched else "No specific rule matched; the default route handles it.",
			"No routing rule matches this message and no default is set.",
			"Add a routing rule for this conversation or choose a default agent or flow.",
		))
	else:
		matched = False
		results.append(_check("A route matches this message", False, "",
			"Routing is skipped while the gateway is turned off.", "Turn the gateway on first."))
	has_default = bool(gateway.default_target_type and (gateway.default_agent or gateway.default_flow))
	results.append(_check(
		"A default agent or flow is set", has_default or bool(matched),
		"A default agent or flow is set.", "No default agent or flow is set for unmatched messages.",
		"Choose a default agent or flow in the gateway settings.",
	))
	if event.status in ("Rejected", "Unrouted", "Failed") and event.error_message:
		results.append(_check(
			"Recorded result", False, "",
			f"The event was recorded as {event.status}: {_clip(redact(event.error_message), EVENT_ERROR_MAX_CHARS)}",
			"Fix the issue above, then send a new message.",
		))
	return results
