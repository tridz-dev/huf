"""Shared, provider-neutral gateway ingress and routing.

Provider adapters are responsible for authenticating their native webhook and
normalising it into :func:`ingest_gateway_event`.  This module deliberately
does not expose a guest endpoint: each adapter owns its verification contract.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import os
import random
import re
import secrets
import threading
import time
from typing import Any

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import add_to_date, now_datetime

from huf.ai import whatsapp_outbound_policy as policy
from huf.ai.gateway_adapters import provider_hooks
from huf.ai.gateway_adapters.provider_ids import provider_to_service_id


MATCH_CONTEXT_KEY = {
    "Direct message": "conversation_id",
    "Room or channel": "conversation_id",
    "Thread": "thread_id",
    "Sender": "sender_id",
}
SENSITIVE_PAYLOAD_KEYS = {
    "authorization",
    "token",
    "secret",
    "signature",
    "api_key",
    "password",
    # Additional credential-related keys cross-referenced against adapter
    # credential_schema field names (huf/ai/gateway_adapters/*.py).
    "bearer_token",
    "x_api_key",
    "auth_token",
    "webhook_secret",
    "access_token",
    "client_secret",
    "signing_secret",
    # Adapter-specific credential fields (huf/ai/gateway_adapters/*.py).
    "corp_secret",
    "callback_token",
    "app_secret",
    "app_password",
    "bot_token",
    "public_key",
    "community_token",
    "callback_secret",
    "verification_token",
    # Google Chat (huf/ai/gateway_adapters/google_chat.py): G1/G6 credential
    # schema -- service_account_key is a full service-account private key.
    "service_account_key",
}


_FALLBACK_REPLY_WINDOW_SECONDS = 600


def _agent_run_failure(result) -> tuple[str, str] | None:
    """Return ``(error_code, short_reason)`` when an agent run did not produce a sendable reply.

    A failed run (``success`` False / ``error`` set), a non-dict result or an empty response
    must never reach the customer. ``error_code`` is ``provider_<kind>`` when the provider
    failure was classified, otherwise ``agent_run_failed``.
    """
    if not isinstance(result, dict):
        return "agent_run_failed", "The agent run returned no result."
    if result.get("success") is False or (result.get("error") and not result.get("response")):
        kind = str(result.get("error_kind") or "")
        code = f"provider_{kind}" if kind and kind != "unknown" else "agent_run_failed"
        reason = _redact_error_text(str(result.get("error") or "The agent run failed."))
        return code, reason
    response = result.get("response")
    if not response or not str(response).strip():
        return "agent_run_failed", "Gateway agent run completed without a text response."
    return None


def _gateway_fallback_reply_text(gateway) -> str:
    """Optional plain-text apology configured as an Integration Settings credential row
    ``fallback_reply_text`` (default: none, i.e. stay silent).

    ``Gateway.error_reply_text`` takes precedence over that credential row when set."""
    own = str(getattr(gateway, "error_reply_text", "") or "").strip()
    if own:
        return own
    try:
        if gateway.integration_settings:
            int_doc = frappe.get_doc("Integration Settings", gateway.integration_settings)
            for row in getattr(int_doc, "credentials", []) or []:
                if row.key == "fallback_reply_text":
                    value = row.get_password("value") if hasattr(row, "get_password") else row.value
                    return str(value or "").strip()
    except Exception:
        frappe.logger("huf").warning("Gateway fallback_reply_text could not be read")
    return ""


_FALLBACK_TEXTS = {
    "en": {
        "error": "Sorry, something went wrong on our side and I could not answer. Please try again in a moment.",
        "attachment": "Sorry, I could not open the file you sent. Please send it again or describe it in a message.",
    },
    "es": {
        "error": "Lo sentimos, algo salio mal y no pude responder. Por favor intentalo de nuevo en un momento.",
        "attachment": "Lo sentimos, no pude abrir el archivo que enviaste. Envialo de nuevo o descríbelo en un mensaje.",
    },
    "fr": {
        "error": "Désolé, un problème est survenu et je n'ai pas pu répondre. Veuillez réessayer dans un instant.",
        "attachment": "Désolé, je n'ai pas pu ouvrir le fichier envoyé. Renvoyez-le ou décrivez-le dans un message.",
    },
    "pt": {
        "error": "Desculpe, algo deu errado e nao consegui responder. Tente novamente em instantes.",
        "attachment": "Desculpe, nao consegui abrir o arquivo enviado. Envie novamente ou descreva em uma mensagem.",
    },
    "de": {
        "error": "Entschuldigung, es ist ein Fehler aufgetreten und ich konnte nicht antworten. Bitte versuchen Sie es gleich noch einmal.",
        "attachment": "Entschuldigung, ich konnte die gesendete Datei nicht öffnen. Bitte senden Sie sie erneut oder beschreiben Sie sie kurz.",
    },
    "ar": {
        "error": "عذرا، حدث خطأ ولم أتمكن من الرد. يرجى المحاولة مرة أخرى بعد قليل.",
        "attachment": "عذرا، لم أتمكن من فتح الملف الذي أرسلته. يرجى إرساله مرة أخرى أو وصفه في رسالة.",
    },
}
ATTACHMENT_UNAVAILABLE_NOTE = "[Attachment unavailable: the file the user sent could not be downloaded]"


def _lang_code(value: Any) -> str:
    return str(value or "").strip().replace("-", "_").split("_")[0].lower()


def _contact_language(event) -> str:
    raw = getattr(event, "raw_payload", None)
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            raw = None
    if isinstance(raw, dict):
        return _lang_code(raw.get("language") or raw.get("locale"))
    return ""


def _default_fallback_text(gateway, event, kind: str) -> str:
    """Plain, localized text: contact language > gateway default language > English."""
    if kind == "error":
        custom = _gateway_fallback_reply_text(gateway)
        if custom:
            return custom
    for code in (_contact_language(event), _lang_code(getattr(gateway, "fallback_template_language", ""))):
        if code in _FALLBACK_TEXTS:
            return _FALLBACK_TEXTS[code][kind]
    return _FALLBACK_TEXTS["en"][kind]


def _send_fallback_once(event, gateway, kind: str = "error") -> bool:
    """Send the default fallback reply at most once per event and kind, through the normal reply
    pipeline (opt-out and window rules apply). Never raises."""
    try:
        if event.sender_id and is_opted_out(gateway, event.sender_id):
            return False
        key = f"huf_gw_fallback_reply:{event.name}:{kind}"
        if not frappe.cache().set(key, 1, ex=86400, nx=True):
            return False
        from huf.ai.gateway_webhook import send_gateway_reply

        delivery = send_gateway_reply(gateway, event, _default_fallback_text(gateway, event, kind))
        if kind == "error":
            _record_reply_sent(event, getattr(delivery, "provider_message_id", None))
        return True
    except Exception:
        frappe.logger("huf").warning("Gateway fallback reply failed to send")
        return False


def _inbound_media_type(event) -> str | None:
    """Media message type of the inbound WhatsApp message, when it carries a downloadable id."""
    raw = getattr(event, "raw_payload", None)
    try:
        if isinstance(raw, str):
            raw = json.loads(raw)
        message = raw.get("message") if isinstance(raw, dict) else None
        msg_type = message.get("type") if isinstance(message, dict) else None
        if msg_type in ("image", "document", "audio", "video", "sticker") and (message.get(msg_type) or {}).get("id"):
            return msg_type
    except Exception:
        pass
    return None


def _fail_event_for_agent_run(
    event, gateway, result, error_code: str, reason: str, fallback_kind: str = "error"
) -> dict:
    """Mark the event Failed for a failed agent run and send nothing (bar the default fallback reply)."""
    agent_run_id = result.get("agent_run_id") if isinstance(result, dict) else None
    message = f"{error_code}: {reason}"[:500]
    values = {"status": "Failed", "error_message": message, "delivery_error": message[:140]}
    if agent_run_id:
        values["agent_run"] = agent_run_id
    event.db_set(values)
    frappe.log_error(message, "Gateway agent run failed")
    fallback_sent = _send_fallback_once(event, gateway, fallback_kind)
    return {
        "event_name": event.name,
        "status": "Failed",
        "error": reason,
        "error_code": error_code,
        "agent_run_id": agent_run_id,
        "fallback_sent": fallback_sent,
    }



def _call_instructions_hook(hook, gateway) -> str | None:
	"""Run a provider ``agent_instructions`` hook; never let a hook failure fail the inbound event.

	Passes ``gateway`` only when the hook accepts a positional argument (inspected, not inferred from a
	caught TypeError, which would also swallow TypeErrors raised inside the hook). Any exception yields
	``None`` (no channel note) and a warning without the error message, which may carry secrets.
	"""
	try:
		sig = inspect.signature(hook)
	except (TypeError, ValueError):
		sig = None
	takes_gateway = sig is None or any(
		p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD, p.VAR_POSITIONAL) for p in sig.parameters.values()
	)
	try:
		return hook(gateway) if takes_gateway else hook()
	except Exception as exc:
		frappe.logger("huf").warning(
			f"Agent instructions hook failed for provider {getattr(gateway, 'provider', None)}: {type(exc).__name__}"
		)
		return None


def _idempotency_key(gateway_name: str, provider_event_id: str) -> str:
    value = f"{gateway_name}:{provider_event_id}".encode()
    return hashlib.sha256(value).hexdigest()


# GW-07: a provider outbound call's HTTPError can carry the request URL
# verbatim in its string representation (e.g. Telegram's
# ``https://api.telegram.org/bot<TOKEN>/sendMessage`` scheme), and several
# call sites here turn "whatever the exception says" into an externally
# readable string -- ``notification_status`` returned to the caller of
# ``approve_gateway_pairing``, and ``frappe.log_error``'s traceback dump.
# This generalizes the ad hoc ``_sanitize_token`` helper in
# ``huf.ai.tools.telegram`` (which only ever had the one bot token in scope
# to redact) into a provider-agnostic pattern match so every adapter's
# URL-embedded or header-embedded credential is stripped before it reaches
# any such surface, not just Telegram's.
_URL_TOKEN_PATTERNS = (
    # Bot-token-in-path schemes (Telegram: /bot<digits>:<token>/...).
    re.compile(r"(/bot)\d+:[A-Za-z0-9_-]+"),
    # Authorization-style credentials appearing in dumped text.
    re.compile(r"(?i)\b(Bearer|Basic|Token)\s+[A-Za-z0-9._~+/=-]{8,}"),
    # Sensitive query-string parameters embedded in a URL.
    re.compile(r"(?i)([?&](?:token|api[_-]?key|secret|access_token|key|password)=)[^&\s\"'<>]+"),
)


def _redact_error_text(text: str) -> str:
    """Strip provider credentials that leaked into an exception's string form
    before it reaches any externally-readable field (``notification_status``,
    ``frappe.log_error``, a ``db_set`` error_message, ...)."""
    if not text:
        return text
    redacted = text
    redacted = _URL_TOKEN_PATTERNS[0].sub(r"\1[redacted]", redacted)
    redacted = _URL_TOKEN_PATTERNS[1].sub(r"\1 [redacted]", redacted)
    redacted = _URL_TOKEN_PATTERNS[2].sub(r"\1[redacted]", redacted)
    return redacted


# Types that json.dumps (used by the JSON `raw_payload` field) can serialize
# natively. Anything else (datetime/date/time, Decimal, set, a Frappe Document
# child row, ...) must be stringified here rather than left for json.dumps to
# choke on -- GW-04: `Communication.as_dict()` carries native `datetime`
# objects (e.g. `communication_date`), and frappe's JSON field write path does
# a plain `json.dumps` with no `default=str`, so passing one through
# unconverted crashes with `TypeError: Object of type datetime is not JSON
# serializable` on every real inbound email.
_JSON_NATIVE_TYPES = (str, int, float, bool, type(None))


def _record_reply_sent(event, provider_message_id) -> None:
    """Remember the outbound wamid so delivery statuses can be joined back. Never raises."""
    try:
        if provider_message_id:
            event.db_set(
                {"reply_message_id": str(provider_message_id)[:255], "reply_status": "sent"},
                update_modified=False,
            )
    except Exception:
        pass


def _redact_payload(value: Any) -> Any:
    """Retain support evidence without persisting provider credentials.

    Also makes the result safe to store in a JSON field: dict/list containers
    are walked recursively, values of JSON-native types pass through as-is,
    and anything else is coerced to its string representation.
    """
    if isinstance(value, dict):
        return {
            key: "[redacted]" if key.lower() in SENSITIVE_PAYLOAD_KEYS else _redact_payload(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_redact_payload(item) for item in value]
    if isinstance(value, _JSON_NATIVE_TYPES):
        return value
    return str(value)


# CL-02: every adapter declares GatewayCapabilities.max_outbound_messages_per_second
# but nothing previously read it before calling adapter.send_reply. This is a
# minimal per-gateway token bucket (capacity 1 -- a single send is never
# delayed, but a tight burst is spread out at the declared rate) enforced in
# process_gateway_event just before send_gateway_reply is invoked.
_OUTBOUND_RATE_LOCK = threading.Lock()
_OUTBOUND_RATE_NEXT_ALLOWED: dict[str, float] = {}


def _monotonic() -> float:
    return time.monotonic()


def _sleep(seconds: float) -> None:
    if seconds > 0:
        time.sleep(seconds)


def _outbound_rate_cap(provider: str | None) -> float | None:
    """Resolve the declared outbound rate cap for a Gateway's provider without
    instantiating its adapter (capabilities is a class-level attribute, so no
    credentials are needed just to read the declared limit)."""
    if not provider:
        return None
    try:
        from huf.ai.gateway_webhook import _adapter_class_for_provider

        adapter_cls = _adapter_class_for_provider(provider)
        return adapter_cls.capabilities.max_outbound_messages_per_second
    except Exception:
        return None


def _throttle_outbound_send(gateway_name: str, max_per_second: float | None) -> None:
    """Block only long enough to keep this gateway's outbound sends at or
    under its declared ``max_outbound_messages_per_second`` cap."""
    if not max_per_second or max_per_second <= 0:
        return
    min_interval = 1.0 / max_per_second
    with _OUTBOUND_RATE_LOCK:
        now = _monotonic()
        next_allowed = _OUTBOUND_RATE_NEXT_ALLOWED.get(gateway_name, 0.0)
        wait = max(0.0, next_allowed - now)
        _OUTBOUND_RATE_NEXT_ALLOWED[gateway_name] = max(now, next_allowed) + min_interval
    _sleep(wait)


def _whatsapp_send_errors(provider: str | None) -> tuple[type[BaseException], ...]:
    """Delivery errors that mean "not sendable right now" for WhatsApp (A7).

    Imported lazily, and only for WhatsApp gateways, so other deployments never
    import the whatsapp modules. Returns ``()`` (matches nothing in ``except``)
    for every other provider.
    """
    hook = provider_hooks.get(provider, "send_errors")
    return hook() if hook is not None else ()


WHATSAPP_FALLBACK_NOTE = "Fallback template sent; agent reply suppressed (24h window closed)"


def _provider_error_text(provider: str | None, exc: BaseException) -> str:
    """Operator-readable delivery error text via the provider's ``error_text`` hook."""
    hook = provider_hooks.get(provider, "error_text")
    return hook(exc) if hook is not None else (_redact_error_text(str(exc)) or "Delivery failed")


def _whatsapp_error_text(exc: BaseException) -> str:
    """Operator-readable text for a WhatsAppWindowClosed / BridgeError."""
    payload = getattr(exc, "payload", None)
    if isinstance(payload, dict):
        detail = payload.get("message") or payload.get("error") or "bridge_error"
        return f"WhatsApp delivery failed: {detail}"
    return _redact_error_text(str(exc)) or "WhatsApp delivery failed"


def _normalize_sender_for_provider(provider: str | None, entry_type: str, external_id: Any) -> str:
    """Canonicalise WhatsApp sender ids (digits only) so allowlist keys never drift (A10).

    Meta's ``wa_id`` is canonical (e.g. Brazil/Mexico numbers may differ from the
    number a human types); inbound sender ids already are wa_ids, so only the
    punctuation/prefix form is normalised -- never digits added or removed.
    """
    hook = provider_hooks.get(provider, "normalize_sender")
    return hook(entry_type, external_id) if hook is not None else str(external_id)


_MEDIA_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]")


_MIME_EXTENSIONS = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
    "audio/ogg": "ogg",
    "audio/mpeg": "mp3",
    "audio/mp4": "m4a",
    "audio/aac": "aac",
    "audio/amr": "amr",
    "video/mp4": "mp4",
    "video/3gpp": "3gp",
    "application/pdf": "pdf",
    "text/plain": "txt",
    "text/csv": "csv",
    "application/msword": "doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/vnd.ms-excel": "xls",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "application/vnd.ms-powerpoint": "ppt",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
}


def _media_file_name(msg_type: str, media: dict, media_id: str, downloaded: dict) -> str:
    """A readable file name: the sender's own filename for documents, else ``<type>-<id>.<ext>``."""
    mime = str(downloaded.get("mime_type") or (media or {}).get("mime_type") or "").split(";")[0].strip().lower()
    ext = _MIME_EXTENSIONS.get(mime) or (mime.split("/")[-1] if "/" in mime and mime.split("/")[-1].isalnum() else "")
    original = os.path.basename(str((media or {}).get("filename") or ""))
    if not original:
        # Meta's media metadata sometimes names the file; the bridge falls back to the raw id.
        provided = os.path.basename(str(downloaded.get("filename") or ""))
        if provided and _MEDIA_SAFE_NAME.sub("_", media_id) not in (provided, provided.rsplit(".", 1)[0]):
            original = provided
    if original:
        name = original
    else:
        name = f"{msg_type}-{media_id}"
    name = _MEDIA_SAFE_NAME.sub("_", name).lstrip(".")[:100] or f"{msg_type}-{media_id}"
    if ext and "." not in os.path.basename(name):
        name = f"{name}.{ext}"[:100]
    return name


def _save_event_media(event, gateway) -> list[str]:
    """Provider ``media_save`` hook; no hook = no inbound media is saved."""
    hook = provider_hooks.get(gateway.provider, "media_save")
    return hook(event, gateway) if hook is not None else []


def _save_whatsapp_media(event, gateway) -> list[str]:
    """Best-effort download of inbound WhatsApp media into private Files (A9).

    Never raises: any failure is logged and the text flow continues.
    """
    saved: list[str] = []
    try:
        raw = event.raw_payload
        if isinstance(raw, str):
            raw = json.loads(raw)
        message = raw.get("message") if isinstance(raw, dict) else None
        if not isinstance(message, dict):
            return saved
        msg_type = message.get("type")
        media = message.get(msg_type) if msg_type in ("image", "document", "audio", "video", "sticker") else None
        media_id = str((media or {}).get("id") or "")
        if not media_id:
            return saved

        from huf.ai.gateway_adapters import whatsapp_bridge as bridge

        account = (getattr(gateway, "whatsapp_account", "") or "").strip() or None
        direct = None
        if not account:
            # Direct mode (no WhatsApp Account): use the gateway's own Meta credentials.
            from huf.ai.gateway_webhook import _gateway_credentials

            creds = _gateway_credentials(gateway)
            direct = {"token": creds.get("access_token"), "url": bridge.graph_base_url(creds.get("graph_api_url"))}
        downloaded = bridge.download_media(
            account, media_id, credentials=direct, kind=msg_type, filename=(media or {}).get("filename")
        )
        name = _media_file_name(msg_type, media, media_id, downloaded)
        file_doc = frappe.get_doc(
            {
                "doctype": "File",
                "file_name": name,
                "content": downloaded["content"],
                "attached_to_doctype": "Gateway Event",
                "attached_to_name": event.name,
                "is_private": 1,
            }
        ).insert(ignore_permissions=True)
        saved.append(file_doc.file_url)
    except Exception as exc:
        frappe.logger("huf").warning(f"WhatsApp media download skipped: {_redact_error_text(str(exc))}")
    return saved


def _describe_attachments(raw_payload: Any) -> str:
    """Best-effort, provider-agnostic sniff of stored raw payload for attachments.

    GW-30 added an ``attachments`` field to ``NormalizedGatewayEvent``, but the
    ``Gateway Event`` doctype has no dedicated column for it yet (out of scope
    for this change -- see findings). Since the full (redacted) provider
    payload is already persisted on every event, this recovers "was media
    attached, and what kind" from the well-known per-provider payload shapes
    so the note can survive round-tripping through storage, rather than
    requiring attachments to be threaded through as a brand-new doctype field.
    Returns "" when nothing recognizable is found -- callers must not assume
    absence of a note means absence of media for providers not covered here.
    """
    if not isinstance(raw_payload, dict):
        return ""

    kinds: list[str] = []

    # Telegram: message/edited_message carries one of these media keys directly.
    message = raw_payload.get("message") or raw_payload.get("edited_message")
    if isinstance(message, dict):
        for key in ("photo", "document", "voice", "video", "audio", "video_note", "sticker"):
            if message.get(key):
                kinds.append(key)

    # WhatsApp Gateway Event shape ({"message": <Meta message>}), see WhatsAppGatewayAdapter.
    if isinstance(message, dict) and message.get("type") in (
        "image", "document", "audio", "video", "sticker",
    ):
        kinds.append(message["type"])

    # WhatsApp Business/Cloud API webhook shape.
    try:
        value = raw_payload["entry"][0]["changes"][0]["value"]
        msg = (value.get("messages") or [None])[0]
        if isinstance(msg, dict) and msg.get("type") in (
            "image", "document", "audio", "video", "sticker",
        ):
            kinds.append(msg["type"])
    except (KeyError, IndexError, TypeError):
        pass

    # Messenger/Instagram webhook shape.
    try:
        messaging_event = raw_payload["entry"][0]["messaging"][0]
        for attachment in (messaging_event.get("message") or {}).get("attachments") or []:
            if attachment.get("type"):
                kinds.append(str(attachment["type"]))
    except (KeyError, IndexError, TypeError):
        pass

    # MS Teams Bot Framework activity shape.
    for attachment in raw_payload.get("attachments") or []:
        if isinstance(attachment, dict) and attachment.get("contentUrl"):
            kinds.append("file")

    # Twilio-style SMS/MMS form payload (persisted as a flat dict of params).
    if raw_payload.get("NumMedia") not in (None, "0", 0):
        kinds.append("mms")

    if not kinds:
        return ""

    unique_kinds = sorted(set(kinds))
    return "[Attachment(s) present: " + ", ".join(unique_kinds) + "]"


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


# ---------------------------------------------------------------------------
# Admission, pairing, opt-out and per-sender limits (T2)
# ---------------------------------------------------------------------------

# 31 unambiguous characters: A-Z without I, L, O and 2-9 (no 0/1).
PAIRING_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
PAIRING_CODE_LENGTH = 8
PAIRING_PREFIX = "PAIR-"
PAIRING_RESEND_COOLDOWN_MINUTES = 10
PAIRING_APPROVAL_MAX_FAILURES_PER_MINUTE = 5
PENDING_ENTRY_RETENTION_DAYS = 7
PAIRING_DEFAULT_PENDING_LIMIT = 50
PAIRING_DEFAULT_REPLY_DAILY_LIMIT = 20
PAIRING_MAX_REQUESTS_PER_SENDER_PER_DAY = 3

# Access entry states that stop a sender from being admitted or re-paired.
ENTRY_STATE_BLOCKED = "Blocked"
ENTRY_STATE_REVOKED = "Revoked"
ENTRY_STATE_OPTED_OUT = "Opted out"
ENTRY_STATE_EXPIRED = "Expired"
_RESTORABLE_STATES = ("Approved", ENTRY_STATE_REVOKED, ENTRY_STATE_BLOCKED)
_LIVE_ENTRY_STATES = ("Approved", "Pending", ENTRY_STATE_OPTED_OUT, ENTRY_STATE_REVOKED, ENTRY_STATE_BLOCKED)

# Providers that run STOP/START handling and the per-sender inbound limit.
# Other providers keep their previous behaviour byte-for-byte.
def _consent_enabled(provider: str | None) -> bool:
    hook = provider_hooks.get(provider, "consent_required")
    return bool(hook()) if hook is not None else False


DEFAULT_OPT_OUT_KEYWORDS = "STOP\nUNSUBSCRIBE\nCANCEL\nEND\nQUIT"
DEFAULT_OPT_IN_KEYWORDS = "START\nUNSTOP\nSUBSCRIBE"
DEFAULT_OPT_OUT_REPLY = (
    "You have been unsubscribed and will not receive further messages. Reply START to resubscribe."
)
DEFAULT_OPT_IN_REPLY = "You have been resubscribed. Reply STOP at any time to unsubscribe."
DEFAULT_INBOUND_SENDER_LIMIT = 20
INBOUND_SENDER_WINDOW_SECONDS = 600

_GATEWAY_ADMIN_ROLES = ("System Manager", "Huf Admin")


# -- small cache counter helpers ------------------------------------------------


def _counter_key(*parts: Any) -> str:
    return "huf:gw:" + ":".join(str(p) for p in parts)


def _bump_counter(key: str, ttl_seconds: int) -> int:
    """Atomically increment a fixed-window counter and return the new value."""
    cache = frappe.cache()
    redis_key = cache.make_key(key)
    count = int(cache.incrby(redis_key, 1))
    cache.expire(redis_key, ttl_seconds)
    return count


def _read_counter(key: str) -> int:
    cache = frappe.cache()
    try:
        return int(cache.get(cache.make_key(key)) or 0)
    except (TypeError, ValueError):
        return 0


# -- authority ------------------------------------------------------------------


def _is_gateway_admin() -> bool:
    """Single authority for list/approve/revoke: System Manager, Huf Admin, or ``system.integrations.manage``."""
    if set(frappe.get_roles() or []).intersection(_GATEWAY_ADMIN_ROLES):
        return True
    try:
        from huf.permissions import is_gateway_admin

        return bool(is_gateway_admin(frappe.session.user))
    except Exception:
        return False


def _require_gateway_admin() -> None:
    if not _is_gateway_admin():
        frappe.throw(_("Gateway administrator permission is required."), frappe.PermissionError)


# -- pairing codes --------------------------------------------------------------


def _generate_pairing_code() -> str:
    suffix = "".join(secrets.choice(PAIRING_ALPHABET) for _i in range(PAIRING_CODE_LENGTH))
    return f"{PAIRING_PREFIX}{suffix}"


def normalize_pairing_code(value: Any) -> str:
    """Return the canonical ``PAIR-XXXXXXXX`` form, or ``""`` if ``value`` is not a code.

    Accepts any case, surrounding whitespace, and the dash being omitted
    (``pair-abcd2345``, ``PAIRABCD2345``, bare ``ABCD2345``).
    """
    text = re.sub(r"\s+", "", str(value or "")).upper()
    if text.startswith("PAIR"):
        text = text[4:].lstrip("-")
    if len(text) != PAIRING_CODE_LENGTH or any(ch not in PAIRING_ALPHABET for ch in text):
        return ""
    return f"{PAIRING_PREFIX}{text}"


def _code_in_use(gateway_name: str, code: str) -> bool:
    return bool(
        frappe.get_all(
            "Gateway Access Entry",
            filters={"gateway": gateway_name, "state": "Pending", "pairing_code": code},
            pluck="name",
            limit_page_length=1,
        )
    )


def _new_unique_pairing_code(gateway_name: str) -> str:
    for _attempt in range(10):
        code = _generate_pairing_code()
        if not _code_in_use(gateway_name, code):
            return code
    frappe.throw(_("Could not allocate a unique pairing code. Try again."))


# -- access entries -------------------------------------------------------------


def _save_entry(entry, updates: dict[str, Any]):
    """Apply ``updates`` through ``save()`` so Frappe's version log (track_changes) records who changed what."""
    if isinstance(entry, str):
        entry = frappe.get_doc("Gateway Access Entry", entry)
    entry.update(updates)
    entry.save(ignore_permissions=True, ignore_version=False)
    return entry


def _has_access_entry(gateway, entry_type: str, external_id: str) -> bool:
    if not external_id:
        return False
    entries = frappe.get_all(
        "Gateway Access Entry",
        filters={
            "gateway": gateway.name, "entry_type": entry_type, "provider": gateway.provider,
            "external_id": _normalize_sender_for_provider(gateway.provider, entry_type, external_id),
            "state": "Approved",
        },
        or_filters=[["expires_at", "is", "not set"], ["expires_at", ">=", now_datetime()]],
        pluck="name",
        limit_page_length=1,
    )
    return bool(entries)


def _sender_negative_state(gateway, sender_id: str) -> str | None:
    """Return ``Opted out``, ``Blocked`` or ``Revoked`` if the sender is in that state.

    Opted out and Blocked always win. Revoked loses to a currently valid
    Approved entry (an admin explicitly re-approved the sender).
    """
    if not sender_id:
        return None
    external_id = _normalize_sender_for_provider(gateway.provider, "Sender", sender_id)
    states = set(
        frappe.get_all(
            "Gateway Access Entry",
            filters={
                "gateway": gateway.name,
                "entry_type": "Sender",
                "provider": gateway.provider,
                "external_id": ["in", _linked_sender_ids(gateway.name, gateway.provider, sender_id)],
                "state": ["in", [ENTRY_STATE_OPTED_OUT, ENTRY_STATE_BLOCKED, ENTRY_STATE_REVOKED]],
            },
            pluck="state",
            limit_page_length=0,
        )
        or []
    )
    if ENTRY_STATE_OPTED_OUT in states:
        return ENTRY_STATE_OPTED_OUT
    if ENTRY_STATE_BLOCKED in states:
        return ENTRY_STATE_BLOCKED
    if ENTRY_STATE_REVOKED in states and not _has_access_entry(gateway, "Sender", sender_id):
        return ENTRY_STATE_REVOKED
    return None


def _raw_bsuid(raw: Any) -> str:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            return ""
    return str(raw.get("bsuid") or "") if isinstance(raw, dict) else ""


def _linked_sender_ids(gateway_name: str, provider: str | None, sender: str) -> list[str]:
    """The normalised sender id plus the other WhatsApp id (phone <-> BSUID) seen with it on an event."""
    primary = _normalize_sender_for_provider(provider, "Sender", sender)
    ids = [primary]
    if not primary or provider_hooks.get(provider, "linked_sender_ids") is None:
        return ids
    return provider_hooks.call(provider, "linked_sender_ids", gateway_name, primary)


def _whatsapp_linked_sender_ids(gateway_name: str, primary: str, provider: str) -> list[str]:
    """Phone <-> BSUID aliases seen with ``primary`` (WhatsApp ``linked_sender_ids`` hook)."""
    ids = [primary]
    from huf.ai.gateway_adapters import whatsapp_bridge as bridge

    if bridge.is_bsuid(primary):
        filters = {"gateway": gateway_name, "raw_payload": ["like", f"%{primary}%"]}
    else:
        filters = {"gateway": gateway_name, "sender_id": primary, "raw_payload": ["like", "%bsuid%"]}
    rows = frappe.get_all(
        "Gateway Event", filters=filters, fields=["sender_id", "raw_payload"],
        order_by="creation desc", limit_page_length=20,
    )  # fmt: skip
    for row in rows or []:
        if bridge.is_bsuid(primary):
            if _raw_bsuid(row.get("raw_payload")) == primary and row.get("sender_id"):
                other = _normalize_sender_for_provider(provider, "Sender", row["sender_id"])
            else:
                continue
        else:
            other = _raw_bsuid(row.get("raw_payload"))
        if other and other not in ids:
            ids.append(other)
    return ids


def is_opted_out(gateway, sender: str) -> bool:
    """True if ``sender`` opted out (STOP) on ``gateway``.

    Outbound proactive/template sends MUST call this and refuse when True.
    ``gateway`` may be a Gateway doc or its name. The opt-out confirmation
    itself is sent inside ``_consent_send_scope`` which makes this return False
    for that one sender so the confirmation is not blocked by its own gate.
    """
    if not sender:
        return False
    if isinstance(gateway, str):
        provider = frappe.db.get_value("Gateway", gateway, "provider")
        gateway_name = gateway
    else:
        provider = gateway.provider
        gateway_name = gateway.name
    external_id = _normalize_sender_for_provider(provider, "Sender", sender)
    if getattr(frappe.local, "huf_consent_send_scope", None) == (gateway_name, external_id):
        return False
    return bool(
        frappe.get_all(
            "Gateway Access Entry",
            filters={
                "gateway": gateway_name,
                "entry_type": "Sender",
                "external_id": ["in", _linked_sender_ids(gateway_name, provider, sender)],
                "state": ENTRY_STATE_OPTED_OUT,
            },
            pluck="name",
            limit_page_length=1,
        )
    )


class _consent_send_scope:
    """Context manager letting the opt-out/in confirmation bypass ``is_opted_out``."""

    def __init__(self, gateway, sender_id: str):
        self._token = (gateway.name, _normalize_sender_for_provider(gateway.provider, "Sender", sender_id))
        self._previous = None

    def __enter__(self):
        self._previous = getattr(frappe.local, "huf_consent_send_scope", None)
        frappe.local.huf_consent_send_scope = self._token
        return self

    def __exit__(self, *exc):
        frappe.local.huf_consent_send_scope = self._previous
        return False


def _send_plain_reply(gateway, sender_id: str, conversation_id: str | None, text: str) -> None:
    """Best-effort text reply through the gateway adapter (never raises)."""
    try:
        from huf.ai.gateway_adapters.types import GatewayReply
        from huf.ai.gateway_webhook import get_gateway_adapter

        with _consent_send_scope(gateway, sender_id):
            get_gateway_adapter(gateway).send_reply(
                GatewayReply(conversation_id=conversation_id or sender_id, text=text)
            )
    except _whatsapp_send_errors(gateway.provider) as exc:
        frappe.logger("huf").warning(f"Consent reply not delivered: {_whatsapp_error_text(exc)}")
    except Exception as exc:
        frappe.logger("huf").warning(f"Failed to send consent reply: {_redact_error_text(str(exc))}")


# -- opt-out / opt-in -----------------------------------------------------------


def _normalize_consent_text(text: Any) -> str:
    """Lowercase, drop punctuation/symbols/emoji, collapse whitespace."""
    import unicodedata

    out = []
    for ch in str(text or "").casefold():
        if ch in ("︎", "️", "‍"):
            continue
        category = unicodedata.category(ch)
        out.append(ch if category[0] in ("L", "N", "M") else " ")
    return " ".join("".join(out).split())


def _keyword_set(gateway, fieldname: str, default: str) -> set[str]:
    raw = getattr(gateway, fieldname, None)
    if raw is None or not str(raw).strip():
        raw = default
    keywords = set()
    for part in re.split(r"[\n,]", str(raw)):
        normalized = _normalize_consent_text(part)
        if normalized:
            keywords.add(normalized)
    return keywords


def _text_matches_keywords(gateway, text: Any, fieldname: str, default: str) -> bool:
    normalized = _normalize_consent_text(text)
    return bool(normalized) and normalized in _keyword_set(gateway, fieldname, default)


def _live_sender_entry(gateway, sender_id: str) -> dict | None:
    external_id = _normalize_sender_for_provider(gateway.provider, "Sender", sender_id)
    rows = frappe.get_all(
        "Gateway Access Entry",
        filters={
            "gateway": gateway.name,
            "entry_type": "Sender",
            "provider": gateway.provider,
            "external_id": external_id,
            "state": ["in", list(_LIVE_ENTRY_STATES)],
        },
        fields=["name", "state", "previous_state"],
        order_by="modified desc",
        limit_page_length=0,
    )
    for row in rows or []:
        return row
    return None


def _record_opt_out(gateway, sender_id: str, display_name: str | None = None) -> None:
    external_id = _normalize_sender_for_provider(gateway.provider, "Sender", sender_id)
    row = _live_sender_entry(gateway, sender_id)
    if row:
        _save_entry(row["name"], {"state": ENTRY_STATE_OPTED_OUT, "previous_state": row["state"]})
        return
    frappe.get_doc(
        {
            "doctype": "Gateway Access Entry",
            "gateway": gateway.name,
            "entry_type": "Sender",
            "provider": gateway.provider,
            "external_id": external_id,
            "state": ENTRY_STATE_OPTED_OUT,
            "previous_state": "",
            "display_label": (display_name or "").strip() or f"Sender {external_id}",
        }
    ).insert(ignore_permissions=True)


def _record_opt_out_linked(gateway, event, sender_id: str, display_name: str | None = None) -> None:
    """Record the opt-out under the sender id and, when the event carries both, the BSUID too."""
    _record_opt_out(gateway, sender_id, display_name)
    other = _raw_bsuid(getattr(event, "raw_payload", None))
    if other and other != sender_id:
        _record_opt_out(gateway, other, display_name)


def _record_opt_in_linked(gateway, sender_id: str) -> None:
    """START clears the opt-out under every id linked to the sender (phone and BSUID), like STOP set it."""
    for linked in _linked_sender_ids(gateway.name, gateway.provider, sender_id):
        _record_opt_in(gateway, linked)


def _record_opt_in(gateway, sender_id: str) -> None:
    row = _live_sender_entry(gateway, sender_id)
    if not row or row["state"] != ENTRY_STATE_OPTED_OUT:
        return
    previous = row.get("previous_state")
    restored = previous if previous in _RESTORABLE_STATES else ENTRY_STATE_EXPIRED
    _save_entry(row["name"], {"state": restored, "previous_state": ""})


def _reject_event(event, reason: str) -> dict:
    event.db_set({"status": "Rejected", "error_message": reason})
    return {"event_name": event.name, "status": "Rejected"}


def access_rate_gate(gateway, context: dict[str, Any]) -> str:
    """Per-sender inbound rate gate for ingest to call BEFORE any consent/admission side effect.

    Returns ``""`` when the event may proceed, else the rejection reason.
    """
    return _sender_rate_limit_reason(gateway, context)


def _sender_is_known(gateway, sender_id: str) -> bool:
    """True if the sender is approved or already has any live access entry (no side effects)."""
    if _has_access_entry(gateway, "Sender", sender_id):
        return True
    return _live_sender_entry(gateway, sender_id) is not None


def record_consent_event(event, gateway, context: dict[str, Any]) -> dict | None:
    """STOP/START handling for ingest. Returns a result dict when handled.

    Call after :func:`access_rate_gate`. A sender that is not admitted and has
    no access entry gets neither a row nor a reply (a stranger's STOP must not
    allocate state or trigger outbound traffic).
    """
    return _handle_consent_event(event, gateway, context)


def _handle_consent_event(event, gateway, context: dict[str, Any]) -> dict | None:
    """STOP/START handling. Returns a result dict when handled."""
    if not _consent_enabled(gateway.provider) or context.get("is_room"):
        return None
    sender_id = str(context.get("sender_id") or "")
    if not sender_id:
        return None
    if not _sender_is_known(gateway, sender_id):
        text = context.get("message_text")
        if _text_matches_keywords(
            gateway, text, "opt_out_keywords", DEFAULT_OPT_OUT_KEYWORDS
        ) and policy.has_received_template(gateway.name, sender_id):
            # We messaged this contact first (proactive template): their STOP must be honoured.
            _record_opt_out_linked(gateway, event, sender_id, str(context.get("display_name") or "") or None)
            reply = getattr(gateway, "opt_out_reply_text", None) or DEFAULT_OPT_OUT_REPLY
            _send_plain_reply(gateway, sender_id, str(context.get("conversation_id") or "") or sender_id, reply)
            return _reject_event(event, "Sender opted out (STOP) after a proactive template; no agent run")
        if _text_matches_keywords(gateway, text, "opt_out_keywords", DEFAULT_OPT_OUT_KEYWORDS) or _text_matches_keywords(
            gateway, text, "opt_in_keywords", DEFAULT_OPT_IN_KEYWORDS
        ):
            return _reject_event(event, "Sender is not admitted; consent keyword ignored")
        return None
    text = context.get("message_text")
    state = _sender_negative_state(gateway, sender_id)
    conversation_id = str(context.get("conversation_id") or "") or sender_id

    if state == ENTRY_STATE_OPTED_OUT:
        if _text_matches_keywords(gateway, text, "opt_in_keywords", DEFAULT_OPT_IN_KEYWORDS):
            _record_opt_in_linked(gateway, sender_id)
            _send_plain_reply(gateway, sender_id, conversation_id, DEFAULT_OPT_IN_REPLY)
            return _reject_event(event, "Sender opted back in (START); no agent run")
        return _reject_event(event, "Sender has opted out")

    if state in (ENTRY_STATE_BLOCKED, ENTRY_STATE_REVOKED):
        return None  # admission rejects these silently

    if _text_matches_keywords(gateway, text, "opt_out_keywords", DEFAULT_OPT_OUT_KEYWORDS):
        _record_opt_out_linked(gateway, event, sender_id, str(context.get("display_name") or "") or None)
        reply = getattr(gateway, "opt_out_reply_text", None) or DEFAULT_OPT_OUT_REPLY
        _send_plain_reply(gateway, sender_id, conversation_id, reply)
        return _reject_event(event, "Sender opted out (STOP); no agent run")
    return None


# -- per-sender inbound limit ---------------------------------------------------


def _sender_rate_limit_reason(gateway, context: dict[str, Any]) -> str:
    """Return a rejection reason when the sender exceeded the per-10-minute limit."""
    if not _consent_enabled(gateway.provider):
        return ""
    sender_id = str(context.get("sender_id") or "")
    limit = getattr(gateway, "inbound_sender_limit", None)
    limit = DEFAULT_INBOUND_SENDER_LIMIT if limit is None else int(limit)
    if not sender_id or limit <= 0:
        return ""
    bucket = int(time.time() // INBOUND_SENDER_WINDOW_SECONDS)
    count = _bump_counter(_counter_key("sender", gateway.name, sender_id, bucket), INBOUND_SENDER_WINDOW_SECONDS * 2)
    if count > limit:
        return f"sender_rate_limited: more than {limit} messages in 10 minutes from this sender"
    return ""


def _process_time_block_reason(gateway, event) -> str:
    """Re-check, at run time, that the sender is still allowed (revoked/blocked/opted out after queueing)."""
    sender_id = str(getattr(event, "sender_id", "") or "")
    state = _sender_negative_state(gateway, sender_id) if sender_id else None
    if state:
        return f"Sender is no longer admitted ({state})"
    return ""


# -- pairing --------------------------------------------------------------------


def _int_setting(gateway, fieldname: str, default: int) -> int:
    value = getattr(gateway, fieldname, None)
    try:
        return default if value in (None, "") else int(value)
    except (TypeError, ValueError):
        return default


def _pairing_cap_reason(gateway, sender_id: str) -> str:
    """Return why a NEW pairing request may not be created (``""`` when allowed).

    Caps: Pending requests per gateway, and pairing requests per sender per 24h
    (expired and revoked rows count, so a sender cannot churn new rows).
    """
    limit = _int_setting(gateway, "pairing_pending_limit", PAIRING_DEFAULT_PENDING_LIMIT)
    if limit > 0:
        pending = frappe.get_all(
            "Gateway Access Entry",
            filters={"gateway": gateway.name, "state": "Pending"},
            pluck="name",
            limit_page_length=limit,
        )
        if len(pending or []) >= limit:
            return "Pairing capacity reached for this gateway"
    external_id = _normalize_sender_for_provider(gateway.provider, "Sender", sender_id)
    recent = frappe.get_all(
        "Gateway Access Entry",
        filters={
            "gateway": gateway.name,
            "entry_type": "Sender",
            "external_id": external_id,
            "creation": [">", add_to_date(now_datetime(), hours=-24)],
        },
        pluck="name",
        limit_page_length=PAIRING_MAX_REQUESTS_PER_SENDER_PER_DAY,
    )
    if len(recent or []) >= PAIRING_MAX_REQUESTS_PER_SENDER_PER_DAY:
        return "Too many pairing requests from this sender"
    return ""


def _pairing_reply_budget_left(gateway) -> bool:
    """Count one pairing reply against the gateway's daily budget; False once it is spent."""
    limit = _int_setting(gateway, "pairing_reply_daily_limit", PAIRING_DEFAULT_REPLY_DAILY_LIMIT)
    if limit <= 0:
        return False
    day = int(time.time() // 86400)
    return _bump_counter(_counter_key("pairing_reply", gateway.name, day), 90000) <= limit


def _create_pairing_request(
    gateway, sender_id: str, conversation_id: str | None = None, display_name: str | None = None
) -> str:
    """Issue (or return) a live pairing request code (``PAIR-XXXXXXXX``).

    Returns ``""`` when no new code was issued because one was sent to this
    sender within the resend cooldown.
    """
    if not sender_id:
        return ""
    sender_id = _normalize_sender_for_provider(gateway.provider, "Sender", sender_id)
    now = now_datetime()
    existing = frappe.get_all(
        "Gateway Access Entry",
        filters={
            "gateway": gateway.name,
            "entry_type": "Sender",
            "provider": gateway.provider,
            "external_id": str(sender_id),
            "state": "Pending",
        },
        fields=["name", "pairing_code", "expires_at"],
        limit_page_length=0,
    )
    for row in existing or []:
        if row.get("expires_at") and row.get("expires_at") < now:
            _save_entry(row["name"], {"state": ENTRY_STATE_EXPIRED})
            continue
        return row.get("pairing_code") or ""

    recent = frappe.get_all(
        "Gateway Access Entry",
        filters={
            "gateway": gateway.name,
            "entry_type": "Sender",
            "provider": gateway.provider,
            "external_id": str(sender_id),
            "pairing_sent_at": [">", add_to_date(now, minutes=-PAIRING_RESEND_COOLDOWN_MINUTES)],
            # an expired code must never block issuing a fresh one
            "state": ["!=", ENTRY_STATE_EXPIRED],
        },
        pluck="name",
        limit_page_length=1,
    )
    if recent:
        return ""  # cooldown: at most one pairing message per sender per window

    if _pairing_cap_reason(gateway, sender_id):
        return ""

    pairing_code = _new_unique_pairing_code(gateway.name)
    # Replies to unknown numbers are opt-in (default OFF) and capped per day.
    reply_enabled = bool(getattr(gateway, "pairing_reply_enabled", 0)) and _pairing_reply_budget_left(gateway)
    ttl_minutes = int(gateway.pairing_ttl_minutes or 60)
    doc = frappe.get_doc(
        {
            "doctype": "Gateway Access Entry",
            "gateway": gateway.name,
            "entry_type": "Sender",
            "provider": gateway.provider,
            "external_id": str(sender_id),
            "pairing_code": pairing_code,
            "state": "Pending",
            "expires_at": add_to_date(now, minutes=ttl_minutes),
            "pairing_sent_at": now if (reply_enabled and getattr(gateway, "integration_settings", None)) else None,
            "display_label": display_name.strip() if display_name and display_name.strip() else f"Sender {sender_id}",
        }
    ).insert(ignore_permissions=True)

    if reply_enabled:
        try:
            if gateway.integration_settings:
                from huf.ai.gateway_adapters.types import GatewayReply

                if provider_hooks.get(gateway.provider, "adapter_context") is not None:
                    # Needs gateway_context so the adapter can apply the 24h
                    # window check and the fallback template (A7).
                    from huf.ai.gateway_webhook import get_gateway_adapter

                    adapter = get_gateway_adapter(gateway)
                else:
                    int_doc = frappe.get_doc("Integration Settings", gateway.integration_settings)
                    creds = {}
                    for row in getattr(int_doc, "credentials", []):
                        creds[row.key] = row.get_password("value") if hasattr(row, "get_password") else row.value

                    from huf.ai.gateway_webhook import _adapter_class_for_provider

                    adapter_cls = _adapter_class_for_provider(gateway.provider)
                    adapter = adapter_cls(creds)
                target_conv = conversation_id or sender_id
                reply_msg = (
                    f"🔒 Access approval required.\n\n"
                    f"Your pairing code is: `{pairing_code}`\n\n"
                    f"Please share this code with the bot administrator to get approved. "
                    f"It expires in {ttl_minutes} minutes."
                )
                adapter.send_reply(GatewayReply(conversation_id=target_conv, text=reply_msg))
        except _whatsapp_send_errors(gateway.provider) as exc:
            frappe.logger("huf").warning(
                f"Pairing code message not delivered (window closed or bridge error): {_whatsapp_error_text(exc)}"
            )
        except Exception as exc:
            frappe.logger("huf").warning(f"Failed to send pairing code message: {_redact_error_text(str(exc))}")

    return pairing_code


def _policy_admits(policy: str | None, gateway, entry_type: str, external_id: str) -> bool:
    """Evaluate one admission policy value against its matching access entry.

    ``Open`` admits unconditionally, ``Allow list`` requires an approved
    ``Gateway Access Entry``, and anything else (``Disabled``/unset) denies.
    """
    if policy == "Open":
        return True
    if policy == "Allow list":
        return _has_access_entry(gateway, entry_type, external_id)
    return False


def _mask_code(code: str) -> str:
    """Keep the live code off the event row: only the last two characters stay visible."""
    code = str(code or "")
    return "*" * max(len(code) - 2, 0) + code[-2:]


def _admission(gateway, context: dict[str, Any]) -> tuple[bool, str]:
    sender_id, conversation_id = str(context.get("sender_id") or ""), str(context.get("conversation_id") or "")
    is_room = bool(context.get("is_room"))
    if not is_room:
        policy = gateway.direct_policy or "Allow list"
        if policy == "Pairing":
            # Revoked/Blocked/Opted-out senders are never re-paired and get no reply.
            blocked = _sender_negative_state(gateway, sender_id)
            if blocked:
                return False, f"Sender is blocked ({blocked})"
            if _has_access_entry(gateway, "Sender", sender_id):
                return True, ""
            display_name = str(context.get("display_name") or "") or None
            code = _create_pairing_request(
                gateway, sender_id, conversation_id=conversation_id, display_name=display_name
            )
            if not code:
                capped = _pairing_cap_reason(gateway, sender_id)
                if capped:
                    return False, f"Sender pairing approval is required ({capped})"
                return False, "Sender pairing approval is required (pairing code was sent recently)"
            return False, f"Sender pairing approval is required. Pairing code: {_mask_code(code)}"
        return (policy == "Allow list" and _has_access_entry(gateway, "Sender", sender_id), "Sender is not approved for this gateway")

    room_ok = _policy_admits(gateway.room_policy, gateway, "Room", conversation_id)
    sender_ok = _policy_admits(gateway.room_sender_policy, gateway, "Sender", sender_id)
    mentioned = bool(context.get("mentioned"))
    if gateway.mention_required and not mentioned:
        return False, "Room messages must mention the gateway"
    return room_ok and sender_ok, "Room or sender is not approved for this gateway"


def _find_pending_entry_by_code(pairing_code: str, gateway: str) -> str | None:
    """Constant-time-compare a candidate code against the Pending entries of ONE gateway."""
    pending = frappe.get_all(
        "Gateway Access Entry",
        filters={"state": "Pending", "gateway": gateway},
        fields=["name", "pairing_code"],
    )
    matched = None
    for row in pending:
        # Compare every row (no early exit) so timing does not reveal position.
        if row.pairing_code and secrets.compare_digest(row.pairing_code, pairing_code):
            matched = row.name
    return matched


def _approval_failure_key() -> str:
    return _counter_key("pairing_fail", frappe.session.user, int(time.time() // 60))


def _approve_rate_gate() -> None:
    """Per-admin (not per-IP) bucket: admins behind one proxy must not share a budget."""


_approve_rate_limited = rate_limit(key="_approve_rl_user", limit=20, seconds=60, ip_based=False)(
    _approve_rate_gate
)


@frappe.whitelist(methods=["POST"])
def approve_gateway_pairing(code_or_entry_name: str, notes: str | None = None, gateway: str | None = None) -> dict:
    frappe.form_dict["_approve_rl_user"] = frappe.session.user
    try:
        _approve_rate_limited()
    except frappe.RateLimitExceededError:
        try:
            frappe.local.response_headers["Retry-After"] = "60"
        except Exception:
            pass
        raise
    return _approve_gateway_pairing(code_or_entry_name, notes, gateway)


def _approve_gateway_pairing(code_or_entry_name: str, notes: str | None = None, gateway: str | None = None) -> dict:
    """Approve a pending Gateway Access Entry by its ``PAIR-XXXXXXXX`` code or doc name.

    Admin-only (System Manager / Huf Admin / ``system.integrations.manage``).
    A code is looked up only among the Pending entries of ``gateway`` (required
    when approving by code), compared in constant time. More than 5 wrong
    attempts per admin per minute are refused.
    """
    _require_gateway_admin()
    if not code_or_entry_name or not str(code_or_entry_name).strip():
        frappe.throw(_("A pairing code or entry name is required."))

    failure_key = _approval_failure_key()
    if _read_counter(failure_key) >= PAIRING_APPROVAL_MAX_FAILURES_PER_MINUTE:
        frappe.throw(_("Too many failed pairing attempts. Wait a minute and try again."), frappe.TooManyRequestsError)

    raw = str(code_or_entry_name).strip()
    code = normalize_pairing_code(raw)
    entry_name = None
    if code:
        if not gateway:
            frappe.throw(_("A gateway is required to approve by pairing code."))
        entry_name = _find_pending_entry_by_code(code, gateway)
    if not entry_name and frappe.db.exists("Gateway Access Entry", raw):
        entry_name = raw
        if gateway and frappe.db.get_value("Gateway Access Entry", raw, "gateway") != gateway:
            entry_name = None

    if not entry_name:
        _bump_counter(failure_key, 120)
        frappe.throw(_("No pending pairing request found matching '{0}'.").format(code_or_entry_name))

    entry = frappe.get_doc("Gateway Access Entry", entry_name)
    if entry.state != "Pending" or (entry.expires_at and entry.expires_at < now_datetime()):
        frappe.throw(_("This pairing request is not active."))

    # expires_at held the pairing-request TTL, not an approval TTL. Leaving it
    # set means _has_access_entry's `expires_at >= now` filter makes this
    # newly-approved entry silently stop matching once that TTL elapses.
    updates = {
        "state": "Approved",
        "approved_by": frappe.session.user,
        "approved_at": now_datetime(),
        "expires_at": None,
    }
    if notes:
        updates["notes"] = notes
    _save_entry(entry, updates)

    notification_status = "Not attempted"
    try:
        from huf.ai.gateway_webhook import get_gateway_adapter
        from huf.ai.gateway_adapters.types import GatewayReply

        gw_doc = frappe.get_doc("Gateway", entry.gateway)
        if gw_doc.integration_settings:
            adapter = get_gateway_adapter(gw_doc)

            target_conv = entry.external_id
            target_thread = None
            recent_events = frappe.get_all(
                "Gateway Event",
                filters={"gateway": entry.gateway, "sender_id": entry.external_id},
                fields=["conversation_id", "thread_id"],
                order_by="creation desc",
                limit=1
            )
            if recent_events and recent_events[0].conversation_id:
                target_conv = recent_events[0].conversation_id
                target_thread = recent_events[0].thread_id

            welcome_text = (
                "🎉 Your access pairing request has been approved!\n\n"
                "You can now interact directly with this assistant."
            )
            adapter.send_reply(GatewayReply(
                conversation_id=target_conv,
                text=welcome_text,
                thread_id=target_thread or None,
                reply_to_provider_message_id=target_thread or None,
            ))
            notification_status = "Welcome message sent to sender"
    except _whatsapp_send_errors(entry.provider) as exc:
        # A7: never roll back the approval because the welcome could not be delivered.
        notification_status = f"Approval saved, welcome message not sent: {_whatsapp_error_text(exc)}"
        frappe.logger("huf").warning(notification_status)
    except Exception as exc:
        safe_exc = _redact_error_text(str(exc))
        notification_status = f"Approval saved, welcome message notice: {safe_exc}"
        frappe.log_error(
            "Failed to send welcome message on frontend approval",
            _redact_error_text(f"{exc}\n{frappe.get_traceback()}"),
        )

    return {
        "name": entry.name,
        "state": "Approved",
        "gateway": entry.gateway,
        "provider": entry.provider,
        "external_id": entry.external_id,
        "notification_status": notification_status,
    }


@frappe.whitelist(methods=["POST"])
def approve_gateway_access_entry(entry_name: str) -> dict:
    """Backward-compatible alias; approve_gateway_pairing is now canonical."""
    result = approve_gateway_pairing(entry_name)
    return {"name": result["name"], "state": result["state"]}


@frappe.whitelist(methods=["GET"])
def list_gateway_access_entries(gateway: str | None = None, state: str = "Pending") -> list[dict]:
    """List Gateway Access Entries, defaulting to the pending-approval queue.

    Admin-only. Pairing codes are masked: approve by entry name from this list,
    or by the full code the sender received.
    """
    _require_gateway_admin()
    filters: dict[str, Any] = {}
    if state:
        filters["state"] = state
    if gateway:
        filters["gateway"] = gateway
    rows = frappe.get_all(
        "Gateway Access Entry",
        filters=filters,
        fields=[
            "name", "gateway", "provider", "entry_type", "external_id", "pairing_code",
            "state", "expires_at", "display_label", "approved_by", "approved_at",
            "revoked_at", "revoked_by", "notes", "creation",
        ],
        order_by="creation desc",
        limit_page_length=0,
    )
    for row in rows:
        if row.get("pairing_code"):
            row["pairing_code"] = _mask_code(row["pairing_code"])
    return rows


@frappe.whitelist(methods=["POST"])
def revoke_gateway_access_entry(entry_name: str) -> dict:
    """Revoke an entry, pending or previously approved, denying it going forward.

    A revoked sender is blocked: it never gets a new pairing request or run.
    Revoke never weakens a negative consent state: ``Opted out`` and ``Blocked``
    entries keep their state (only ``revoked_at``/``revoked_by`` are recorded,
    and an opted-out sender who later sends START lands on ``Revoked``).
    """
    _require_gateway_admin()
    entry = frappe.get_doc("Gateway Access Entry", entry_name)
    updates: dict[str, Any] = {"revoked_at": now_datetime(), "revoked_by": frappe.session.user}
    if entry.state == ENTRY_STATE_OPTED_OUT:
        updates["previous_state"] = ENTRY_STATE_REVOKED
    elif entry.state != ENTRY_STATE_BLOCKED:
        updates["state"] = ENTRY_STATE_REVOKED
    _save_entry(entry, updates)
    return {"name": entry.name, "state": entry.state}


def cleanup_stale_access_entries() -> dict:
    """Daily job: mark expired Pending entries Expired, delete Expired ones after 7 days."""
    now = now_datetime()
    expired = frappe.get_all(
        "Gateway Access Entry",
        filters={"state": "Pending", "expires_at": ["<", now]},
        pluck="name",
        limit_page_length=0,
    )
    for name in expired:
        _save_entry(name, {"state": ENTRY_STATE_EXPIRED})
    stale = frappe.get_all(
        "Gateway Access Entry",
        filters={
            "state": ENTRY_STATE_EXPIRED,
            "modified": ["<", add_to_date(now, days=-PENDING_ENTRY_RETENTION_DAYS)],
        },
        pluck="name",
        limit_page_length=0,
    )
    for name in stale:
        frappe.delete_doc("Gateway Access Entry", name, ignore_permissions=True, force=True)
    return {"expired": len(expired), "deleted": len(stale)}


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


# Small Text is a 64 KB column; cap well below it (utf8mb4 is up to 4 bytes/char) so an oversized
# body never makes the Gateway Event insert fail. The full text is not kept.
MESSAGE_TEXT_MAX_CHARS = 16000
_CONVERSATION_RACE_ATTEMPTS = 4
_CONVERSATION_RACE_BACKOFF = 0.2


def _cap_message_text(value: Any) -> str:
    text = str(value or "")
    if len(text) <= MESSAGE_TEXT_MAX_CHARS:
        return text
    return text[:MESSAGE_TEXT_MAX_CHARS] + "\n[truncated]"


def _conversation_race_errors() -> tuple[type, ...]:
    return (frappe.QueryDeadlockError, frappe.TimestampMismatchError)


BUSY_CONVERSATION_MARKER = "currently executing another run"
_BUSY_ATTEMPTS = 6
_BUSY_BASE_DELAY = 2.0
_BUSY_MAX_DELAY = 20.0
_CONVERSATION_LOCK_WAIT = 90
_CONVERSATION_LOCK_TTL = 330
_REQUEUE_MAX = 25
_PROCESS_JOB_TIMEOUT = 300
_REQUEUE_TTL = 7200


class ConversationBusy(Exception):
    """The sender's conversation stayed busy for the whole retry budget; the event is re-queued."""


def _is_busy_conversation_error(exc: BaseException) -> bool:
    return isinstance(exc, frappe.ValidationError) and BUSY_CONVERSATION_MARKER in str(exc)


def _busy_delay(attempt: int) -> float:
    return min(_BUSY_BASE_DELAY * (2 ** (attempt - 1)), _BUSY_MAX_DELAY) * random.uniform(0.75, 1.25)


def _run_agent_serialised(run_fn, *, lock_key: str, **kwargs):
    """Run one event's agent turn while holding a per-conversation lock, so messages from the same
    sender are processed one after another. Waiting too long raises :class:`ConversationBusy`."""
    try:
        lock = frappe.cache.lock(lock_key, timeout=_CONVERSATION_LOCK_TTL, blocking_timeout=_CONVERSATION_LOCK_WAIT)
        acquired = lock.acquire()
    except Exception:
        # No lock backend: fall back to the busy-conversation retry alone.
        return _run_agent_with_retry(run_fn, **kwargs)
    if not acquired:
        raise ConversationBusy(f"Conversation {lock_key} is busy")
    try:
        return _run_agent_with_retry(run_fn, **kwargs)
    finally:
        try:
            lock.release()
        except Exception:
            pass


def _requeue_busy_event(event, error: str) -> dict:
    """Leave the event Queued for another worker pass; fail it only after a bounded number of requeues."""
    key = f"huf_gw_requeue:{event.name}"
    count = int(frappe.cache.get_value(key) or 0) + 1
    frappe.db.rollback()
    if count > _REQUEUE_MAX:
        event.db_set({"status": "Failed", "error_message": f"Conversation stayed busy: {error}"[-500:]})
        _commit_unless_testing()
        try:
            _send_fallback_once(event, frappe.get_doc("Gateway", event.gateway), "error")
            _commit_unless_testing()
        except Exception:
            frappe.logger("huf").warning("Busy fallback reply skipped")
        return {"event_name": event.name, "status": "Failed", "error": "conversation_busy"}
    frappe.cache.set_value(key, count, expires_in_sec=_REQUEUE_TTL)
    event.db_set({"status": "Queued", "error_message": f"Conversation busy; retry {count}/{_REQUEUE_MAX}"})
    _commit_unless_testing()
    frappe.enqueue(
        "huf.ai.gateway_service.process_gateway_event",
        queue="default",
        timeout=_PROCESS_JOB_TIMEOUT,
        event_name=event.name,
        enqueue_after_commit=True,
    )
    return {"event_name": event.name, "status": "Queued", "requeued": count}


def _run_agent_with_retry(run_fn, **kwargs):
    """Run the agent, retrying with backoff when concurrent same-sender events collide on the
    conversation row (deadlock / timestamp mismatch) or the conversation is busy with another run,
    instead of terminally failing the event. The idempotency key keeps a retry from duplicating a run."""
    import time

    busy_attempts = 0
    attempt = 0
    while True:
        attempt += 1
        try:
            result = run_fn(**kwargs)
            if attempt > 1 and isinstance(result, dict) and (
                result.get("queued") or result.get("status") in ("Queued", "Started")
            ):
                # The earlier attempt already created the Agent Run (deduped by idempotency key) and
                # it is still in flight: never execute it a second time.
                raise RuntimeError(
                    f"Agent run {result.get('agent_run_id')} is still in progress after a conversation conflict"
                )
            return result
        except _conversation_race_errors():
            if attempt >= _CONVERSATION_RACE_ATTEMPTS:
                raise
            frappe.db.rollback()
            time.sleep(_CONVERSATION_RACE_BACKOFF * attempt)
        except frappe.ValidationError as exc:
            if not _is_busy_conversation_error(exc):
                raise
            busy_attempts += 1
            if busy_attempts >= _BUSY_ATTEMPTS:
                raise ConversationBusy(str(exc)) from exc
            frappe.db.rollback()
            time.sleep(_busy_delay(busy_attempts))


UNSUPPORTED_REPLY = (
    "Sorry, I can't read this type of message. Please send text, a photo, a document, audio or a location."
)
_SILENT_UNSUPPORTED_CODES = (131060,)
_RECORD_ONLY_KINDS = ("edit", "revoke", "system", "unknown")


def _record_event(event, reason: str, **extra) -> dict:
    """Mark an event Recorded (kept for audit, never routed or run) and log why."""
    event.db_set({"status": "Recorded", "error_message": reason})
    frappe.logger("huf").info(f"Gateway event {event.name} recorded: {reason}")
    return {"event_name": event.name, "status": "Recorded", **extra}


def _mark_original_event(gateway_name: str, context: dict[str, Any], kind: str, new_event_id: str) -> None:
    """edit -> original superseded; revoke -> original revoked (a not-yet-run Queued run is neutralised).

    Only the original's own sender can touch it; anything else is ignored.
    """
    original_id = str(context.get("original_message_id") or "")
    if not original_id:
        return
    row = frappe.db.get_value(
        "Gateway Event",
        {"idempotency_key": _idempotency_key(gateway_name, original_id)},
        ["name", "status", "sender_id", "raw_payload"],
        as_dict=True,
    )
    if not row or str(row.get("sender_id") or "") != str(context.get("sender_id") or ""):
        return
    raw = row.get("raw_payload")
    if isinstance(raw, (str, bytes)):
        try:
            raw = json.loads(raw)
        except ValueError:
            raw = {}
    raw = dict(raw) if isinstance(raw, dict) else {}
    values: dict[str, Any] = {}
    if kind == "revoke":
        raw["revoked"] = True
        values["message_text"] = "[deleted by sender]"
        if row.get("status") in ("Received", "Queued"):
            values["status"] = "Rejected"
            values["error_message"] = "revoked_by_sender: deleted before it was processed; no run"
    else:
        raw["superseded_by"] = new_event_id
    values["raw_payload"] = json.dumps(raw)
    frappe.db.set_value("Gateway Event", row["name"], values)


def _handle_record_only(event, gateway_name: str, context: dict[str, Any], kind: str, provider_event_id: str) -> dict:
    if kind in ("edit", "revoke"):
        _mark_original_event(gateway_name, context, kind, provider_event_id)
    return _record_event(event, f"{kind}_recorded: no run")


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
            "message_text": _cap_message_text(context.get("message_text")),
            "raw_payload": _redact_payload(raw_payload or {}),
        }
    )
    try:
        event.insert(ignore_permissions=True)
    except (frappe.DuplicateEntryError, frappe.UniqueValidationError):
        # A unique-index race surfaces as UniqueValidationError (DuplicateEntryError's sibling).
        existing = frappe.db.get_value("Gateway Event", {"idempotency_key": key}, "name")
        return {"duplicate": True, "event_name": existing}

    return _continue_ingest(event, gateway_name, provider_event_id, context, verified_sender)


def _continue_ingest(
    event, gateway_name: str, provider_event_id: str, context: dict[str, Any], verified_sender: bool
) -> dict:
    """Everything after the event row exists: reject, record-only, admission, routing, enqueue.

    Split out so the reaper and the dead-letter replay can resume an event that was inserted but
    never routed, with exactly the same rules as a fresh delivery.
    """
    if not verified_sender:
        event.db_set({"status": "Rejected", "error_message": "Provider did not verify sender"})
        return {"event_name": event.name, "status": "Rejected"}

    kind = str(context.get("kind") or "message")
    if kind == "reaction":
        # Short-circuit: no consent, pairing, admission, rate bucket or run for a reaction.
        return _record_event(event, REACTION_RECORDED_NOTE, reaction=True)
    if kind in _RECORD_ONLY_KINDS:
        # edit/revoke/system/unknown never reach an agent or LLM; edit/revoke only mark the original.
        return _handle_record_only(event, gateway_name, context, kind, provider_event_id)

    gateway = frappe.get_doc("Gateway", gateway_name)
    if not gateway.is_enabled:
        event.db_set({"status": "Rejected", "error_message": "Gateway is disabled"})
        return {"event_name": event.name, "status": "Rejected"}
    # Rate limit first so a STOP/START or pairing flood cannot bypass the per-sender bucket.
    limited = _sender_rate_limit_reason(gateway, context)
    if limited:
        return _reject_event(event, limited)
    consent = _handle_consent_event(event, gateway, context)
    if consent is not None:
        return consent
    admitted, reason = _admission(gateway, context)
    if not admitted:
        event.db_set({"status": "Rejected", "error_message": reason})
        return {"event_name": event.name, "status": "Rejected"}
    if kind == "unsupported":
        # Fixed reply (or silence for the expected 131060), never an LLM turn.
        codes = {str(c) for c in (context.get("provider_error_codes") or [])}
        if not codes & {str(c) for c in _SILENT_UNSUPPORTED_CODES}:
            _send_plain_reply(
                gateway,
                str(context.get("sender_id") or ""),
                str(context.get("conversation_id") or "") or None,
                UNSUPPORTED_REPLY,
            )
        return _record_event(event, "unsupported_recorded: fixed reply, no run")

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


def _commit_unless_testing() -> None:
    """Make state durable for the worker; skipped under the test runner so test rollback still cleans up."""
    if not frappe.flags.in_test:
        frappe.db.commit()


STUCK_RUNNING_MINUTES = 15
_TERMINAL_STATES = ("Succeeded", "Failed")

# Reaper v2 (WP-5). Every recovery attempt is persisted on the event (``recovery_attempts``) with a
# ``retry_deadline`` set at the first attempt, so the budget survives cache flushes and restarts.
QUEUED_STUCK_MINUTES = 10  # Queued, enqueue lost (worker killed / job dropped)
RECEIVED_STUCK_MINUTES = 5  # inserted but never routed (crash between insert and route)
RETRYING_STUCK_MINUTES = 10  # reply_status 'retrying' whose retry job is gone
RECOVERY_MAX_ATTEMPTS = 3
RECOVERY_DEADLINE_MINUTES = 60
DEAD_LETTER_PREFIX = "dead_letter:"
# Callables ``hook(event_name, reason)`` run (best effort) when an event ends Failed because
# recovery gave up or a worker died. The failure/fallback path (WP-4b) registers the sender notice here.
REAP_FAILURE_HOOKS: list = []


def fail_event_after_budget(event_name: str, reason: str) -> dict:
    """End an event Failed with ``reason`` and flag it for a sender notice (hooks never raise)."""
    frappe.db.set_value("Gateway Event", event_name, {"status": "Failed", "error_message": reason[:500]})
    for hook in list(REAP_FAILURE_HOOKS):
        try:
            hook(event_name, reason)
        except Exception:
            frappe.log_error(frappe.get_traceback(), "Gateway reaper failure hook failed")
    return {"event_name": event_name, "status": "Failed", "notify_sender": True, "reason": reason}


RECOVERY_RACED = "raced"  # another worker already recovered this event; do nothing


def _spend_recovery_attempt(row: dict, now) -> str | None:
    """Persist one more recovery attempt under a row lock.

    Returns a failure reason when the budget is spent, ``RECOVERY_RACED`` when another worker already
    handled the event since ``row`` was listed, else None.
    """
    fresh = frappe.db.get_value(
        "Gateway Event",
        row["name"],
        ["status", "modified", "recovery_attempts", "retry_deadline"],
        as_dict=True,
        for_update=True,
    )
    if not fresh or fresh.get("status") != row.get("status") or fresh.get("modified") != row.get("modified"):
        return RECOVERY_RACED
    attempts = int(fresh.get("recovery_attempts") or 0)
    deadline = fresh.get("retry_deadline")
    if attempts >= RECOVERY_MAX_ATTEMPTS:
        return f"Recovery gave up after {attempts} attempts; the event was never completed."
    if deadline and now > deadline:
        return "Recovery deadline passed before the event completed."
    values = {"recovery_attempts": attempts + 1}
    if not deadline:
        values["retry_deadline"] = add_to_date(now, minutes=RECOVERY_DEADLINE_MINUTES)
    frappe.db.set_value("Gateway Event", row["name"], values)
    return None


_RECOVERY_FIELDS = [
    "name", "status", "modified", "received_at", "reply_status", "reply_message_id",
    "agent_run", "recovery_attempts", "retry_deadline", "gateway",
]  # fmt: skip


def _reply_parts_for_run(agent_run: str, provider: str | None = None) -> list[str]:
    """Rebuild the reply parts from the finished Agent Run (empty when it cannot be recovered)."""
    if not agent_run:
        return []
    if provider_hooks.get(provider, "recover_reply_parts") is None:
        return []
    response = frappe.db.get_value("Agent Run", agent_run, "response")
    if not response:
        return []
    return provider_hooks.call(provider, "recover_reply_parts", response)


def _recover_orphaned_events(limit: int = 50) -> int:
    """Recover Queued / Received orphans and 'retrying' replies whose job is gone (bounded)."""
    now = now_datetime()
    recovered = 0

    def fetch(filters):
        return frappe.get_all(
            "Gateway Event", filters=filters, fields=_RECOVERY_FIELDS, limit_page_length=limit
        )

    queued = fetch({"status": "Queued", "modified": ["<", add_to_date(now, minutes=-QUEUED_STUCK_MINUTES)]})
    received = fetch(
        {"status": "Received", "modified": ["<", add_to_date(now, minutes=-RECEIVED_STUCK_MINUTES)]}
    )
    retrying = fetch(
        {
            "status": "Running",
            "reply_status": "retrying",
            "modified": ["<", add_to_date(now, minutes=-RETRYING_STUCK_MINUTES)],
        }
    )
    for row in queued + received + retrying:
        try:
            reason = _spend_recovery_attempt(row, now)
            if reason == RECOVERY_RACED:
                continue
            if reason:
                fail_event_after_budget(row["name"], f"{row['status']} orphan: {reason}")
            elif row["status"] == "Queued":
                frappe.enqueue(
                    "huf.ai.gateway_service.process_gateway_event",
                    queue="default",
                    timeout=300,
                    event_name=row["name"],
                    enqueue_after_commit=True,
                )
            elif row["status"] == "Received":
                try:
                    _replay_event_ingest(row["name"])
                except Exception as exc:
                    _mark_dead_letter(row["name"], exc)
            else:
                _recover_retrying_reply(row)
            recovered += 1
        except Exception:
            frappe.log_error(frappe.get_traceback(), "Gateway orphan recovery failed")
    return recovered


def _recover_retrying_reply(row: dict) -> None:
    attempts = int(row.get("recovery_attempts") or 0) + 1  # already spent above
    provider = frappe.db.get_value("Gateway", row.get("gateway"), "provider") if row.get("gateway") else None
    parts = [] if row.get("reply_message_id") else _reply_parts_for_run(row.get("agent_run") or "", provider)
    if not parts:
        fail_event_after_budget(
            row["name"],
            "Reply retry lost: the retry job is gone and the unsent part of the reply cannot be rebuilt.",
        )
        return
    frappe.enqueue(
        "huf.ai.gateway_service.retry_gateway_reply",
        queue="default",
        timeout=300,
        enqueue_after_commit=True,
        event_name=row["name"],
        parts_remaining=parts,
        attempt=1 + attempts,
        not_before=0,
    )


_FLOW_RUN_TERMINAL = ("Success", "Failed")
REAPED_PREFIX = "Stuck in Running for over"


def _flow_run_is_active(event_name: str) -> bool:
    """A Flow-routed event whose run is not finished (running, queued or parked on a human) is not stuck."""
    run = frappe.db.get_value("Gateway Event", event_name, "flow_run")
    if not run:
        return False
    status = frappe.db.get_value("Flow Run", run, "status")
    return bool(status) and status not in _FLOW_RUN_TERMINAL


def _reap_one_stuck(name: str, cutoff, minutes: int) -> bool:
    """Fail one stuck event under its row lock, unless it moved on since it was listed."""
    fresh = frappe.db.get_value(
        "Gateway Event", name, ["status", "modified", "reply_status"], as_dict=True, for_update=True
    )
    if (
        not fresh
        or fresh.get("status") not in _REAPABLE_STATUSES
        or fresh.get("reply_status") == "retrying"
        or not fresh.get("modified")
        or fresh["modified"] >= cutoff
        or _flow_run_is_active(name)
    ):
        return False
    fail_event_after_budget(
        name,
        f"{REAPED_PREFIX} {minutes} minutes; the worker finished or died without recording a result.",
    )
    return True


_REAPABLE_STATUSES = ("Running", "Replying")


def reap_stuck_gateway_events(minutes: int = STUCK_RUNNING_MINUTES, limit: int = 50) -> int:
    """Recover or fail events a worker lost: stuck Running, orphaned Queued/Received, dead 'retrying' replies."""
    try:
        cutoff = add_to_date(now_datetime(), minutes=-minutes)
        stuck = frappe.get_all(
            "Gateway Event",
            filters={
                "status": ["in", list(_REAPABLE_STATUSES)],
                "modified": ["<", cutoff],
                # a pending send-only reply retry is handled by the retrying recovery below
                "reply_status": ["!=", "retrying"],
            },
            pluck="name",
            limit_page_length=limit,
        )
        count = sum(1 for name in stuck if _reap_one_stuck(name, cutoff, minutes))
        count += _recover_orphaned_events(limit)
        if count:
            _commit_unless_testing()
        return count
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Gateway stuck-event reaper failed")
        return 0


# -- ingest dead letters --------------------------------------------------------


def _mark_dead_letter(event_name: str, error: BaseException | str) -> None:
    text = _redact_error_text(str(error))[:400]
    frappe.db.set_value(
        "Gateway Event",
        event_name,
        {"status": "Failed", "error_message": f"{DEAD_LETTER_PREFIX} ingest failed: {text}"},
    )


def store_ingest_dead_letter(
    gateway_name: str,
    provider_event_id: str,
    context: dict[str, Any],
    raw_payload: dict[str, Any] | None,
    error: BaseException | str,
) -> str:
    """Keep a deterministically failing delivery as a Failed Gateway Event (dead letter).

    The row carries the redacted raw payload plus the ingest context so ``retry_gateway_event`` can
    replay it, and uses the normal idempotency key so a provider redelivery or a replay can never
    create a second event.
    """
    key = _idempotency_key(gateway_name, provider_event_id)
    reason = f"{DEAD_LETTER_PREFIX} ingest failed: {_redact_error_text(str(error))[:400]}"
    existing = frappe.db.get_value("Gateway Event", {"idempotency_key": key}, ["name", "status"], as_dict=True)
    if existing:
        if existing.get("status") in ("Received", "Failed"):
            frappe.db.set_value("Gateway Event", existing["name"], {"status": "Failed", "error_message": reason})
        return existing["name"]
    payload = _redact_payload(raw_payload or {})
    payload = dict(payload) if isinstance(payload, dict) else {"payload": payload}
    payload["_replay_context"] = _redact_payload(dict(context or {}))
    doc = frappe.get_doc(
        {
            "doctype": "Gateway Event",
            "gateway": gateway_name,
            "idempotency_key": key,
            "provider_event_id": provider_event_id,
            "status": "Failed",
            "received_at": now_datetime(),
            "verified_sender": 1,
            "sender_id": str((context or {}).get("sender_id") or ""),
            "conversation_id": str((context or {}).get("conversation_id") or ""),
            "thread_id": str((context or {}).get("thread_id") or ""),
            "message_text": _cap_message_text((context or {}).get("message_text")),
            "raw_payload": payload,
            "error_message": reason,
        }
    )
    doc.insert(ignore_permissions=True)
    return doc.name


def _replay_context(event) -> dict[str, Any]:
    raw = event.raw_payload
    if isinstance(raw, (str, bytes)):
        try:
            raw = json.loads(raw)
        except ValueError:
            raw = {}
    saved = raw.get("_replay_context") if isinstance(raw, dict) else None
    if isinstance(saved, dict):
        return saved
    return {
        "kind": "message",
        "sender_id": event.sender_id or "",
        "conversation_id": event.conversation_id or "",
        "thread_id": event.thread_id or "",
        "message_text": event.message_text or "",
    }


def _replay_event_ingest(event_name: str) -> dict:
    """Resume ingest for an existing event row (same idempotency key, same rules as a fresh delivery)."""
    event = frappe.get_doc("Gateway Event", event_name)
    return _continue_ingest(
        event,
        event.gateway,
        event.provider_event_id or "",
        _replay_context(event),
        bool(event.verified_sender),
    )


@frappe.whitelist(methods=["POST"])
def retry_gateway_event(name: str) -> dict:
    """Admin action: replay an ingest dead letter. Idempotent; only dead letters, only once they are Failed."""
    _require_gateway_admin()
    row = frappe.db.get_value(
        "Gateway Event", name, ["name", "status", "error_message"], as_dict=True, for_update=True
    )
    if not row:
        raise frappe.DoesNotExistError(_("Gateway Event {0} not found").format(name))
    is_dead = row.get("status") == "Failed" and str(row.get("error_message") or "").startswith(
        DEAD_LETTER_PREFIX
    )
    if not is_dead:
        if row.get("status") == "Failed":
            frappe.throw(_("Only ingest dead letters can be replayed."))
        return {"event_name": name, "replayed": False, "status": row.get("status")}
    previous_error = row["error_message"]
    frappe.db.savepoint("gw_replay")
    frappe.db.set_value("Gateway Event", name, {"status": "Received", "error_message": ""})
    try:
        result = _replay_event_ingest(name)
    except Exception as exc:
        frappe.db.rollback(save_point="gw_replay")
        frappe.db.set_value("Gateway Event", name, {"status": "Failed", "error_message": previous_error})
        frappe.log_error(frappe.get_traceback(), "Gateway dead-letter replay failed")
        return {"event_name": name, "replayed": False, "status": "Failed", "error": _redact_error_text(str(exc))[:300]}
    _commit_unless_testing()
    return {"event_name": name, "replayed": True, "status": result.get("status")}


def _persist_terminal_state(event_name: str, result: Any) -> None:
    """Commit, then verify a terminal result really reached the database; repair and log if not."""
    _commit_unless_testing()
    if not isinstance(result, dict) or result.get("status") not in _TERMINAL_STATES:
        return
    expected = {"status": result["status"]}
    if result.get("agent_run_id"):
        expected["agent_run"] = result["agent_run_id"]
    actual = frappe.db.get_value("Gateway Event", event_name, list(expected), as_dict=True) or {}
    if all(actual.get(k) == v for k, v in expected.items()):
        return
    frappe.log_error(
        f"Terminal write for {event_name} was lost (expected {expected}, found {dict(actual)}); repairing",
        "Gateway event terminal write lost",
    )
    frappe.db.set_value("Gateway Event", event_name, expected)
    _commit_unless_testing()


def _flow_trigger_payload(event, gateway, attachments: list[str]) -> dict:
    """What a Flow gets for a gateway message: who, where, what, media and reply context."""
    try:
        raw = event.raw_payload
        raw = json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        raw = None
    message = raw.get("message") if isinstance(raw, dict) and isinstance(raw.get("message"), dict) else {}
    msg_type = str(message.get("type") or "text")
    context = message.get("context") if isinstance(message.get("context"), dict) else {}
    interactive = message.get("interactive") if isinstance(message.get("interactive"), dict) else {}
    reply = interactive.get("button_reply") or interactive.get("list_reply") or {}
    sender = str(event.sender_id or "")
    payload = {
        "gateway_event": event.name,
        "gateway": gateway.name,
        "provider": gateway.provider,
        "sender_id": sender,
        "wa_id": "",
        "conversation_id": event.conversation_id,
        "thread_id": event.thread_id,
        "message_id": event.provider_event_id,
        "message": event.message_text,
        "text": event.message_text,
        "message_type": msg_type,
        "attachments": list(attachments),
        "reply_to_message_id": str(context.get("id") or "") or None,
        "interactive_reply": {"id": reply.get("id"), "title": reply.get("title")} if reply else None,
    }
    extra = provider_hooks.get(gateway.provider, "extra_event_fields")
    if extra is not None:
        payload.update(extra(event, gateway, sender) or {})
    return payload


def _start_flow_for_event(event, gateway) -> dict:
    """Start the routed Flow once per event; a re-queued or redelivered event never starts a second run."""
    from huf.ai.flow_engine import create_flow_run

    existing = frappe.db.get_value("Gateway Event", event.name, "flow_run", for_update=True)
    if existing:
        event.db_set("status", "Running")
        return {"event_name": event.name, "status": "Running", "flow_run_id": existing}
    attachments = _save_event_media(event, gateway)
    # Route authorisation already happened (enabled gateway, flow bound by an admin), so the run is
    # created on the gateway's behalf: the execution user needs no Huf User role.
    flow_run = create_flow_run(
        flow_id=event.target_flow,
        payload=_flow_trigger_payload(event, gateway, attachments),
        trigger_type="Gateway",
        ignore_permissions=True,
    )
    event.db_set({"flow_run": flow_run.name, "status": "Running"})
    frappe.enqueue(
        "huf.ai.flow_engine.run_flow",
        queue="default",
        timeout=300,
        flow_run_name=flow_run.name,
        enqueue_after_commit=True,
    )
    return {"event_name": event.name, "status": "Running", "flow_run_id": flow_run.name}


def finish_flow_event(flow_run_name: str, status: str, reply_text: str | None = None, error: str = "") -> None:
    """Flow Run -> Gateway Event: deliver the Flow's reply through the normal pipeline and sync the status.

    Idempotent: a terminal event is left alone, so a replayed completion never sends twice. Never raises.
    """
    try:
        event_name = frappe.db.get_value("Gateway Event", {"flow_run": flow_run_name}, "name")
        if not event_name:
            return
        locked = frappe.db.get_value(
            "Gateway Event", event_name, ["status", "error_message"], as_dict=True, for_update=True
        )
        current = (locked or {}).get("status")
        reaped = current == "Failed" and str((locked or {}).get("error_message") or "").startswith(REAPED_PREFIX)
        if not locked or current in ("Succeeded", "Rejected", "Replying") or (current == "Failed" and not reaped):
            return
        event = frappe.get_doc("Gateway Event", event_name)
        if status != "Success":
            event.db_set({"status": "Failed", "error_message": _redact_error_text(error or "Flow failed")[-500:]})
            return
        # Compare-and-set (row is locked): exactly one completion claims the reply, then sends.
        event.db_set({"status": "Replying", "error_message": ""})
        _commit_unless_testing()
        gateway = frappe.get_doc("Gateway", event.gateway)
        text = (reply_text or "").strip()
        if not text or _is_no_reply(text):
            event.db_set({"status": "Succeeded", **({"reply_status": "suppressed"} if text else {})})
            return
        send_hook = provider_hooks.get(gateway.provider, "send_reply")
        if send_hook is not None:
            send_hook(event, gateway, None, text)
            return
        from huf.ai.gateway_webhook import send_gateway_reply

        delivery = send_gateway_reply(gateway, event, text)
        _record_reply_sent(event, delivery.provider_message_id)
        event.db_set("status", "Succeeded")
    except Exception:
        message = _redact_error_text(frappe.get_traceback())
        frappe.log_error(message, "Gateway flow completion failed")
        try:
            frappe.db.set_value("Gateway Event", {"flow_run": flow_run_name}, {"status": "Failed", "error_message": message[-500:]})
        except Exception:
            pass


def process_gateway_event(event_name: str) -> dict:
    """Run one queued event, then make sure its terminal state is committed and verified."""
    reap_stuck_gateway_events()
    result = _process_gateway_event(event_name)
    _persist_terminal_state(event_name, result)
    return result


def _process_gateway_event(event_name: str) -> dict:
    """Start queued Huf work under the Gateway's configured service user."""
    event = frappe.get_doc("Gateway Event", event_name)
    if event.status != "Queued":
        return {"event_name": event.name, "status": event.status}

    if _is_reaction_event(event):
        # A reaction is recorded on the event only: no admission side effects, no agent run, no reply.
        event.db_set({"status": "Rejected", "error_message": REACTION_RECORDED_NOTE})
        return {"event_name": event.name, "status": "Rejected", "reaction": True}

    gateway = frappe.get_doc("Gateway", event.gateway)
    if not gateway.is_enabled or not gateway.execution_user:
        event.db_set({"status": "Rejected", "error_message": "Gateway is disabled or has no Run as user"})
        return {"event_name": event.name, "status": "Rejected"}

    blocked_reason = _process_time_block_reason(gateway, event)
    if blocked_reason:
        return _reject_event(event, blocked_reason)

    if event.target_type == "Agent":
        # GW-08: this pre-gate authorizes the run as the Gateway's configured
        # execution_user, NOT as Guest.
        #
        # It used to call assert_agent_access(agent_doc, user="Guest"), which
        # short-circuits on `allow_guest` alone (agent_access.check_agent_access).
        # That made Agent.allow_guest=1 the only way to put any Agent behind any
        # Gateway -- and because `Agent.allow_guest` is also the sole gate on the
        # unauthenticated `run_agent_sync` / `run_agent_sync_chat` endpoints, the
        # only way to enable a Telegram/WhatsApp integration was to simultaneously
        # expose that Agent to anonymous callers over the public REST API. The
        # gateway sender is anonymous, but the *authorization* for the run has
        # never come from the sender: it comes from execution_user, which an admin
        # configures on the Gateway and which Gateway.validate already constrains
        # (allowed role + check_agent_access against default_agent, ST-04.4).
        # Authorizing as Guest was therefore both weaker than intended and
        # coupled to an unrelated, larger exposure.
        #
        # This is defence in depth and a clean rejection surface (the Gateway
        # Event records why it was refused). The load-bearing check is the one
        # inside run_agent_sync, which runs under the same execution_user after
        # frappe.set_user() below and additionally requires the `agent.use`
        # capability.
        #
        # GW-11: this pre-gate is now routed through the shared
        # resolve_run_identity_and_authorize() helper alongside the other 3
        # "run an agent" trigger surfaces, but keeps its own rejection
        # reporting shape (a Gateway Event status/error_message, not a raised
        # exception) -- see agent_access.RunIdentityResult's docstring.
        from huf.ai.agent_access import TRIGGER_GATEWAY, resolve_run_identity_and_authorize

        agent_doc = frappe.get_doc("Agent", event.target_agent)
        identity = resolve_run_identity_and_authorize(
            agent_doc,
            TRIGGER_GATEWAY,
            {"execution_user": gateway.execution_user, "target_agent": event.target_agent},
        )
        if not identity.authorized:
            event.db_set({"status": "Rejected", "error_message": identity.reason})
            return {"event_name": event.name, "status": "Rejected"}

    try:
        frappe.set_user(gateway.execution_user)
        event.db_set("status", "Running")
        if event.target_type == "Agent":
            from huf.ai.agent_integration import run_agent_sync
            from huf.ai.gateway_webhook import send_gateway_reply

            attachment_note = _describe_attachments(event.raw_payload)
            saved_files = _save_event_media(event, gateway)
            if saved_files:
                attachment_note = "\n".join(
                    [attachment_note] * bool(attachment_note)
                    + [f"[Attachment saved: {file_url}]" for file_url in saved_files]
                )
            kind_hook = provider_hooks.get(gateway.provider, "inbound_kind")
            media_type = kind_hook(event) if kind_hook is not None else None
            # The agent is the only responder for an unsaved attachment; the standalone note is sent
            # only if the run fails or yields no reply.
            attachment_unavailable = bool(media_type and not saved_files)
            fallback_kind = "attachment" if attachment_unavailable else "error"
            if attachment_unavailable:
                attachment_note = "\n".join([attachment_note] * bool(attachment_note) + [ATTACHMENT_UNAVAILABLE_NOTE])
            media_files: list = []
            media_prep_result = None
            if saved_files:
                from huf.ai import media_prep

                media_prep_result = media_prep.prepare_media_for_agent(
                    media_prep.resolve_event_files(event.name, saved_files), event.target_agent
                )
                media_files = media_prep_result.files
            if media_prep_result:
                prompt = media_prep.build_prompt(attachment_note, event.message_text, media_prep_result)
            else:
                prompt = f"{attachment_note}\n{event.message_text}" if attachment_note else event.message_text

            instructions_hook = provider_hooks.get(gateway.provider, "agent_instructions")
            if instructions_hook is not None:
                channel_note = _call_instructions_hook(instructions_hook, gateway)
                context_hook = provider_hooks.get(gateway.provider, "agent_event_context")
                if context_hook is not None:
                    try:
                        event_note = context_hook(event, gateway)
                    except Exception as exc:
                        event_note = None
                        frappe.logger("huf").warning(f"Agent event context hook failed: {type(exc).__name__}")
                    if event_note:
                        channel_note = f"{channel_note} {event_note}" if channel_note else event_note
                if channel_note:
                    prompt = f"[Channel note: {channel_note}]\n{prompt}"

            fallback_note = ""
            _maybe_mark_read_typing(event, gateway)
            _commit_unless_testing()  # keep Running status and saved media across a retry rollback
            key_hook = provider_hooks.get(gateway.provider, "conversation_key")
            conversation_ref = (key_hook(event) if key_hook else None) or (
                event.thread_id or event.conversation_id or event.sender_id
            )
            runner_hook = provider_hooks.get(gateway.provider, "agent_runner")
            run_fn = (runner_hook(event, gateway) if runner_hook else None) or run_agent_sync
            result = _run_agent_serialised(
                run_fn,
                lock_key=f"huf_gw_conv:{gateway.name}:{conversation_ref}",
                agent_name=event.target_agent,
                prompt=prompt,
                channel_id=f"gateway:{gateway.name}",
                external_id=conversation_ref,
                now=True,
                client_idempotency_key=f"gateway-event:{event.name}",
                files=media_files or None,
            )
            failure = _agent_run_failure(result)
            if failure:
                return _fail_event_for_agent_run(event, gateway, result, *failure, fallback_kind=fallback_kind)
            response = result.get("response")
            if attachment_unavailable and (_is_no_reply(response) or not str(response or "").strip()):
                _send_fallback_once(event, gateway, "attachment")
                return _suppress_reply(event, result.get("agent_run_id"), NO_REPLY_NOTE)
            if _is_no_reply(response):
                return _suppress_reply(event, result.get("agent_run_id"), NO_REPLY_NOTE)
            send_hook = provider_hooks.get(gateway.provider, "send_reply")
            if send_hook is not None:
                return send_hook(event, gateway, result.get("agent_run_id"), str(response))
            try:
                _throttle_outbound_send(gateway.name, _outbound_rate_cap(gateway.provider))
                delivery = send_gateway_reply(gateway, event, str(response))
                provider_message_id = delivery.provider_message_id
                _record_reply_sent(event, provider_message_id)
                if (getattr(delivery, "provider_response", None) or {}).get("fallback_template_sent"):
                    fallback_note = WHATSAPP_FALLBACK_NOTE
            except _whatsapp_send_errors(gateway.provider) as exc:
                # A7: a closed 24h window / bridge failure is an operator-fixable
                # condition, not a transient one -- fail the event cleanly, no retry loop.
                error_text = _whatsapp_error_text(exc)
                event.db_set(
                    {
                        "agent_run": result.get("agent_run_id"),
                        "status": "Failed",
                        "error_message": error_text[-500:],
                    }
                )
                frappe.log_error(error_text, "Gateway WhatsApp delivery failed")
                return {
                    "event_name": event.name,
                    "status": "Failed",
                    "error": error_text,
                    "agent_run_id": result.get("agent_run_id"),
                }
            except frappe.ValidationError as exc:
                if "No installed Gateway Adapter supports this channel" in str(exc):
                    provider_message_id = "agent_tool_delivery"
                else:
                    raise

            succeeded = {"agent_run": result.get("agent_run_id"), "status": "Succeeded"}
            if fallback_note:
                succeeded["error_message"] = fallback_note
            event.db_set(succeeded)
            return {
                "event_name": event.name,
                "status": "Succeeded",
                "agent_run_id": result.get("agent_run_id"),
                "provider_message_id": provider_message_id,
            }

        if event.target_type == "Flow":
            return _start_flow_for_event(event, gateway)

        raise frappe.ValidationError(_("Gateway event has no valid target."))
    except ConversationBusy as busy:
        return _requeue_busy_event(event, str(busy))
    except Exception:
        message = _redact_error_text(frappe.get_traceback())
        # GW-06: a failure here (e.g. send_gateway_reply raising after a
        # successful agent run) can leave uncommitted state from this request
        # queued behind the background job's own rollback-on-reraise. Discard
        # that partial state first, then reapply *only* the Failed status
        # against a clean transaction and commit it immediately, so the event
        # can never surface stuck at "Running" -- re-raising afterwards still
        # propagates the failure to the job queue for logging/retry policy.
        frappe.db.rollback()
        event.db_set({"status": "Failed", "error_message": message[-500:]})
        frappe.db.commit()
        frappe.log_error(message, "Gateway event failed")
        if not getattr(event, "reply_message_id", ""):
            try:
                if _send_fallback_once(event, frappe.get_doc("Gateway", event.gateway), "error"):
                    frappe.db.commit()
            except Exception:
                pass
        raise



# -- WhatsApp reply pipeline ----------------------------------------------------

REACTION_RECORDED_NOTE = "reaction_recorded: no run"
NO_REPLY_SENTINEL = "<NO_REPLY>"
NO_REPLY_NOTE = "Agent chose not to reply (<NO_REPLY>)"
_RETRY_CLAIM_SECONDS = 600
_RETRY_POLL_SECONDS = 1.0


def _epoch() -> float:
    return time.time()


def _is_reaction_event(event) -> bool:
    raw = event.get("raw_payload")
    if isinstance(raw, (str, bytes)):
        try:
            raw = json.loads(raw)
        except ValueError:
            return False
    return isinstance(raw, dict) and raw.get("kind") == "reaction"


def _is_no_reply(response) -> bool:
    """The whole agent message is the ``<NO_REPLY>`` sentinel (case-insensitive): send nothing."""
    return isinstance(response, str) and response.strip().upper() == NO_REPLY_SENTINEL


def _suppress_reply(event, agent_run_id, note: str) -> dict:
    values = {"status": "Succeeded", "reply_status": "suppressed", "error_message": note}
    if agent_run_id:
        values["agent_run"] = agent_run_id
    event.db_set(values)
    return {
        "event_name": event.name,
        "status": "Succeeded",
        "agent_run_id": agent_run_id,
        "reply_status": "suppressed",
        "reply_suppressed": True,
    }


def _maybe_mark_read_typing(event, gateway) -> None:
    """Read receipt + typing indicator when a run is about to start. Best effort, never raises."""
    try:
        hook = provider_hooks.get(gateway.provider, "typing")
        if hook is not None:
            hook(event, gateway)
    except Exception:
        pass


def _reply_max_attempts(gateway) -> int:
    try:
        value = int(getattr(gateway, "retry_max_attempts", 0) or 0)
    except (TypeError, ValueError):
        value = 0
    return value if value > 0 else 4


def _send_whatsapp_reply(event, gateway, agent_run_id, response: str) -> dict:
    """Format, split and send the agent's reply. The run is finished and never rerun on a send error."""
    from huf.ai.gateway_adapters import whatsapp_format as wf

    if agent_run_id:
        event.db_set("agent_run", agent_run_id)
    if event.sender_id and is_opted_out(gateway, event.sender_id):
        return _suppress_reply(event, agent_run_id, "Recipient opted out: reply not sent")
    from huf.ai import whatsapp_voice_reply as voice

    mode = voice.reply_mode(event, gateway, response)
    if mode == voice.VOICE_ONLY:
        if event.reply_message_id or _send_voice_only(event, gateway, response):
            return _finish_voice_only(event, gateway)
    parts = wf.split_body(wf.to_whatsapp(response)) or [response]
    result = _attempt_reply_parts(event, gateway, parts, 1)
    if mode == voice.TEXT_AND_VOICE and result.get("status") == "Succeeded":
        voice.send_voice_reply(event, gateway, response, quote=False, once=True)
    return result


def _send_telegram_reply(event, gateway, agent_run_id, response: str) -> dict:
    """Telegram reply: opt-out gate, format + split, idempotent part send (see telegram_pipeline)."""
    from huf.ai.gateway_adapters import telegram_pipeline as tp

    if agent_run_id:
        event.db_set("agent_run", agent_run_id)
    if event.sender_id and is_opted_out(gateway, event.sender_id):
        return _suppress_reply(event, agent_run_id, tp.OPT_OUT_NOTE)
    guest_hook = provider_hooks.get(gateway.provider, "guest_reply")
    if guest_hook is not None:
        guest_result = guest_hook(event, gateway, response)
        if guest_result is not None:
            return guest_result
    parts = tp.make_parts(response) or [response]
    voice_hook = provider_hooks.get(gateway.provider, "voice_reply")
    if voice_hook is not None:
        return voice_hook(
            event, gateway, tp.spoken_text(response), lambda: _attempt_reply_parts(event, gateway, parts, 1)
        )
    return _attempt_reply_parts(event, gateway, parts, 1)


def _send_voice_only(event, gateway, response: str) -> bool:
    from huf.ai import whatsapp_voice_reply as voice

    _throttle_outbound_send(gateway.name, _outbound_rate_cap(gateway.provider))
    wamid = voice.send_voice_reply(event, gateway, response)
    _record_reply_sent(event, wamid)
    return bool(wamid)


def _finish_voice_only(event, gateway) -> dict:
    from huf.ai.gateway_webhook import touch_last_event

    event.db_set({"status": "Succeeded", "delivery_error": ""})
    touch_last_event(gateway)
    return {
        "event_name": event.name,
        "status": "Succeeded",
        "agent_run_id": event.agent_run,
        "provider_message_id": event.reply_message_id,
        "attempts": 1,
        "voice": True,
    }


def _attempt_reply_parts(event, gateway, parts: list[str], attempt: int) -> dict:
    attempt_hook = provider_hooks.get(gateway.provider, "attempt_reply_parts")
    if attempt_hook is not None:
        return attempt_hook(event, gateway, parts, attempt)
    from huf.ai.gateway_webhook import send_gateway_parts, touch_last_event

    try:
        _throttle_outbound_send(gateway.name, _outbound_rate_cap(gateway.provider))
        delivery = send_gateway_parts(gateway, event, parts, quote=not event.reply_message_id)
    except Exception as exc:
        return _handle_reply_send_failure(event, gateway, exc, parts, attempt)

    if not event.reply_message_id:
        _record_reply_sent(event, delivery.provider_message_id)
    elif frappe.db.get_value("Gateway Event", event.name, "reply_status") == "retrying":
        event.db_set("reply_status", "sent", update_modified=False)
    note = WHATSAPP_FALLBACK_NOTE if (getattr(delivery, "provider_response", None) or {}).get("fallback_template_sent") else ""
    final = {"status": "Succeeded"}
    if note:
        final["error_message"] = note
    if attempt > 1:
        final["delivery_error"] = ""
    event.db_set(final)
    touch_last_event(gateway)
    return {
        "event_name": event.name,
        "status": "Succeeded",
        "agent_run_id": event.agent_run,
        "provider_message_id": delivery.provider_message_id,
        "attempts": attempt,
    }


def _handle_reply_send_failure(event, gateway, exc: BaseException, parts: list[str], attempt: int) -> dict:
    """Classify a failed send: schedule a send-only retry when transient, otherwise fail the event."""
    from huf.ai.gateway_adapters import whatsapp as wa
    from huf.ai.gateway_adapters import whatsapp_errors as we

    cls = wa.classify_send_exception(exc)
    cause = exc
    remaining = parts
    if isinstance(exc, wa.WhatsAppPartsError):
        cause, remaining = exc.cause, exc.remaining
        if exc.sent_ids and not event.reply_message_id:
            _record_reply_sent(event, exc.sent_ids[0])
    operator_text = cls.get("operator_text") or "WhatsApp delivery failed"
    max_attempts = _reply_max_attempts(gateway)

    if remaining and we.should_retry(cls, attempt, max_attempts):
        delay = we.backoff_seconds(cls, attempt)
        delay = we.BACKOFF_BASE_SECONDS if delay is None else delay
        try:
            event.db_set(
                {
                    "status": "Running",
                    "reply_status": "retrying",
                    "delivery_error": f"retrying ({attempt}/{max_attempts}) in {delay:.0f}s: {operator_text}"[:500],
                }
            )
            frappe.enqueue(
                "huf.ai.gateway_service.retry_gateway_reply",
                queue="default",
                timeout=300,
                enqueue_after_commit=True,
                event_name=event.name,
                parts_remaining=list(remaining),
                attempt=attempt + 1,
                not_before=_epoch() + delay,
            )
            return {
                "event_name": event.name,
                "status": "Running",
                "reply_status": "retrying",
                "retry_in_seconds": delay,
                "attempt": attempt,
                "agent_run_id": event.agent_run,
            }
        except Exception:
            frappe.logger("huf").warning("Gateway reply retry could not be scheduled")

    if isinstance(cause, _whatsapp_send_errors(gateway.provider)):
        error_text = _provider_error_text(gateway.provider, cause)
    else:
        error_text = _redact_error_text(str(cause)) or operator_text
    delivery_error = f"gave up after {attempt} attempts: {operator_text}" if cls.get("retryable") else operator_text
    event.db_set(
        {
            "status": "Failed",
            "reply_status": "sent" if event.reply_message_id else "failed",
            "error_message": error_text[-500:],
            "delivery_error": delivery_error[:500],
        }
    )
    frappe.log_error(f"{delivery_error}\n{error_text}", "Gateway WhatsApp delivery failed")
    try:
        from huf.ai.gateway_webhook import _set_gateway_error

        _set_gateway_error(gateway.name, f"Reply to {event.name} failed: {delivery_error}")
    except Exception:
        pass
    return {
        "event_name": event.name,
        "status": "Failed",
        "error": error_text,
        "error_code": cls.get("code"),
        "agent_run_id": event.agent_run,
        "attempts": attempt,
    }


def retry_gateway_reply(event_name: str, parts_remaining: list[str], attempt: int = 2, not_before: float | None = None) -> dict:
    """Queued job: re-send the unsent reply parts. Never reruns the agent. Idempotent per (event, attempt)."""
    event = frappe.get_doc("Gateway Event", event_name)
    if event.reply_status != "retrying" or event.status != "Running" or not parts_remaining:
        return {"event_name": event_name, "skipped": True}
    wait = (not_before or 0) - _epoch()
    if wait > 0:
        # Not due yet: hop back onto the queue instead of holding a worker for the whole backoff.
        _sleep(min(wait, _RETRY_POLL_SECONDS))
        # Keep the event looking alive to the reaper while it waits out the backoff.
        frappe.db.set_value("Gateway Event", event_name, "modified", now_datetime(), update_modified=False)
        frappe.enqueue(
            "huf.ai.gateway_service.retry_gateway_reply",
            queue="default",
            timeout=300,
            enqueue_after_commit=True,
            event_name=event_name,
            parts_remaining=list(parts_remaining),
            attempt=attempt,
            not_before=not_before,
        )
        return {"event_name": event_name, "deferred": True}
    claim_key = f"huf_gw_reply_retry:{event_name}"  # one in-flight retry per event, whatever the attempt
    if not frappe.cache().set(claim_key, 1, ex=_RETRY_CLAIM_SECONDS, nx=True):
        return {"event_name": event_name, "skipped": True}

    gateway = frappe.get_doc("Gateway", event.gateway)
    try:
        if gateway.execution_user:
            frappe.set_user(gateway.execution_user)
        if event.sender_id and is_opted_out(gateway, event.sender_id):
            return _suppress_reply(event, event.agent_run, "Recipient opted out: reply not sent")
        return _attempt_reply_parts(event, gateway, list(parts_remaining), int(attempt))
    except Exception:
        message = _redact_error_text(frappe.get_traceback())
        event.db_set({"status": "Failed", "reply_status": "failed", "error_message": message[-500:]})
        frappe.log_error(message, "Gateway reply retry failed")
        return {"event_name": event_name, "status": "Failed"}
    finally:
        frappe.cache().delete(claim_key)


@frappe.whitelist(methods=["POST"])
def test_gateway_send(gateway_name: str, test_recipient_id: str) -> dict:
	"""Send a test message through a gateway to verify credentials and connectivity.

	Returns a dict with:
	- success (bool): Whether the message was sent
	- message (str): Human-readable status or error message
	- provider_response (str): Raw response from the provider (if applicable)
	"""
	if not frappe.has_permission("Gateway", "read"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	if not gateway_name or not test_recipient_id:
		frappe.throw(_("Gateway name and test recipient ID are required."))

	gateway = None
	try:
		gateway = frappe.get_doc("Gateway", gateway_name)

		if not gateway.is_enabled:
			return {
				"success": False,
				"message": "Gateway is disabled. Enable it to test.",
				"provider_response": None,
			}

		if not gateway.integration_settings:
			return {
				"success": False,
				"message": "Gateway has no credentials configured.",
				"provider_response": None,
			}

		# Get the adapter for this gateway
		from huf.ai.gateway_webhook import get_gateway_adapter
		from huf.ai.gateway_adapters.types import GatewayReply

		adapter = get_gateway_adapter(gateway)

		# Send a test message
		test_message = "Test message from Huf. If you see this, the connection is working."
		reply = GatewayReply(
			conversation_id=test_recipient_id,
			text=test_message,
		)

		delivery = adapter.send_reply(reply)

		return {
			"success": True,
			"message": f"Test message sent successfully to {test_recipient_id}",
			"provider_response": json.dumps({"delivery_id": delivery.delivery_id}) if delivery else None,
		}

	except _whatsapp_send_errors(gateway.provider if gateway is not None else None) as exc:
		error_msg = _redact_error_text(_whatsapp_error_text(exc))
		return {
			"success": False,
			"message": f"Failed to send test message: {error_msg}",
			"provider_response": error_msg,
		}
	except Exception as exc:
		error_msg = _redact_error_text(str(exc))
		return {
			"success": False,
			"message": f"Failed to send test message: {error_msg}",
			"provider_response": error_msg,
		}


@frappe.whitelist(methods=["POST"])
def preview_gateway_route(gateway_name: str, context: str | dict) -> dict:
    """Preview a route for administrators without executing any work."""
    if not frappe.has_permission("Gateway", "read"):
        frappe.throw(_("Not permitted"), frappe.PermissionError)
    if isinstance(context, str):
        context = json.loads(context)
    return resolve_gateway_route(gateway_name, context or {})


# GW-15: the frontend readiness checklist (gatewayReadiness.ts) only checked 3
# conditions (credentials connected, route target set, enabled) while
# Gateway.validate() enforces at least 5 more before an enabled gateway can
# actually save: execution_user set, the chosen route target concretely
# filled in, required provider credentials present, execution_user's role,
# and execution_user's access to the default agent. Rather than re-encode
# those rules a second time in TypeScript (and have them drift again), this
# endpoint runs the real Gateway.validate() checks in dry-run mode -- read
# only, no save, no side effects -- and returns each one as a pass/fail item
# the frontend can render directly.
GATEWAY_READINESS_CHECKS = (
    ("enabled", "Gateway enabled"),
    ("execution-user", "Run as user set"),
    ("route-target", "Route target set"),
    ("route-target-concrete", "Route target fully chosen"),
    ("credentials", "Credentials connected"),
    ("credential-values", "Required credential values set"),
    ("execution-user-role", "Run-as user has gateway role"),
    ("agent-access", "Run-as user can access default agent"),
)


@frappe.whitelist()
def preview_gateway_readiness(gateway_name: str) -> dict:
    """Report, per-check, whether a Gateway meets every precondition Gateway.validate()
    would enforce if it were enabled and saved right now -- without saving it.

    Reuses Gateway's own private validation methods (read-only) so this list can
    never silently drift from what actually blocks save/enable.
    """
    if not frappe.has_permission("Gateway", "read"):
        frappe.throw(_("Not permitted"), frappe.PermissionError)

    gateway = frappe.get_doc("Gateway", gateway_name)
    results: dict[str, dict] = {}

    def record(check_id: str, label: str, ok: bool, hint: str | None = None):
        results[check_id] = {"id": check_id, "label": label, "done": bool(ok), "hint": None if ok else hint}

    def run_check(check_id: str, label: str, fn, default_hint: str):
        try:
            fn()
            record(check_id, label, True)
        except frappe.exceptions.ValidationError as e:
            record(check_id, label, False, str(e) or default_hint)
        except Exception as e:  # defensive: never let a lookup error break the preview
            record(check_id, label, False, str(e) or default_hint)

    record("enabled", "Gateway enabled", bool(gateway.is_enabled), "Turn the gateway on")

    def _execution_user_set():
        if not gateway.execution_user:
            frappe.throw(_("Set a Run as user."))

    run_check("execution-user", "Run as user set", _execution_user_set, "Set a least-privileged Run as user")

    record(
        "route-target",
        "Route target set",
        bool(gateway.default_target_type),
        "Choose an agent or flow to receive messages",
    )

    def _route_target_concrete():
        if gateway.default_target_type == "Agent" and not gateway.default_agent:
            frappe.throw(_("Choose a default agent or clear the default route."))
        if gateway.default_target_type == "Flow" and not gateway.default_flow:
            frappe.throw(_("Choose a default flow or clear the default route."))

    run_check(
        "route-target-concrete",
        "Route target fully chosen",
        _route_target_concrete,
        "Finish choosing the agent or flow for this route",
    )

    def _credentials_connected():
        expected_service = provider_to_service_id(gateway.provider) if gateway.provider else None
        if not expected_service:
            return
        if not gateway.integration_settings:
            frappe.throw(_("Connect credentials for this channel."))
        integration = frappe.get_doc("Integration Settings", gateway.integration_settings)
        if integration.service != expected_service:
            frappe.throw(
                _("The connected integration must use the {0} service.").format(expected_service)
            )

    run_check("credentials", "Credentials connected", _credentials_connected, "Connect credentials for this channel")

    run_check(
        "credential-values",
        "Required credential values set",
        gateway._validate_required_credentials,
        "Fill in the required credential fields for this provider",
    )

    def _execution_user_role():
        if gateway.execution_user:
            gateway._validate_execution_user_role()

    run_check(
        "execution-user-role",
        "Run-as user has gateway role",
        _execution_user_role,
        "Grant the Run as user the required gateway role",
    )

    def _agent_access():
        if gateway.execution_user and gateway.default_agent:
            gateway._validate_agent_access()

    run_check(
        "agent-access",
        "Run-as user can access default agent",
        _agent_access,
        "Grant the Run as user access to the default agent",
    )

    ordered = [results[check_id] for check_id, _label in GATEWAY_READINESS_CHECKS]
    blocking = [c for c in ordered if not c["done"]]
    return {"ready": len(blocking) == 0, "blocking_count": len(blocking), "checks": ordered}


GATEWAY_EVENT_REJECTED_RETENTION_DAYS = 30


def purge_old_rejected_gateway_events(retention_days: int | None = None) -> int:
    """Scheduler entry point (``daily``, F-35): hard-delete stale Rejected Gateway Events.

    ``ingest_gateway_event`` deliberately keeps its ``event.insert()`` call
    ahead of the admission checks (see the docstring there) so that the
    idempotency-key uniqueness constraint stays race-safe and every
    rejection has a forensic audit row. That means a flood of spoofed or
    unverified webhooks still creates one ``Gateway Event`` row per request
    -- a storage DoS vector (F-35) if left unbounded. This job bounds growth
    by purging ``Rejected`` rows once they are older than the retention
    window, without touching the insert-before-admission ordering that the
    idempotency/audit-trail guarantees depend on.

    Registered in ``huf/hooks.py``'s ``scheduler_events["daily"]``.
    """
    days = retention_days if retention_days is not None else GATEWAY_EVENT_REJECTED_RETENTION_DAYS
    cutoff = add_to_date(now_datetime(), days=-days)
    return frappe.db.delete("Gateway Event", {"status": "Rejected", "received_at": ["<", cutoff]})
