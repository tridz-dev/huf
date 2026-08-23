import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

from huf.ai import system_records
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


ALLOWED_NODE_TYPES = {
	"trigger.webhook",
	"trigger.schedule",
	"trigger.doc-event",
	"agent.run",
	"tool.call",
	"router.llm",
	"human.approval",
	"condition",
	"http_request",
	"transform",
	"loop",
	"end",
}

ALLOWED_EDGE_TYPES = {"always", "on_success", "on_failure", "expression"}


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
		"""Validate the flow definition JSON against v0.1 schema rules."""
		if not self.definition_json:
			frappe.throw(_("Definition JSON is required"))

		try:
			defn = json.loads(self.definition_json) if isinstance(self.definition_json, str) else self.definition_json
		except (json.JSONDecodeError, TypeError) as e:
			frappe.throw(_("Invalid JSON in definition: {0}").format(str(e)))

		# Validate required top-level keys
		required_keys = {"schema_version", "id", "version", "entry", "nodes", "edges", "settings", "metadata"}
		missing = required_keys - set(defn.keys())
		if missing:
			frappe.throw(_("Missing required keys in definition JSON: {0}").format(", ".join(sorted(missing))))

		# Validate id matches flow_id
		if defn.get("id") != self.flow_id:
			frappe.throw(_("definition_json.id ({0}) must match flow_id ({1})").format(defn.get("id"), self.flow_id))

		# Validate schema_version
		self.schema_version = defn.get("schema_version", 1)

		# Validate nodes
		nodes = defn.get("nodes", [])
		if not isinstance(nodes, list):
			frappe.throw(_("definition_json.nodes must be an array"))

		node_ids = set()
		for node in nodes:
			if not isinstance(node, dict):
				frappe.throw(_("Each node must be an object"))

			node_id = node.get("id")
			if not node_id:
				frappe.throw(_("Every node must have an 'id' field"))

			if node_id in node_ids:
				frappe.throw(_("Duplicate node id: {0}").format(node_id))
			node_ids.add(node_id)

			node_type = node.get("type")
			if not node_type:
				frappe.throw(_("Node '{0}' must have a 'type' field").format(node_id))

			if node_type not in ALLOWED_NODE_TYPES:
				frappe.throw(
					_("Node '{0}' has unknown type '{1}'. Allowed: {2}").format(
						node_id, node_type, ", ".join(sorted(ALLOWED_NODE_TYPES))
					)
				)

		# Validate entry exists
		entry = defn.get("entry")
		if entry not in node_ids:
			frappe.throw(_("Entry node '{0}' does not exist in nodes").format(entry))

		# Validate edges
		edges = defn.get("edges", [])
		if not isinstance(edges, list):
			frappe.throw(_("definition_json.edges must be an array"))

		for edge in edges:
			if not isinstance(edge, dict):
				frappe.throw(_("Each edge must be an object"))

			edge_from = edge.get("from")
			edge_to = edge.get("to")

			if not edge_from or not edge_to:
				frappe.throw(_("Edge must have 'from' and 'to' fields"))

			if edge_from not in node_ids:
				frappe.throw(_("Edge references unknown source node: {0}").format(edge_from))

			if edge_to not in node_ids:
				frappe.throw(_("Edge references unknown target node: {0}").format(edge_to))

			edge_type = edge.get("type", "always")
			if edge_type not in ALLOWED_EDGE_TYPES:
				frappe.throw(
					_("Edge from '{0}' to '{1}' has unknown type '{2}'. Allowed: {3}").format(
						edge_from, edge_to, edge_type, ", ".join(sorted(ALLOWED_EDGE_TYPES))
					)
				)

			# Expression edges must have a condition
			if edge_type == "expression" and not edge.get("condition"):
				frappe.throw(
					_("Edge from '{0}' to '{1}' has type 'expression' but no 'condition'").format(edge_from, edge_to)
				)
