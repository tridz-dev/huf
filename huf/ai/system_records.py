# Copyright (c) 2025, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Shared "system record" locking pattern.

Several DocTypes (Agent, Flow Definition, and more to come) carry a boolean
flag -- conventionally ``is_system`` -- marking a record as platform-owned
rather than user-owned. System records must be invisible to and untouchable
by anyone who is not a System Manager. Agent (huf/huf/doctype/agent/agent.py)
implemented this ad hoc, in five places, before this module existed. This
module extracts that pattern into reusable, doctype-agnostic pieces:

    - ``make_permission_query_conditions`` -- hides system records from list
      views and queries for non-System-Managers.
    - ``guard_flag_tamper`` -- only a System Manager may flip the flag itself.
    - ``guard_field_immutability`` -- locks every field on a system record
      except an explicit allow-list, for non-System-Managers.
    - ``guard_delete`` -- system records cannot be deleted.
    - ``guard_rename`` -- system records cannot be renamed.

Callers wire these into a Document's ``validate``/``on_trash``/
``before_rename`` and into ``hooks.py``'s ``permission_query_conditions``.
Agent is NOT migrated onto this module (see PLAN.md T-15: that refactor is
filed separately as follow-up F-20 to avoid behaviour risk on a working
feature). Flow Definition is the first and, at the time of writing, only
consumer.

GAP 1 -- lock by default (hardened here, was a gap in Agent):
Agent's immutability guard enumerates the LOCKED fields (a fixed tuple of
seven field names plus one child table). Anything not on that list is
silently editable on a system record -- a new field added to the Agent
DocType is unprotected by default, with no test or reviewer prompted to add
it to the list. ``guard_field_immutability`` inverts this: it walks the
DocType's own field list and locks everything, and the caller instead passes
an explicit ``unlocked_fields`` allow-list of fields that remain editable.
Forgetting to update the allow-list now fails closed (an editable field
becomes locked) instead of failing open (a new field stays silently
editable).

GAP 2 -- Document-lifecycle only (documented here, NOT fixed here):
Every guard in this module is a Document controller hook (``validate``,
``on_trash``, ``before_rename``). None of them run for
``frappe.db.set_value(...)``, ``frappe.db.sql(...)``, bulk update/delete, or
any other path that mutates rows without loading and saving a Document. A
caller with direct DB access -- or a bug that reaches for ``db.set_value``
instead of ``doc.save()`` -- silently bypasses every layer here. This is why
PLAN.md invariant I6 ("Active versions are immutable... Structural, not
merely guarded") requires T-20's Agent Procedure version immutability to be
a property of the data model (e.g. a separate, append-only version table, or
a DB-level constraint) and NOT implemented by calling into this module. Do
not extend this module to claim it enforces immutability against raw SQL --
it does not, and cannot, from the Document layer.
"""

import frappe
from frappe import _

# Flags under which system-record guards do not apply -- these are the
# trusted, non-interactive code paths (fixtures, app install, migrations,
# uninstall) that must be able to create/modify/remove system records freely.
_MUTATION_BYPASS_FLAGS = ("in_seeding", "in_install", "in_migrate")
_LIFECYCLE_BYPASS_FLAGS = ("in_install", "in_migrate", "in_uninstall")

# DocType field types that never hold a comparable value (layout-only), so
# they are excluded from the lock-by-default sweep in guard_field_immutability.
_NO_VALUE_FIELDTYPES = {
	"Section Break",
	"Column Break",
	"Tab Break",
	"HTML",
	"Button",
	"Fold",
	"Heading",
}

_CHILD_TABLE_FIELDTYPES = {"Table", "Table MultiSelect"}


def _is_privileged(bypass_flags):
	if "System Manager" in frappe.get_roles():
		return True
	return any(getattr(frappe.flags, flag, False) for flag in bypass_flags)


def make_permission_query_conditions(doctype: str, flag_field: str = "is_system"):
	"""Build a ``permission_query_conditions`` hook function for ``doctype``.

	Register the returned callable in hooks.py::

	    permission_query_conditions = {
	        "Flow Definition": "huf.ai.system_records.make_permission_query_conditions(...)",
	    }

	In practice hooks.py needs a plain dotted path, not a factory call, so
	doctype controllers should instead expose a thin module-level wrapper --
	see flow_definition.py's ``get_permission_query_conditions`` -- that
	calls this factory once and delegates to it. Non-System-Managers never
	see a row where ``flag_field`` is truthy.
	"""

	def get_permission_query_conditions(user=None):
		if not user:
			user = frappe.session.user
		if "System Manager" in frappe.get_roles(user):
			return None
		return f"`tab{doctype}`.`{flag_field}` = 0"

	return get_permission_query_conditions


def guard_flag_tamper(doc, flag_field: str = "is_system", message=None):
	"""Throw if a non-privileged user is changing ``flag_field`` itself."""
	if doc.is_new():
		return
	if not doc.has_value_changed(flag_field):
		return
	if _is_privileged(_MUTATION_BYPASS_FLAGS):
		return

	frappe.throw(
		message or _("Only System Managers can change the {0} flag.").format(flag_field),
		title=_("System Record Protected"),
	)


def guard_field_immutability(
	doc,
	flag_field: str = "is_system",
	unlocked_fields: tuple = (),
	unlocked_child_tables: tuple = (),
	message=None,
):
	"""Lock every field on a system record except an explicit allow-list.

	Lock-by-default (GAP 1, see module docstring): this walks ``doc.meta``'s
	own field list rather than a caller-maintained "locked" list, so a field
	added to the DocType later is protected automatically. ``unlocked_fields``
	and ``unlocked_child_tables`` name what stays editable; everything else
	on a system record (``doc.get(flag_field)`` truthy) is locked for
	non-System-Managers.
	"""
	if not doc.get(flag_field) or doc.is_new():
		return
	if _is_privileged(_MUTATION_BYPASS_FLAGS):
		return

	before = doc.get_doc_before_save()
	if not before:
		return

	unlocked = set(unlocked_fields) | {flag_field}
	unlocked_children = set(unlocked_child_tables)
	changed = []

	for df in doc.meta.fields:
		fieldname = df.fieldname
		if fieldname in unlocked or df.fieldtype in _NO_VALUE_FIELDTYPES:
			continue

		if df.fieldtype in _CHILD_TABLE_FIELDTYPES:
			if fieldname in unlocked_children:
				continue
			current_rows = [row.as_dict() for row in doc.get(fieldname) or []]
			previous_rows = [row.as_dict() for row in before.get(fieldname) or []]
			if frappe.as_json(current_rows) != frappe.as_json(previous_rows):
				changed.append(fieldname)
			continue

		if doc.has_value_changed(fieldname):
			changed.append(fieldname)

	if changed:
		frappe.throw(
			message
			or _("Only System Managers can modify {0} on a system record.").format(", ".join(changed)),
			title=_("System Record Protected"),
		)


def guard_delete(doc, flag_field: str = "is_system", message=None):
	"""Throw if a system record is being deleted outside a trusted flag."""
	if not doc.get(flag_field):
		return
	if _is_privileged(_LIFECYCLE_BYPASS_FLAGS):
		return

	frappe.throw(
		message or _("System records cannot be deleted."),
		title=_("System Record Protected"),
	)


def guard_rename(doc, old_name: str = None, new_name: str = None, merge: bool = False, flag_field: str = "is_system", message=None):
	"""Throw if a system record is being renamed outside a trusted flag."""
	if not doc.get(flag_field):
		return
	if _is_privileged(_LIFECYCLE_BYPASS_FLAGS):
		return

	frappe.throw(
		message or _("System records cannot be renamed."),
		title=_("System Record Protected"),
	)
