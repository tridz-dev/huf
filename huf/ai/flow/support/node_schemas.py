"""Node-type descriptors for the Flow editor, generated from ``graph_ir.schema.json``.

Split out of ``api.py`` (which serves them through ``get_node_schemas``).
"""

from __future__ import annotations

import json

# Display metadata only. Every config field below the node is generated from graph_ir.schema.json.
_NODE_DISPLAY = {
	"trigger.webhook": ("Webhook Trigger", "Webhook", "trigger"),
	"trigger.schedule": ("Schedule Trigger", "Clock", "trigger"),
	"trigger.doc-event": ("Doc Event Trigger", "FileText", "trigger"),
	"trigger.unset": ("Unset Trigger", "CircleDashed", "trigger"),
	"agent.run": ("Run Agent", "SquareAsterisk", "ai"),
	"tool.call": ("Call Tool", "Wrench", "ai"),
	"router.llm": ("LLM Router", "GitBranch", "control"),
	"router.decision": ("Decision Router", "GitBranch", "control"),
	"human.approval": ("Human Approval", "UserCheck", "control"),
	"condition": ("Condition (IF)", "GitFork", "control"),
	"foreach": ("Loop", "RotateCw", "control"),
	"validate": ("Validate", "ShieldCheck", "control"),
	"output": ("End", "CheckCircle2", "control"),
	"transform": ("Transform Data", "Repeat", "transform"),
	"state.get": ("Get State", "DatabaseZap", "state"),
	"state.set": ("Set State", "Database", "state"),
	"state.delete": ("Delete State", "Trash2", "state"),
	"doc.create": ("Create Document", "FilePlus", "data"),
	"code.run": ("Execute Code", "Terminal", "data"),
}

_SCHEMA_FILE = None


def _graph_schema() -> dict:
	global _SCHEMA_FILE
	if _SCHEMA_FILE is None:
		import os

		path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "graph", "graph_ir.schema.json")
		with open(path, encoding="utf-8") as fh:
			_SCHEMA_FILE = json.load(fh)
	return _SCHEMA_FILE


def _ref_name(schema: dict) -> str | None:
	ref = schema.get("$ref") if isinstance(schema, dict) else None
	return ref.rsplit("/", 1)[-1] if ref else None


def _field_type(schema: dict) -> dict:
	"""Map one JSON-schema property to a UI field descriptor (type + constraints)."""
	ref = _ref_name(schema)
	if ref == "NodeId":
		return {"type": "node_select"}
	if ref == "Expression":
		return {"type": "expression"}
	if ref == "Reference":
		return {"type": "reference"}
	if ref == "ToolId":
		return {"type": "tool_select"}
	if ref == "Value":
		return {"type": "value"}
	if "enum" in schema:
		return {"type": "select", "options": list(schema["enum"])}
	if "const" in schema:
		return {"type": "select", "options": [schema["const"]], "default": schema["const"]}
	if "anyOf" in schema:
		return {"type": "value"}
	kind = schema.get("type")
	if kind == "string":
		out = {"type": "string"}
		for src, dst in (("minLength", "min_length"), ("maxLength", "max_length")):
			if src in schema:
				out[dst] = schema[src]
		return out
	if kind == "integer":
		out = {"type": "number"}
		for src, dst in (("minimum", "min"), ("maximum", "max")):
			if src in schema:
				out[dst] = schema[src]
		return out
	if kind == "boolean":
		return {"type": "boolean"}
	if kind == "array":
		item = schema.get("items", {})
		if _ref_name(item) == "NodeId":
			return {"type": "node_list"}
		if item.get("type") == "string":
			return {"type": "string_list"}
	return {"type": "json"}


def _node_config_schema(node_def: dict) -> tuple[str | None, dict, bool]:
	"""``(node_type, config_schema, forbids_next)`` for one FlowGraph node definition."""
	node_type, config, forbids_next = None, {}, False
	for part in node_def.get("allOf", [node_def]):
		props = part.get("properties") or {}
		if "type" in props and "const" in props["type"]:
			node_type = props["type"]["const"]
			config = props.get("config", {})
		if part.get("not", {}).get("required") == ["next"]:
			forbids_next = True
	return node_type, config, forbids_next


def build_node_schemas(schema: dict | None = None) -> dict:
	"""Node-type -> UI descriptor, generated from ``graph_ir.schema.json`` (FlowGraph node list)."""
	schema = schema or _graph_schema()
	defs = schema["$defs"]
	out: dict = {}
	for entry in defs["FlowNode"]["oneOf"]:
		node_def = defs[_ref_name(entry)]
		node_type, config, forbids_next = _node_config_schema(node_def)
		if not node_type:
			continue
		required = set(config.get("required", []))
		fields = []
		for name, prop in (config.get("properties") or {}).items():
			descriptor = _field_type(prop)
			descriptor.update(
				{"name": name, "label": name.replace("_", " ").title(), "required": name in required}
			)
			if prop.get("description"):
				descriptor["description"] = prop["description"]
			if "default" in prop:
				descriptor["default"] = prop["default"]
			fields.append(descriptor)
		label, icon, category = _NODE_DISPLAY.get(node_type, (node_type, "Circle", "other"))
		out[node_type] = {
			"label": label,
			"icon": icon,
			"category": category,
			"description": node_def.get("description") or label,
			"has_backend": True,
			"routing": {"next": not forbids_next, "on_error": True},
			"config_schema": fields,
			"json_schema": config,
		}
	return out
