"""Which Solutions own or use a WhatsApp template.

A template is identified by ``(whatsapp_account, Meta template name, language)``; the account is a plain
Data string (never a Link into frappe_whatsapp). Nothing here imports frappe_whatsapp, so it works on
sites without that app. No permission checks: callers (management.py) gate access before calling.
"""

from __future__ import annotations

from typing import Any

import frappe

DOCTYPE = "Template Usage"
BUTTON_PAYLOAD_PREFIX = "sol:"


def _key(account: Any, template: Any, language: Any) -> dict[str, str]:
	return {
		"whatsapp_account": str(account or ""),
		"template": str(template or ""),
		"language": str(language or ""),
	}


def _titles(solutions: list[str]) -> dict[str, str]:
	if not solutions:
		return {}
	rows = frappe.get_all("Solution", filters={"name": ("in", solutions)}, fields=["name", "title"])
	return {r.name: r.title for r in rows}


def _empty() -> dict[str, Any]:
	return {"owner": None, "used_by": [], "shared": False}


def _shape(rows: list[Any], titles: dict[str, str]) -> dict[str, Any]:
	if not rows:
		return _empty()
	used_by = [{"solution": r.solution, "title": titles.get(r.solution) or r.solution} for r in rows]
	owner = next((u for u, r in zip(used_by, rows) if r.kind == "Owner"), None)
	return {"owner": owner, "used_by": used_by, "shared": len(used_by) > 1}


def _fetch(filters: dict[str, Any]) -> list[Any]:
	return frappe.get_all(
		DOCTYPE, filters=filters, fields=["name", "solution", "kind", "source", "whatsapp_account", "template", "language"],
		order_by="creation asc, name asc", limit_page_length=0,
	)


def _row(account: Any, template: Any, language: Any, solution: str) -> Any:
	rows = _fetch({**_key(account, template, language), "solution": solution})
	return rows[0] if rows else None


def _has_owner(account: Any, template: Any, language: Any) -> bool:
	return bool(frappe.db.exists(DOCTYPE, {**_key(account, template, language), "kind": "Owner"}))


def _insert(account: Any, template: Any, language: Any, solution: str, kind: str, source: str) -> None:
	frappe.get_doc(
		{"doctype": DOCTYPE, **_key(account, template, language), "solution": solution, "kind": kind, "source": source}
	).insert(ignore_permissions=True)


def record_observed(account: Any, template: Any, language: Any, solution: str | None) -> None:
	"""A send happened on behalf of ``solution``: idempotent. First writer becomes Owner, later ones User."""
	if not (account and template and solution):
		return
	if _row(account, template, language, solution):
		return
	kind = "User" if _has_owner(account, template, language) else "Owner"
	_insert(account, template, language, solution, kind, "Observed")


def declare(account: Any, template: Any, language: Any, solution: str, owner: bool = False) -> dict[str, Any]:
	"""Declare that ``solution`` uses the template (source Declared); ``owner=True`` also makes it the owner."""
	if not (account and template and solution):
		raise ValueError("account, template and solution are required")
	existing = _row(account, template, language, solution)
	if existing:
		if existing.source != "Declared":
			frappe.db.set_value(DOCTYPE, existing.name, "source", "Declared")
	else:
		kind = "User" if _has_owner(account, template, language) else "Owner"
		_insert(account, template, language, solution, kind if not owner else "User", "Declared")
	if owner:
		set_owner(account, template, language, solution)
	return usage_for(account, template, language)


def set_owner(account: Any, template: Any, language: Any, solution: str) -> None:
	"""Make ``solution`` the single Owner (demoting any previous owner to User); creates the row if missing."""
	for r in _fetch({**_key(account, template, language), "kind": "Owner"}):
		if r.solution != solution:
			frappe.db.set_value(DOCTYPE, r.name, "kind", "User")
	row = _row(account, template, language, solution)
	if row:
		if row.kind != "Owner":
			frappe.db.set_value(DOCTYPE, row.name, "kind", "Owner")
	else:
		_insert(account, template, language, solution, "Owner", "Declared")


def usage_for(account: Any, template: Any, language: Any) -> dict[str, Any]:
	rows = _fetch(_key(account, template, language))
	return _shape(rows, _titles([r.solution for r in rows]))


def bulk_usage(account: Any, templates: list[Any]) -> dict[tuple[str, str], dict[str, Any]]:
	"""Usage for many ``(template, language)`` pairs of one account with two queries."""
	pairs = [(str(t or ""), str(lang or "")) for t, lang in templates]
	if not pairs:
		return {}
	rows = _fetch({"whatsapp_account": str(account or ""), "template": ("in", sorted({p[0] for p in pairs}))})
	grouped: dict[tuple[str, str], list[Any]] = {}
	for r in rows:
		grouped.setdefault((r.template, r.language), []).append(r)
	titles = _titles(sorted({r.solution for r in rows}))
	return {p: _shape(grouped.get(p, []), titles) for p in pairs}


def solutions_templates(account: Any, solution: str) -> set[tuple[str, str]]:
	"""``(template, language)`` pairs a solution uses on an account."""
	rows = _fetch({"whatsapp_account": str(account or ""), "solution": solution})
	return {(r.template, r.language) for r in rows}


def guard_shared(account: Any, template: Any, language: Any, acknowledge: Any) -> dict[str, Any] | None:
	"""``None`` when the change may proceed, else the structured ``shared_template`` refusal."""
	if str(acknowledge).strip().lower() in ("1", "true", "yes"):
		return None
	usage = usage_for(account, template, language)
	if not usage["shared"]:
		return None
	from huf.ai.whatsapp import management

	names = ", ".join(u["title"] for u in usage["used_by"])
	out = management._error("shared_template", f"This template is used by several solutions ({names}).")
	out["used_by"] = usage["used_by"]
	out["owner"] = usage["owner"]
	return out


def template_identity(docname: str) -> tuple[str, str, str] | None:
	"""``(account, Meta template name, language)`` of a WhatsApp Templates document, or None.

	Safe on sites without frappe_whatsapp (returns None).
	"""
	try:
		row = frappe.db.get_value(
			"WhatsApp Templates", docname, ["whatsapp_account", "actual_name", "template_name", "language_code"], as_dict=True
		)
	except Exception:
		return None
	if not row:
		return None
	return (row.get("whatsapp_account") or "", row.get("actual_name") or row.get("template_name") or "", row.get("language_code") or "")


def solution_for_run(run_id: str | None) -> str | None:
	"""The solution an Agent Run belongs to, if any."""
	if not run_id:
		return None
	try:
		return frappe.db.get_value("Agent Run", run_id, "solution") or None
	except Exception:
		return None


def solution_button_payload(solution: str | None, free: str) -> str:
	"""Quick-reply payload carrying the solution (``sol:<solution>|<free>``) so the reply routes back to it.

	Documented helper only: the send path (``whatsapp_templates.build_send_components``) has no quick-reply
	button support, so it is not applied automatically.
	"""
	free = str(free or "")
	return f"{BUTTON_PAYLOAD_PREFIX}{solution}|{free}" if solution else free
