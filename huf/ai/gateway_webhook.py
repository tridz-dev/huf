"""Runtime bridge between Gateway routing and provider-native adapters.

The module is intentionally lazy about provider imports: the Gateway foundation
can remain independently reviewable while regional adapter packages are merged
on top of the Adapter SDK.  A configured gateway still fails closed if its
adapter package or required credentials are unavailable.
"""

from __future__ import annotations

import json
from typing import Any

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit

from huf.ai.gateway_adapters import provider_hooks
from huf.ai.gateway_adapters.provider_ids import provider_to_service_id
from huf.ai.gateway_adapters.registered import get_adapter_class

EXEMPT_AUTH_ROUTES: frozenset[str] = frozenset(
	{
		# Bot Framework (and every other native-adapter) webhook: Teams posts
		# ``Authorization: Bearer <token>``; verification happens inside
		# ``TeamsGatewayAdapter.verify_inbound`` after this route is reached.
		"/api/method/huf.ai.gateway_webhook.handle_gateway_webhook",
		# Teams *Outgoing Webhook*: posts ``Authorization: HMAC <base64>``,
		# verified inside ``handle_teams_outgoing_webhook`` itself.
		"/api/method/huf.ai.tools.teams_webhook.handle_teams_outgoing_webhook",
	}
)


def exempt_gateway_webhook_auth() -> None:
	"""``auth_hooks`` entry: let allowlisted webhook routes reach their own auth.

	Frappe's core ``validate_auth`` (``frappe/auth.py``) splits the
	``Authorization`` header and, whenever it has exactly two parts (a scheme
	and a token — e.g. ``Bearer <token>`` or ``HMAC <token>``), first tries
	OAuth/API-key auth and then, if neither matched, raises
	``AuthenticationError`` unless ``frappe.session.user`` is already a real
	user. That check runs *before* Frappe ever looks at ``allow_guest=True``
	on the target whitelisted method, so any Gateway webhook that authenticates
	itself with a custom two-part ``Authorization`` scheme (rather than
	Frappe's own token/basic/oauth schemes) is rejected at 401 by core before
	its own signature/HMAC verification ever runs.

	This hook runs inside ``validate_auth`` (via ``validate_auth_via_hooks``),
	strictly before that terminal guest check. For routes on the
	``EXEMPT_AUTH_ROUTES`` allowlist only, it authenticates the request as a
	deliberately unprivileged, disabled technical user so the terminal check
	passes and control reaches the whitelisted method's own verification
	(HMAC/Bearer/signature). The route's handler still fails closed on a bad
	or missing signature; this hook only gets it past the framework-level
	guest check, it grants no document permissions of its own.
	"""
	request = frappe.request
	if request is None or request.method != "POST":
		return
	if request.path not in EXEMPT_AUTH_ROUTES:
		return

	authorization = frappe.get_request_header("Authorization") or ""
	if len(authorization.split(" ")) != 2:
		return

	if frappe.session.user not in ("", "Guest"):
		return

	frappe.set_user(_gateway_webhook_auth_user())


def _gateway_webhook_auth_user() -> str:
	"""Return (creating once) the disabled technical user used only to satisfy
	Frappe's terminal guest check for allowlisted webhook routes.

	It is created ``enabled=0`` and with no roles: it cannot log in, and
	nothing about it grants any Gateway/Integration document permission —
	those doctypes are exempt from generic /api/resource access entirely
	(see the ``has_permission``/``permission_query_conditions`` hooks in
	``huf/hooks.py``). Its only job is to be a non-"Guest", non-empty
	``frappe.session.user`` value.
	"""
	technical_user = "gateway-webhook@huf.system"
	if not frappe.db.exists("User", technical_user):
		frappe.get_doc(
			{
				"doctype": "User",
				"email": technical_user,
				"first_name": "Gateway Webhook (system)",
				"user_type": "System User",
				"enabled": 0,
				"send_welcome_email": 0,
				"roles": [],
			}
		).insert(ignore_permissions=True, ignore_if_duplicate=True)
	return technical_user


# Doctypes in the Gateway/Integration family. None of them have a per-row
# owner or "shared with" concept the way Agent/Agent Run do: a Gateway Access
# Entry, Integration Credential, etc. are account-wide configuration, and the
# app only ever reads/writes them through its own bespoke whitelisted methods
# (gateway pairing, adapter routing, the Integrations UI's own controllers),
# never through a generic list/get. Rather than invent row-level semantics
# these doctypes were never designed for, generic ``/api/resource/<DocType>``
# access is blocked outright for everyone except System Manager, matching how
# the app itself never talks to them that way.
GATEWAY_INTEGRATION_DOCTYPES: frozenset[str] = frozenset(
	{
		"Gateway",
		"Gateway Access Entry",
		"Gateway Event",
		"Gateway Binding",
		"Integration Settings",
		"Integration Service",
		"Integration Credential",
	}
)


def has_permission_gateway_family(doc, ptype: str = "read", user: str | None = None) -> bool:
	"""``has_permission`` hook: only System Manager may touch these doctypes.

	Registered for every doctype in ``GATEWAY_INTEGRATION_DOCTYPES``. These
	records carry credentials and routing/permission data for every configured
	Gateway and Integration; the app itself never reads or writes them through
	generic ``/api/resource`` access, only through its own whitelisted
	pairing/adapter/API surface (which runs with ``ignore_permissions=True``
	where appropriate and does its own checks). A user with a generic DocType
	read/write role permission on these doctypes, but who is not a System
	Manager, must not gain list/get/save access to them just because the
	doctype exists — hence this hook rather than leaving them to the
	role-permission default.
	"""
	user = user or frappe.session.user
	return bool(frappe.db.get_value("Has Role", {"parent": user, "role": "System Manager"}, "name"))


def get_permission_query_conditions_gateway_family(user: str | None = None) -> str:
	"""``permission_query_conditions`` hook mirroring ``has_permission_gateway_family``.

	Without this, a non-System-Manager user with a generic read role on one of
	these doctypes could still see rows show up in a ``/api/resource`` list
	call (list views apply ``permission_query_conditions``, not
	``has_permission``, to filter rows) even though ``has_permission`` would
	refuse a ``get`` on any individual one.
	"""
	user = user or frappe.session.user
	if frappe.db.get_value("Has Role", {"parent": user, "role": "System Manager"}, "name"):
		return ""
	return "1=0"


def _adapter_class_for_provider(provider: str):
	"""Resolve a ``Gateway.provider`` display value to its adapter class.

	Routes through the shared ``provider_to_service_id`` transform and the
	``GatewayAdapterRegistry`` (via ``get_adapter_class``, which imports the
	adapter's module lazily on first use) rather than a hardcoded map.
	"""
	try:
		return get_adapter_class(provider_to_service_id(provider))
	except KeyError as exc:
		raise frappe.ValidationError(_("No installed Gateway Adapter supports this channel.")) from exc
	except (ImportError, AttributeError) as exc:
		raise frappe.ValidationError(
			_("The Gateway Adapter package for this channel is not installed.")
		) from exc


def _gateway_credentials(gateway) -> dict[str, str]:
	if not gateway.integration_settings:
		raise frappe.ValidationError(_("This gateway needs a connected integration for its credentials."))
	settings = frappe.get_doc("Integration Settings", gateway.integration_settings)
	credentials = {}
	for row in settings.credentials or []:
		if row.key:
			credentials[row.key] = row.get_password("value") or ""
	if getattr(gateway, "provider", None) == "Telegram" and getattr(gateway, "telegram_test_environment", 0):
		credentials["test_environment"] = "1"  # read by the Telegram adapter/clients; not a secret
	return credentials


def _fallback_params(gateway, contact_name: str):
	"""The Gateway's ``fallback_template_params`` (a JSON list or map; ``{{contact_name}}`` is substituted)."""
	raw = str(gateway.get("fallback_template_params") or "").strip()
	if not raw:
		return None
	try:
		value = json.loads(raw)
	except ValueError:
		return None

	def fill(item):
		return str(item).replace("{{contact_name}}", contact_name or "there")

	if isinstance(value, dict):
		return {str(k): fill(v) for k, v in value.items()}
	if isinstance(value, list):
		return [fill(v) for v in value]
	return None


def get_gateway_adapter(gateway, contact_name: str = ""):
	"""Instantiate the configured adapter without exposing stored credentials."""
	adapter_class = _adapter_class_for_provider(gateway.provider)
	credentials = _gateway_credentials(gateway)
	kwargs = {}
	context_hook = provider_hooks.get(gateway.provider, "adapter_context")
	if context_hook is not None:
		kwargs["gateway_context"] = context_hook(gateway, contact_name)
	if _accepts_gateway_name(adapter_class):  # e.g. Teams: outbound routing is scoped to this gateway
		kwargs["gateway_name"] = gateway.name
	return adapter_class(credentials, **kwargs)


def _accepts_gateway_name(cls) -> bool:
	import inspect

	try:
		return "gateway_name" in inspect.signature(cls.__init__).parameters
	except (TypeError, ValueError):
		return False


def _inbound_request():
	from huf.ai.gateway_adapters.types import GatewayInboundRequest

	request = frappe.request
	if not request:
		raise frappe.ValidationError(_("A provider HTTP request is required."))
	return GatewayInboundRequest(
		body=request.get_data(),
		headers=dict(request.headers),
		query=dict(request.args),
		method=request.method,
	)


def _event_context(event) -> dict[str, Any]:
	raw = getattr(event, "raw_payload", None)
	raw = raw if isinstance(raw, dict) else {}
	message = raw.get("message") if isinstance(raw.get("message"), dict) else {}
	codes = [
		e.get("code")
		for e in (message.get("errors") if isinstance(message.get("errors"), list) else [])
		if isinstance(e, dict) and e.get("code") is not None
	]
	kind = getattr(event, "kind", "message")
	return {
		"kind": kind if isinstance(kind, str) and kind else "message",
		"original_message_id": str(raw.get("original_message_id") or ""),
		"provider_error_codes": codes,
		"sender_id": event.sender_id,
		"conversation_id": event.conversation_id,
		"thread_id": event.thread_id,
		"message_text": event.message_text,
		"is_room": event.is_room,
		"mentioned": event.mentioned,
		"display_name": getattr(event, "display_name", "") or "",
	}


def _text_response(value: str) -> None:
	"""Return a provider challenge as raw text rather than Frappe API JSON."""
	frappe.local.response.update(
		{"type": "txt", "doctype": "gateway-callback", "result": value}
	)


def _ingest_rate_gate() -> None:
	"""Count one request against the per-gateway ingest rate limit (100/60s).

	This used to be a decorator on ``handle_gateway_webhook``, which counted
	every POST. Providers that batch and interleave delivery receipts
	(WhatsApp) must not have status-only traffic consume the ingest budget, so
	the same ``rate_limit`` is now applied explicitly: up front for
	single-event providers (unchanged), and only for forged requests or
	payloads that actually carry messages for ``parse_payload`` providers.
	"""


_ingest_rate_limited = rate_limit(key="gateway_name", limit=100, seconds=60)(_ingest_rate_gate)
_RATE_LIMIT_WINDOW_SECONDS = 60
MAX_BODY_BYTES = 3 * 1024 * 1024  # Meta's webhook payload cap
MAX_MESSAGES_PER_PAYLOAD = 100  # calls handled per delivery
# Policy for large deliveries (no silent drops): every message is ingested inline, up to this cap on
# total work per request. Past it the first MAX_INGEST_PER_REQUEST are ingested and the webhook answers
# HTTP 503 + Retry-After so Meta redelivers the whole payload; ingest is idempotent per message id, so
# the redelivery skips what is stored and continues with the rest. Meta caps a delivery at ~3 MB.
MAX_INGEST_PER_REQUEST = 500
_DEFERRED_RETRY_AFTER_SECONDS = 30
# A payload that still has unprocessed messages after this many 503 passes is acked; the rest are dead-lettered.
MAX_DEFERRALS_PER_PAYLOAD = 5
_DEFERRAL_TTL_SECONDS = 3600


def _ingest_rate_gate() -> None:
	"""Apply the ingest rate limit; a rejection also tells the sender when to retry."""
	try:
		_ingest_rate_limited()
	except frappe.RateLimitExceededError:
		try:
			frappe.local.response_headers["Retry-After"] = str(_RATE_LIMIT_WINDOW_SECONDS)
		except Exception:
			pass
		raise


def _transient_error_types() -> tuple[type, ...]:
	types: list[type] = [frappe.QueryDeadlockError, frappe.QueryTimeoutError, ConnectionError, TimeoutError]
	try:
		import pymysql

		types.append(pymysql.OperationalError)
	except Exception:
		pass
	return tuple(types)


# Errors worth a provider retry (Meta redelivers on non-2xx; ingest is deduped).
# Everything else is deterministic: retrying the same payload cannot succeed.
_TRANSIENT_ERRORS = _transient_error_types()
_TEMPLATE_BAD_STATES = frozenset({"REJECTED", "PAUSED", "DISABLED"})
_GATEWAY_ERROR_MAX = 500


def _set_gateway_error(gateway_name: str, text: str, *, touch_event: bool = False) -> None:
	"""Best-effort, redacted operator-visible note on the Gateway. Never raises."""
	try:
		from huf.ai.gateway_service import _redact_error_text

		values: dict[str, Any] = {"last_error": _redact_error_text(str(text))[:_GATEWAY_ERROR_MAX]}
		if touch_event:
			values["last_event_at"] = frappe.utils.now_datetime()
		frappe.db.set_value("Gateway", gateway_name, values, update_modified=False)
	except Exception:
		# Never raise from a diagnostics write, but never swallow it silently either.
		try:
			frappe.logger("huf").warning(f"Could not record Gateway last_error for {gateway_name}")
		except Exception:
			pass


_WEBHOOK_SIGNAL_THROTTLE_SECONDS = 60


def _record_webhook_signal(gateway, field: str) -> None:
	"""Stamp ``last_signature_failure_at`` / ``last_verify_ok_at`` on the Gateway, at most once a minute.

	Stores only a timestamp (no headers, body, token or secret). The throttle reads the value of
	the already-loaded document, so unauthenticated traffic costs at most one write per gateway
	per minute per field. Best effort: never raises and never changes the response.
	"""
	try:
		now = frappe.utils.now_datetime()
		last = gateway.get(field)
		if last:
			last = frappe.utils.get_datetime(last)
			if 0 <= (now - last).total_seconds() < _WEBHOOK_SIGNAL_THROTTLE_SECONDS:
				return
		frappe.db.set_value("Gateway", gateway.name, field, now, update_modified=False)
		gateway.set(field, now)
		frappe.db.commit()  # GET requests are not committed by the framework
	except Exception:
		pass


def _has_webhook_signals(gateway) -> bool:
	"""Whether the provider records verify/signature health timestamps (registered hook)."""
	hook = provider_hooks.get(getattr(gateway, "provider", ""), "webhook_signals")
	return bool(hook()) if hook is not None else False


def _record_failed_status(gateway_name: str, status: dict, provider: str | None = None) -> None:
	"""Record a failed outbound delivery status through the provider's ``failed_status`` hook."""
	hook = provider_hooks.get(provider, "failed_status")
	if hook is not None:
		hook(gateway_name, status)


def _record_failed_status_whatsapp(gateway_name: str, status: dict) -> None:
	"""A failed outbound delivery must be visible even when nothing is forwarded (direct mode)."""
	try:
		errors = status.get("errors") if isinstance(status.get("errors"), list) else []
		first = errors[0] if errors and isinstance(errors[0], dict) else {}
		if str(first.get("code")) in ("131060", "2593109"):
			return  # informational (WP-11): no alert, no Failed marking
		code = first.get("code") or "unknown"
		title = first.get("title") or first.get("message") or "no detail"
		recipient = str(status.get("recipient_id") or "")
		masked = f"...{recipient[-4:]}" if len(recipient) > 4 else "recipient"
		text = f"WhatsApp delivery failed to {masked}: error {code} ({title})"
		_set_gateway_error(gateway_name, text, touch_event=True)
		frappe.log_error(title="WhatsApp delivery failed", message=text)
	except Exception:
		pass


_REPLY_STATUSES = frozenset({"sent", "delivered", "read", "played", "failed"})
_REPLY_STATUS_RANK = {"sent": 1, "delivered": 2, "read": 3, "played": 4}
_REPLY_DELIVERED = frozenset({"delivered", "read", "played"})


def _reply_status_wins(current: str, state: str) -> bool:
	"""Whether a Meta status may replace the stored ``reply_status``.

	Order is sent < delivered < read < played. A ``failed`` never downgrades a message already
	delivered/read/played, and a late ``sent`` never resurrects a ``failed`` one. Anything
	delivered/read/played does overwrite ``failed`` (the message reached the phone after all).
	"""
	if state == "failed":
		return current not in _REPLY_DELIVERED
	if current == "failed":
		return state in _REPLY_DELIVERED
	return _REPLY_STATUS_RANK.get(state, 0) >= _REPLY_STATUS_RANK.get(current, 0)


def _update_reply_status(gateway_name: str, status: dict) -> None:
	"""Mirror a Meta delivery status onto the Gateway Event that sent the reply. Never raises."""
	try:
		state = str(status.get("status") or "").lower()
		message_id = str(status.get("id") or "")
		if state not in _REPLY_STATUSES or not message_id:
			return
		row = frappe.db.get_value(
			"Gateway Event",
			{"gateway": gateway_name, "reply_message_id": message_id},
			["name", "reply_status"],
			as_dict=True,
		)
		if not isinstance(row, dict):
			return
		current = row.get("reply_status") or ""
		if not _reply_status_wins(current, state):
			return  # out-of-order webhook: never regress delivered/read, never resurrect failed with sent
		values: dict[str, Any] = {"reply_status": state}
		if state == "failed":
			from huf.ai.gateway_service import _redact_error_text

			errors = status.get("errors") if isinstance(status.get("errors"), list) else []
			first = errors[0] if errors and isinstance(errors[0], dict) else {}
			code = first.get("code") or "unknown"
			title = first.get("title") or first.get("message") or "no detail"
			values["delivery_error"] = _redact_error_text(f"error {code}: {title}")[:_GATEWAY_ERROR_MAX]
		elif current == "failed":
			values["delivery_error"] = ""
		frappe.db.set_value("Gateway Event", row["name"], values, update_modified=False)
	except Exception:
		pass


_LAST_EVENT_THROTTLE_SECONDS = 60


def _is_lock_error(exc: BaseException) -> bool:
	return isinstance(exc, (frappe.QueryDeadlockError, frappe.QueryTimeoutError)) or "deadlock" in str(exc).lower()


def touch_last_event(gateway) -> None:
	"""Stamp ``Gateway.last_event_at`` on a successful inbound ingest or reply, at most once a minute.

	``gateway`` is a Gateway doc (its loaded value drives the throttle) or a name. Cheap ``set_value`` without
	touching ``modified``; never raises and never commits. Callers that just wrote terminal event state commit
	it first, so a deadlock here (two workers stamping the same Gateway row) cannot roll that state back.
	Lock errors are retried briefly, then logged at WARNING by type name only.
	"""
	import time

	try:
		now = frappe.utils.now_datetime()
		name = gateway if isinstance(gateway, str) else gateway.name
		last = frappe.db.get_value("Gateway", name, "last_event_at") if isinstance(gateway, str) else gateway.get("last_event_at")
		if last:
			last = frappe.utils.get_datetime(last)
			if 0 <= (now - last).total_seconds() < _LAST_EVENT_THROTTLE_SECONDS:
				return
		for attempt in range(3):
			try:
				frappe.db.set_value("Gateway", name, "last_event_at", now, update_modified=False)
				break
			except Exception as exc:
				if not _is_lock_error(exc) or attempt == 2:
					raise
				time.sleep(0.05 * (attempt + 1))
		if not isinstance(gateway, str):
			gateway.set("last_event_at", now)
	except Exception as exc:
		try:
			frappe.logger("huf.gateway").warning("touch_last_event failed: %s", type(exc).__name__)
		except Exception:
			pass


def _record_unknown_phone_ids(gateway_name: str, phone_ids) -> None:
	for phone_id in phone_ids:
		text = (
			f"payload for phone number id {phone_id} ignored; "
			"one Gateway per Meta app/number (create a separate Gateway for each number)"
		)
		try:
			frappe.logger("huf").warning(f"WhatsApp gateway {gateway_name}: {text}")
		except Exception:
			pass
		_set_gateway_error(gateway_name, text, touch_event=True)


_TEMPLATE_BAD_QUALITY = frozenset({"LOW", "RED"})
_TEMPLATE_KIND_FIELDS = {
	"quality": "message_template_quality_update",
	"category": "template_category_update",
}


def _template_update_text(update: dict, name: str) -> str | None:
	"""Operator-facing note for an update that needs attention, else None."""
	kind = update.get("kind") or ("quality" if "new_quality_score" in update else "category" if "new_category" in update else "status")
	if kind == "quality":
		score = str(update.get("new_quality_score") or "").upper()
		if score not in _TEMPLATE_BAD_QUALITY:
			return None
		previous = str(update.get("previous_quality_score") or "").upper()
		return f"Fallback template {name} quality dropped to {score}" + (f" (was {previous})" if previous else "")
	if kind == "category":
		new = str(update.get("new_category") or "").upper()
		if not new:
			return None
		previous = str(update.get("previous_category") or "").upper()
		return f"Fallback template {name} category changed to {new}" + (f" (was {previous})" if previous else "")
	state = str(update.get("event") or update.get("status") or "").upper()
	if state not in _TEMPLATE_BAD_STATES:
		return None
	reason = str(update.get("reason") or "").strip()
	return f"Fallback template {name} is {state}" + (f" ({reason})" if reason and reason != "NONE" else "")


def _warn(text: str) -> None:
	try:
		frappe.logger("huf").warning(text)
	except Exception:
		pass


def _route_template_update(gateway_name: str, update: dict) -> tuple[list[str], bool]:
	"""Accounts a template update belongs to, by WABA id (``entry[].id`` == ``WhatsApp Account.business_id``).

	Template webhooks always arrive on the Meta app's default callback, i.e. at whichever Gateway
	owns that URL, so the receiving Gateway says nothing about which account the template is on.
	Returns ``(accounts, handled)``: with the bridge present an unmatched WABA is ignored (logged,
	``handled`` False) instead of being guessed onto the receiving gateway's account. Without the
	bridge there are no accounts; the update is recorded unscoped (``[""]``).
	"""
	from huf.ai.gateway_adapters import whatsapp_bridge as bridge

	if not bridge.is_available():
		return [""], True
	waba_id = str(update.get("waba_id") or "").strip()
	accounts = bridge.accounts_for_waba(waba_id)
	if not accounts:
		_warn(
			f"WhatsApp gateway {gateway_name}: template update for WABA '{waba_id or '(none)'}' ignored; "
			"no WhatsApp Account has that business_id"
		)
		return [], False
	return accounts, True


def _record_template_update(update: dict, gateway_name: str = "") -> bool:
	"""Store the template's review/quality state per account, then flag fallback templates needing attention.

	The update is routed to the account(s) of its WABA, never to "whichever Gateway received it".
	Only gateways linked to those accounts (or, in direct mode with no account, the receiving
	gateway itself) whose fallback template is this one get the operator note.
	"""
	accounts: list[str] = []
	try:
		from huf.ai.gateway_adapters import whatsapp_bridge as bridge

		accounts, handled = _route_template_update(gateway_name, update)
		if not handled:
			return False
		for account in accounts:
			bridge.record_template_webhook(update, account or None)  # best effort, never raises
	except Exception:
		pass
	try:
		name = str(update.get("message_template_name") or update.get("name") or "").strip()
		if not name:
			return True
		text = _template_update_text(update, name)
		if not text:
			return True
		linked = {a for a in accounts if a}
		for row in frappe.get_all(
			"Gateway",
			filters={"provider": "WhatsApp", "fallback_template": name},
			fields=["name", "whatsapp_account"],
		):
			row_name = row["name"] if isinstance(row, dict) else row.name
			row_account = (row.get("whatsapp_account") if isinstance(row, dict) else getattr(row, "whatsapp_account", "")) or ""
			if (row_account and row_account in linked) or (not row_account and row_name == gateway_name):
				_set_gateway_error(row_name, text)
	except Exception:
		pass
	return True


def _handle_calls(gateway, calls) -> list[dict]:
	"""Record/route `calls` webhook items (metadata only; never an agent run). Errors never fail the ack."""
	from huf.ai.gateway_adapters import whatsapp_calls

	results: list[dict] = []
	for call in list(calls)[:MAX_MESSAGES_PER_PAYLOAD]:
		try:
			results.append(whatsapp_calls.handle_call(gateway, call))
		except Exception:
			frappe.log_error(frappe.get_traceback(), "WhatsApp call handling failed")
	return results


def _savepoint(name: str) -> None:
	try:
		frappe.db.savepoint(name)
	except Exception:
		pass


def _rollback_to_savepoint(name: str) -> None:
	try:
		frappe.db.rollback(save_point=name)
	except Exception:
		pass


def _dead_letter(gateway_name: str, event, exc: BaseException) -> int:
	"""Keep a deterministically failing message as a replayable Failed Gateway Event. Never raises."""
	from huf.ai.gateway_service import store_ingest_dead_letter

	_rollback_to_savepoint("gw_ingest")  # drop whatever the failed ingest left half-written
	try:
		store_ingest_dead_letter(
			gateway_name, event.provider_event_id, _event_context(event), dict(event.raw_payload or {}), exc
		)
		return 1
	except Exception:
		frappe.log_error(frappe.get_traceback(), "WhatsApp gateway dead letter failed")
		return 0

def _apply_account_events(events, gateway_name: str) -> int:
	"""account_update / user_preferences: applied to the receiving gateway only, no Gateway Event row (WP-11)."""
	if not events:
		return 0
	from huf.ai.whatsapp import account_events

	return account_events.apply_account_events(events, gateway_name)


def _deferral_key(gateway_name: str, request) -> str:
	import hashlib

	return f"huf:wa_deferrals:{gateway_name}:{hashlib.sha256(getattr(request, 'body', b'') or b'').hexdigest()[:32]}"


def _deferral_count(key: str) -> int:
	try:
		return int(frappe.cache.get_value(key) or 0)
	except Exception:
		return 0


def _bump_deferral(key: str, count: int) -> None:
	try:
		frappe.cache.set_value(key, count + 1, expires_in_sec=_DEFERRAL_TTL_SECONDS)
	except Exception:
		pass


def _supports_batch_parse(adapter) -> bool:
	# Class-level lookup so duck-typed/mock adapters do not accidentally qualify.
	return callable(getattr(type(adapter), "parse_payload", None))


def _handle_batched_payload(gateway, adapter, request) -> dict:
	"""Fan out one verified, possibly batched, provider delivery (WhatsApp)."""
	from huf.ai.gateway_adapters import whatsapp_bridge as bridge
	from huf.ai.gateway_service import ingest_gateway_event

	try:
		parsed = adapter.parse_payload(request)
	except ValueError:
		frappe.local.response.http_status_code = 400
		return {"success": False, "error": "Invalid payload"}

	messages = list(parsed.messages)
	if messages or getattr(parsed, "calls", ()):
		_ingest_rate_gate()

	ingested = duplicates = 0
	results: list[dict] = []
	first_transient = None
	failed = dead_lettered = 0
	account_name = None
	cap_hit_at = None
	for index, event in enumerate(messages):
		# Only NEW ingests count toward the cap, so a redelivery walks past already-stored
		# duplicates and makes progress instead of re-deferring the same tail forever.
		if ingested >= MAX_INGEST_PER_REQUEST:
			cap_hit_at = index
			break
		_savepoint("gw_ingest")
		try:
			result = ingest_gateway_event(
				gateway.name,
				event.provider_event_id,
				_event_context(event),
				verified_sender=True,
				raw_payload=dict(event.raw_payload),
			)
		except Exception as exc:
			frappe.log_error(frappe.get_traceback(), "WhatsApp gateway ingest failed")
			_set_gateway_error(gateway.name, f"Inbound message {event.provider_event_id} not stored: {exc}")
			if isinstance(exc, _TRANSIENT_ERRORS):
				first_transient = first_transient or exc  # re-raised below so Meta retries (deduped)
			else:
				failed += 1  # deterministic: a retry cannot succeed, so still ack 200 ...
				dead_lettered += _dead_letter(gateway.name, event, exc)  # ... but never lose the message
			continue
		results.append(result)
		if result.get("duplicate"):
			duplicates += 1
			continue
		ingested += 1
		touch_last_event(gateway)
		if result.get("status") in ("Rejected", "Recorded"):
			continue  # rejected or record-only (reaction/edit/revoke/system/unknown/unsupported): not mirrored
		try:  # best-effort mirror into frappe_whatsapp (A4)
			if account_name is None:
				# the Gateway's own account only: never a default or first-Active guess
				account_name = (getattr(gateway, "whatsapp_account", "") or "").strip()
				if not account_name and bridge.is_available():
					_warn(
						f"WhatsApp gateway {gateway.name}: no WhatsApp Account linked; "
						"inbound messages are not mirrored into frappe_whatsapp"
					)
			message = (event.raw_payload or {}).get("message")
			payload_phone_id = str(((event.raw_payload or {}).get("metadata") or {}).get("phone_number_id") or "")
			if (
				account_name
				and isinstance(message, dict)
				and bridge.account_matches_phone_id(account_name, payload_phone_id)
			):
				bridge.record_incoming(account_name, message, getattr(event, "display_name", "") or None)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "WhatsApp record_incoming failed")

	remaining = messages[cap_hit_at:] if cap_hit_at is not None else []
	deferred = len(remaining)
	deferral_key = _deferral_key(gateway.name, request)
	if deferred:
		seen = _deferral_count(deferral_key)
		if seen >= MAX_DEFERRALS_PER_PAYLOAD:
			# bounded: stop asking Meta to redeliver; keep the tail as replayable dead letters and ack
			_warn(f"WhatsApp gateway {gateway.name}: {deferred} messages still deferred after {seen} passes; dead-lettering")
			for event in remaining:
				dead_lettered += _dead_letter(gateway.name, event, RuntimeError("deferral limit exceeded"))
			failed += deferred
			deferred = 0
		else:
			_bump_deferral(deferral_key, seen)
			_warn(
				f"WhatsApp gateway {gateway.name}: ingested {MAX_INGEST_PER_REQUEST} new messages, answering 503 "
				f"so the provider redelivers the other {deferred}"
			)

	_record_unknown_phone_ids(gateway.name, getattr(parsed, "unknown_phone_ids", ()) or ())
	# A deferred pass only ingests messages: statuses/templates/calls/account events run once, on the
	# final pass, so Meta's redeliveries of a big payload never re-apply them.
	routed_updates: list = []
	call_results: list = []
	account_applied = forwarded = 0
	if not deferred:
		for status in parsed.statuses:
			_update_reply_status(gateway.name, status)
			if str(status.get("status") or "").lower() == "failed":
				_record_failed_status(gateway.name, status, getattr(gateway, "provider", None))
		routed_updates = [update for update in parsed.template_updates if _record_template_update(update, gateway.name)]
		call_results = _handle_calls(gateway, getattr(parsed, "calls", ()) or ())
		account_applied = _apply_account_events(getattr(parsed, "account_events", ()) or (), gateway.name)

		changes = [{"field": "messages", "value": {"statuses": [status]}} for status in parsed.statuses]
		changes += [
			{
				"field": _TEMPLATE_KIND_FIELDS.get(update.get("kind"), "message_template_status_update"),
				"value": {k: v for k, v in update.items() if k not in ("kind", "waba_id")},
			}
			for update in routed_updates
		]
		for change in changes:
			try:
				if bridge.forward_status(change):
					forwarded += 1
			except Exception:
				pass  # best effort, never fail the ack

	if first_transient is not None:
		raise first_transient
	if deferred:
		frappe.local.response.http_status_code = 503
		try:
			frappe.local.response_headers["Retry-After"] = str(_DEFERRED_RETRY_AFTER_SECONDS)
		except Exception:
			pass
	return {
		"success": not deferred,
		"messages": len(messages) - deferred,
		"ingested": ingested,
		"duplicates": duplicates,
		"statuses": len(parsed.statuses),
		"template_updates": len(parsed.template_updates),
		"calls": len(call_results),
		"account_events": account_applied,
		"forwarded": forwarded,
		"ignored": parsed.ignored,
		"deferred": deferred,
		"note": (
			f"{deferred} messages not processed yet; retry the delivery (503)" if deferred else ""
		),
		"failed": failed,
		"dead_lettered": dead_lettered,
		"results": results,
	}


@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])
def handle_gateway_webhook() -> dict | None:
	"""Verify a native provider callback, then hand only normalized data to Gateway.

	The URL contains a Gateway document name, never a credential.  Native
	verification happens before persistence or queueing, and no provider payload
	is normalized until that verification succeeds.

	gateway_name is read directly from the query string rather than taken as
	a function argument: every provider here posts application/json, and
	frappe.app.make_form_dict replaces frappe.form_dict wholesale with the
	parsed JSON body whenever Content-Type is JSON, so a query-string kwarg
	never actually reaches this function on a real webhook call.
	"""
	from huf.ai.gateway_service import ingest_gateway_event

	gateway_name = frappe.request.args.get("gateway_name") if frappe.request is not None else None
	if not gateway_name:
		frappe.local.response.http_status_code = 400
		return {"success": False, "error": "Missing gateway_name"}
	# JSON bodies replace form_dict wholesale, so the rate limiter's
	# form_dict key would be empty; key the buckets on the query-string name.
	frappe.form_dict["gateway_name"] = gateway_name

	try:
		gateway = frappe.get_doc("Gateway", gateway_name)
	except frappe.DoesNotExistError:
		frappe.local.response.http_status_code = 404
		return {"success": False, "error": "Unknown gateway"}
	declared = getattr(frappe.request, "content_length", None) if frappe.request is not None else None
	if declared is not None and declared > MAX_BODY_BYTES:
		frappe.local.response.http_status_code = 413
		return {"success": False, "error": "Payload too large"}

	adapter = get_gateway_adapter(gateway)
	request = _inbound_request()
	if len(getattr(request, "body", b"") or b"") > MAX_BODY_BYTES:
		frappe.local.response.http_status_code = 413
		return {"success": False, "error": "Payload too large"}
	if request.method == "GET" and hasattr(adapter, "verify_url"):
		_ingest_rate_gate()
		try:
			challenge = adapter.verify_url(request) or ""
		except frappe.PermissionError:
			if _has_webhook_signals(gateway):
				_record_webhook_signal(gateway, "last_signature_failure_at")
			frappe.local.response.http_status_code = 403
			return {"success": False, "error": "Webhook verification failed"}
		if _has_webhook_signals(gateway):
			_record_webhook_signal(gateway, "last_verify_ok_at")
		_text_response(challenge)
		return None
	# Only ingest is gated on is_enabled: Meta's callback verification (GET) runs when the
	# callback is saved, normally before the gateway is enabled.
	if not gateway.is_enabled:
		frappe.local.response.http_status_code = 403
		return {"success": False, "error": "Gateway is disabled"}
	batched = _supports_batch_parse(adapter)
	if not batched:
		_ingest_rate_gate()
	if not adapter.verify_inbound(request):
		if batched:
			_ingest_rate_gate()  # forged/unsigned traffic still consumes the budget
		if _has_webhook_signals(gateway):
			_record_webhook_signal(gateway, "last_signature_failure_at")
		frappe.local.response.http_status_code = 401
		return {"success": False, "error": "Provider verification failed"}
	if batched:
		return _handle_batched_payload(gateway, adapter, request)

	ingest_hook = provider_hooks.get(gateway.provider, "ingest_update")
	if ingest_hook is not None:
		handled = ingest_hook(gateway, adapter, request)
		if handled is not None:
			return handled

	event = adapter.normalize_inbound(request)
	frappe.local.gateway_response_override = None  # never inherit a stale override
	result = ingest_gateway_event(
		gateway.name,
		event.provider_event_id,
		_event_context(event),
		verified_sender=True,
		raw_payload=dict(event.raw_payload),
	)
	override = _take_response_override()
	if override is not None:
		return override
	if isinstance(result, dict) and result.get("duplicate"):
		duplicate = _duplicate_invoke_response(gateway, event)
		if duplicate is not None:
			return duplicate
	if not result.get("duplicate"):
		touch_last_event(gateway)
	return {"success": True, **result}


def _duplicate_invoke_response(gateway, event):
	"""A redelivered Teams card click still needs a proper invoke response body, not our JSON.

	Ingest short-circuits duplicates before any filter runs, so no hook set an override. The
	adapter-tagged ``huf_kind`` identifies the activity; the Teams handler answers read-only.
	"""
	raw = getattr(event, "raw_payload", None)
	if not isinstance(raw, dict) or raw.get("huf_kind") != "card_action":
		return None
	try:
		from huf.ai.gateways import teams_actions

		frappe.local.gateway_response_override = None
		teams_actions.duplicate_card_response(gateway, raw)
		return _take_response_override()
	except Exception:
		return None


def _take_response_override():
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


def event_contact_name(event) -> str:
	"""The sender's profile name recorded on the inbound event (empty when unknown)."""
	raw = getattr(event, "raw_payload", None)
	if isinstance(raw, str):
		try:
			raw = json.loads(raw)
		except ValueError:
			raw = None
	return str(raw.get("contact_name") or "").strip() if isinstance(raw, dict) else ""


def send_gateway_reply(gateway, event, text: str, *, sleep=None, max_attempts: int = SEND_MAX_ATTEMPTS):
	"""Deliver one completed Agent response through the same verified gateway.

	Transient failures (429/5xx/timeouts) are retried with exponential backoff up to
	``max_attempts``; permanent errors raise immediately. Once the adapter returns a
	receipt nothing is re-sent. Returns the adapter's delivery receipt.
	"""
	import time

	from huf.ai.gateway_adapters.types import GatewayReply

	sleep = sleep or time.sleep
	adapter = get_gateway_adapter(gateway, event_contact_name(event))
	target_hook = provider_hooks.get(gateway.provider, "reply_target")
	if target_hook is not None:
		thread_id, reply_to = target_hook(event)
	else:
		thread_id = event.thread_id or None
		reply_to = event.thread_id or None
	reply = GatewayReply(
		conversation_id=event.conversation_id,
		text=text,
		thread_id=thread_id,
		reply_to_provider_message_id=reply_to,
	)
	attempt = 0
	while True:
		attempt += 1
		try:
			return adapter.send_reply(reply)
		except Exception as exc:
			if attempt >= max(1, max_attempts) or not _is_transient_send_error(exc):
				raise
			sleep(_send_retry_delay(exc, attempt))


def send_gateway_parts(gateway, event, parts: list[str], *, quote: bool = True):
	"""Send already formatted WhatsApp text parts in order (reply send/retry path).

	``quote`` puts the reply-to context on the first part only; pass False when an earlier part was
	already delivered. Raises ``WhatsAppPartsError`` carrying what was sent and what remains.
	"""
	return provider_hooks.call(gateway.provider, "send_parts", gateway, event, parts, quote)


def mark_gateway_read_typing(gateway, event) -> bool:
	"""Best-effort read receipt + typing indicator for the inbound message. Never raises."""
	try:
		if not event.provider_event_id:
			return False
		hook = provider_hooks.get(gateway.provider, "mark_read_typing")
		if hook is None:
			return False
		return bool(hook(get_gateway_adapter(gateway), event.provider_event_id))
	except Exception:
		return False
