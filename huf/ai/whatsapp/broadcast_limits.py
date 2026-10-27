# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Messaging limit, quality and throughput for a WhatsApp gateway, and the pre-start preview of a Broadcast.

``get_messaging_limit`` reads one phone-number node with the gateway's own credentials
(``token_check.resolve_credentials`` mirrors the gateway adapter; ``token_check._call`` is the
same Graph call path used by the token check). Results are cached 10 minutes. Failures
of any kind return all-None and are never raised, so a Meta outage can never break a
broadcast preview. The token is never returned, logged or cached.

``preview`` combines that limit with the Broadcast's own rows and template and returns
``warnings`` (advisory) and ``blocking`` (start must not proceed).

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

LOGGER = "huf.whatsapp.broadcast"
CACHE_TTL_SECONDS = 600
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
		cached = cache.get_value(_cache_key(gateway))
		if isinstance(cached, dict):
			return dict(cached)
		result = _fetch(gateway)
		if result is None:
			return _empty()
		cache.set_value(_cache_key(gateway), result, expires_in_sec=CACHE_TTL_SECONDS)
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
		["gateway", "template", "consent_attested", "body_params", "header_params", "button_params"],
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


def _running_others(gateway: str, broadcast: str) -> list[str]:
	rows = frappe.db.sql(
		"select name from `tabWhatsApp Broadcast` "
		"where gateway=%s and status='Running' and name!=%s order by name",
		(gateway, broadcast),
	)
	return [str(r[0]) for r in rows]


def _used_24h(gateway: str) -> int:
	"""Unique recipients already started in the last 24h by ANY broadcast on this gateway."""
	cutoff = add_to_date(now_datetime(), hours=-24)
	row = frappe.db.sql(
		"""
		select count(distinct r.recipient)
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
	return int(row[0][0]) if row else 0


# ---------------------------------------------------------------- template parameters


def _loads(value: Any) -> Any:
	"""Same decoding as broadcast_send._json (JSON string -> value, blank -> None)."""
	from huf.ai.whatsapp.broadcast_send import _json

	return _json(value)


def _samples(account: str | None, template: str, view: dict[str, Any]) -> dict[str, str]:
	"""``{variable: sample}`` for the body, from the Template Extra (named_samples / components_json)."""
	from huf.ai.gateway_adapters import whatsapp_template_guard as guard

	try:
		extra = guard.get_extra(account, template) or {}
	except Exception:  # noqa: BLE001
		extra = {}
	out: dict[str, str] = {}
	for item in extra.get("named_samples") or []:
		if isinstance(item, dict) and item.get("name"):
			out[str(item["name"])] = str(item.get("example") or "")
	if not out:
		for comp in extra.get("components_json") or []:
			if isinstance(comp, dict) and str(comp.get("type") or "").upper() == "BODY":
				rows = (comp.get("example") or {}).get("body_text") or []
				for i, val in enumerate(rows[0] if rows else []):
					out[str(i + 1)] = str(val)
	return out


def template_requirements(template: str) -> dict[str, Any] | None:
	"""What a send of WhatsApp Templates row ``template`` needs, derived with the bridge's own helpers.

	``{"tpl", "view", "parameter_format", "body": [{name|index, sample}], "header": {...}|None,
	"buttons": [...]}`` or None when the row does not exist.
	"""
	from huf.ai.gateway_adapters import whatsapp_bridge as bridge
	from huf.ai.gateway_adapters import whatsapp_templates as wt

	tpl = bridge._template_row(template or "")
	if not tpl:
		return None
	view = bridge._send_view(tpl)
	tv = wt._template_view(view)
	named = tv["fmt"] == "NAMED"
	samples = _samples(tpl.get("whatsapp_account"), template, view)
	body = [
		({"name": v, "sample": samples.get(v)} if named else {"index": int(v), "sample": samples.get(v)})
		for v in tv["body_vars"]
	]
	htype = tv["header_type"]
	header: dict[str, Any] | None = None
	if htype in ("", "TEXT") and tv["header_vars"]:
		v = tv["header_vars"][0]
		header = {"type": "TEXT", "required": True, ("name" if named else "index"): v if named else int(v), "sample": None}
	elif htype in wt.MEDIA_HEADER_TYPES:
		has_default = htype == "IMAGE" and wt.is_http_url(str(tpl.get("sample") or ""))
		header = {"type": htype, "required": not has_default}
	elif htype == "LOCATION":
		header = {"type": htype, "required": True}
	buttons = []
	for i, b in enumerate(tpl.get("buttons") or []):
		kind = b.get("button_type")
		if kind == "Visit Website" and b.get("url_type") == "Dynamic":
			buttons.append({"index": i, "sub_type": "url", "required": True, "label": b.get("button_label")})
		elif kind == wt.DOCTYPE_BUTTON_TYPE["COPY_CODE"]:
			buttons.append({"index": i, "sub_type": "copy_code", "required": True, "label": b.get("button_label")})
		elif kind == "Quick Reply":
			buttons.append({"index": i, "sub_type": "quick_reply", "required": False, "label": b.get("button_label")})
	return {
		"tpl": tpl, "view": view, "parameter_format": tv["fmt"], "tv": tv,
		"body": body, "header": header, "buttons": buttons,
	}


def send_problems(req: dict[str, Any], body: Any, header: Any, button: Any) -> dict[str, list[str]]:
	"""What the send of one recipient would be refused for, using the same validation as ``bridge.send_template``.

	``{"missing": [labels], "extra": [labels], "invalid": [messages]}`` (all empty when the send would pass).
	"""
	from huf.ai.gateway_adapters import whatsapp_bridge as bridge
	from huf.ai.gateway_adapters import whatsapp_templates as wt

	tpl, view, tv = req["tpl"], req["view"], req["tv"]
	button_list = button if isinstance(button, list) else ([button] if button else [])
	other, copy_comps, errors = bridge.split_copy_code_params(button_list)
	header_raw = bridge._header_list(header, True)
	components, build_errors = wt.build_send_components(view, body, header_raw, other)
	errors += build_errors
	seen = {(e["field"], e["code"]) for e in errors}
	errors += [
		e for e in bridge._check_send_against_template(tpl, view, body, header_raw, other, copy_comps)
		if (e["field"], e["code"]) not in seen
	]
	if tv["header_type"] in wt.MEDIA_HEADER_TYPES and not any(c.get("type") == "header" for c in components):
		if not (tv["header_type"] == "IMAGE" and wt.is_http_url(str(tpl.get("sample") or ""))):
			errors.append(wt._e("header_params", "required", f"This template has an {tv['header_type']} header; provide a media link."))

	named = tv["fmt"] == "NAMED"
	names = list(tv["body_vars"])
	given = list(body.values()) if isinstance(body, dict) else list(body or [])
	missing: list[str] = []
	extra: list[str] = []
	invalid: list[str] = []
	for e in errors:
		field, code, msg = e["field"], e["code"], e.get("message", "")
		if code == "param_missing":
			missing.append(field.split(".", 1)[-1])
		elif code == "param_count_mismatch" and field == "body_params":
			if len(given) < len(names):
				missing += names[len(given):] if not isinstance(body, dict) or not named else names
			else:
				extra.append(f"{len(given) - len(names)} extra body value(s)")
		elif code == "param_unknown":
			extra.append(field.split(".", 1)[-1])
		elif code in ("not_expected", "unexpected"):
			extra.append(field)
		elif code == "required":
			missing.append("header" if field.startswith("header") else field.replace("_params", ""))
		else:
			invalid.append(msg or f"{field}: {code}")
	dedupe = lambda xs: list(dict.fromkeys(xs))  # noqa: E731
	return {"missing": dedupe(missing), "extra": dedupe(extra), "invalid": dedupe(invalid)}


def _queued_params(broadcast: str) -> list[tuple[str | None, int]]:
	"""Distinct raw ``params`` of queued/deferred recipients with how many recipients carry each."""
	rows = frappe.db.sql(
		"select params, count(*) from `tabWhatsApp Broadcast Recipient` "
		"where broadcast=%s and status in ('queued','deferred') group by params",
		broadcast,
	)
	return [(r[0], int(r[1])) for r in rows]


def _check_params(b: dict[str, Any], broadcast: str, blocking: list[str], warnings: list[str]) -> None:
	"""Block when a queued/deferred recipient would be refused at send time for its template parameters."""
	req = template_requirements(b.get("template") or "")
	if not req:
		return
	from huf.ai.whatsapp.broadcast_send import _merge_params

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
		blocking.append(f"{n_missing} recipients are missing values for template variables: {uniq(missing)}")
	if n_extra:
		# the bridge refuses these too (param_unknown / count mismatch), so they block rather than warn
		blocking.append(f"{n_extra} recipients carry values the template does not use: {uniq(extra)}")
	if n_invalid:
		blocking.append(f"{n_invalid} recipients have invalid template values: {uniq(invalid)}")


def _fill(broadcast: str, out: dict[str, Any]) -> None:
	b = _broadcast_row(broadcast)
	if not b:
		out["blocking"].append("broadcast_not_found")
		return
	warnings: list[str] = out["warnings"]
	blocking: list[str] = out["blocking"]

	counts = _recipient_counts(broadcast)
	out["recipients"] = sum(counts.values())
	out["queued"] = counts.get("queued", 0)
	out["skipped"] = counts.get("skipped", 0)

	tpl = _template_row(b.get("template") or "")
	if not tpl:
		blocking.append("template_not_found")
	else:
		tpl_status = str(tpl.get("status") or "").strip().upper()
		out["template_status"] = tpl_status or None
		out["category"] = str(tpl.get("category") or "").strip().upper() or None
		if tpl_status != "APPROVED":
			blocking.append(f"template_not_approved:{tpl_status or 'unknown'}")

	if tpl:
		_check_params(b, broadcast, blocking, warnings)

	if out["category"] == "MARKETING":
		us = [n for n in _queued_numbers(broadcast) if _is_us_plus_one(n)]
		if us:
			warnings.append(
				f"{len(us)} queued recipient(s) are US +1 numbers; "
				"WhatsApp does not deliver marketing templates to them."
			)

	if not b.get("consent_attested"):
		blocking.append("consent_not_attested")

	gateway = b.get("gateway") or ""
	others = _running_others(gateway, broadcast)
	if others:
		blocking.append("another_broadcast_running:" + ",".join(others))

	limit = get_messaging_limit(gateway)
	if limit["quality"] == "RED":
		blocking.append("quality_red")
	elif limit["quality"] == "YELLOW":
		warnings.append("Number quality is YELLOW; sends may be throttled.")

	if limit["tier"] == UNLIMITED:
		out["remaining_24h"] = None
		out["within_limit"] = True
	elif limit["max_unique_24h"] is None:
		out["remaining_24h"] = None
		out["within_limit"] = None
		warnings.append("Messaging limit is unknown; the 24h budget was not checked.")
	else:
		remaining = max(limit["max_unique_24h"] - _used_24h(gateway), 0)
		out["remaining_24h"] = remaining
		out["within_limit"] = out["queued"] <= remaining
		if not out["within_limit"]:
			blocking.append(f"recipients_exceed_24h_budget:{out['queued']}>{remaining}")


def preview(broadcast: str) -> dict[str, Any]:
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
	}
	try:
		_fill(broadcast or "", out)
	except Exception as exc:  # noqa: BLE001 - class name only
		frappe.logger(LOGGER).warning("broadcast preview failed (%s)", type(exc).__name__)
		out["blocking"].append("preview_failed")
	return out
