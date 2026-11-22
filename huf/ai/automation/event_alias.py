# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Event Aliases: business names for raw document events.

An Event Alias maps ``(reference_doctype, doc_event)`` to a named event such
as ``shop.customer_purchase`` and fires the existing App Event automation
trigger. No new trigger type.

Runtime rules (see the PR spec):

* fires once, after commit (a rollback fires nothing, repeated saves dedupe);
* never fails a save: every error is logged, counted, and swallowed;
* zero cost for doctypes without aliases: one cached map lookup, no queries;
* the map is cleared whenever an Event Alias is saved or deleted.
"""

from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.utils.safe_exec import safe_eval

from huf.ai.automation.app_event import fan_out_app_event
from huf.ai.automation.runtime_flag import automation_runtime_is_new

MAP_CACHE_KEY = "huf:event_alias_map"
HEALTH_CACHE_KEY = "huf:event_alias_health"
DEDUPE_PREFIX = "huf:event_alias_dedupe:"
DEDUPE_TTL_SECONDS = 30

# Doc events an Event Alias Source may listen to (matches the Select options).
ALIAS_DOC_EVENTS = (
	"after_insert",
	"on_update",
	"on_submit",
	"on_cancel",
	"on_trash",
	"after_delete",
)

# Doctypes the wildcard hook never dispatches for: our own housekeeping doctypes
# and Error Log (record_failure() inserts one). Everything else, including
# Communication or Comment, is a legitimate alias source. Recursion safety
# comes from the re-entrancy flag, not from this list.
IGNORED_DOCTYPES = frozenset({"Event Alias", "Event Alias Source", "Error Log"})

_REENTRY_FLAG = "huf_event_alias_dispatching"


# --------------------------------------------------------------------------
# Authoring helpers (used by the Event Alias controller)
# --------------------------------------------------------------------------


def check_expression(expression: str, field_label: str, row_idx: int | None = None):
	"""Raise a readable error if ``expression`` is not valid Python syntax."""
	try:
		compile(expression, "<event alias>", "eval")
	except SyntaxError as e:
		frappe.throw(
			_("Row {0}: {1} is not a valid expression ({2}).").format(row_idx or "?", _(field_label), e.msg)
		)


def parse_mapping(raw, row_idx: int | None = None) -> dict:
	"""Parse a Payload Mapping value (JSON object of name -> expression)."""
	if not raw:
		return {}
	try:
		mapping = json.loads(raw) if isinstance(raw, str) else raw
	except ValueError:
		frappe.throw(_("Row {0}: Payload Mapping must be valid JSON.").format(row_idx or "?"))
	if not isinstance(mapping, dict):
		frappe.throw(_("Row {0}: Payload Mapping must be a JSON object.").format(row_idx or "?"))
	for name, expression in mapping.items():
		check_expression(str(expression), f"Payload Mapping ({name})", row_idx)
	return mapping


# --------------------------------------------------------------------------
# Cached map
# --------------------------------------------------------------------------


def clear_alias_cache():
	try:
		frappe.cache().delete_value(MAP_CACHE_KEY)
	except Exception:
		pass


def _build_map() -> dict:
	sources: dict[str, list] = {}
	aliases: dict[str, dict] = {}
	for alias in frappe.get_all(
		"Event Alias",
		fields=["name", "app", "key", "status", "version", "replaced_by"],
	):
		aliases[alias["name"]] = dict(alias)
		rows = frappe.get_all(
			"Event Alias Source",
			filters={"parent": alias["name"], "parenttype": "Event Alias", "enabled": 1},
			fields=["reference_doctype", "doc_event", "condition", "payload_mapping", "dedupe_key"],
			order_by="idx asc",
		)
		for row in rows:
			try:
				mapping = parse_mapping(row.get("payload_mapping"))
			except Exception:
				mapping = {}
			sources.setdefault(f"{row['reference_doctype']}|{row['doc_event']}", []).append(
				{
					"alias": alias["name"],
					"condition": row.get("condition") or "",
					"payload_mapping": mapping,
					"dedupe_key": row.get("dedupe_key") or "",
				}
			)
	return {"sources": sources, "aliases": aliases}


def _tables_ready() -> bool:
	try:
		return bool(frappe.db.table_exists("Event Alias") and frappe.db.table_exists("Event Alias Source"))
	except Exception:
		return False


def get_alias_map() -> dict:
	"""Return the cached map, building it on first use. An empty map is cached too."""
	cached = frappe.cache().get_value(MAP_CACHE_KEY)
	if cached is not None:
		return cached
	if not _tables_ready():
		# Doctype not migrated yet (first migrate after upgrade): empty map,
		# deliberately not cached so the real map is built once the table exists.
		return {"sources": {}, "aliases": {}}
	built = _build_map()
	frappe.cache().set_value(MAP_CACHE_KEY, built)
	return built


def get_sources(doctype: str, event: str) -> list:
	return get_alias_map()["sources"].get(f"{doctype}|{event}") or []


# --------------------------------------------------------------------------
# Health counter
# --------------------------------------------------------------------------


def record_failure(alias: str | None, where: str):
	"""Log to Error Log and count against the alias. Must never raise.

	Runs with the re-entrancy flag set so the Error Log insert cannot fire
	``dispatch_doc_event`` again.
	"""
	previous = getattr(frappe.local, _REENTRY_FLAG, False)
	setattr(frappe.local, _REENTRY_FLAG, True)
	try:
		frappe.log_error(
			title=f"Event Alias error: {alias or 'unknown'} ({where})", message=frappe.get_traceback()
		)
	except Exception:
		pass
	finally:
		setattr(frappe.local, _REENTRY_FLAG, previous)
	try:
		raw = frappe.cache().hget(HEALTH_CACHE_KEY, alias or "unknown")
		count = int(raw or 0) + 1
		frappe.cache().hset(HEALTH_CACHE_KEY, alias or "unknown", count)
	except Exception:
		pass


def get_error_count(alias: str) -> int:
	try:
		return int(frappe.cache().hget(HEALTH_CACHE_KEY, alias) or 0)
	except Exception:
		return 0


# --------------------------------------------------------------------------
# Dispatcher (hooks.py doc_events["*"])
# --------------------------------------------------------------------------


def dispatch_doc_event(doc, method=None, *args, **kwargs):
	"""Fire matching Event Aliases for a document event, after commit.

	Never raises. Returns immediately (no queries) for doctypes without aliases.
	"""
	previous = getattr(frappe.local, _REENTRY_FLAG, False)
	if previous:
		return
	setattr(frappe.local, _REENTRY_FLAG, True)
	try:
		_dispatch(doc, method)
	except Exception:
		record_failure(None, "dispatch")
	finally:
		setattr(frappe.local, _REENTRY_FLAG, previous)


def _dispatch(doc, method):
	if method not in ALIAS_DOC_EVENTS:
		return
	if doc.doctype in IGNORED_DOCTYPES:
		return
	if frappe.flags.in_import or frappe.flags.in_patch or frappe.flags.in_install or frappe.flags.in_migrate:
		return

	sources = get_sources(doc.doctype, method)
	if not sources:
		return

	if not automation_runtime_is_new():
		_log_legacy_once()
		return

	user = frappe.session.user
	for source in sources:
		try:
			prepared = _prepare(doc, method, source)
			if prepared:
				_schedule(source["alias"], prepared["payload"], prepared["dedupe"], user)
		except Exception:
			record_failure(source.get("alias"), "dispatch")


def _prepare(doc, method: str, source: dict) -> dict | None:
	context = {"doc": doc, "event": method}
	if source["condition"] and not safe_eval(source["condition"], None, dict(context)):
		return None

	mapping = source["payload_mapping"]
	if mapping:
		payload = {name: safe_eval(str(expr), None, dict(context)) for name, expr in mapping.items()}
	else:
		payload = {"doctype": doc.doctype, "name": doc.name}

	if source["dedupe_key"]:
		dedupe = str(safe_eval(source["dedupe_key"], None, dict(context)))
	else:
		dedupe = f"{doc.doctype}:{doc.name}:{method}"
	return {"payload": json.loads(frappe.as_json(payload)), "dedupe": dedupe}


def _schedule(alias: str, payload: dict, dedupe: str, user: str):
	"""Queue the fire for after commit. A rollback drops the callback."""

	def after_commit():
		try:
			if not claim_dedupe(alias, dedupe):
				return
			frappe.enqueue(
				"huf.ai.automation.event_alias.fire_alias",
				queue="default",
				alias_name=alias,
				payload=payload,
				run_as=user,
				enqueue_after_commit=False,
			)
		except Exception:
			record_failure(alias, "enqueue")

	frappe.db.after_commit.add(after_commit)


def claim_dedupe(alias: str, dedupe: str) -> bool:
	"""True the first time (alias, dedupe) is seen inside the TTL window."""
	key = f"{DEDUPE_PREFIX}{alias}:{dedupe}"
	cache = frappe.cache()
	if cache.get_value(key, expires=True):
		return False
	cache.set_value(key, 1, expires_in_sec=DEDUPE_TTL_SECONDS)
	return True


def _log_legacy_once():
	if frappe.flags.get("huf_event_alias_legacy_logged"):
		return
	frappe.flags.huf_event_alias_legacy_logged = True
	frappe.logger("huf").info("Event Alias dispatcher skipped: automation runtime is set to legacy.")


# --------------------------------------------------------------------------
# Firing
# --------------------------------------------------------------------------


def fire_alias(alias_name: str, payload: dict | None = None, run_as: str | None = None) -> dict:
	"""Run the App Event automations for an alias. Never raises.

	Shared by the doc-event dispatcher and the direct ``emit`` API.
	"""
	try:
		if not automation_runtime_is_new():
			_log_legacy_once()
			return {"triggered": 0, "skipped": "legacy_runtime"}

		meta = get_alias_map()["aliases"].get(alias_name)
		if not meta:
			return {"triggered": 0, "skipped": "unknown_alias"}

		if meta.get("status") == "Deprecated":
			frappe.logger("huf").warning(
				f"Event Alias {alias_name} is deprecated; use {meta.get('replaced_by') or 'its replacement'}."
			)

		return fan_out_app_event(meta["app"], meta["key"], payload or {}, run_as or frappe.session.user)
	except Exception:
		record_failure(alias_name, "fire")
		return {"triggered": 0, "error": True}


# --------------------------------------------------------------------------
# Versioning
# --------------------------------------------------------------------------


def deprecate_alias(name: str, replaced_by: str | None = None):
	"""Mark an alias Deprecated (optionally pointing at its replacement) and bump its version.

	Automations on a deprecated alias keep firing; ``fire_alias`` warns.
	"""
	doc = frappe.get_doc("Event Alias", name)
	doc.status = "Deprecated"
	doc.replaced_by = replaced_by
	doc.version = (doc.version or 1) + 1
	doc.save(ignore_permissions=True)
	return doc


# --------------------------------------------------------------------------
# Python-defined aliases (``huf_event_aliases`` hook)
# --------------------------------------------------------------------------


def _hook_alias_definitions() -> list[dict]:
	"""Collect alias dicts from every app's ``huf_event_aliases`` hook.

	Each hook entry is a dict, a list of dicts, or a dotted path to a callable
	returning either.
	"""
	found: list[dict] = []
	for entry in frappe.get_hooks("huf_event_aliases") or []:
		try:
			value = frappe.get_attr(entry)() if isinstance(entry, str) else entry
		except Exception:
			record_failure(None, "hook_aliases")
			continue
		if isinstance(value, dict):
			value = [value]
		found.extend(v for v in value or [] if isinstance(v, dict))
	return found


def sync_hook_aliases() -> int:
	"""Upsert aliases declared through the hook, with the same snapshot and admin-edit rules as seed files."""
	from huf.ai.app_seeding.loaders import upsert_event_alias

	count = 0
	for definition in _hook_alias_definitions():
		ok, error = upsert_event_alias(definition, definition.get("app"), "hooks:huf_event_aliases")
		if ok:
			count += 1
		else:
			frappe.logger("huf").warning(f"huf_event_aliases entry skipped: {error}")
	return count
