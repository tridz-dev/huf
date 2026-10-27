"""Durable Teams outbox (WP T6).

Every Teams delivery is persisted as a ``Teams Outbound Message`` row first and then
sent by ``deliver``. Failures are retried with backoff by ``retry_due`` (scheduler,
every minute). Only the *delivery* is retried; business transactions are never re-run.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from typing import Any, Callable, Mapping

import frappe

DOCTYPE = "Teams Outbound Message"
KINDS = ("reply", "card", "card_update", "proactive")

# Delay (seconds) before attempt N+1 after the Nth transient failure.
BACKOFF_SECONDS = (30, 120, 600, 1800, 7200)
MAX_ATTEMPTS = 6
MAX_RETRY_AFTER = 6 * 3600
CLAIM_LEASE_SECONDS = 300
MAX_ERROR_LEN = 500

_SECRET_KEY_RE = re.compile(
	r"(token|authorization|secret|password|passwd|api[_-]?key|credential|bearer|client[_-]?secret)",
	re.IGNORECASE,
)
_SECRET_VALUE_RES = (
	re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+"),
	re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]*"),
	re.compile(r"(?i)((?:access_token|client_secret|password|authorization|api[_-]?key)\s*[=:]\s*)[^\s&\"',;]+"),
)
REDACTED = "[REDACTED]"


# --------------------------------------------------------------------- redaction


def redact_payload(payload: Any) -> Any:
	"""Return a deep copy with token/authorization/secret-like keys and bearer values masked."""
	if isinstance(payload, Mapping):
		out = {}
		for k, v in payload.items():
			out[k] = REDACTED if _SECRET_KEY_RE.search(str(k)) else redact_payload(v)
		return out
	if isinstance(payload, (list, tuple)):
		return [redact_payload(v) for v in payload]
	if isinstance(payload, str):
		return _scrub_text(payload)
	return payload


def _scrub_text(text: str) -> str:
	text = _SECRET_VALUE_RES[0].sub("Bearer " + REDACTED, text)
	text = _SECRET_VALUE_RES[1].sub(REDACTED, text)
	return _SECRET_VALUE_RES[2].sub(lambda m: m.group(1) + REDACTED, text)


def _safe_error(exc: BaseException) -> str:
	return _scrub_text(f"{type(exc).__name__}: {exc}")[:MAX_ERROR_LEN]


# ----------------------------------------------------------------- classification


def _status_of(exc: BaseException) -> int | None:
	for obj in (exc, getattr(exc, "response", None)):
		for attr in ("status", "status_code", "http_status"):
			v = getattr(obj, attr, None) if obj is not None else None
			if isinstance(v, int) and not isinstance(v, bool):
				return v
	return None


def is_transient(exc: BaseException) -> bool:
	"""429/5xx/timeouts/transport are transient; other 4xx and validation errors are permanent.

	Unknown exception types are treated as transient (bounded by MAX_ATTEMPTS).
	"""
	if isinstance(exc, (TimeoutError, ConnectionError)):
		return True
	if type(exc).__name__ in ("Timeout", "ReadTimeout", "ConnectTimeout", "ConnectionError"):
		return True
	status = _status_of(exc)
	if status is not None:
		return status == 429 or 500 <= status < 600
	if isinstance(exc, (ValueError, TypeError, KeyError, PermissionError, NotImplementedError)):
		return False
	return True


def retry_delay(exc: BaseException | None, attempt: int) -> int:
	"""Seconds to wait after failed attempt number ``attempt`` (1-based)."""
	hint = getattr(exc, "retry_after", None) if exc is not None else None
	if hint is not None:
		try:
			return int(max(0.0, min(float(hint), MAX_RETRY_AFTER)))
		except (TypeError, ValueError):
			pass
	return BACKOFF_SECONDS[min(max(attempt, 1), len(BACKOFF_SECONDS)) - 1]


# ---------------------------------------------------------------------- db layer


def _now() -> datetime:
	return datetime.now()


def _dup_errors() -> tuple:
	e = getattr(frappe, "DuplicateEntryError", None)
	return (e,) if isinstance(e, type) else ()


def _find_by_key(key: str) -> str | None:
	return frappe.db.get_value(DOCTYPE, {"idempotency_key": key}, "name")


def _insert(values: dict) -> str:
	doc = frappe.get_doc({"doctype": DOCTYPE, **values})
	doc.insert(ignore_permissions=True)
	return doc.name


def _load(name: str) -> dict | None:
	return frappe.db.get_value(DOCTYPE, name, "*", as_dict=True) or None


def _update(name: str, values: dict) -> None:
	frappe.db.set_value(DOCTYPE, name, values, update_modified=False)


def _claim(name: str, now: datetime) -> bool:
	"""Atomically lease a due Pending row. Exactly one concurrent caller gets True."""
	lease = now + timedelta(seconds=CLAIM_LEASE_SECONDS)
	frappe.db.sql(
		"UPDATE `tabTeams Outbound Message` SET next_attempt_at=%s "
		"WHERE name=%s AND status='Pending' AND (next_attempt_at IS NULL OR next_attempt_at<=%s)",
		(lease, name, now),
	)
	return _rowcount() > 0


def _rowcount() -> int:
	return int(frappe.db.sql("SELECT ROW_COUNT()")[0][0])


def _due_names(now: datetime, limit: int) -> list[str]:
	rows = frappe.get_all(
		DOCTYPE,
		filters={"status": "Pending", "next_attempt_at": ("<=", now)},
		fields=["name"],
		order_by="next_attempt_at asc",
		limit_page_length=limit,
	)
	null_rows = []
	if len(rows) < limit:
		null_rows = frappe.get_all(
			DOCTYPE,
			filters={"status": "Pending", "next_attempt_at": ("is", "not set")},
			fields=["name"],
			limit_page_length=limit - len(rows),
		)
	return [r["name"] for r in list(rows) + list(null_rows)]


def _enqueue_job(method: str, **kwargs) -> None:
	frappe.enqueue(method, queue="short", enqueue_after_commit=True, **kwargs)


# --------------------------------------------------------------------- public API


def enqueue(
	gateway: str,
	snapshot: Mapping[str, Any] | None,
	kind: str,
	payload: Mapping[str, Any],
	idempotency_key: str,
) -> str:
	"""Persist an outbound message (idempotent on ``idempotency_key``) and schedule delivery.

	``snapshot`` carries ``conversation_ref``/``conversation_id``/``service_url``/``tenant_id`` so
	the row is self-contained. Never raises from the delivery scheduling step.
	"""
	if kind not in KINDS:
		raise ValueError(f"Unknown outbox kind: {kind!r}")
	if not idempotency_key:
		raise ValueError("idempotency_key is required")
	existing = _find_by_key(idempotency_key)
	if existing:
		return existing
	snap = dict(snapshot or {})
	values = {
		"gateway": gateway,
		"kind": kind,
		"status": "Pending",
		"idempotency_key": idempotency_key,
		"conversation_ref": snap.get("conversation_ref"),
		"conversation_id": snap.get("conversation_id"),
		"service_url": snap.get("service_url"),
		"tenant_id": snap.get("tenant_id"),
		"payload": json.dumps(redact_payload(dict(payload or {}))),
		"attempts": 0,
		"next_attempt_at": _now(),
	}
	try:
		name = _insert(values)
	except _dup_errors():
		name = _find_by_key(idempotency_key)
		if not name:
			raise
		return name
	_schedule_delivery(name)
	return name


def _schedule_delivery(name: str) -> None:
	try:
		_enqueue_job("huf.ai.gateways.teams_outbox.deliver", name=name)
	except Exception:
		# Row is durable; retry_due will pick it up. Never break the caller.
		try:
			frappe.log_error(title="Teams outbox: enqueue delivery failed", message=name)
		except Exception:
			pass


class MissingCredentialsError(ValueError):
	"""The gateway has no usable Teams credentials. Permanent (not retried); secret-free."""


def _gateway_creds(gateway_name: str | None) -> dict:
	"""app_id / app_password / tenant_id from the Integration Settings linked to the gateway."""
	if not gateway_name:
		raise MissingCredentialsError("Teams outbox row has no gateway; cannot obtain credentials")
	try:
		from huf.ai.gateways import teams_tenant

		gateway = frappe.get_doc("Gateway", gateway_name)
		creds = {key: teams_tenant.get_gateway_credential(gateway, key) for key in CRED_KEYS}
	except MissingCredentialsError:
		raise
	except Exception as exc:
		raise MissingCredentialsError(
			f"Teams credentials for gateway {gateway_name!r} could not be loaded ({type(exc).__name__})"
		) from None
	missing = [k for k in CRED_KEYS if not creds.get(k)]
	if missing:
		raise MissingCredentialsError(
			f"Teams credentials for gateway {gateway_name!r} are incomplete: missing {', '.join(missing)}"
		)
	return creds


CRED_KEYS = ("app_id", "app_password", "tenant_id")


def _default_sender(
	kind: str,
	snapshot: Mapping[str, Any],
	payload: Mapping[str, Any],
	*,
	http: Callable | None = None,
) -> str:
	try:
		from huf.ai.gateways import teams_api  # type: ignore
	except Exception as exc:  # fail closed
		raise NotImplementedError("teams_api is not available; cannot deliver Teams message") from exc
	gateway_name = snapshot.get("gateway")
	creds = _gateway_creds(gateway_name)
	token = teams_api.make_token_provider(creds, gateway_name=gateway_name, http=http)
	service_url, conv = snapshot.get("service_url"), snapshot.get("conversation_id")
	if kind == "card_update":
		res = teams_api.update_activity(
			service_url,
			conv,
			payload.get("activity_id"),
			payload.get("activity", payload),
			token=token,
			http=http,
		)
	else:
		res = teams_api.post_activity(
			service_url, conv, payload.get("activity", payload), token=token, http=http
		)
	pid = res.get("id") if isinstance(res, Mapping) else res
	return str(pid or "")


def deliver(
	name: str,
	*,
	sender: Callable[[str, Mapping[str, Any], Mapping[str, Any]], str] | None = None,
	now: datetime | None = None,
	sleep: Callable[[float], None] | None = None,
	http: Callable | None = None,
) -> str:
	"""Attempt delivery of one row. Returns the resulting status (or "Skipped" if not claimed)."""
	now = now or _now()
	row = _load(name)
	if not row or row.get("status") != "Pending":
		return "Skipped"
	if not _claim(name, now):
		return "Skipped"
	payload = row.get("payload") or {}
	if isinstance(payload, str):
		try:
			payload = json.loads(payload)
		except ValueError:
			payload = {}
	snapshot = {
		k: row.get(k) for k in ("conversation_ref", "conversation_id", "service_url", "tenant_id", "gateway")
	}
	attempts = int(row.get("attempts") or 0) + 1
	try:
		if sender is not None:
			pid = sender(row.get("kind"), snapshot, payload)
		else:
			pid = _default_sender(row.get("kind"), snapshot, payload, http=http)
	except Exception as exc:
		return _record_failure(name, exc, attempts, now)
	if row.get("kind") == "card":
		_record_card_activity(payload, pid)
	_update(
		name,
		{
			"status": "Sent",
			"attempts": attempts,
			"provider_message_id": str(pid or ""),
			"sent_at": now,
			"last_error": None,
		},
	)
	return "Sent"


def _record_card_activity(payload: Mapping[str, Any], activity_id: Any) -> None:
	"""Remember the delivered card's activity id on its Teams Action Session (best effort)."""
	session = payload.get("action_session") if isinstance(payload, Mapping) else None
	if not (session and activity_id):
		return
	try:
		from huf.ai.gateways import teams_actions

		teams_actions.record_card_activity(str(session), str(activity_id))
	except Exception:
		try:
			frappe.log_error(title="Teams outbox: recording card activity id failed")
		except Exception:
			pass


def _record_failure(name: str, exc: BaseException, attempts: int, now: datetime) -> str:
	values: dict = {"attempts": attempts, "last_error": _safe_error(exc)}
	if not is_transient(exc):
		values["status"] = "Failed"
	elif attempts >= MAX_ATTEMPTS:
		values["status"] = "Dead"
	else:
		values["status"] = "Pending"
		values["next_attempt_at"] = now + timedelta(seconds=retry_delay(exc, attempts))
	_update(name, values)
	return values["status"]


def retry_due(limit: int = 50, now: datetime | None = None) -> list[str]:
	"""Scheduler entry: enqueue delivery for Pending rows whose next_attempt_at has passed."""
	names = _due_names(now or _now(), limit)[:limit]
	for n in names:
		_schedule_delivery(n)
	return names
