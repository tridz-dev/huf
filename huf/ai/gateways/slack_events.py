"""Slack Events webhook handler."""
import frappe
import json
import re
import hmac
import hashlib
import time
from frappe.rate_limiter import rate_limit
from huf.ai.gateway_service import ingest_gateway_event

# Verification failure reason -> HTTP status.
_REASON_STATUS = {
    "unknown_gateway": 404,
    "gateway_disabled": 403,
    "wrong_provider": 403,
    "missing_headers": 401,
    "invalid_timestamp": 401,
    "stale_timestamp": 401,
    "missing_secret": 401,
    "bad_signature": 401,
}


# Only plain (subtype absent), thread_broadcast and file_share messages are processed;
# message_changed/message_deleted/bot_message/joins etc. are ignored.
_ALLOWED_SUBTYPES = (None, "thread_broadcast", "file_share")


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=100, seconds=60)
def handle_slack_event():
    gateway_name = frappe.request.args.get("gateway_name") if frappe.request is not None else None
    body = frappe.request.get_data(as_text=False)  # Get raw bytes for signature verification

    # Verify Slack signature before parsing JSON
    reason = _verify_slack_signature(gateway_name, body, frappe.request.headers)
    if reason:
        frappe.local.response.http_status_code = _REASON_STATUS[reason]
        return {"ok": False, "error": reason}

    # Now safe to parse JSON
    try:
        payload = json.loads(body.decode("utf-8") if isinstance(body, bytes) else body)
    except (ValueError, UnicodeDecodeError):
        payload = None
    if not isinstance(payload, dict):
        frappe.local.response.http_status_code = 400
        return {"ok": False, "error": "malformed_payload"}

    if payload.get("type") == "url_verification":
        from werkzeug.wrappers import Response
        return Response(json.dumps({"challenge": payload.get("challenge")}), status=200, mimetype="application/json")

    # Slack retries unacknowledged deliveries; acknowledge without re-ingesting.
    if frappe.request.headers.get("X-Slack-Retry-Num"):
        return {"ok": True}

    # Gateway existence/enabled/provider were already enforced by signature verification.
    gateway = frappe.get_doc("Gateway", gateway_name)

    event = payload.get("event") or {}
    if (
        event.get("type") in ("message", "app_mention")
        and not event.get("bot_id")
        and event.get("subtype") in _ALLOWED_SUBTYPES
    ):
        channel = str(event.get("channel") or "")
        ts = str(event.get("ts") or "")
        # Provider event id is channel:ts of the message itself. Slack sends both a
        # `message` and an `app_mention` event for one mention; both share this id.
        provider_event_id = f"{channel}:{ts}"
        text = str(event.get("text") or "")
        authorizations = payload.get("authorizations") or []
        bot_id = ""
        if authorizations and isinstance(authorizations[0], dict):
            bot_id = str(authorizations[0].get("user_id") or "")
        mention_token = f"<@{bot_id}>" if bot_id else ""
        mentioned = event.get("type") == "app_mention" or bool(mention_token and mention_token in text)
        if mention_token:
            # Strip the bot mention (and following whitespace); unknown bot id => text untouched.
            text = re.sub(re.escape(mention_token) + r"\s*", "", text)
        context = {
            "sender_id": str(event.get("user") or ""),
            "conversation_id": channel,
            # thread_id = thread_ts for replies, else the message's own ts (it roots a thread).
            "thread_id": str(event.get("thread_ts") or ts),
            "message_text": text,
            "is_room": _is_room(event, channel),
            "mentioned": mentioned,
        }

        ingest_gateway_event(
            gateway.name,
            provider_event_id,
            context,
            verified_sender=True,  # Signature was verified above before JSON parsing
            raw_payload=payload,
        )

    return {"ok": True}


def _is_room(event: dict, channel: str) -> bool:
    """True for public/private channels and group DMs (mpim); False for 1:1 DMs.

    Prefers event["channel_type"] (channel/group/mpim/im); falls back to the id
    prefix (C/G rooms, D DM).
    """
    channel_type = event.get("channel_type")
    if channel_type:
        return channel_type in ("channel", "group", "mpim")
    return channel.startswith(("C", "G"))


def _verify_slack_signature(gateway_name: str, body: bytes, headers: dict) -> str | None:
    """Verify Slack HMAC-SHA256 v0 signature with ±5 minute replay window.

    Per Slack's Events API documentation, signatures are computed as:
    v0=sha256(v0:<timestamp>:<raw_body>, signing_secret)

    Args:
        gateway_name: Name of the Gateway doc (used to look up signing_secret)
        body: Raw request body bytes
        headers: Request headers dict

    Returns:
        None if the signature is valid and the timestamp is within ±5 minutes,
        otherwise a failure reason key from _REASON_STATUS.
    """
    # Extract signature and timestamp headers
    sig_header = headers.get("X-Slack-Signature", "").strip()
    ts_header = headers.get("X-Slack-Request-Timestamp", "").strip()

    # Fail closed: both headers must be present
    if not sig_header or not ts_header:
        return "missing_headers"

    # Verify timestamp is within ±5 minutes (300 seconds) to prevent replay attacks
    try:
        ts = int(ts_header)
    except (ValueError, TypeError):
        return "invalid_timestamp"

    current_time = int(time.time())
    if abs(current_time - ts) > 300:
        return "stale_timestamp"

    # Look up the Gateway's signing_secret from Integration Settings
    if not gateway_name or not frappe.db.exists("Gateway", gateway_name):
        return "unknown_gateway"

    try:
        gateway = frappe.get_doc("Gateway", gateway_name)
    except frappe.DoesNotExistError:
        return "unknown_gateway"

    if gateway.provider != "Slack":
        return "wrong_provider"
    if not gateway.is_enabled:
        return "gateway_disabled"

    # Get signing_secret from Integration Settings credentials
    try:
        settings = frappe.get_doc("Integration Settings", gateway.integration_settings)
        signing_secret = ""
        for row in settings.credentials or []:
            if row.key == "signing_secret":
                signing_secret = row.get_password("value") or ""
                break
    except (frappe.DoesNotExistError, AttributeError):
        return "missing_secret"

    if not signing_secret:
        return "missing_secret"

    # Compute expected signature: v0=sha256(v0:<timestamp>:<raw_body>, signing_secret)
    sig_base_string = f"v0:{ts_header}:".encode() + body
    expected_sig = "v0=" + hmac.new(
        signing_secret.encode("utf-8"),
        sig_base_string,
        hashlib.sha256,
    ).hexdigest()

    # Compare using constant-time comparison to prevent timing attacks
    if not hmac.compare_digest(sig_header, expected_sig):
        return "bad_signature"

    return None
