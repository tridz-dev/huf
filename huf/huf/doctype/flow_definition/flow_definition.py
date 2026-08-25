import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

from huf.ai import system_records
from huf.ai.graph.validator import FLOW_NODE_TYPES, validate_flow_graph
from huf.ai.transaction import commit_if_background

# Flow Definition fields that stay editable on a system-owned flow. Every
# other field is locked for non-System-Managers by system_records'
# lock-by-default guard -- see huf/ai/system_records.py. updated_by/updated_at
# are excluded because validate() stamps them on every save (see below),
# which would otherwise self-trigger the guard on every legitimate write.
SYSTEM_RECORD_UNLOCKED_FIELDS: tuple = ("updated_by", "updated_at")


def get_permission_query_conditions(user=None):
	"""Hide system Flow Definitions from non-System-Managers. Registered in hooks.py."""
	return system_records.make_permission_query_conditions("Flow Definition")(user)


# Kept as a re-export for any external caller that used to introspect Flow's allowed
# node types from this module -- the actual set is now owned by the shared graph-IR
# validator (huf.ai.graph.validator.FLOW_NODE_TYPES) so Flow and Procedure never drift
# apart on what a node type means. There is no ALLOWED_EDGE_TYPES any more: the shared
# IR has no separate edges array -- every node carries its own successor pointer
# ("next"), its own error route ("on_error"), and self-routing nodes (condition,
# router.llm, human.approval) carry their branch targets directly in their own
# "config" (on_true/on_false, options/default, approve_next/reject_next). An "edge" is
# no longer a first-class thing in the definition JSON; it is just how two node
# pointers happen to relate.
ALLOWED_NODE_TYPES = FLOW_NODE_TYPES


class FlowDefinition(Document):
	def validate(self):
		self._validate_definition_json()
		self.updated_by = frappe.session.user
		self.updated_at = now_datetime()
		system_records.guard_flag_tamper(self)
		system_records.guard_field_immutability(self, unlocked_fields=SYSTEM_RECORD_UNLOCKED_FIELDS)

	def before_save(self):
		if not self.is_new():
			self.version = (self.version or 0) + 1

	def on_update(self):
		self._maybe_convert_to_procedure()

	def on_trash(self):
		system_records.guard_delete(self)

	def before_rename(self, old_name: str, new_name: str, merge: bool = False):
		system_records.guard_rename(self, old_name, new_name, merge)

	def _maybe_convert_to_procedure(self):
		"""On save, if the checkbox is set, (re)compile this Flow into a Draft Agent
		Procedure -- the convenience the original plan's separate "Convert to procedure"
		action does not give you: tick the box once, every subsequent save keeps the
		Procedure in sync with the Flow.

		Deliberately NOT the Phase 6 "Analyse Agent" UX (GOAL.md), which is a distinct,
		explicit action surfaced to the user with a Test/Enable choice -- see PLAN.md
		T-52. This is a narrower, save-triggered convenience on top of the same
		conversion primitive (huf.ai.procedure_conversion / flow_api.convert_flow_to_procedure),
		and it inherits every one of that primitive's guarantees: the result is always
		tier="Draft"/status="Draft" (I8 -- never auto-activated, never auto-bound to an
		Agent), and a non-deterministic Flow (containing agent.run / router.llm /
		human.approval) is refused with a specific reason rather than partially converted.

		Runs in on_update (after the row is committed), not validate, so a refusal here
		never blocks saving the Flow itself -- the checkbox is a best-effort convenience,
		not a save-time gate.
		"""
		if not self.auto_convert_to_procedure:
			return
		if self.is_system:
			# System flows are locked content (D12); do not spawn procedures from them
			# via a checkbox a non-admin could have ticked before the flow was locked.
			return

		from huf.ai.flow_api import convert_flow_to_procedure

		try:
			result = convert_flow_to_procedure(self.flow_id)
		except Exception as e:  # noqa: BLE001 -- this must never fail the Flow save itself
			frappe.db.set_value(
				"Flow Definition",
				self.name,
				{"converted_procedure": None, "conversion_note": f"Not converted: {e}"},
				update_modified=False,
			)
			commit_if_background()
			return

		procedure_name = result.get("name")
		if not result.get("convertible", True) or not procedure_name:
			note = result.get("reason") or "Not convertible: contains an agent.run/router.llm/human.approval node."
			frappe.db.set_value(
				"Flow Definition",
				self.name,
				{"converted_procedure": None, "conversion_note": note},
				update_modified=False,
			)
		else:
			reduction = result.get("estimated_round_trip_reduction_pct")
			note = f"Draft procedure created/refreshed as {procedure_name}."
			if reduction is not None:
				note += f" Estimated {reduction}% fewer round trips."
			frappe.db.set_value(
				"Flow Definition",
				self.name,
				{"converted_procedure": procedure_name, "conversion_note": note},
				update_modified=False,
			)
		commit_if_background()

	def _validate_definition_json(self):
		"""Validate the flow definition JSON against the shared graph-IR schema.

		This is deliberately the *same* gate ``huf.ai.procedure_conversion`` re-runs
		before it will convert a Flow to a Procedure (see
		``huf.ai.procedure_conversion.analyze_conversion``, step 1) -- a Flow that
		saves here is now guaranteed to be schema-valid graph-IR, so conversion can
		never reject a saved Flow purely for being a shape ``validate_flow_graph``
		has never seen (the old bug: this validator used to accept a top-level
		``edges`` array with ``schema_version`` as an int, while the shared IR
		requires nodes carrying their own ``next``/``on_error`` pointers and
		``schema_version`` as the literal string ``"1.0.0"`` -- no Flow saved under
		the old rules could ever have passed the shared validator).
		"""
		if not self.definition_json:
			frappe.throw(_("Definition JSON is required"))

		try:
			defn = json.loads(self.definition_json) if isinstance(self.definition_json, str) else self.definition_json
		except (json.JSONDecodeError, TypeError) as e:
			frappe.throw(_("Invalid JSON in definition: {0}").format(str(e)))

		result = validate_flow_graph(defn)
		if not result.ok:
			frappe.throw(
				_("Definition JSON does not conform to the graph-IR Flow profile: {0}").format(
					"; ".join(str(err) for err in result.errors)
				)
			)

		# schema_version is a schema-validated const ("1.0.0") at this point; store it
		# verbatim rather than re-deriving or defaulting it.
		self.schema_version = defn.get("schema_version")
