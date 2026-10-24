"""Write API for Solutions (API contract v1, WP S2).

Every function is whitelisted, accepts dict or JSON-string arguments, checks ``_can_manage_integrations()``
(A11) plus Gateway write authority, runs inside a savepoint (a failure creates nothing) and returns either
the plain object or ``{"error": {"code", "message"}}``.
"""

from __future__ import annotations

import functools
import re
from typing import Any

import frappe

from huf.ai.solutions import intents, template_usage
from huf.ai.solutions.read_models import _error, _summary_for, list_entry_points
from huf.ai.whatsapp.management import _can_manage_integrations, _gateway_write_allowed

PRIORITY = {"Keyword": 1, "Ad or link tag": 2, "Catch-all": 8, "Triage": 9}
_MULTI = ("Keyword", "Ad or link tag")
_ENTRY_TYPES = tuple(PRIORITY)
_UPDATABLE = {
	"title", "description", "purpose", "primary_target_type", "primary_agent", "primary_flow", "test_mode",
}
_CODE = re.compile(r"^\s*(cap_exceeds_ceiling|scope_loosening)\s*:\s*(.*)", re.S)


class _Err(Exception):
	def __init__(self, code: str, message: str = ""):
		super().__init__(message)
		self.code, self.message = code, message


def _arg(value: Any, label: str) -> Any:
	if isinstance(value, str):
		if not value.strip():
			return None
		try:
			return frappe.parse_json(value)
		except Exception:
			raise _Err("invalid_payload", f"{label} must be valid JSON")
	return value


def _obj(value: Any, label: str) -> dict:
	parsed = _arg(value, label)
	if not isinstance(parsed, dict):
		raise _Err("invalid_payload", f"{label} must be an object")
	return parsed


def _name(value: Any, label: str) -> str:
	if isinstance(value, str) and value.strip().startswith(("{", '"')):
		value = _arg(value, label)
	if isinstance(value, dict):
		value = value.get("name")
	value = str(value or "").strip()
	if not value:
		raise _Err("invalid_payload", f"{label} is required")
	return value


def _api(fn):
	"""Permission gate, savepoint (atomic) and error mapping."""

	@functools.wraps(fn)
	def wrapper(*args, **kwargs):
		if not _can_manage_integrations():
			return _error("not_permitted", "Not permitted to manage solutions.")
		sp = "solutions_crud_sp"
		frappe.db.savepoint(sp)
		try:
			return fn(*args, **kwargs)
		except _Err as exc:
			frappe.db.rollback(save_point=sp)
			return _error(exc.code, exc.message)
		except frappe.PermissionError:
			frappe.db.rollback(save_point=sp)
			return _error("not_permitted", "Not permitted.")
		except frappe.ValidationError as exc:
			frappe.db.rollback(save_point=sp)
			text = re.sub(r"<[^>]+>", "", str(exc))
			match = _CODE.match(text)
			if match:
				return _error(match.group(1), match.group(2).strip())
			return _error("invalid_payload", text)
		except Exception:
			frappe.db.rollback(save_point=sp)
			raise

	return wrapper


def _gateway_check(gateway: str) -> None:
	if not frappe.db.exists("Gateway", gateway):
		raise _Err("not_found", "Gateway not found.")
	if not _gateway_write_allowed(gateway):
		raise _Err("not_permitted", "Not permitted to change this Gateway.")


def _solution(name: str):
	if not frappe.db.exists("Solution", name):
		raise _Err("not_found", "Solution not found.")
	return frappe.get_doc("Solution", name)


def _target(target_type: Any, name: Any) -> tuple[str, str]:
	if target_type not in ("Agent", "Flow"):
		raise _Err("invalid_payload", "Target type must be Agent or Flow.")
	if not name:
		raise _Err("invalid_payload", f"Choose a {target_type.lower()}.")
	if not frappe.db.exists("Agent" if target_type == "Agent" else "Flow Definition", name):
		raise _Err("not_found", f"{target_type} not found.")
	return target_type, str(name)


def _clean_entry(entry: Any) -> dict:
	if not isinstance(entry, dict):
		raise _Err("invalid_payload", "Each entry must be an object.")
	match_type = entry.get("match_type")
	if match_type not in _ENTRY_TYPES:
		raise _Err("invalid_payload", "match_type must be one of " + ", ".join(_ENTRY_TYPES) + ".")
	values = entry.get("match_values") or []
	if isinstance(values, str):
		values = [v for v in values.split(",")]
	values = [str(v).strip() for v in values if str(v).strip()]
	if match_type in _MULTI and not values:
		raise _Err("invalid_payload", f"{match_type} needs at least one value.")
	return {**entry, "match_type": match_type, "match_values": values}


def _binding_fields(sol, entry: dict) -> dict:
	"""Gateway Binding field values for a cleaned entry of solution ``sol``."""
	triage = entry["match_type"] == "Triage"
	f: dict[str, Any] = {
		"match_type": "Catch-all" if triage else entry["match_type"],
		"match_value": ", ".join(entry["match_values"]) if entry["match_type"] in _MULTI else "",
		"target_type": "Triage" if triage else (sol.primary_target_type or "Agent"),
		"agent": None if triage else sol.primary_agent,
		"flow": None if triage else sol.primary_flow,
	}
	if "cap_per_day" in entry:
		f["cap_per_day"] = int(entry["cap_per_day"] or 0)
	if "allow_first_message" in entry:
		f["allow_first_message"] = 1 if entry["allow_first_message"] else 0
	if "is_enabled" in entry:
		f["is_enabled"] = 1 if entry["is_enabled"] else 0
	scope = entry.get("scope_override")
	if sol.purpose == "team":
		scope = "Allow list"
	if "scope_override" in entry or sol.purpose == "team":
		f["scope_override"] = scope or ""
	return f


def _account(gateway: str) -> str:
	return frappe.db.get_value("Gateway", gateway, "whatsapp_account") or ""


def _declare_templates(gateway: str, solution: str, templates: list, draft: Any) -> None:
	account = _account(gateway)
	if templates and not account:
		raise _Err("invalid_payload", "Templates need a WhatsApp gateway with an account.")
	for tpl in templates:
		tpl = str(tpl or "").strip()
		if not tpl:
			continue
		ident = template_usage.template_identity(tpl)
		name, lang = (ident[1], ident[2]) if ident else (tpl, "")
		template_usage.declare(account, name, lang, solution)
	if draft:
		if not isinstance(draft, dict):
			raise _Err("invalid_payload", "draft_template must be an object.")
		from huf.ai.whatsapp import management

		name = str(draft.get("name") or "").strip()
		lang = str(draft.get("language") or "en")
		title = frappe.db.get_value("Solution", solution, "title")
		payload = {
			"template_name": name,
			"language_code": lang,
			"category": str(draft.get("category") or "UTILITY").upper(),
			"body": draft.get("body") or draft.get("template") or f"Hello, this is {title}. Reply to this message and we will help.",
		}
		review = str(draft.get("status") or "Draft") != "Draft"
		res = management.create_template_draft(payload=payload, submit_for_review=1 if review else 0, gateway_name=gateway)
		if not isinstance(res, dict) or not res.get("success"):
			err = (res or {}).get("error")
			code = err.get("code") if isinstance(err, dict) else err
			raise _Err("invalid_payload", f"Template draft failed: {code or 'unknown'}. {(res or {}).get('message', '')}".strip())
		if account:
			template_usage.declare(account, name, lang, solution)


def _cascade_target(sol) -> None:
	for row in frappe.get_all("Gateway Binding", filters={"solution": sol.name, "target_type": ("!=", "Triage")}, pluck="name"):
		b = frappe.get_doc("Gateway Binding", row)
		b.target_type = sol.primary_target_type or "Agent"
		b.agent = sol.primary_agent
		b.flow = sol.primary_flow
		b.save(ignore_permissions=True)


def _entry_for(solution: str, name: str) -> dict:
	rows = list_entry_points(solution)
	if isinstance(rows, dict):
		raise _Err(rows["error"]["code"], rows["error"]["message"])
	return next((r for r in rows if r["name"] == name), {})


@frappe.whitelist(methods=["POST"])
@_api
def create_solution(payload):
	p = _obj(payload, "payload")
	title = str(p.get("title") or "").strip()
	if not title:
		raise _Err("invalid_payload", "Title is required.")
	mode = p.get("mode")
	if mode not in ("intent", "existing", "blank"):
		raise _Err("invalid_payload", "mode must be intent, existing or blank.")
	purpose = "custom" if mode == "blank" else (p.get("purpose") or "custom")
	if purpose not in intents.PURPOSES:
		raise _Err("invalid_payload", "Unknown purpose.")
	gateway = str(p.get("gateway") or "").strip()
	if not gateway:
		raise _Err("invalid_payload", "gateway is required.")
	_gateway_check(gateway)
	target = None
	if mode == "existing":
		et = p.get("existing_target")
		if not isinstance(et, dict):
			raise _Err("invalid_payload", "existing_target is required for mode existing.")
		target = _target(et.get("type"), et.get("name"))
	inbound = bool(p.get("inbound", True))
	entries = [_clean_entry(e) for e in (p.get("entries") or [])] if inbound else []
	templates = p.get("templates") or []
	if not isinstance(templates, list):
		raise _Err("invalid_payload", "templates must be a list.")

	doc = {"doctype": "Solution", "title": title, "purpose": purpose, "status": "Paused", "test_mode": 1 if p.get("test_mode") else 0}
	if p.get("description"):
		doc["description"] = p["description"]
	if target:
		doc["primary_target_type"] = target[0]
		doc["primary_agent" if target[0] == "Agent" else "primary_flow"] = target[1]
	sol = frappe.get_doc(doc).insert(ignore_permissions=True)
	for e in entries:
		frappe.get_doc(
			{"doctype": "Gateway Binding", "gateway": gateway, "solution": sol.name, "is_enabled": 1,
			 "priority": PRIORITY[e["match_type"]], **_binding_fields(sol, e)}
		).insert(ignore_permissions=True)
	_declare_templates(gateway, sol.name, templates, p.get("draft_template"))
	return _summary_for(sol.name)


@frappe.whitelist(methods=["POST"])
@_api
def update_solution(name, fields):
	sol = _solution(_name(name, "name"))
	f = _obj(fields, "fields")
	bad = set(f) - _UPDATABLE
	if bad:
		raise _Err("invalid_payload", "Cannot update: " + ", ".join(sorted(bad)))
	if "purpose" in f and f["purpose"] not in intents.PURPOSES:
		raise _Err("invalid_payload", "Unknown purpose.")
	retarget = {"primary_target_type", "primary_agent", "primary_flow"} & set(f)
	if retarget:
		ttype = f.get("primary_target_type", sol.primary_target_type)
		if ttype in (None, ""):
			if sol.status == "Live":
				raise _Err("no_target", "A live solution needs an answering agent or flow.")
			f.update(primary_target_type=None, primary_agent=None, primary_flow=None)
		else:
			agent = f.get("primary_agent") if "primary_agent" in f else (sol.primary_agent if ttype == "Agent" else None)
			flow = f.get("primary_flow") if "primary_flow" in f else (sol.primary_flow if ttype == "Flow" else None)
			_target(ttype, agent if ttype == "Agent" else flow)
			f.update(primary_target_type=ttype, primary_agent=agent if ttype == "Agent" else None, primary_flow=flow if ttype == "Flow" else None)
	if "test_mode" in f:
		f["test_mode"] = 1 if f["test_mode"] else 0
	sol.update(f)
	sol.save(ignore_permissions=True)
	if retarget:
		_cascade_target(sol)
	return _summary_for(sol.name)


@frappe.whitelist(methods=["POST"])
@_api
def pause_solution(name):
	sol = _solution(_name(name, "name"))
	sol.status = "Paused"
	sol.save(ignore_permissions=True)
	return _summary_for(sol.name)


@frappe.whitelist(methods=["POST"])
@_api
def resume_solution(name):
	sol = _solution(_name(name, "name"))
	if sol.test_mode:
		raise _Err("invalid_payload", "A solution in test mode cannot be resumed. Use Go live.")
	if not sol.primary_target_type:
		raise _Err("no_target", "Choose an agent or flow before resuming.")
	sol.status = "Live"
	sol.save(ignore_permissions=True)
	return _summary_for(sol.name)


@frappe.whitelist(methods=["POST"])
@_api
def go_live(name):
	sol = _solution(_name(name, "name"))
	if not sol.primary_target_type:
		raise _Err("no_target", "Choose an agent or flow before going live.")
	intent = intents.get_intent(sol.purpose)
	if not (intent and intent["entry"] == "none"):
		if not frappe.db.exists("Gateway Binding", {"solution": sol.name, "is_enabled": 1}):
			raise _Err("invalid_payload", "Add at least one enabled entry point before going live.")
	_cascade_target(sol)
	sol.test_mode = 0
	sol.status = "Live"
	sol.save(ignore_permissions=True)
	return _summary_for(sol.name)


@frappe.whitelist(methods=["POST"])
@_api
def save_entry_point(solution, entry):
	sol = _solution(_name(solution, "solution"))
	e = _obj(entry, "entry")
	existing = None
	if e.get("name"):
		if not frappe.db.exists("Gateway Binding", {"name": e["name"], "solution": sol.name}):
			raise _Err("not_found", "Entry point not found.")
		existing = frappe.get_doc("Gateway Binding", e["name"])
	if existing:
		current = "Triage" if existing.target_type == "Triage" else existing.match_type
		e = {"match_type": current, "match_values": [v.strip() for v in (existing.match_value or "").split(",") if v.strip()], **e}
	e = _clean_entry(e)
	gateway = e.get("gateway") or (existing.gateway if existing else None) or frappe.db.get_value(
		"Gateway Binding", {"solution": sol.name}, "gateway"
	)
	if not gateway:
		raise _Err("invalid_payload", "gateway is required.")
	_gateway_check(gateway)
	fields = _binding_fields(sol, e)
	if existing:
		existing.update({**fields, "gateway": gateway})
		if e.get("priority") is not None:
			existing.priority = int(e["priority"])
		existing.save(ignore_permissions=True)
		doc = existing
	else:
		doc = frappe.get_doc(
			{"doctype": "Gateway Binding", "gateway": gateway, "solution": sol.name, "is_enabled": 1,
			 "priority": int(e["priority"]) if e.get("priority") is not None else PRIORITY[e["match_type"]], **fields}
		).insert(ignore_permissions=True)
	return _entry_for(sol.name, doc.name)


@frappe.whitelist(methods=["POST"])
@_api
def delete_entry_point(name):
	name = _name(name, "name")
	row = frappe.db.get_value("Gateway Binding", name, ["solution", "gateway"], as_dict=True)
	if not row:
		raise _Err("not_found", "Entry point not found.")
	if not row.solution:
		raise _Err("invalid_payload", "This entry point does not belong to a solution.")
	_gateway_check(row.gateway)
	if frappe.db.get_value("Solution", row.solution, "status") == "Live" and frappe.db.count("Gateway Binding", {"solution": row.solution}) <= 1:
		raise _Err("invalid_payload", "A live solution needs at least one entry point. Pause it first.")
	frappe.delete_doc("Gateway Binding", name, ignore_permissions=True)
	return {"deleted": name}
