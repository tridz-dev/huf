# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Single source of truth for every limit the WhatsApp Broadcast feature applies.

Each :class:`Limit` has a ``kind``:

* ``meta``     - imposed by Meta/WhatsApp; read-only, shown with the reason.
* ``setting``  - a Huf limit an operator may change (``WhatsApp Broadcast Settings``).
* ``safety``   - a Huf safety net, on by default; editable, shown as a safety.
* ``internal`` - a Huf engine constant; read-only, shown for transparency.

:func:`get` is the only read path: per-broadcast override > ``WhatsApp Broadcast Settings`` > default.
A blank settings field means "use the default". For ``max_recipients_default`` and
``max_recipients_ceiling`` a stored ``0`` means "no limit" (``get`` then returns ``None``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import frappe

SETTINGS = "WhatsApp Broadcast Settings"
NO_LIMIT = 0  # stored value meaning "no limit" for limits flagged ``zero_unlimited``


@dataclass(frozen=True)
class Limit:
	key: str
	label: str
	default: Any
	kind: str  # meta | setting | safety | internal
	group: str  # meta | recipients | speed | safety | quality | confirmation | api
	unit: str = ""
	min: float | None = None
	max: float | None = None
	note: str = ""
	verified: bool = True  # meta/internal rows: checked against Meta docs or the repo's citations
	zero_unlimited: bool = False
	boolean: bool = False

	@property
	def editable(self) -> bool:
		return self.kind in ("setting", "safety")


def _L(*a, **k) -> Limit:
	return Limit(*a, **k)


_API_NOTE = "Requests allowed per minute for this action, per caller address."


def _rate(key: str, label: str, default: int) -> Limit:
	return Limit(key, label, default, "safety", "api", "requests/min", 1, 1000, _API_NOTE)


LIMITS: tuple[Limit, ...] = (
	# ---- Meta (read-only)
	Limit("template_approved_only", "Templates must be approved", True, "meta", "meta", note="Meta only delivers APPROVED templates to start a conversation."),
	Limit("messaging_tier_24h", "Unique contacts per 24 hours", None, "meta", "meta", "contacts", note="Set by your WhatsApp messaging tier (250, 1K, 10K, 100K, unlimited). Read live from Meta when a broadcast is chosen."),
	Limit("quality_rating", "Number quality rating", None, "meta", "meta", note="Set by Meta from user feedback; a low rating can reduce your tier."),
	Limit("marketing_stop_131050", "Contacts who stopped marketing", True, "meta", "meta", note="Meta rejects marketing messages to contacts who chose to stop them (error 131050); they are skipped."),
	Limit("opt_out_stop", "STOP replies", True, "meta", "meta", note="Contacts who reply STOP are never messaged again until they opt back in."),
	Limit("bsuid_refused", "Username-only contacts", True, "meta", "meta", note="A business-scoped user ID cannot be used as a recipient; send to the phone number.", verified=False),
	Limit("us_plus_one_marketing", "US (+1) marketing", True, "meta", "meta", note="Meta does not deliver marketing templates to US +1 numbers.", verified=False),
	Limit("per_user_marketing_limit_131049", "Per-contact marketing cap", True, "meta", "meta", note="Meta limits how many marketing messages one person receives (error 131049); that contact is skipped."),
	Limit("header_text_max", "Header text length", 60, "meta", "meta", "characters", note="Template header text is limited to 60 characters."),
	Limit("copy_code_max", "Copy-code length", 15, "meta", "meta", "characters", note="A copy-code button value is up to 15 letters or digits.", verified=False),
	Limit("max_phone_digits", "Phone number length", 15, "meta", "meta", "digits", note="E.164 allows at most 15 digits."),
	# ---- recipients
	Limit("max_recipients_default", "Recipients per broadcast (default)", 1000, "setting", "recipients", "recipients", 1, 10_000_000, "Used when a broadcast does not set its own cap. 0 = no limit.", zero_unlimited=True),
	Limit("max_recipients_ceiling", "Recipients per broadcast (highest allowed)", 10000, "setting", "recipients", "recipients", 1, 10_000_000, "No broadcast may ask for more than this. 0 = no limit.", zero_unlimited=True),
	Limit("max_rows_per_broadcast", "Stored rows per broadcast", 50000, "setting", "recipients", "rows", 1, 10_000_000, "Includes skipped contacts."),
	Limit("max_rows_per_request", "Recipients per request", 10000, "setting", "recipients", "rows", 1, 1_000_000, "How many recipients one add call accepts."),
	Limit("max_csv_mb", "CSV size", 2, "setting", "recipients", "MB", 1, 100, "Largest CSV text accepted in one request."),
	Limit("min_phone_digits", "Shortest phone number", 8, "setting", "recipients", "digits", 5, 15, "Numbers with fewer digits are rejected as invalid."),
	Limit("returned_list_limit", "Skipped rows echoed back", 200, "internal", "recipients", "rows", note="How many skipped/invalid entries an add call lists; totals are always exact."),
	Limit("location_text_max", "Location name/address length", 1000, "internal", "recipients", "characters", note="Huf's own cap; Meta does not state a length.", verified=False),
	Limit("url_suffix_max", "Link suffix length", 2000, "internal", "recipients", "characters", note="Huf's own cap; Meta's documented URL maximum is 2000.", verified=False),
	# ---- speed
	Limit("default_mps", "Default sending speed", 20, "setting", "speed", "messages/s", 1, 1000, "Used when a broadcast sets no speed."),
	Limit("max_mps_cap", "Speed cap", 80, "setting", "speed", "messages/s", 1, 1000, "Meta's default throughput is 80/s. When Meta reports a rate it is used unless you set a lower cap here."),
	Limit("ramp_first_batch", "First batch size", 20, "setting", "speed", "messages", 1, 1000, "Sending starts small, then doubles each chunk."),
	Limit("max_batch", "Largest batch", 200, "setting", "speed", "messages", 1, 5000, "Upper bound for one chunk."),
	Limit("max_attempts", "Attempts per recipient", 5, "setting", "speed", "attempts", 1, 20, "After this many tries a recipient is marked failed."),
	Limit("auth_defer_seconds", "Wait after an access-token error", 300, "setting", "speed", "seconds", 10, 86400, "The recipient is retried after this delay."),
	Limit("gateway_down_defer_seconds", "Wait when the gateway is down", 300, "setting", "speed", "seconds", 10, 86400, "The recipient is retried after this delay."),
	# ---- quality / safety
	Limit("held_throttle_enabled", "Slow down when Meta holds messages", True, "safety", "quality", "", note="Cuts speed to a quarter while many messages are held for quality assessment.", boolean=True),
	Limit("held_ratio_limit", "Held-message ratio that slows sending", 0.30, "safety", "quality", "ratio", 0.01, 1.0, "Share of recent sends held by Meta before sending slows."),
	Limit("held_window", "Held-message window", 50, "safety", "quality", "messages", 10, 500, "How many recent sends are examined."),
	Limit("min_held_sample", "Minimum sample before slowing", 10, "safety", "quality", "messages", 1, 100, "Avoids slowing on one held message out of two."),
	Limit("one_active_per_gateway", "One running broadcast per gateway", True, "safety", "safety", "", note="Only one broadcast sends from a gateway at a time.", boolean=True),
	# ---- confirmation
	Limit("require_typed_count", "Type the recipient count to start", True, "safety", "confirmation", "", note="The start step asks for the queued count (callers using API keys skip the typing).", boolean=True),
	Limit("require_consent_attestation", "Require consent confirmation", True, "safety", "confirmation", "", note="Meta requires opt-in for business-initiated messages; this box is Huf's record of it.", boolean=True),
	# ---- engine constants
	Limit("tick_timeout", "Worker job timeout", 1800, "internal", "safety", "seconds"),
	Limit("tick_budget_seconds", "Work per tick", 240, "internal", "safety", "seconds", note="A tick works this long, then re-enqueues itself."),
	Limit("lock_ttl", "Tick lock lifetime", 600, "internal", "safety", "seconds"),
	Limit("heartbeat_seconds", "Lock refresh interval", 30, "internal", "safety", "seconds"),
	Limit("heartbeat_every_sends", "Lock refresh every N sends", 20, "internal", "safety", "messages"),
	Limit("perm_recheck_every_sends", "Permission re-check every N sends", 50, "internal", "safety", "messages"),
	Limit("stale_sending_minutes", "Stuck 'sending' timeout", 10, "internal", "safety", "minutes", note="A row stuck sending this long becomes 'unknown' and is never resent."),
	Limit("limits_cache_ttl_seconds", "Meta tier/quality cache", 600, "internal", "safety", "seconds"),
	Limit("prepare_retries", "Retries on database deadlock", 3, "internal", "recipients", "attempts"),
	# ---- API rate limits
	_rate("rate_create_broadcast", "Create broadcast", 60),
	_rate("rate_add_recipients", "Add recipients", 60),
	_rate("rate_remove_recipient", "Remove recipient", 120),
	_rate("rate_delete_broadcast", "Delete broadcast", 30),
	_rate("rate_attest_consent", "Confirm consent", 60),
	_rate("rate_start_broadcast", "Start broadcast", 30),
	_rate("rate_pause_broadcast", "Pause broadcast", 60),
	_rate("rate_resume_broadcast", "Resume broadcast", 60),
	_rate("rate_cancel_broadcast", "Cancel broadcast", 60),
	_rate("rate_pause_all", "Pause all broadcasts", 30),
	_rate("rate_limits_read", "Read limits", 120),
	_rate("rate_limits_write", "Change limits", 30),
	_rate("rate_audience_read", "Audience reads", 120),
	_rate("rate_audience_write", "Audience changes", 60),
	_rate("rate_audience_import", "Audience import", 10),
)

BY_KEY: dict[str, Limit] = {lim.key: lim for lim in LIMITS}
assert len(BY_KEY) == len(LIMITS), "duplicate limit key"

# Per-broadcast overrides: limit key -> Broadcast field
BROADCAST_FIELDS = {"max_recipients_default": "max_recipients", "default_mps": "mps"}


def _parse_doc(doc) -> dict[str, Any]:
	out: dict[str, Any] = {}
	for lim in LIMITS:
		if not lim.editable:
			continue
		raw = doc.get(lim.key)
		if not isinstance(raw, (str, int, float)) or str(raw).strip() == "":
			continue
		if lim.boolean:
			out[lim.key] = raw in (1, True, "On", "1")
		else:
			try:
				out[lim.key] = float(raw) if isinstance(lim.default, float) else int(float(raw))
			except (TypeError, ValueError):
				continue  # a corrupt value falls back to the default
	return out


def stored_values() -> dict[str, Any]:
	"""Raw stored settings (key -> value) for editable limits; blank fields are absent."""
	try:
		return _parse_doc(frappe.get_cached_doc(SETTINGS))
	except Exception:  # doctype not migrated yet, or no site
		return {}


def resolve(key: str, broadcast: Any = None) -> tuple[Any, str]:
	"""``(effective_value, source)``; source is ``broadcast`` | ``settings`` | ``default``."""
	lim = BY_KEY[key]
	if broadcast is not None and key in BROADCAST_FIELDS:
		field = BROADCAST_FIELDS[key]
		own = broadcast.get(field) if isinstance(broadcast, dict) else getattr(broadcast, field, None)
		if isinstance(own, (int, float)) and not isinstance(own, bool) and own > 0:
			return own, "broadcast"
	if lim.editable:
		stored = stored_values()
		if key in stored:
			value = stored[key]
			if lim.zero_unlimited and value == NO_LIMIT:
				return None, "settings"
			return value, "settings"
	return lim.default, "default"


def get(key: str, broadcast: Any = None) -> Any:
	"""Effective value of limit ``key`` (``None`` means "no limit" or "unknown")."""
	return resolve(key, broadcast)[0]


def rate(key: str) -> Callable[[], int]:
	"""Callable for ``frappe.rate_limiter.rate_limit(limit=...)``: re-read on every request."""
	return lambda: int(get(key))


def effective_mps_cap(reported: int | None) -> int:
	"""Speed ceiling: Meta's reported rate, or the cap; an explicit setting can only lower it."""
	cap_value, source = resolve("max_mps_cap")
	if source == "settings":
		return max(1, min(int(cap_value), int(reported)) if reported else int(cap_value))
	return int(reported or cap_value)


def validate_values(values: dict[str, Any]) -> dict[str, Any]:
	"""Clean ``values`` (key -> value; ``None``/"" resets). Raises ``ValueError('key: message')``."""
	clean: dict[str, Any] = {}
	for key, raw in (values or {}).items():
		lim = BY_KEY.get(key)
		if lim is None:
			raise ValueError(f"{key}: unknown limit")
		if not lim.editable:
			raise ValueError(f"{key}: this limit cannot be changed")
		if raw in (None, ""):
			clean[key] = None
			continue
		if lim.boolean:
			if isinstance(raw, str):
				raw = raw.strip().lower() in ("1", "true", "on", "yes")
			clean[key] = bool(raw)
			continue
		if isinstance(raw, bool):
			raise ValueError(f"{key}: must be a number")
		try:
			num = float(raw) if isinstance(lim.default, float) else int(float(raw))
			if not isinstance(lim.default, float) and num != float(raw):
				raise ValueError
		except (TypeError, ValueError):
			raise ValueError(f"{key}: must be a number") from None
		if lim.zero_unlimited and num == NO_LIMIT:
			clean[key] = NO_LIMIT
			continue
		if (lim.min is not None and num < lim.min) or (lim.max is not None and num > lim.max):
			raise ValueError(f"{key}: must be between {lim.min:g} and {lim.max:g}")
		clean[key] = num
	return clean


def validate_combination(merged: dict[str, Any]) -> None:
	"""Cross-field rules over parsed stored values (absent/``None`` = default)."""

	def eff(key):
		v = merged.get(key)
		return BY_KEY[key].default if v is None else v

	default_cap, ceiling = eff("max_recipients_default"), eff("max_recipients_ceiling")
	if default_cap != NO_LIMIT and ceiling != NO_LIMIT and default_cap > ceiling:
		raise ValueError("max_recipients_default: cannot be higher than the highest allowed")
	if eff("ramp_first_batch") > eff("max_batch"):
		raise ValueError("ramp_first_batch: cannot be larger than the largest batch")
	if eff("min_held_sample") > eff("held_window"):
		raise ValueError("min_held_sample: cannot be larger than the held-message window")


def set_values(values: dict[str, Any]) -> None:
	"""Validate and store ``values`` (``None`` resets that key). Caller owns permission checks."""
	clean = validate_values(values)
	doc = frappe.get_doc(SETTINGS)
	merged = _parse_doc(doc)
	for key, value in clean.items():
		if value is None:
			merged.pop(key, None)
		else:
			merged[key] = value
	validate_combination(merged)
	for key, value in clean.items():
		lim = BY_KEY[key]
		if value is None:
			doc.set(key, "")
		elif lim.boolean:
			doc.set(key, "On" if value else "Off")
		else:
			doc.set(key, str(value))
	doc.flags.ignore_permissions = True
	doc.save()


# --------------------------------------------------------------------------- docs

_KIND_LABEL = {"meta": "Set by Meta", "setting": "Huf setting", "safety": "Safety", "internal": "Internal"}
DOCS_HEADER = """# WhatsApp Broadcast limits

Generated from `huf/ai/whatsapp/broadcast/policy.py` (`python -m huf.ai.whatsapp.broadcast.policy`); a
test fails when this file drifts from the registry. Do not edit the table by hand.

Effective value = per-broadcast override, then **WhatsApp Broadcast Settings**, then the default.
A blank setting uses the default. For the two recipient caps, `0` means no limit.

"""


def _cell(value: Any) -> str:
	if value is None:
		return "-"
	if value is True:
		return "on"
	if value is False:
		return "off"
	return str(value)


def render_docs() -> str:
	lines = [
		"| Key | Limit | Type | Default | Range | Unit | Note |",
		"| --- | --- | --- | --- | --- | --- | --- |",
	]
	for lim in LIMITS:
		rng = "-" if lim.min is None else f"{lim.min:g} to {lim.max:g}"
		note = lim.note
		if lim.kind in ("meta", "internal") and not lim.verified:
			note = (note + " " if note else "") + "(Not verified against Meta's documentation.)"
		lines.append(
			f"| `{lim.key}` | {lim.label} | {_KIND_LABEL[lim.kind]} | {_cell(lim.default)} | {rng} | {lim.unit or '-'} | {note or '-'} |"
		)
	return DOCS_HEADER + "\n".join(lines) + "\n"


if __name__ == "__main__":
	import os

	root = os.path.abspath(os.path.join(os.path.dirname(__file__), *[".."] * 4))
	with open(os.path.join(root, "docs", "whatsapp", "BROADCAST_LIMITS.md"), "w", encoding="utf-8") as fh:
		fh.write(render_docs())
