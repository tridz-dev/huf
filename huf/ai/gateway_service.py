"""Shared, provider-neutral gateway ingress and routing.

Provider adapters are responsible for authenticating their native webhook and
normalising it into :func:`ingest_gateway_event`.  This module deliberately
does not expose a guest endpoint: each adapter owns its verification contract.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

import frappe
from frappe import _
from frappe.utils import add_to_date, now_datetime


MATCH_CONTEXT_KEY = {
    "Direct message": "conversation_id",
    "Room or channel": "conversation_id",
    "Thread": "thread_id",
    "Sender": "sender_id",
}
SENSITIVE_PAYLOAD_KEYS = {"authorization", "token", "secret", "signature", "api_key", "password"}


def _idempotency_key(gateway_name: str, provider_event_id: str) -> str:
    value = f"{gateway_name}:{provider_event_id}".encode()
    return hashlib.sha256(value).hexdigest()


def _redact_payload(value: Any) -> Any:
    """Retain support evidence without persisting provider credentials."""
    if isinstance(value, dict):
        return {
            key: "[redacted]" if key.lower() in SENSITIVE_PAYLOAD_KEYS else _redact_payload(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_payload(item) for item in value]
    return value


def _binding_matches(binding: dict, context: dict[str, Any]) -> bool:
    if binding.match_type == "Any conversation":
        return True
    key = MATCH_CONTEXT_KEY.get(binding.match_type)
    return bool(key and binding.match_value and str(context.get(key) or "") == binding.match_value)


def _route_target(target_type: str | None, agent: str | None, flow: str | None) -> dict | None:
    if target_type == "Agent" and agent:
        return {"target_type": "Agent", "agent": agent, "flow": None}
    if target_type == "Flow" and flow:
        return {"target_type": "Flow", "agent": None, "flow": flow}
    return None


def _has_access_entry(gateway, entry_type: str, external_id: str) -> bool:
    if not external_id:
        return False
    entries = frappe.get_all(
        "Gateway Access Entry",
        filters={
            "gateway": gateway.name, "entry_type": entry_type, "provider": gateway.provider,
            "external_id": str(external_id), "state": "Approved",
        },
        or_filters=[["expires_at", "is", "not set"], ["expires_at", ">=", now_datetime()]],
        pluck="name",
        limit_page_length=1,
    )
    return bool(entries)


def _create_pairing_request(gateway, sender_id: str, conversation_id: str | None = None) -> str:
    """Create a live pairing request with a short pairing code (PAIR-XXXX)."""
    if not sender_id:
        return ""
    existing = frappe.get_all(
        "Gateway Access Entry",
        filters={
            "gateway": gateway.name,
            "entry_type": "Sender",
            "provider": gateway.provider,
            "external_id": str(sender_id),
            "state": "Pending",
        },
        fields=["name", "pairing_code"],
        limit_page_length=1,
    )
    if existing:
        return existing[0].get("pairing_code") or ""

    import secrets

    code_suffix = secrets.token_hex(2).upper()
    pairing_code = f"PAIR-{code_suffix}"

    doc = frappe.get_doc(
        {
            "doctype": "Gateway Access Entry",
            "gateway": gateway.name,
            "entry_type": "Sender",
            "provider": gateway.provider,
            "external_id": str(sender_id),
            "pairing_code": pairing_code,
            "state": "Pending",
            "expires_at": add_to_date(now_datetime(), minutes=int(gateway.pairing_ttl_minutes or 60)),
            "display_label": f"Sender {sender_id}",
        }
    ).insert(ignore_permissions=True)

    try:
        if gateway.integration_settings:
            int_doc = frappe.get_doc("Integration Settings", gateway.integration_settings)
            creds = {}
            for row in getattr(int_doc, "credentials", []):
                creds[row.key] = row.get_password("value") if hasattr(row, "get_password") else row.value

            from huf.ai.gateway_webhook import _adapter_class_for_provider
            from huf.ai.gateway_adapters.types import GatewayReply

            adapter_cls = _adapter_class_for_provider(gateway.provider)
            adapter = adapter_cls(creds)
            target_conv = conversation_id or sender_id
            reply_msg = (
                f"🔒 Access approval required.\n\n"
                f"Your pairing code is: `{pairing_code}`\n\n"
                f"Please share this code with the bot administrator to get approved."
            )
            adapter.send_reply(GatewayReply(conversation_id=target_conv, text=reply_msg))
    except Exception as exc:
        frappe.logger("huf").warning(f"Failed to send pairing code message: {exc}")

    return pairing_code


def _admission(gateway, context: dict[str, Any]) -> tuple[bool, str]:
    sender_id, conversation_id = str(context.get("sender_id") or ""), str(context.get("conversation_id") or "")
    is_room = bool(context.get("is_room"))
    if not is_room:
        policy = gateway.direct_policy or "Allow list"
        if policy == "Pairing":
            code = _create_pairing_request(gateway, sender_id, conversation_id=conversation_id)
            return False, f"Sender pairing approval is required. Pairing code: {code}"
        return (policy == "Allow list" and _has_access_entry(gateway, "Sender", sender_id), "Sender is not approved for this gateway")

    room_ok = gateway.room_policy == "Allow list" and _has_access_entry(gateway, "Room", conversation_id)
    sender_ok = gateway.room_sender_policy == "Allow list" and _has_access_entry(gateway, "Sender", sender_id)
    mentioned = bool(context.get("mentioned"))
    if gateway.mention_required and not mentioned:
        return False, "Room messages must mention the gateway"
    return room_ok and sender_ok, "Room or sender is not approved for this gateway"


@frappe.whitelist(methods=["POST"])
def approve_gateway_access_entry(entry_name: str) -> dict:
    """Approve a pending pairing request; only system administrators may widen admission."""
    if not frappe.has_permission("Gateway Access Entry", "write"):
        frappe.throw(_("Not permitted"), frappe.PermissionError)
    entry = frappe.get_doc("Gateway Access Entry", entry_name)
    if entry.state != "Pending" or (entry.expires_at and entry.expires_at < now_datetime()):
        frappe.throw(_("This pairing request is not active."))
    entry.db_set({"state": "Approved", "approved_by": frappe.session.user, "approved_at": now_datetime()})
    return {"name": entry.name, "state": "Approved"}


def resolve_gateway_route(gateway_name: str, context: dict[str, Any]) -> dict:
    """Resolve the first enabled binding by priority, then the default route.

    No fuzzy matching is permitted.  A missing target is an explicit Unrouted
    result, which allows a provider adapter to safely remain silent or return a
    fixed help response without invoking a model.
    """
    gateway = frappe.get_doc("Gateway", gateway_name)
    if not gateway.is_enabled:
        return {"status": "Rejected", "reason": "Gateway is disabled"}

    bindings = frappe.get_all(
        "Gateway Binding",
        filters={"gateway": gateway.name, "is_enabled": 1},
        fields=["name", "priority", "match_type", "match_value", "target_type", "agent", "flow"],
        order_by="priority asc, creation asc",
    )
    for binding in bindings:
        if _binding_matches(binding, context):
            target = _route_target(binding.target_type, binding.agent, binding.flow)
            if target:
                return {"status": "Queued", "binding": binding.name, **target}

    target = _route_target(gateway.default_target_type, gateway.default_agent, gateway.default_flow)
    if target:
        return {"status": "Queued", "binding": None, **target}
    return {"status": "Unrouted", "reason": "No enabled route matches this message"}


def ingest_gateway_event(
    gateway_name: str,
    provider_event_id: str,
    context: dict[str, Any],
    *,
    verified_sender: bool,
    raw_payload: dict[str, Any] | None = None,
) -> dict:
    """Persist, deduplicate and queue one verified provider event.

    The provider event ID is unique within a Gateway.  It is stored as a hash
    to make the database uniqueness constraint race-safe while keeping the
    original identifier available for support investigations.
    """
    if not provider_event_id:
        raise frappe.ValidationError(_("Provider event ID is required."))

    key = _idempotency_key(gateway_name, provider_event_id)
    existing = frappe.db.get_value("Gateway Event", {"idempotency_key": key}, "name")
    if existing:
        return {"duplicate": True, "event_name": existing}

    event = frappe.get_doc(
        {
            "doctype": "Gateway Event",
            "gateway": gateway_name,
            "idempotency_key": key,
            "provider_event_id": provider_event_id,
            "status": "Received",
            "received_at": now_datetime(),
            "verified_sender": 1 if verified_sender else 0,
            "sender_id": str(context.get("sender_id") or ""),
            "conversation_id": str(context.get("conversation_id") or ""),
            "thread_id": str(context.get("thread_id") or ""),
            "message_text": context.get("message_text") or "",
            "raw_payload": _redact_payload(raw_payload or {}),
        }
    )
    try:
        event.insert(ignore_permissions=True)
    except frappe.DuplicateEntryError:
        existing = frappe.db.get_value("Gateway Event", {"idempotency_key": key}, "name")
        return {"duplicate": True, "event_name": existing}

    if not verified_sender:
        event.db_set({"status": "Rejected", "error_message": "Provider did not verify sender"})
        return {"event_name": event.name, "status": "Rejected"}

    gateway = frappe.get_doc("Gateway", gateway_name)
    if not gateway.is_enabled:
        event.db_set({"status": "Rejected", "error_message": "Gateway is disabled"})
        return {"event_name": event.name, "status": "Rejected"}
    admitted, reason = _admission(gateway, context)
    if not admitted:
        event.db_set({"status": "Rejected", "error_message": reason})
        return {"event_name": event.name, "status": "Rejected"}

    route = resolve_gateway_route(gateway_name, context)
    if route["status"] != "Queued":
        event.db_set({"status": route["status"], "error_message": route.get("reason", "")})
        return {"event_name": event.name, **route}

    event.db_set(
        {
            "status": "Queued",
            "binding": route.get("binding"),
            "target_type": route["target_type"],
            "target_agent": route.get("agent"),
            "target_flow": route.get("flow"),
        }
    )
    frappe.enqueue(
        "huf.ai.gateway_service.process_gateway_event",
        queue="default",
        timeout=300,
        event_name=event.name,
        enqueue_after_commit=True,
    )
    return {"event_name": event.name, **route}


def process_gateway_event(event_name: str) -> dict:
    """Start queued Huf work under the Gateway's configured service user."""
    event = frappe.get_doc("Gateway Event", event_name)
    if event.status != "Queued":
        return {"event_name": event.name, "status": event.status}

    gateway = frappe.get_doc("Gateway", event.gateway)
    if not gateway.is_enabled or not gateway.execution_user:
        event.db_set({"status": "Rejected", "error_message": "Gateway is disabled or has no Run as user"})
        return {"event_name": event.name, "status": "Rejected"}

    if event.target_type == "Agent":
        from huf.ai.agent_access import assert_agent_access

        agent_doc = frappe.get_doc("Agent", event.target_agent)
        try:
            assert_agent_access(agent_doc, user="Guest")
        except frappe.PermissionError:
            event.db_set(
                {
                    "status": "Rejected",
                    "error_message": "Agent does not allow guest/public access",
                }
            )
            return {"event_name": event.name, "status": "Rejected"}

    try:
        frappe.set_user(gateway.execution_user)
        event.db_set("status", "Running")
        if event.target_type == "Agent":
            from huf.ai.agent_integration import run_agent_sync
            from huf.ai.gateway_webhook import send_gateway_reply

            result = run_agent_sync(
                agent_name=event.target_agent,
                prompt=event.message_text,
                channel_id=f"gateway:{gateway.name}",
                external_id=event.thread_id or event.conversation_id or event.sender_id,
                now=True,
            )
            response = result.get("response") if isinstance(result, dict) else None
            if not response or not str(response).strip():
                raise frappe.ValidationError(_("Gateway agent run completed without a text response."))
            try:
                delivery = send_gateway_reply(gateway, event, str(response))
                provider_message_id = delivery.provider_message_id
            except frappe.ValidationError as exc:
                if "No installed Gateway Adapter supports this channel" in str(exc):
                    provider_message_id = "agent_tool_delivery"
                else:
                    raise

            event.db_set({"agent_run": result.get("agent_run_id"), "status": "Succeeded"})
            return {
                "event_name": event.name,
                "status": "Succeeded",
                "agent_run_id": result.get("agent_run_id"),
                "provider_message_id": provider_message_id,
            }

        if event.target_type == "Flow":
            from huf.ai.flow_engine import create_flow_run

            # TODO(#473-followup): Gateway trigger_type is temporarily removed from
            # Flow Run options because the feature is incomplete. Re-enable once
            # docs/gateway-todo.md checklist is done and adapters are live.
            flow_run = create_flow_run(
                flow_id=event.target_flow,
                payload={"gateway_event": event.name, "message": event.message_text},
                trigger_type="Gateway",
            )
            event.db_set({"flow_run": flow_run.name, "status": "Queued"})
            frappe.enqueue(
                "huf.ai.flow_engine.run_flow",
                queue="default",
                timeout=300,
                flow_run_name=flow_run.name,
                enqueue_after_commit=True,
            )
            return {"event_name": event.name, "status": "Queued", "flow_run_id": flow_run.name}

        raise frappe.ValidationError(_("Gateway event has no valid target."))
    except Exception:
        message = frappe.get_traceback()
        event.db_set({"status": "Failed", "error_message": message[-500:]})
        frappe.log_error(message, "Gateway event failed")
        raise


@frappe.whitelist(methods=["POST"])
def preview_gateway_route(gateway_name: str, context: str | dict) -> dict:
    """Preview a route for administrators without executing any work."""
    if not frappe.has_permission("Gateway", "read"):
        frappe.throw(_("Not permitted"), frappe.PermissionError)
    if isinstance(context, str):
        context = json.loads(context)
    return resolve_gateway_route(gateway_name, context or {})
