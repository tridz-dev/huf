"""Credential redaction helpers for gateway payloads and error text."""

from __future__ import annotations

import re
from typing import Any

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
    # Slack file objects: private URLs are only fetchable with the bot token
    # and permalinks identify workspace content.
    "url_private",
    "url_private_download",
    "permalink",
}


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
