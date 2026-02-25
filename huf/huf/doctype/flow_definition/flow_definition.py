import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime


ALLOWED_NODE_TYPES = {
	"trigger.webhook",
	"agent.run",
	"tool.call",
	"router.llm",
	"human.approval",
	"end",
}

ALLOWED_EDGE_TYPES = {"always", "on_success", "on_failure", "expression"}


class FlowDefinition(Document):
	def validate(self):
		self._validate_definition_json()
		self.updated_by = frappe.session.user
		self.updated_at = now_datetime()

	def before_save(self):
		if not self.is_new():
			self.version = (self.version or 0) + 1

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
