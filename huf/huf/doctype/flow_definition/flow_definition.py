import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime


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

		# Integrity rules below only block the save when the flow is (becoming) Active.
		# A Draft may be half-built - these are exactly the gaps that make a flow
		# unrunnable, so they must not stop someone from saving work in progress.
		if self.status == "Active":
			self._validate_active_integrity(defn, nodes, node_ids, edges, entry)

	def _validate_active_integrity(self, defn, nodes, node_ids, edges, entry):
		"""Integrity rules enforced only for Active flows.

		These catch definitions that save fine today but can never run:
		no trigger, dangling condition/loop targets, unreachable nodes, and
		executor nodes missing the config keys their engine implementation
		actually requires (see huf/ai/flow_engine.py _exec_agent_run,
		_exec_tool_call, _exec_http_request).
		"""
		errors = []
		nodes_by_id = {node.get("id"): node for node in nodes}

		# Rule 1: at least one trigger node.
		trigger_nodes = [n for n in nodes if str(n.get("type") or "").startswith("trigger.")]
		if not trigger_nodes:
			errors.append(_("No trigger node found: at least one node with a type starting with 'trigger.' is required to activate this flow"))

		# Rule 2: true_node / false_node / loop_node / done_node must resolve.
		# These route by config, not by edges, so they're checked separately from edges.
		typed_refs = []
		for node in nodes:
			node_id = node.get("id")
			config = node.get("config") or {}
			if not isinstance(config, dict):
				continue
			for key in ("true_node", "false_node", "loop_node", "done_node"):
				target = config.get(key)
				if not target:
					continue
				typed_refs.append((node_id, target))
				if target not in node_ids:
					errors.append(
						_("Node '{0}' has '{1}' pointing to '{2}', which does not exist in nodes").format(
							node_id, key, target
						)
					)

		# Rule 3: every node must be reachable from entry, following edges plus
		# the typed *_node references above (condition/loop route by config,
		# not by edges, so an edges-only walk would miss real paths).
		if entry in node_ids:
			adjacency = {}
			for edge in edges:
				if not isinstance(edge, dict):
					continue
				adjacency.setdefault(edge.get("from"), set()).add(edge.get("to"))
			for node_id, target in typed_refs:
				if target in node_ids:
					adjacency.setdefault(node_id, set()).add(target)

			visited = set()
			stack = [entry]
			while stack:
				current = stack.pop()
				if current in visited:
					continue
				visited.add(current)
				for nxt in adjacency.get(current, ()):
					if nxt not in visited:
						stack.append(nxt)

			unreachable = sorted(node_ids - visited)
			if unreachable:
				errors.append(
					_("Node(s) unreachable from entry '{0}': {1}").format(entry, ", ".join(unreachable))
				)

		# Rule 4: per-executor required config, matching the engine's actual guards.
		for node in nodes:
			node_id = node.get("id")
			node_type = node.get("type")
			config = node.get("config") or {}
			if not isinstance(config, dict):
				config = {}

			if node_type == "tool.call" and not config.get("tool_name"):
				errors.append(_("Node '{0}' (tool.call) is missing required 'tool_name' in config").format(node_id))
			elif node_type == "http_request" and not config.get("url"):
				errors.append(_("Node '{0}' (http_request) is missing required 'url' in config").format(node_id))
			elif node_type == "agent.run" and not config.get("agent_name"):
				errors.append(_("Node '{0}' (agent.run) is missing required 'agent_name' in config").format(node_id))

		if errors:
			frappe.throw(
				_("Cannot activate flow - the definition has the following problem(s):<br>{0}").format(
					"<br>".join(errors)
				)
			)
