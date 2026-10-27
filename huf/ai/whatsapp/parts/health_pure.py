"""Pure constants and helpers for WhatsApp health (moved out of health.py; re-imported there)."""

from __future__ import annotations

import re
from datetime import timedelta
from typing import Any

WINDOW = timedelta(hours=24)
APP_DASHBOARD = "https://developers.facebook.com/apps/"
WHATSAPP_MANAGER = "https://business.facebook.com/latest/whatsapp_manager/message_templates"
_APP_ID_RE = re.compile(r"^\d{5,30}$")
_BAD_TEMPLATE_STATES = frozenset({"REJECTED", "PAUSED", "DISABLED"})
_REPLIED = ("sent", "delivered", "read")
_SECRET_RE = re.compile(r"(?i)((?:access_)?token=)[^&\s\"'<>]+|EAA[A-Za-z0-9]{12,}")
_MAX_EVENTS = 5000
_AFTER_APP_SECRET = frozenset({"configure_webhook", "subscribe_messages", "approve_sender", "send_test_message"})

# next-step priority, then (code, label, action anchor)
_STEPS = (
	("meta_app", "create_meta_app", "Create a Meta app", APP_DASHBOARD),
	("credentials", "add_credentials", "Add the access token and phone number ID", "#credentials"),
	("app_secret", "add_app_secret", "Add the app secret", "#app-secret"),
	("enabled", "enable_gateway", "Turn the gateway on", "#enabled"),
	("webhook", "configure_webhook", "Set the callback URL in Meta", None),
	("subscribed", "subscribe_messages", "Subscribe to the messages field in Meta", None),
	("approve_sender", "approve_sender", "Approve the people waiting to talk to your agent", "#access"),
	("test_message", "send_test_message", "Send a test message to this number", "#test-message"),
)


def redact(text: Any) -> str:
	"""Strip tokens from text before it is shown (gateway service redactor, then a local pass)."""
	out = str(text or "")
	try:
		from huf.ai.gateway_service import _redact_error_text

		out = str(_redact_error_text(out))
	except Exception:
		pass
	return _SECRET_RE.sub(lambda m: (m.group(1) + "[redacted]") if m.group(1) else "[redacted]", out)


def mask_id(value: Any) -> str:
	text = str(value or "")
	return f"...{text[-4:]}" if len(text) > 6 else text


def _iso(value: Any) -> str | None:
	return str(value) if value else None


def meta_links(app_id: str | None) -> dict[str, str | None]:
	app = str(app_id or "").strip()
	known = bool(_APP_ID_RE.match(app))
	return {
		"app_dashboard": f"{APP_DASHBOARD}{app}/" if known else None,
		"whatsapp_manager": WHATSAPP_MANAGER,  # list page; Meta documents no deep links
		# best-effort path, not documented by Meta
		"webhook_config": f"{APP_DASHBOARD}{app}/whatsapp-business/wa-settings/" if known else None,
	}


def _reason(code: str, severity: str, message: str) -> dict[str, str]:
	return {"code": code, "severity": severity, "message": message}


def _count_text(count: int) -> str:
	return f"{count} in the last 24 hours"


def _is_failed(row: dict[str, Any]) -> bool:
	err = (row.get("delivery_error") or "").strip()
	if err and re.search(r"\b(131060|2593109)\b", err):
		return False  # informational codes never count as failures
	return str(row.get("status") or "") == "Failed" or str(row.get("reply_status") or "").lower() == "failed" or bool(err)


_AGENT_ERROR_RE = re.compile(r"^(?:provider_([a-z_]+)|agent_run_failed):")


def _agent_error_kind(row: dict[str, Any]) -> str | None:
	"""Kind of a failed-agent-run event (``unknown`` for a plain agent_run_failed), else None."""
	if str(row.get("status") or "") != "Failed":
		return None
	match = _AGENT_ERROR_RE.match(str(row.get("error_message") or ""))
	if not match:
		return None
	return match.group(1) or "unknown"


def count_events(rows: list[dict[str, Any]]) -> dict[str, int]:
	"""Pure: events_24h counters from event rows already limited to the last 24 hours."""
	return {
		"received": len(rows),
		"failed": sum(1 for r in rows if _is_failed(r)),
		"agent_failed": sum(1 for r in rows if _agent_error_kind(r) is not None),
		"unrouted": sum(1 for r in rows if str(r.get("status") or "") == "Unrouted"),
		"rejected": sum(1 for r in rows if str(r.get("status") or "") == "Rejected"),
	}
