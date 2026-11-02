"""Webhook helpers: response override, duplicate invoke reply, send retry/backoff, adapter kwargs."""

def accepts_gateway_name(cls) -> bool:
	import inspect

	try:
		return "gateway_name" in inspect.signature(cls.__init__).parameters
	except (TypeError, ValueError):
		return False


def _duplicate_invoke_response(frappe, gateway, event):
	"""A redelivered Teams card click still needs a proper invoke response body, not our JSON.

	Ingest short-circuits duplicates before any filter runs, so no hook set an override. The
	adapter-tagged ``huf_kind`` identifies the activity; the Teams handler answers read-only.
	"""
	raw = getattr(event, "raw_payload", None)
	if not isinstance(raw, dict) or raw.get("huf_kind") != "card_action":
		return None
	try:
		from huf.ai.gateways.teams import actions as teams_actions

		frappe.local.gateway_response_override = None
		teams_actions.duplicate_card_response(gateway, raw)
		return _take_response_override(frappe)
	except Exception:
		return None


def _take_response_override(frappe):
	"""Raw HTTP response a pre-ingest hook asked for (Teams invoke needs a synchronous body).

	A hook stores ``frappe.local.gateway_response_override = {"status": int, "body": str|dict,
	"content_type": str}`` AFTER the adapter verified the request. Returns a werkzeug Response
	(returned directly, as slack_events does) or None. Malformed values are ignored.
	"""
	override = getattr(frappe.local, "gateway_response_override", None)
	if not isinstance(override, dict):
		return None
	frappe.local.gateway_response_override = None
	body = override.get("body")
	if isinstance(body, (dict, list)):
		import json

		body = json.dumps(body)
	if not isinstance(body, str):
		return None
	status = override.get("status")
	from werkzeug.wrappers import Response

	return Response(
		body,
		status=status if isinstance(status, int) else 200,
		mimetype=str(override.get("content_type") or "application/json"),
	)


SEND_MAX_ATTEMPTS = 3
SEND_BACKOFF_BASE = 1.0
SEND_MAX_DELAY = 30.0
_TRANSIENT_CODES = frozenset(
	{"ratelimited", "rate_limited", "internal_error", "service_unavailable", "fatal_error",
		"request_timeout", "timeout"}
)


def _http_status_of(exc) -> int | None:
	status = getattr(exc, "status", None)
	if not isinstance(status, int) or status <= 0:
		resp = getattr(exc, "response", None)
		status = getattr(resp, "status_code", None) if resp is not None else None
	return status if isinstance(status, int) else None


def _is_transient_send_error(exc: BaseException) -> bool:
	"""True only for retryable delivery failures (429/5xx/timeouts/transport); never auth/channel errors."""
	if isinstance(exc, (TimeoutError, ConnectionError)):
		return True
	name = type(exc).__name__
	if name in ("Timeout", "ReadTimeout", "ConnectTimeout", "ConnectionError"):
		return True
	status = _http_status_of(exc)
	if status is not None and (status == 429 or 500 <= status < 600):
		return True
	code = str(getattr(exc, "error_code", "") or "").lower()
	if code.startswith("transport_error") or code in _TRANSIENT_CODES:
		return True
	if not code and isinstance(exc, ValueError):
		# Slack adapter raises ValueError("Slack chat.postMessage failed: <code>")
		tail = str(exc).rsplit(":", 1)[-1].strip().lower()
		return tail in _TRANSIENT_CODES
	return False


def _send_retry_delay(exc: BaseException, attempt: int) -> float:
	hint = getattr(exc, "retry_after", None)
	if hint is None:
		headers = getattr(getattr(exc, "response", None), "headers", None) or {}
		try:
			hint = headers.get("Retry-After")
		except Exception:
			hint = None
	try:
		delay = float(hint) if hint is not None else SEND_BACKOFF_BASE * (2 ** (attempt - 1))
	except (TypeError, ValueError):
		delay = SEND_BACKOFF_BASE * (2 ** (attempt - 1))
	return max(0.0, min(delay, SEND_MAX_DELAY))


def adapter_kwargs(adapter_class, gateway, contact_name, provider_hooks) -> dict:
	"""Extra adapter ctor kwargs: provider context hook, plus gateway name when accepted (Teams)."""
	kwargs = {}
	context_hook = provider_hooks.get(gateway.provider, "adapter_context")
	if context_hook is not None:
		kwargs["gateway_context"] = context_hook(gateway, contact_name)
	if accepts_gateway_name(adapter_class):  # outbound routing is scoped to this gateway
		kwargs["gateway_name"] = gateway.name
	return kwargs


def finish_response(frappe, gateway, event, result):
	"""Raw response for the webhook (hook override, or duplicate invoke body) or None."""
	override = _take_response_override(frappe)
	if override is not None:
		return override
	if isinstance(result, dict) and result.get("duplicate"):
		return _duplicate_invoke_response(frappe, gateway, event)
	return None


def send_with_retry(adapter, reply, sleep=None, max_attempts: int = SEND_MAX_ATTEMPTS):
	"""adapter.send_reply with exponential backoff on transient errors; permanent errors raise."""
	import time

	sleep = sleep or time.sleep
	attempt = 0
	while True:
		attempt += 1
		try:
			return adapter.send_reply(reply)
		except Exception as exc:
			if attempt >= max(1, max_attempts) or not _is_transient_send_error(exc):
				raise
			sleep(_send_retry_delay(exc, attempt))
