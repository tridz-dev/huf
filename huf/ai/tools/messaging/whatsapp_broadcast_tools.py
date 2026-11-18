"""Generic built-in agent tools for WhatsApp audiences and broadcasts (any app's agent can use them).

Every handler runs as the signed-in user (the agent run's session user): it calls the same whitelisted
broadcast / audience functions the Huf UI uses, so Gateway write authority, size caps, rate limits, opt-out
and policy checks apply exactly as for a human. Nothing here uses ``ignore_permissions`` and nothing uses the
``externally_managed`` upsert path.

Consent: no tool attests recipient consent. ``whatsapp_broadcast_start`` refuses with ``consent_not_attested``
until a human attested the broadcast (``attest_broadcast_consent``, or an audience attested by a human, in the
Huf broadcast screen). ``send_otp`` is deliberately NOT a tool (see ``OTP_TOOL_DENYLIST``).

Flags: ``whatsapp_broadcast_start`` is the only outbound tool (``is_outbound=1``, always parks for human
confirmation with the resolved recipient count). The others send nothing: templates/status are reads, audience
upsert and broadcast create / retry-failed only write Drafts.
"""

from __future__ import annotations

import json
from typing import Any

import frappe

ROLE = "HUF Messaging Manager"
REQUIRED_ROLES = f"{ROLE}, System Manager"
_MAX_TEMPLATES = 60
_FAILURE_SAMPLE = 20
_ROW_FIELDS = {"phone": "phone", "recipient": "phone", "display_name": "name", "name": "name"}


def _out(payload: dict) -> str:
	return json.dumps(payload, default=str)


def _fail(code: str, message: str, **extra) -> str:
	return _out({"success": False, "error": code, "message": message, **extra})


def _guarded(fn):
	"""Turn permission errors into a stable JSON refusal; never leak a traceback to the model."""

	def wrapper(**kwargs):
		kwargs.pop("kwargs", None)
		try:
			return fn(**kwargs)
		except frappe.PermissionError:
			return _fail("permission_denied", "You do not have permission for this WhatsApp action.")
		except (frappe.ValidationError, ValueError, TypeError) as exc:
			return _fail("invalid", str(exc)[:300])

	wrapper.__name__ = fn.__name__
	wrapper.__doc__ = fn.__doc__
	return wrapper


def _parse(value: Any, label: str):
	if isinstance(value, str):
		value = value.strip()
		if not value:
			return None
		try:
			return json.loads(value)
		except ValueError as exc:
			raise ValueError(f"{label} must be valid JSON") from exc
	return value


def _result(res: Any, **extra) -> str:
	res = res if isinstance(res, dict) else {"success": False, "error": "unexpected_result"}
	if res.get("error") and "success" not in res:
		res = {"success": False, **res}
	return _out({**res, **extra})


# --- 1. templates -----------------------------------------------------------------------------------
@_guarded
def handle_list_templates(gateway: str = "", **_ignored) -> str:
	"""Approved templates of the gateway's account with variable counts and category (read only)."""
	from huf.ai.whatsapp import management
	from huf.ai.whatsapp.broadcast import api_read

	res = management.list_templates(gateway_name=gateway or None, status="APPROVED")
	if not isinstance(res, dict) or not res.get("success"):
		return _result(res)
	out = []
	for tpl in (res.get("templates") or [])[:_MAX_TEMPLATES]:
		name = tpl.get("actual_name") or tpl.get("template_name") or tpl.get("name")
		counts = {"body": None, "header": None, "buttons": None}
		try:
			req = api_read.get_broadcast_template_params(gateway=gateway, template=tpl.get("name"))
			if req.get("success"):
				counts = {
					"body": len(req.get("body") or []),
					"header": 1 if (req.get("header") or {}).get("required") else 0,
					"buttons": len([b for b in req.get("buttons") or [] if b.get("required")]),
				}
		except Exception:
			pass
		out.append(
			{
				"template": tpl.get("name"), "name": name, "language_code": tpl.get("language_code"),
				"category": tpl.get("category"), "status": tpl.get("status"), "variable_counts": counts,
			}
		)
	return _out({"success": True, "gateway": gateway, "templates": out, "total": len(res.get("templates") or [])})


# --- 2. audience upsert -----------------------------------------------------------------------------
def _member_rows(members: Any) -> tuple[list[dict], dict]:
	rows = _parse(members, "members")
	if not isinstance(rows, list) or not rows:
		raise ValueError("members must be a non-empty list of {recipient, display_name, params, consent_source, consent_at}")
	width = 0
	flat = []
	for raw in rows:
		if not isinstance(raw, dict):
			raise ValueError("each member must be an object")
		item = {
			"phone": raw.get("recipient") or raw.get("phone"),
			"name": raw.get("display_name") or raw.get("name"),
			"consent_source": raw.get("consent_source"),
			"consent_at": raw.get("consent_at"),
		}
		params = raw.get("params")
		if isinstance(params, dict):
			params = params.get("body")
		params = params if isinstance(params, (list, tuple)) else ([] if params in (None, "") else [params])
		width = max(width, len(params))
		for i, value in enumerate(params):
			item[f"p{i + 1}"] = value
		flat.append(item)
	mapping = {
		"phone": "phone", "name": "name", "consent_source": "consent_source", "consent_at": "consent_at",
		"params": [f"p{i + 1}" for i in range(width)],
	}
	for row in flat:  # every row carries every mapped column (the mapper reads headers from row one)
		for key in ("phone", "name", "consent_source", "consent_at", *mapping["params"]):
			row.setdefault(key, None)
	return flat, mapping


@_guarded
def handle_audience_upsert(
	gateway: str = "", audience: str = "", title: str = "", members: Any = None, mode: str = "merge",
	consent_basis: str = "", consent_purposes: Any = None, **_ignored,
) -> str:
	"""Create an audience (``gateway`` + ``title``) or add/replace the members of an existing one.

	Uses ``create_audience`` / ``import_members`` / ``remove_members`` as the signed-in user. The tool never
	attests consent: when the site requires audience consent attestation, create the audience in the Huf UI
	(a human attests) and pass its name as ``audience``.
	"""
	from huf.ai.whatsapp.broadcast.audiences import api as audience_api

	if mode not in ("merge", "replace"):
		return _fail("invalid", "mode must be 'merge' or 'replace'.")
	rows, mapping = _member_rows(members)
	created = False
	if not audience:
		if not gateway or not title:
			return _fail("invalid", "Pass an existing audience, or gateway and title to create one.")
		purposes = _parse(consent_purposes, "consent_purposes") or ["utility"]
		made = audience_api.create_audience(
			gateway=gateway, title=title, consent_source=None, consent_basis=consent_basis or None,
			consent_purposes=purposes, consent_attested=0,
		)
		if made.get("error"):
			hint = {}
			if made.get("error") == "consent_not_attested":
				hint = {"next_step": "Ask the user to create and attest this audience in the Huf audiences screen, then pass its name as 'audience'."}
			return _result(made, **hint)
		audience, created = made["audience"]["name"], True
	cap = len(rows)
	imported = audience_api.import_members(audience=audience, rows=rows, mapping=mapping, on_conflict="update")
	if imported.get("error"):
		return _result(imported, audience=audience, created=created)
	removed = 0
	if mode == "replace":
		if imported.get("queued"):
			return _fail(
				"replace_too_large",
				"This list is too large to replace in one call; the members were added but stale members were not removed.",
				audience=audience, created=created,
			)
		keep = {audience_api.broadcast_recipients.normalize_recipient(r.get("phone")) for r in rows}
		current = audience_api.list_members(audience=audience, limit=cap + 500)  # masked unless Gateway write is held
		stale = [m["recipient"] for m in current.get("members", []) if m["recipient"] not in keep and "*" not in m["recipient"]]
		if stale:
			removed = audience_api.remove_members(audience=audience, recipients=stale).get("removed", 0)
	return _result(imported, audience=audience, created=created, mode=mode, removed=removed)


# --- 3. broadcast create ----------------------------------------------------------------------------
@_guarded
def handle_broadcast_create(
	audience: str = "", template: str = "", title: str = "", language_code: str = "", body_params: Any = None,
	header_params: Any = None, button_params: Any = None, fallback_channels: Any = None, fallback_body: str = "",
	fallback_body_kind: str = "", fallback_sms_gateway: str = "", fallback_email_gateway: str = "", **_ignored,
) -> str:
	"""Create a Draft broadcast from an audience and an approved template. Sends nothing; consent is NOT attested."""
	from huf.ai.whatsapp.broadcast import api as broadcast_api
	from huf.ai.whatsapp.broadcast.audiences import membership as aud, wiring

	if not audience or not frappe.db.exists(aud.AUDIENCE, audience):
		return _fail("not_found", "Audience not found.")
	gateway = frappe.db.get_value(aud.AUDIENCE, audience, "gateway")
	made = broadcast_api.create_broadcast(
		gateway=gateway, template=template, title=title, language_code=language_code or None,
		body_params=body_params or None, header_params=header_params or None, button_params=button_params or None,
		fallback_channels=fallback_channels or None, fallback_body=fallback_body or None,
		fallback_body_kind=fallback_body_kind or None, fallback_sms_gateway=fallback_sms_gateway or None,
		fallback_email_gateway=fallback_email_gateway or None,
	)
	if not made.get("success"):
		return _result(made)
	name = made["broadcast"]
	picked = wiring.set_broadcast_audiences(broadcast=name, selection=json.dumps([{"audience": audience}]))
	if not picked.get("success"):
		return _result({"success": False, "error": picked.get("error") or "audience_failed", "message": picked.get("message"), "broadcast": name})
	row = broadcast_api._broadcast_row(name)
	return _out(
		{
			"success": True, "broadcast": name, "status": "Draft", "category": made.get("category"),
			"queued": picked.get("queued"), "skipped_total": picked.get("skipped_total"),
			"blocked": picked.get("blocked"), "consent_attested": bool(row.get("consent_attested")),
			"next_step": (
				"Draft created. Nothing was sent. Consent is not attested: ask the user to open this broadcast in the "
				"HUF broadcast screen and attest consent, then call whatsapp_broadcast_start."
				if not row.get("consent_attested")
				else "Draft created and consent is already attested. Call whatsapp_broadcast_start."
			),
		}
	)


# --- 4. broadcast start (outbound) ------------------------------------------------------------------
def _queued(name: str) -> int:
	from huf.ai.whatsapp.broadcast import api as broadcast_api

	return int(broadcast_api._queued_count(name) or 0)


@_guarded
def handle_broadcast_start(
	broadcast: str = "", expected_recipient_count: Any = None, scheduled_at: str = "", override_warnings: Any = None,
	**_ignored,
) -> str:
	"""Start the broadcast now, or schedule it when ``scheduled_at`` is given. Runs only after human approval.

	Refuses with ``consent_not_attested`` unless a human attested the broadcast; never attests itself.
	"""
	from huf.ai.whatsapp.broadcast import api as broadcast_api, schedule as broadcast_schedule

	row = broadcast_api._require_broadcast_write(broadcast)
	if row.get("error"):
		return _result(row)
	if not row.get("consent_attested") or not row.get("consent_attested_by"):
		return _fail(
			"consent_not_attested",
			"A human must attest recipient consent before this broadcast can be sent. This tool never attests consent.",
			broadcast=broadcast,
			next_step="Ask the user to open this broadcast in the HUF broadcast screen and attest consent (with the consent source), then retry.",
		)
	queued = _queued(broadcast)
	try:
		expected = int(expected_recipient_count)
	except (TypeError, ValueError):
		return _fail("expected_recipient_count_required", "Pass expected_recipient_count (the queued count the user approved).")
	if expected != queued:
		return _fail(
			"recipient_count_changed",
			f"The broadcast now has {queued} queued recipients, not the {expected} that was approved. Nothing was sent.",
			broadcast=broadcast, queued=queued,
		)
	warnings = json.dumps(_parse(override_warnings, "override_warnings") or [])
	if scheduled_at:
		res = broadcast_schedule.schedule_broadcast(
			broadcast=broadcast, scheduled_at=scheduled_at, confirm_count=queued, override_warnings=warnings
		)
	else:
		res = broadcast_api.start_broadcast(broadcast=broadcast, confirm_count=queued, override_warnings=warnings)
	return _result(res)


# --- 5. status --------------------------------------------------------------------------------------
@_guarded
def handle_broadcast_status(broadcast: str = "", **_ignored) -> str:
	"""Counts by status, a sample of failures (phones masked) and the next scheduled broadcast (read only)."""
	from huf.ai.whatsapp.broadcast import api as broadcast_api, api_read

	res = api_read.get_broadcast(broadcast=broadcast)
	if not res.get("success"):
		return _result(res)
	view = res["broadcast"]
	failures = []
	if (view.get("counts") or {}).get("failed"):
		rows = api_read.list_broadcast_recipients(broadcast=broadcast, status="failed", limit=_FAILURE_SAMPLE)
		failures = [
			{"recipient": broadcast_api._mask_phone(r.get("recipient")), "error_code": r.get("error_code"),
			 "error_message": (r.get("error_message") or "")[:160]}
			for r in (rows.get("recipients") or rows.get("rows") or [])
		]
	upcoming = api_read.list_broadcasts(gateway=view.get("gateway"), status="Scheduled", limit=50).get("broadcasts") or []
	upcoming = sorted((b for b in upcoming if b.get("scheduled_at")), key=lambda b: b["scheduled_at"])
	return _out(
		{
			"success": True, "broadcast": broadcast, "title": view.get("title"), "status": view.get("status"),
			"pause_reason": view.get("pause_reason"), "template": view.get("template"), "counts": view.get("counts"),
			"scheduled_at": view.get("scheduled_at"), "consent_attested": bool(view.get("consent_attested")),
			"failures": failures,
			"next_scheduled": ({"broadcast": upcoming[0]["name"], "scheduled_at": upcoming[0]["scheduled_at"]} if upcoming else None),
		}
	)


# --- 6. retry failed (Draft only) -------------------------------------------------------------------
@_guarded
def handle_broadcast_retry_failed(broadcast: str = "", **_ignored) -> str:
	"""Create a new Draft with the retryable failed recipients. Sends nothing; the new Draft needs fresh consent attestation."""
	from huf.ai.whatsapp.broadcast import schedule as broadcast_schedule

	res = broadcast_schedule.retry_failed_recipients(broadcast=broadcast)
	if res.get("success"):
		res = {**res, "next_step": "A new Draft was created. Nothing was sent. A human must attest consent in the HUF broadcast screen before whatsapp_broadcast_start."}
	return _result(res)


# --- tool declarations ------------------------------------------------------------------------------
def _p(fieldname: str, description: str, required: int = 0, type_: str = "string") -> dict:
	return {"label": fieldname.replace("_", " ").title(), "fieldname": fieldname, "type": type_, "required": required, "description": description}


_BASE = "huf.ai.tools.messaging.whatsapp_broadcast_tools"
_COMMON = {"category": "Communication Tools", "required_roles": REQUIRED_ROLES}

WHATSAPP_BROADCAST_TOOLS = [
	{
		"tool_name": "whatsapp_list_templates",
		"description": "List the APPROVED WhatsApp templates of a gateway with category and variable counts (body/header/button). Read only.",
		"function_path": f"{_BASE}.handle_list_templates",
		"parameters": [_p("gateway", "Gateway name", 1)],
		**_COMMON,
	},
	{
		"tool_name": "whatsapp_audience_upsert",
		"description": (
			"Create an audience (gateway + title) or add/replace members of an existing audience (audience). Members are a JSON list of "
			"{recipient, display_name, params, consent_source, consent_at}. Does not send anything and never attests consent."
		),
		"function_path": f"{_BASE}.handle_audience_upsert",
		"parameters": [
			_p("members", "JSON list of {recipient, display_name, params, consent_source, consent_at}", 1),
			_p("audience", "Existing audience name (omit to create)"),
			_p("gateway", "Gateway for a new audience"),
			_p("title", "Title for a new audience"),
			_p("mode", "merge (default) adds/updates; replace also removes members not in the list"),
			_p("consent_purposes", "JSON list of purposes for a new audience (default [\"utility\"])"),
			_p("consent_basis", "Consent basis text for a new audience"),
		],
		**_COMMON,
	},
	{
		"tool_name": "whatsapp_broadcast_create",
		"description": "Create a Draft broadcast from an audience and an approved template with parameters. Sends nothing; consent still needs human attestation.",
		"function_path": f"{_BASE}.handle_broadcast_create",
		"parameters": [
			_p("audience", "Audience name", 1),
			_p("template", "Template name or '<name>-<language_code>'", 1),
			_p("title", "Broadcast title", 1),
			_p("language_code", "Template language code"),
			_p("body_params", "JSON body parameters shared by all recipients"),
			_p("header_params", "JSON header parameter"),
			_p("button_params", "JSON button parameters"),
			_p("fallback_channels", "JSON list of fallback channels (sms, email)"),
			_p("fallback_body", "Plain-text fallback body"),
			_p("fallback_body_kind", "Fallback body kind"),
			_p("fallback_sms_gateway", "SMS gateway for fallback"),
			_p("fallback_email_gateway", "Email gateway for fallback"),
		],
		**_COMMON,
	},
	{
		"tool_name": "whatsapp_broadcast_start",
		"description": (
			"Start a Draft broadcast now, or schedule it when scheduled_at is given. SENDS MESSAGES to real people: always pauses for human approval "
			"showing recipient count, template, channel and audience. Refuses with consent_not_attested unless a human already attested consent in "
			"the HUF broadcast screen; if so, tell the user to attest there."
		),
		"function_path": f"{_BASE}.handle_broadcast_start",
		"is_outbound": 1,
		"confirmation_summary_path": "huf.ai.tools.messaging.confirmation_summaries.whatsapp_broadcast_start",
		"parameters": [
			_p("broadcast", "Draft broadcast name", 1),
			_p("expected_recipient_count", "Queued recipient count the user is approving (from whatsapp_broadcast_status or create)", 1, "number"),
			_p("scheduled_at", "Optional future time (site timezone, YYYY-MM-DD HH:MM:SS) to schedule instead of starting now"),
			_p("override_warnings", "Optional JSON list of acknowledged warning codes"),
		],
		**_COMMON,
	},
	{
		"tool_name": "whatsapp_broadcast_status",
		"description": "Read a broadcast: counts by status, sample of failures (masked) and the next scheduled broadcast on its gateway. Read only.",
		"function_path": f"{_BASE}.handle_broadcast_status",
		"parameters": [_p("broadcast", "Broadcast name", 1)],
		**_COMMON,
	},
	{
		"tool_name": "whatsapp_broadcast_retry_failed",
		"description": "Create a NEW Draft broadcast with the retryable failed recipients of a finished broadcast. Sends nothing; starting it is gated like any broadcast.",
		"function_path": f"{_BASE}.handle_broadcast_retry_failed",
		"parameters": [_p("broadcast", "Finished broadcast name", 1)],
		**_COMMON,
	},
]
