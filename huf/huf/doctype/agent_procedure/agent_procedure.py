# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Agent Procedure -- the compiled/authored definition (T-20).

Structural version immutability (I6, GT-01, GT-14): each ``Agent Procedure`` document
IS one version. A logical procedure's versions are the set of rows sharing the same
``procedure_id``, distinguished by ``version``. The docname is deterministically built
as ``"<procedure_id>-v<version>"`` (see ``autoname`` below) and is therefore the row's
own primary key -- MariaDB's primary-key uniqueness constraint is what makes a second
insert with the same ``(procedure_id, version)`` pair structurally impossible
(``frappe.db.name_exists`` / a duplicate INSERT raises ``frappe.DuplicateEntryError``),
independent of any validate hook and unreachable by ``frappe.db.set_value`` (which can
only ever target an *existing* name, never fabricate a colliding new one). "Saving a new
version" is therefore always a fresh ``frappe.get_doc({...}).insert()`` with
``version`` left blank (auto-computed as ``max(version) + 1`` for the ``procedure_id``),
never an update to an existing row.

``validate()`` additionally guards content-field immutability on update (defence in
depth, per GT-14's own documented gap: this layer does not run for
``frappe.db.set_value``/raw SQL, only for ``Document.save()``). The structural guarantee
above is the one that matters; this guard exists so an accidental ``doc.save()`` in
application code fails loudly instead of silently corrupting a version's content.
"""

import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

from huf.ai import system_records
from huf.ai.procedure_versioning import (
	CONTENT_FIELDS,
	FlowOnlyNodeError,
	assert_no_flow_only_nodes,
	compute_fingerprint,
	extract_contract_fields,
)

# Tiers that lock a version's fields for non-System-Managers (D12). Draft is the only
# tier an ordinary author may create/hold without System Manager privileges.
LOCKED_TIERS = {"System", "Compiled"}

# Fields that stay editable on a system-tier (System/Compiled) row for non-admins.
# Content fields are never in this list -- they are immutable at every tier, always,
# via the separate _guard_content_immutability below, not via system_records at all.
SYSTEM_RECORD_UNLOCKED_FIELDS: tuple = (
	"status",
	"provenance",
	"confidence",
	"created_from_runs",
	"updated_by",
	"updated_at",
)


def get_permission_query_conditions(user=None):
	"""Hide System/Compiled-tier Agent Procedures from non-System-Managers. Registered in hooks.py."""
	return system_records.make_permission_query_conditions("Agent Procedure")(user)


def _next_version(procedure_id: str) -> int:
	current_max = frappe.db.sql(
		"select max(version) from `tabAgent Procedure` where procedure_id = %s",
		(procedure_id,),
	)
	if current_max and current_max[0][0]:
		return int(current_max[0][0]) + 1
	return 1


class AgentProcedure(Document):
	def autoname(self):
		if not self.procedure_id:
			frappe.throw(_("procedure_id is required"))
		if not self.version:
			self.version = _next_version(self.procedure_id)
		self.name = f"{self.procedure_id}-v{self.version}"

	def validate(self):
		self._parse_and_apply_definition()
		self.tier = self.tier or "Draft"
		self.is_system = 1 if self.tier in LOCKED_TIERS else 0
		self.updated_by = frappe.session.user
		self.updated_at = now_datetime()

		self._guard_content_immutability()
		system_records.guard_flag_tamper(
			self, message=_("Only System Managers can change an Agent Procedure's tier.")
		)
		system_records.guard_field_immutability(self, unlocked_fields=SYSTEM_RECORD_UNLOCKED_FIELDS)

	def on_trash(self):
		system_records.guard_delete(self)

	def before_rename(self, old_name: str, new_name: str, merge: bool = False):
		# Renaming would break the procedure_id-vN identity the structural immutability
		# guarantee depends on -- never allowed, for any tier.
		frappe.throw(_("Agent Procedure records cannot be renamed."))

	def _parse_and_apply_definition(self):
		if not self.definition_json:
			frappe.throw(_("definition_json is required"))

		definition = (
			json.loads(self.definition_json)
			if isinstance(self.definition_json, str)
			else self.definition_json
		)
		if not isinstance(definition, dict):
			frappe.throw(_("definition_json must be a JSON object"))

		if definition.get("profile") not in (None, "procedure"):
			frappe.throw(_('Agent Procedure definition_json.profile must be "procedure"'))
		definition["profile"] = "procedure"

		try:
			assert_no_flow_only_nodes(definition)
		except FlowOnlyNodeError as e:
			frappe.throw(
				_(
					"Node '{0}' has Flow-only type '{1}'. Agent Procedure cannot contain agent.run, "
					"router.llm, human.approval or trigger.* nodes (I3, I4)."
				).format(e.node_id, e.node_type)
			)

		self.schema_version = definition.get("schema_version") or self.schema_version or "1.0.0"
		definition["schema_version"] = self.schema_version

		fingerprint = compute_fingerprint(definition)
		definition["fingerprint"] = fingerprint
		self.fingerprint = fingerprint
		self.definition_json = frappe.as_json(definition, indent=2)

		derived = extract_contract_fields(definition)
		self.input_schema = (
			frappe.as_json(derived["input_schema"]) if derived["input_schema"] is not None else None
		)
		self.output_schema = (
			frappe.as_json(derived["output_schema"]) if derived["output_schema"] is not None else None
		)
		self.applicability = (
			frappe.as_json(derived["applicability"]) if derived["applicability"] is not None else None
		)
		self.permission_envelope = frappe.as_json(derived["permission_envelope"])
		self.contains_writes = 1 if derived["contains_writes"] else 0
		self.contains_code = 1 if derived["contains_code"] else 0
		self.is_read_only = 1 if derived["is_read_only"] else 0

	def _guard_content_immutability(self):
		"""Defence in depth (GT-14): block Document.save() from mutating an existing
		version's content. The structural guarantee is the primary-key uniqueness on
		(procedure_id, version) enforced by autoname() + insert(), not this method --
		this only catches the "someone called doc.save() on an existing row" mistake,
		which frappe.db.set_value bypasses entirely (documented gap, see module docstring
		and huf/ai/system_records.py's own GAP 2).
		"""
		if self.is_new():
			return
		if frappe.flags.in_install or frappe.flags.in_migrate:
			return

		before = self.get_doc_before_save()
		if not before:
			return

		changed = [f for f in CONTENT_FIELDS if self.get(f) != before.get(f)]
		if changed:
			frappe.throw(
				_(
					"Agent Procedure versions are immutable (I6). {0} changed on an existing "
					"version -- insert a new version instead of saving this one."
				).format(", ".join(changed)),
				title=_("Version Immutable"),
			)
