# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Huf's built-in pre-send steps (H-W2-02), run by :mod:`huf.ai.channels.outbound.guard` before any app hook.

Each step takes the request dict and answers ``{"allow": True}`` or ``{"allow": False, "reason": code}``.
The steps in ``STEPS`` only read. Anything they raise is turned into a ``hook_error`` block by the chain.

The frequency cap (H-W2-08) is not in ``STEPS``: the chain runs it last, after every app hook, as
:func:`resolve_caps` (reads app hooks) and then :func:`apply_caps` (counts; a live send commits).

The send window (H-W2-06) is not in ``STEPS`` either: its answer can be "later", so the chain runs it as
:func:`window_deferral`, after these steps and before any ``huf_pre_send_hooks`` handler.

Order of the whole chain: recipient, consent, ``huf_pre_send_consent_hooks``, template, send window, app
hooks (``huf_pre_send_hooks``), frequency cap.

``header`` is not part of the app hook request: the chain adds it for built-in steps only, from
``guard.evaluate(..., header=)``; None means "use the template's default media".
"""

from __future__ import annotations

import contextlib
import contextvars
import copy
import re
from collections.abc import Callable, Iterator
from datetime import datetime, time, timedelta, timezone
from typing import Any
from urllib.parse import urlsplit

import frappe

from huf.ai.flow.policy import frequency_cap, send_window

WINDOW_STEP = "send_window"
WINDOW_HOOK = "huf_send_window_resolver"
WINDOW_KEYS = frozenset({"zone", "windows", "exempt_categories"})
WINDOW_ENTRY_KEYS = frozenset({"start", "end", "weekdays"})
WINDOW_RETRY = timedelta(hours=1)  # closed with no known next opening
_CLOCK = re.compile(r"([01][0-9]|2[0-3]):([0-5][0-9])")
CAP_STEP = "frequency_cap"
CAP_HOOK = "huf_frequency_cap_resolver"
CAP_KEYS = frozenset({"limit", "window_seconds", "bucket"})
MAX_WINDOW_SECONDS = 31622400  # 366 days
MEDIA_HOSTS_CONF = (
	"huf_send_media_hosts"  # list or comma string of hosts (``host:port`` for a port other than 443)
)
MEDIA_TYPES = ("image", "video", "document")
BLOCKING_EVENTS = frozenset({"FLAGGED"})
_E164 = re.compile(r"\+[1-9][0-9]{6,14}")
_SEPARATORS = re.compile(r"[ ()\-]")


# Per-batch cache (H-W2-19). Only set inside :func:`batch`; outside it every send reads afresh.
_BATCH: contextvars.ContextVar[dict | None] = contextvars.ContextVar("huf_guard_batch", default=None)


@contextlib.contextmanager
def batch() -> Iterator[None]:
	"""Share template reads and consent allows between the guarded sends of one batch.

	Nothing outlives the block: a consent allow is never reused by a later batch. Nested blocks reuse the
	outer cache. A block decision is never cached, so it is always read again.
	"""
	if _BATCH.get() is not None:
		yield
		return
	token = _BATCH.set({})
	try:
		yield
	finally:
		_BATCH.reset(token)


def invalidate_consent(recipient: Any = None) -> None:
	"""Forget cached consent allows for ``recipient`` (any form), or all of them. Call on an opt-out."""
	cache = _BATCH.get()
	if not cache:
		return
	digits = _digits(recipient) if recipient is not None else None
	for key in [k for k in cache if k[0] == "consent" and (digits is None or k[-1] == digits)]:
		cache.pop(key, None)


def _digits(raw: Any) -> str:
	value = str(raw or "").strip().lower()
	return value if "@" in value else re.sub(r"[^0-9]", "", value)


def _cached(key: tuple, load: Callable[[], Any], keep: Callable[[Any], bool] = lambda _: True) -> Any:
	cache = _BATCH.get()
	if cache is None:
		return load()
	if key in cache:
		return copy.deepcopy(cache[key])
	value = load()
	if keep(value):
		cache[key] = copy.deepcopy(value)
	return value


def _allow() -> dict:
	return {"allow": True}


def _block(reason: str) -> dict:
	return {"allow": False, "reason": reason}


def normalise_recipient(raw: Any) -> str | None:
	"""``+<digits>`` (E.164), or None. A number without ``+`` or ``00`` is ambiguous and rejected."""
	if not isinstance(raw, str):
		return None
	value = _SEPARATORS.sub("", raw)
	if value.startswith("00"):
		value = "+" + value[2:]
	return value if _E164.fullmatch(value) else None


def check_recipient(request: dict) -> dict:
	if request.get("channel") == "email":
		return _allow()  # validated by the consent step
	if request.get("channel") == "whatsapp":
		from huf.ai.gateway_adapters import whatsapp_bridge as bridge

		if bridge.is_bsuid(request.get("recipient")):
			return _block("bsuid_recipient")
	return _allow() if normalise_recipient(request.get("recipient")) else _block("bad_recipient")


def check_consent(request: dict) -> dict:
	"""Huf's own opt-out records. An app's consent rules go in its ``huf_pre_send_consent_hooks``.

	Inside :func:`batch` an allow is reused for the same recipient; a block drops that recipient's allows.
	"""
	channel, recipient = request.get("channel"), request.get("recipient")
	key = (
		"consent",
		channel,
		request.get("gateway"),
		request.get("category") != "service",
		_digits(recipient),
	)
	verdict = _cached(key, lambda: _read_consent(request), keep=lambda v: v.get("allow") is True)
	if verdict.get("allow") is not True:
		invalidate_consent(recipient)
	return verdict


def _read_consent(request: dict) -> dict:
	channel, recipient = request.get("channel"), request.get("recipient")
	marketing = request.get("category") != "service"
	if channel == "whatsapp":
		from huf.ai.whatsapp import account_events, outbound_policy

		gateway = request.get("gateway")
		if not gateway:
			return _block("blocked_by_hook")
		digits = normalise_recipient(recipient)[1:]
		try:
			outbound_policy.check_recipient(gateway, digits)
		except outbound_policy.OutboundRefused as error:
			return _block(error.code)
		if marketing and not account_events.is_marketing_allowed(gateway, digits):
			return _block("marketing_opted_out")
		return _allow()

	from huf.ai.channels import channel_consent

	allowed, reason = channel_consent.has_consent(channel, recipient, "marketing" if marketing else "utility")
	if allowed:
		return _allow()
	return _block("bad_recipient" if reason == "invalid_recipient" else reason)


def check_template(request: dict) -> dict:
	"""G5: a WhatsApp template is sent only when its row exists and everything known says APPROVED."""
	template, header = request.get("template"), request.get("header")
	if request.get("channel") != "whatsapp" or not template:
		return _block("header_invalid") if header is not None else _allow()

	gateway = request.get("gateway")
	found = _cached(("template", gateway, template), lambda: _load_template(gateway, template), keep=bool)
	if not found:
		return _block("template_not_approved")
	docname, req = found
	row = req["tpl"]
	if str(row.get("status") or "").upper() != "APPROVED":
		return _block("template_not_approved")
	account = row.get("whatsapp_account")
	# only "nothing contradicts APPROVED" is reused; a blocking state is read again every send
	if _cached(
		("state", account, docname), lambda: _state_blocks(account, docname), keep=lambda v: v is False
	):
		return _block("template_not_approved")

	if str(row.get("category") or "").upper() == "MARKETING":
		from huf.ai.whatsapp import outbound_policy

		try:
			outbound_policy.check_template(
				request.get("gateway"), normalise_recipient(request.get("recipient"))[1:], row
			)
		except outbound_policy.OutboundRefused as error:
			return _block(error.code)

	if not _params_match(req, request.get("token_names")):
		return _block("template_params_invalid")
	reason = _header_problem(req, header)
	return _block(reason) if reason else _allow()


def _load_template(gateway: str | None, template: str) -> tuple[str, dict] | None:
	"""(docname, send requirements) of ``template`` on the gateway's own account, else None."""
	from huf.ai.gateway_adapters import whatsapp_bridge as bridge
	from huf.ai.whatsapp.broadcast.checks.template_check import template_requirements

	account = frappe.db.get_value("Gateway", gateway, "whatsapp_account") if gateway else None
	if not account or not frappe.db.exists("DocType", "WhatsApp Templates"):
		return None
	try:
		docname = bridge._template_docname(account, template)
	except bridge.BridgeError:  # several languages share the name: the template is not identified
		return None
	req = template_requirements(docname)
	if not req or req["tpl"].get("whatsapp_account") != account:
		return None
	return docname, req


def _state_blocks(account: str, docname: str) -> bool:
	"""True when the webhook/sync state contradicts APPROVED. A read error raises, so it blocks."""
	from huf.ai.gateway_adapters import whatsapp_bridge as bridge

	if not frappe.db.exists("DocType", bridge.STATE_DOCTYPE):
		return False
	state = frappe.db.get_value(
		bridge.STATE_DOCTYPE, bridge.state_key(account, docname), ["status", "last_event"], as_dict=True
	)
	if not state:
		return False
	status = str(state.get("status") or "").upper()
	return status not in ("", "APPROVED") or str(state.get("last_event") or "").upper() in BLOCKING_EVENTS


def _params_match(req: dict, token_names: Any) -> bool:
	"""One token per body variable, text header variable and required button. Carousels cannot be checked."""
	if not isinstance(token_names, list) or req["tv"].get("carousel"):
		return False
	header = req.get("header") or {}
	expected = (
		len(req["body"]) + (header.get("type") == "TEXT") + sum(bool(b["required"]) for b in req["buttons"])
	)
	return len(token_names) == expected


def _header_problem(req: dict, header: Any) -> str | None:
	kind = str(req["tv"].get("header_type") or "").lower()
	if kind == "location":
		ok = (
			isinstance(header, dict)
			and header.get("type") == "location"
			and header.get("latitude") is not None
			and header.get("longitude") is not None
		)
		return None if ok else "header_invalid"
	if kind not in MEDIA_TYPES:
		return None if header is None else "header_invalid"
	if header is None:
		# only an image template can fall back to its own sample link (as the bridge does)
		link = req["tpl"].get("sample") if kind == "image" else None
	elif isinstance(header, dict) and header.get("type") == kind:
		link = header.get("link")
	else:
		link = None
	if not isinstance(link, str) or not link:
		return "header_invalid"
	return None if media_host_allowed(link) else "media_host_not_allowed"


def media_host_allowed(link: Any) -> bool:
	"""https, no userinfo, and a host listed in site config ``huf_send_media_hosts``. Nothing listed allows nothing."""
	if not isinstance(link, str) or any(c.isspace() or c == "\\" for c in link):
		return False
	try:
		parts = urlsplit(link)
		port = parts.port
	except ValueError:
		return False
	if parts.scheme != "https" or "@" in parts.netloc or not parts.hostname:
		return False
	host = parts.hostname if port in (None, 443) else f"{parts.hostname}:{port}"
	raw = frappe.conf.get(MEDIA_HOSTS_CONF) or []
	hosts = raw.split(",") if isinstance(raw, str) else raw
	return host in {str(h).strip().lower() for h in hosts}


def window_resolvers() -> list[str]:
	paths = frappe.get_hooks(WINDOW_HOOK) or []
	return [paths] if isinstance(paths, str) else list(paths)


def window_deferral(request: dict, resolvers: list[str]) -> datetime | None:
	"""None when the send may leave now, else the aware UTC moment to try again.

	The first resolver answer that is not None decides; none is "always open". Raises on any invalid answer.
	"""
	for path in resolvers:
		answer = frappe.get_attr(path)(copy.deepcopy(request))
		if answer is not None:
			break
	else:
		return None
	zone, windows, exempt = _parse_window_answer(answer)
	now = datetime.now(timezone.utc)
	# evaluated even for an exempt category, so a bad zone or window never passes unnoticed
	decision = send_window.check_send_window(now, zone, windows)
	if decision.allowed or request.get("category") in exempt:
		return None
	return decision.next_open or now + WINDOW_RETRY


def _parse_window_answer(answer: Any) -> tuple[str, list[send_window.Window], list[str]]:
	if not isinstance(answer, dict) or not set(answer) <= WINDOW_KEYS:
		raise ValueError("invalid send window")  # noqa: TRY003
	zone, windows = answer.get("zone"), answer.get("windows")
	exempt = answer.get("exempt_categories", [])
	if not isinstance(zone, str) or not isinstance(windows, list) or not isinstance(exempt, list):
		raise ValueError("invalid send window")  # noqa: TRY003, TRY004
	if not all(isinstance(category, str) for category in exempt):
		raise ValueError("invalid send window")  # noqa: TRY003
	return zone, [_parse_window(entry) for entry in windows], exempt


def _parse_window(entry: Any) -> send_window.Window:
	if not isinstance(entry, dict) or not set(entry) <= WINDOW_ENTRY_KEYS:
		raise ValueError("invalid send window")  # noqa: TRY003
	weekdays = entry.get("weekdays", list(send_window.ALL_WEEKDAYS))
	if not isinstance(weekdays, list) or not all(type(day) is int for day in weekdays):
		raise ValueError("invalid send window")  # noqa: TRY003
	return send_window.Window(_clock(entry.get("start")), _clock(entry.get("end")), frozenset(weekdays))


def _clock(value: Any) -> time:
	match = _CLOCK.fullmatch(value) if isinstance(value, str) else None
	if not match:
		raise ValueError("invalid send window")  # noqa: TRY003
	return time(int(match[1]), int(match[2]))


def resolve_caps(request: dict) -> list[tuple[int, str, int]]:
	"""``(window_seconds, counter channel, limit)`` of every cap on this send, shortest window first.

	Apps answer through ``huf_frequency_cap_resolver``; None, or no resolver, is no cap. Caps sharing a
	counter are merged to the lowest limit, so one send is counted there once. Raises on any invalid answer.
	"""
	paths = frappe.get_hooks(CAP_HOOK) or []
	limits: dict[tuple[int, str], int] = {}
	for path in [paths] if isinstance(paths, str) else paths:
		answer = frappe.get_attr(path)(copy.deepcopy(request))
		if answer is None:
			continue
		for cap in answer if isinstance(answer, list) else [answer]:
			window, channel, limit = _parse_cap(cap, request)
			key = (window, channel)
			limits[key] = min(limit, limits.get(key, limit))
	return [(window, channel, limit) for (window, channel), limit in sorted(limits.items())]


def _parse_cap(cap: Any, request: dict) -> tuple[int, str, int]:
	if not isinstance(cap, dict) or not set(cap) <= CAP_KEYS:
		raise ValueError("invalid frequency cap")  # noqa: TRY003
	limit, window = cap.get("limit"), cap.get("window_seconds")
	channel = cap["bucket"] if "bucket" in cap else request.get("channel")
	if type(limit) is not int or limit < 0 or type(window) is not int or not 0 < window <= MAX_WINDOW_SECONDS:
		raise ValueError("invalid frequency cap")  # noqa: TRY003
	if not isinstance(channel, str) or not channel.strip() or len(channel) > frequency_cap.MAX_KEY_CHARS:
		raise ValueError("invalid frequency cap")  # noqa: TRY003
	return window, channel, limit


def apply_caps(request: dict, caps: list[tuple[int, str, int]]) -> dict:
	"""Claim one send under every cap when ``request["live"] is True``; otherwise only look.

	A claim COMMITS the current transaction (see :mod:`huf.ai.flow.policy.frequency_cap`). A send refused by
	a later window keeps the earlier windows' counts. Store errors propagate, which blocks the send.
	"""
	member, live = request.get("member_key"), request.get("live") is True
	for window, channel, limit in caps:
		if live:
			full = frequency_cap.incr(member, channel, window, limit=limit) is None
		else:
			full = frequency_cap.check(member, channel, window) >= limit
		if full:
			return _block("freq_cap")
	return _allow()


STEPS = (
	("recipient", check_recipient),
	("consent", check_consent),
	("template", check_template),
)
