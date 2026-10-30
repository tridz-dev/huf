# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Messaging limit, quality and throughput for a WhatsApp gateway, and the pre-start preview of a Broadcast.

``get_messaging_limit`` reads one phone-number node with the gateway's own credentials
(``token_check.resolve_credentials`` mirrors the gateway adapter; ``token_check._call`` is the
same Graph call path used by the token check). Results are cached for ``limits_cache_ttl_seconds`` (policy). Failures
of any kind return all-None and are never raised, so a Meta outage can never break a
broadcast preview. The token is never returned, logged or cached.

``preview`` combines that limit with the Broadcast's own rows and template and returns
``warnings`` (overridable: the operator acknowledges each ``code`` at start) and ``blocking``
(start must not proceed). Both are lists of ``{code, message, limit_key}``; ``limits_in_effect``
lists the registry keys that shaped this broadcast. Consent and the one-running-per-gateway rule
are only *reported* here; ``runner.start`` enforces them under a row lock.

Meta facts used (checked 2026-10-27 against developers.facebook.com docs):
* Field ``whatsapp_business_manager_messaging_limit`` on the phone-number node, read with
  ``GET /<PHONE_NUMBER_ID>?fields=...`` (messaging-limits page; the example response is
  ``"TIER_250"``). The page says the older ``messaging_limit_tier`` is deprecated.
  VERIFIED: only ``TIER_250`` appears in the fetched text. The mapping of ``TIER_1K``,
  ``TIER_2K``, ``TIER_10K``, ``TIER_100K`` and ``TIER_UNLIMITED`` to 1000, 2000, 10000,
  100000 and unlimited follows the CONTRACT and the Meta tier list (250, 2K, 10K, 100K,
  unlimited); the enum spellings are UNVERIFIED beyond ``TIER_250``.
* Field ``quality_rating`` (throughput page and phone-number reference). Values seen in
  the docs are GREEN, NA and UNKNOWN; YELLOW and RED are the quality levels the policy
  text uses. Any other value is treated as unknown.
* Field ``throughput`` (throughput page, ``GET ...?fields=throughput``). Default 80 mps,
  auto-upgrade to 1000 mps, and a fixed 20 mps for WhatsApp Business app numbers. The
  VALUE SHAPE is UNVERIFIED (no sample response on the page), so ``mps`` is taken only
  from an integer value or an integer ``mps`` key and is otherwise None.
"""

from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import add_to_date, now_datetime

from huf.ai.whatsapp import token_check as tc
from huf.ai.whatsapp.broadcast import policy
from huf.ai.whatsapp.broadcast.checks import audience_check

LOGGER = "huf.whatsapp.broadcast"
LIMIT_FIELD = "whatsapp_business_manager_messaging_limit"
FIELDS = f"{LIMIT_FIELD},quality_rating,throughput"
UNLIMITED = "TIER_UNLIMITED"
TIER_MAX_UNIQUE_24H: dict[str, int] = {
	"TIER_250": 250,
	"TIER_1K": 1000,
	"TIER_2K": 2000,
	"TIER_10K": 10000,
	"TIER_100K": 100000,
}
QUALITY_VALUES = ("GREEN", "YELLOW", "RED")
SENT_STATUSES = ("sent", "delivered", "read", "unknown")


def _empty() -> dict[str, Any]:
	return {"tier": None, "max_unique_24h": None, "quality": None, "mps": None, "raw": {}}


def _max_for(tier: str | None) -> int | None:
	"""Unique users per 24h for a tier; None when unknown or unlimited."""
	if not tier or tier == UNLIMITED:
		return None
	return TIER_MAX_UNIQUE_24H.get(tier)


def _mps(throughput: Any) -> int | None:
	if isinstance(throughput, bool):
		return None
	if isinstance(throughput, int):
		return throughput
	if isinstance(throughput, dict):
		mps = throughput.get("mps")
		if isinstance(mps, int) and not isinstance(mps, bool):
			return mps
	return None


def _parse(body: dict[str, Any]) -> dict[str, Any]:
	tier = str(body.get(LIMIT_FIELD) or "").strip().upper() or None
	quality = str(body.get("quality_rating") or "").strip().upper()
	return {
		"tier": tier,
		"max_unique_24h": _max_for(tier),
		"quality": quality if quality in QUALITY_VALUES else None,
		"mps": _mps(body.get("throughput")),
		"raw": {k: body.get(k) for k in (LIMIT_FIELD, "quality_rating", "throughput")},
	}


def _cache_key(gateway: str) -> str:
	return f"huf:wa_messaging_limit:{gateway}"


def _fetch(gateway: str) -> dict[str, Any] | None:
	"""Graph GET for the gateway's phone number; None on any failure (never raises on Meta errors)."""
	creds = tc.resolve_credentials(gateway)
	phone_id = creds.get("phone_id") or ""
	if not phone_id:
		return None
	try:
		status, body = tc._call(
			tc.default_http_get,
			f"{creds['base']}/{phone_id}",
			params={"fields": FIELDS},
			headers={"Authorization": f"Bearer {creds['token']}"},
		)
	except (tc._Timeout, tc._Transport):
		return None
	if tc._error_of(status, body) is not None:
		return None
	return _parse(body)


def get_messaging_limit(gateway: str) -> dict[str, Any]:
	"""Messaging tier, unique-user cap per 24h, quality and mps for the gateway's number. Never raises."""
	try:
		if not gateway or not frappe.db.exists("Gateway", gateway):
			return _empty()
		cache = frappe.cache()
		cached = cache.get_value(_cache_key(gateway), expires=True)
		if isinstance(cached, dict):
			return dict(cached)
		result = _fetch(gateway)
		if result is None:
			return _empty()
		cache.set_value(_cache_key(gateway), result, expires_in_sec=int(policy.get("limits_cache_ttl_seconds")))
		return dict(result)
	except Exception as exc:  # noqa: BLE001 - class name only; messages can carry URLs or tokens
		frappe.logger(LOGGER).warning("messaging limit unavailable (%s)", type(exc).__name__)
		return _empty()


def _is_us_plus_one(number: Any) -> bool:
	text = str(number or "")
	return text.isdigit() and len(text) == 11 and text.startswith("1")


def _broadcast_row(broadcast: str) -> dict[str, Any] | None:
	if not frappe.db.exists("WhatsApp Broadcast", broadcast):
		return None
	return frappe.db.get_value(
		"WhatsApp Broadcast",
		broadcast,
		["gateway", "template", "consent_attested", "body_params", "header_params", "button_params", "max_recipients"],
		as_dict=True,
	)


def _template_row(template: str) -> dict[str, Any] | None:
	if not template or not frappe.db.exists("WhatsApp Templates", template):
		return None
	return frappe.db.get_value("WhatsApp Templates", template, ["status", "category"], as_dict=True)


def _recipient_counts(broadcast: str) -> dict[str, int]:
	rows = frappe.db.sql(
		"select status, count(*) from `tabWhatsApp Broadcast Recipient` where broadcast=%s group by status",
		broadcast,
	)
	return {str(status): int(n) for status, n in rows}


def _queued_numbers(broadcast: str) -> list[str]:
	rows = frappe.db.sql(
		"select recipient from `tabWhatsApp Broadcast Recipient` where broadcast=%s and status='queued'",
		broadcast,
	)
	return [str(r[0] or "") for r in rows]


def _running_others(gateway: str, broadcast: str, locked: bool = False) -> list[str]:
	"""Other Running broadcasts on the gateway; ``locked`` = locking read (sees just-committed starts)."""
	rows = frappe.db.sql(
		"select name from `tabWhatsApp Broadcast` "
		"where gateway=%s and status='Running' and name!=%s order by name" + (" for update" if locked else ""),
		(gateway, broadcast),
	)
	return [str(r[0]) for r in rows]


def _used_24h(gateway: str, broadcast: str | None = None, others: list[str] | None = None) -> int:
	"""Unique recipients that count against the gateway's 24h budget.

	Counted: started in the last 24h by ANY broadcast on the gateway. Reserved: recipients still
	waiting (queued, or deferred for retry) in the OTHER Running broadcasts ``others``, so two
	concurrent broadcasts cannot both claim the same remaining budget. Rows held for the next
	window (``next_attempt_at`` in the future) reserve nothing. One recipient counts once."""
	now = now_datetime()
	params: dict[str, Any] = {"gateway": gateway, "cutoff": add_to_date(now, hours=-24), "now": now}
	reserved = ""
	if others:
		marks = ",".join(f"%(o{i})s" for i in range(len(others)))
		params.update({f"o{i}": name for i, name in enumerate(others)})
		reserved = (
			"union select r.recipient from `tabWhatsApp Broadcast Recipient` r "
			f"where r.broadcast in ({marks}) and (r.status = 'deferred' or "
			"(r.status = 'queued' and (r.next_attempt_at is null or r.next_attempt_at <= %(now)s)))"
		)
	row = frappe.db.sql(
		f"""
		select count(*) from (
		  select r.recipient
		  from `tabWhatsApp Broadcast Recipient` r
		  join `tabWhatsApp Broadcast` b on b.name = r.broadcast
		  where b.gateway = %(gateway)s
		    and (
		      (r.status in ('sent','delivered','read','unknown') and r.sent_at >= %(cutoff)s)
		      or (r.status = 'sending' and r.modified >= %(cutoff)s)
		    )
		  {reserved}
		) u
		""",
		params,
	)
	return int(row[0][0]) if row else 0


def oldest_counted_send(gateway: str):
	"""Time of the oldest send inside the 24h budget window on this gateway (None when nothing counts)."""
	cutoff = add_to_date(now_datetime(), hours=-24)
	row = frappe.db.sql(
		"""
		select min(coalesce(r.sent_at, r.modified))
		from `tabWhatsApp Broadcast Recipient` r
		join `tabWhatsApp Broadcast` b on b.name = r.broadcast
		where b.gateway = %(gateway)s
		  and (
		    (r.status in ('sent','delivered','read','unknown') and r.sent_at >= %(cutoff)s)
		    or (r.status = 'sending' and r.modified >= %(cutoff)s)
		  )
		""",
		{"gateway": gateway, "cutoff": cutoff},
	)
	return row[0][0] if row and row[0][0] else None


# template parameters: see template_check (re-exported here)
from huf.ai.whatsapp.broadcast.checks.template_check import _loads, _samples, send_problems, template_requirements  # noqa: E402,F401


def _queued_params(broadcast: str) -> list[tuple[str | None, int]]:
	"""Distinct raw ``params`` of queued/deferred recipients with how many recipients carry each."""
	rows = frappe.db.sql(
		"select params, count(*) from `tabWhatsApp Broadcast Recipient` "
		"where broadcast=%s and status in ('queued','deferred') group by params",
		broadcast,
	)
	return [(r[0], int(r[1])) for r in rows]


def _issue(code: str, message: str, limit_key: str | None = None) -> dict[str, Any]:
	return {"code": code, "message": message, "limit_key": limit_key}


def _gateway_disconnected(gateway: str) -> str | None:
	"""Reason text when the gateway's WhatsApp account is Disconnected (sends are refused), else None."""
	row = frappe.db.get_value("Gateway", gateway, ["connection_state", "connection_reason"], as_dict=True) or {}
	if row.get("connection_state") != "Disconnected":
		return None
	return str(row.get("connection_reason") or "This WhatsApp account is disconnected; reconnect it before sending.")


def _check_params(b: dict[str, Any], broadcast: str, blocking: list[dict[str, Any]]) -> None:
	"""Block when a queued/deferred recipient would be refused at send time for its template parameters."""
	req = template_requirements(b.get("template") or "")
	if not req:
		return
	from huf.ai.whatsapp.broadcast.send import _merge_params

	n_missing = n_extra = n_invalid = 0
	missing: list[str] = []
	extra: list[str] = []
	invalid: list[str] = []
	for raw, count in _queued_params(broadcast):
		body, header, button = _merge_params(b, {"params": raw})
		found = send_problems(req, body, header, button)
		if found["missing"]:
			n_missing += count
			missing += found["missing"]
		if found["extra"]:
			n_extra += count
			extra += found["extra"]
		if found["invalid"]:
			n_invalid += count
			invalid += found["invalid"]
	uniq = lambda xs: ", ".join(dict.fromkeys(xs))  # noqa: E731
	if n_missing:
		blocking.append(_issue("missing_params", f"{n_missing} recipients are missing values for template variables: {uniq(missing)}"))
	if n_extra:
		# the bridge refuses these too (param_unknown / count mismatch), so they block rather than warn
		blocking.append(_issue("missing_params", f"{n_extra} recipients carry values the template does not use: {uniq(extra)}"))
	if n_invalid:
		blocking.append(_issue("missing_params", f"{n_invalid} recipients have invalid template values: {uniq(invalid)}"))


def _fill(broadcast: str, out: dict[str, Any], locked: bool = False) -> None:
	b = _broadcast_row(broadcast)
	if not b:
		out["blocking"].append(_issue("broadcast_not_found", "This broadcast does not exist."))
		return
	warnings: list[dict[str, Any]] = out["warnings"]
	blocking: list[dict[str, Any]] = out["blocking"]
	in_effect: set[str] = set()

	counts = _recipient_counts(broadcast)
	out["recipients"] = sum(counts.values())
	out["queued"] = counts.get("queued", 0)
	out["skipped"] = counts.get("skipped", 0)
	if policy.resolve("max_recipients_default", b)[1] != "default":  # the broadcast's own cap OR a saved setting
		in_effect.add("max_recipients_default")
	if out["queued"] + counts.get("deferred", 0) <= 0:
		blocking.append(_issue("no_recipients", "There are no recipients waiting to be sent."))

	tpl = _template_row(b.get("template") or "")
	if not tpl:
		blocking.append(_issue("template_unavailable", "The template for this broadcast no longer exists."))
	else:
		tpl_status = str(tpl.get("status") or "").strip().upper()
		out["template_status"] = tpl_status or None
		out["category"] = str(tpl.get("category") or "").strip().upper() or None
		in_effect.add("template_approved_only")
		if tpl_status != "APPROVED":
			blocking.append(_issue(
				"template_not_approved",
				f"The template is {tpl_status.lower() or 'not approved'}; Meta only delivers approved templates.",
				"template_approved_only",
			))

	if tpl:
		_check_params(b, broadcast, blocking)
		blocking.extend(audience_check.purpose_issues(broadcast, out["category"]))

	if out["category"] == "MARKETING":
		us = [n for n in _queued_numbers(broadcast) if _is_us_plus_one(n)]
		if us:
			in_effect.add("us_plus_one_marketing")
			warnings.append(_issue(
				"us_plus_one_marketing",
				f"{len(us)} queued recipient(s) are US +1 numbers; WhatsApp does not deliver marketing templates to them.",
				"us_plus_one_marketing",
			))

	if policy.get("require_consent_attestation"):
		in_effect.add("require_consent_attestation")
		if not b.get("consent_attested"):
			blocking.append(_issue(
				"consent_not_attested", "Confirm that these recipients opted in before sending.", "require_consent_attestation"
			))

	gateway = b.get("gateway") or ""
	reason = _gateway_disconnected(gateway) if gateway else None
	if reason:
		blocking.append(_issue("gateway_disconnected", reason))

	others = _running_others(gateway, broadcast, locked)
	cap = policy.concurrency_cap()
	key = "one_active_per_gateway" if policy.get("one_active_per_gateway") else "concurrent_broadcast_max"
	if cap is not None:
		in_effect.add(key)
	if cap is not None and len(others) >= cap:
		blocking.append(_issue(
			"another_broadcast_running",
			("Another broadcast is already sending from this gateway: " if cap == 1
				else f"This gateway already runs {len(others)} broadcasts (limit {cap}): ") + ", ".join(others),
			key,
		))
	elif others:
		warnings.append(_issue(
			"other_broadcast_running",
			"Other broadcasts are sending from this gateway at the same time and share its sending speed: "
			+ ", ".join(others),
			"one_active_per_gateway",
		))

	limit = get_messaging_limit(gateway)
	if limit["quality"]:
		in_effect.add("quality_rating")
	if limit["quality"] == "RED":
		warnings.append(_issue(
			"quality_red",
			"Number quality is RED. Sending more can lower your messaging limit or get the number restricted.",
			"quality_rating",
		))
	elif limit["quality"] == "YELLOW":
		warnings.append(_issue("quality_yellow", "Number quality is YELLOW; sends may be throttled.", "quality_rating"))

	if limit["tier"] == UNLIMITED:
		out["remaining_24h"] = None
		out["within_limit"] = True
	elif limit["max_unique_24h"] is None:
		out["remaining_24h"] = None
		out["within_limit"] = None
		in_effect.add("messaging_tier_24h")
		warnings.append(_issue(
			"tier_unknown", "Messaging limit is unknown; the 24h budget was not checked.", "messaging_tier_24h"
		))
	else:
		in_effect.add("messaging_tier_24h")
		remaining = max(limit["max_unique_24h"] - _used_24h(gateway, broadcast, others), 0)
		out["remaining_24h"] = remaining
		out["within_limit"] = out["queued"] <= remaining
		if not out["within_limit"]:
			warnings.append(_issue(
				"over_budget",
				f"{out['queued']} recipients are queued but only {remaining} fit in your 24-hour messaging limit. "
				f"Continuing sends the first {remaining} now and holds the rest for the next 24 hours.",
				"messaging_tier_24h",
			))
	out["limits_in_effect"] = sorted(in_effect)


def preview(broadcast: str, locked: bool = False) -> dict[str, Any]:
	"""Pre-start check of a Broadcast. Never raises; unexpected errors become a blocking entry."""
	out: dict[str, Any] = {
		"recipients": 0,
		"queued": 0,
		"skipped": 0,
		"category": None,
		"template_status": None,
		"within_limit": None,
		"remaining_24h": None,
		"warnings": [],
		"blocking": [],
		"limits_in_effect": [],
	}
	try:
		_fill(broadcast or "", out, locked)
	except Exception as exc:  # noqa: BLE001 - class name only
		frappe.logger(LOGGER).warning("broadcast preview failed (%s)", type(exc).__name__)
		out["blocking"].append(_issue("preview_failed", "The pre-start check failed; try again."))
	return out
