"""Slack Events webhook handler."""
import frappe
import json
import hmac
import hashlib
import time
from frappe.rate_limiter import rate_limit
from huf.ai.gateway_service import ingest_gateway_event

@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=100, seconds=60)
def handle_slack_event():
    gateway_name = frappe.request.args.get("gateway_name") if frappe.request is not None else None
    body = frappe.request.get_data(as_text=False)  # Get raw bytes for signature verification

    # Verify Slack signature before parsing JSON
    if not _verify_slack_signature(gateway_name, body, frappe.request.headers):
        frappe.throw("Unauthorized: Invalid Slack signature", frappe.PermissionError)

    # Now safe to parse JSON
    payload = json.loads(body.decode("utf-8") if isinstance(body, bytes) else body)

    if payload.get("type") == "url_verification":
        from werkzeug.wrappers import Response
        return Response(json.dumps({"challenge": payload.get("challenge")}), status=200, mimetype="application/json")

    if not gateway_name or not frappe.db.exists("Gateway", gateway_name):
        frappe.log_error("Slack Debug - Early Return", f"Unknown gateway: '{gateway_name}'")
        return {"error": "Unknown gateway"}

    gateway = frappe.get_doc("Gateway", gateway_name)
    if gateway.provider != "Slack" or not gateway.is_enabled:
        frappe.log_error("Slack Debug - Early Return", f"Gateway inactive or wrong provider. Provider: {gateway.provider}, Enabled: {gateway.is_enabled}")
        return {"error": "Gateway is inactive"}

    event = payload.get("event") or {}
    if event.get("type") in ("message", "app_mention") and not event.get("bot_id"):
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
            verified_sender=True,  # Signature was verified above before JSON parsing
            raw_payload=payload,
        )
    else:
        frappe.log_error("Slack Debug - Event Ignored", f"Event Type: {event.get('type')}, Bot ID: {event.get('bot_id')}")
        
    return {"ok": True}


def _verify_slack_signature(gateway_name: str, body: bytes, headers: dict) -> bool:
    """Verify Slack HMAC-SHA256 v0 signature with ±5 minute replay window.

    Per Slack's Events API documentation, signatures are computed as:
    v0=sha256(v0:<timestamp>:<raw_body>, signing_secret)

    Args:
        gateway_name: Name of the Gateway doc (used to look up signing_secret)
        body: Raw request body bytes
        headers: Request headers dict

    Returns:
        True if signature is valid and timestamp is within ±5 minutes, False otherwise.
    """
    # Extract signature and timestamp headers
    sig_header = headers.get("X-Slack-Signature", "").strip()
    ts_header = headers.get("X-Slack-Request-Timestamp", "").strip()

    # Fail closed: both headers must be present
    if not sig_header or not ts_header:
        frappe.log_error(
            "Slack Signature Verification Failed",
            f"Missing signature or timestamp header for gateway {gateway_name}",
        )
        return False

    # Verify timestamp is within ±5 minutes (300 seconds) to prevent replay attacks
    try:
        ts = int(ts_header)
    except (ValueError, TypeError):
        frappe.log_error(
            "Slack Signature Verification Failed",
            f"Invalid timestamp format: {ts_header}",
        )
        return False

    current_time = int(time.time())
    if abs(current_time - ts) > 300:
        frappe.log_error(
            "Slack Signature Verification Failed",
            f"Timestamp replay attack detected: {abs(current_time - ts)} seconds old",
        )
        return False

    # Look up the Gateway's signing_secret from Integration Settings
    if not gateway_name or not frappe.db.exists("Gateway", gateway_name):
        frappe.log_error(
            "Slack Signature Verification Failed",
            f"Unknown gateway: {gateway_name}",
        )
        return False

    try:
        gateway = frappe.get_doc("Gateway", gateway_name)
    except frappe.DoesNotExistError:
        return False

    if gateway.provider != "Slack" or not gateway.is_enabled:
        frappe.log_error(
            "Slack Signature Verification Failed",
            f"Gateway is not a Slack gateway or not enabled: {gateway_name}",
        )
        return False

    # Get signing_secret from Integration Settings credentials
    try:
        settings = frappe.get_doc("Integration Settings", gateway.integration_settings)
        signing_secret = ""
        for row in settings.credentials or []:
            if row.key == "signing_secret":
                signing_secret = row.get_password("value") or ""
                break
    except (frappe.DoesNotExistError, AttributeError):
        frappe.log_error(
            "Slack Signature Verification Failed",
            f"Could not retrieve signing_secret for gateway {gateway_name}",
        )
        return False

    if not signing_secret:
        frappe.log_error(
            "Slack Signature Verification Failed",
            f"signing_secret not configured for gateway {gateway_name}",
        )
        return False

    # Compute expected signature: v0=sha256(v0:<timestamp>:<raw_body>, signing_secret)
    sig_base_string = f"v0:{ts_header}:".encode() + body
    expected_sig = "v0=" + hmac.new(
        signing_secret.encode("utf-8"),
        sig_base_string,
        hashlib.sha256,
    ).hexdigest()

    # Compare using constant-time comparison to prevent timing attacks
    if not hmac.compare_digest(sig_header, expected_sig):
        frappe.log_error(
            "Slack Signature Verification Failed",
            f"Signature mismatch for gateway {gateway_name}",
        )
        return False

    return True
