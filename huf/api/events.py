# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Public Event Alias API: discover aliases and emit them from app code."""

from __future__ import annotations

import hashlib
import json

import frappe
from frappe import _

from huf.ai.automation import event_alias as runtime
from huf.ai.automation.runtime_flag import automation_runtime_is_new

_LIST_FIELDS = [
	"name",
	"app",
	"key",
	"label",
	"description",
	"status",
	"version",
	"replaced_by",
	"payload_schema",
	"pii_fields",
]


@frappe.whitelist()
def list_aliases(app: str | None = None) -> list[dict]:
	"""List Event Aliases the caller may read, ordered by app then label."""
	frappe.has_permission("Event Alias", "read", throw=True)
	filters = {"app": app} if app else {}
	return frappe.get_list(
		"Event Alias",
		filters=filters,
		fields=_LIST_FIELDS,
		order_by="app asc, label asc",
		limit_page_length=0,
	)


@frappe.whitelist()
def get_alias(name: str) -> dict:
	"""Return one Event Alias with its sources and recent error count."""
	doc = frappe.get_doc("Event Alias", name)
	doc.check_permission("read")
	out = doc.as_dict()
	out["error_count"] = runtime.get_error_count(doc.name)
	return out


def _resolve_run_as(run_as: str | None) -> str:
	"""Automations run as the session user unless a service user is named.

	Naming a different user needs write access to Event Alias (System Manager
	or Huf Manager), and that user must exist and be enabled.
	"""
	session_user = frappe.session.user
	if not run_as or run_as == session_user:
		return session_user
	if not frappe.has_permission("Event Alias", "write"):
		frappe.throw(_("You do not have permission to run events as another user."), frappe.PermissionError)
	if not frappe.db.get_value("User", run_as, "enabled"):
		frappe.throw(_("User {0} does not exist or is disabled.").format(run_as))
	return run_as


@frappe.whitelist()
def emit(
	app: str,
	key: str,
	payload: dict | str | None = None,
	run_as: str | None = None,
	dedupe_key: str | None = None,
) -> dict:
	"""Emit an Event Alias from app code (for example from an outbox).

	Follows the same rules as document-event aliases: the fire is queued after
	commit (a rollback drops it), duplicates inside a short window are
	ignored, and failures are logged and counted, never raised to the caller.

	``run_as`` names the service user the automations run as. It defaults to
	the calling user; naming someone else needs Event Alias write access.
	``dedupe_key`` overrides the default guard (a hash of the payload).
	"""
	if not app or not key:
		frappe.throw(_("app and key are required."))
	name = f"{app}.{key}"
	if not frappe.db.exists("Event Alias", name):
		frappe.throw(_("Event Alias {0} does not exist.").format(name), frappe.DoesNotExistError)
	frappe.has_permission("Event Alias", "read", doc=name, throw=True)

	if isinstance(payload, str):
		try:
			payload = json.loads(payload) if payload else {}
		except ValueError:
			frappe.throw(_("payload must be valid JSON."))
	if payload is None:
		payload = {}
	if not isinstance(payload, dict):
		frappe.throw(_("payload must be an object."))

	user = _resolve_run_as(run_as)

	if not automation_runtime_is_new():
		return {"alias": name, "scheduled": False, "skipped": "legacy_runtime"}

	try:
		clean = json.loads(frappe.as_json(payload))
		dedupe = dedupe_key or hashlib.sha1(
			json.dumps(clean, sort_keys=True, default=str).encode()
		).hexdigest()
		runtime._schedule(name, clean, str(dedupe), user)
	except Exception:
		runtime.record_failure(name, "emit")
		return {"alias": name, "scheduled": False, "error": True}
	return {"alias": name, "scheduled": True, "run_as": user}
