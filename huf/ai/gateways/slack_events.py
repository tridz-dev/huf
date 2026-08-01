"""Slack Events webhook handler."""
import frappe
import json
from huf.ai.gateway_service import ingest_gateway_event

@frappe.whitelist(allow_guest=True, methods=["POST"])
def handle_slack_event(gateway_name: str | None = None):
    if not gateway_name or not frappe.db.exists("Gateway", gateway_name):
        return {"error": "Unknown gateway"}

    gateway = frappe.get_doc("Gateway", gateway_name)
    if gateway.provider != "Slack" or not gateway.is_enabled:
        return {"error": "Gateway is inactive"}

    body = frappe.request.get_data(as_text=True)
    payload = json.loads(body)
    
    if payload.get("type") == "url_verification":
        return {"challenge": payload.get("challenge")}
        
    event = payload.get("event") or {}
    if event.get("type") == "message" and not event.get("bot_id"):
        context = {
            "sender_id": str(event.get("user") or ""),
            "conversation_id": str(event.get("channel") or ""),
            "thread_id": str(event.get("thread_ts") or event.get("ts") or ""),
            "message_text": str(event.get("text") or ""),
            "is_room": str(event.get("channel") or "").startswith("C"),
            "mentioned": "<@" in str(event.get("text") or ""),
        }
        
        ingest_gateway_event(
            gateway.name,
            str(event.get("client_msg_id") or event.get("ts")),
            context,
            verified_sender=True,
            raw_payload=payload,
        )
    return {"ok": True}
