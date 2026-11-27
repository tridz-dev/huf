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
	"trigger.app": ("App Trigger", "AppWindow", "trigger"),
	"trigger.gateway": ("Chat Message Trigger", "MessageSquare", "trigger"),
	"trigger.whatsapp": ("WhatsApp Message Trigger", "MessageCircle", "trigger"),
	"trigger.telegram": ("Telegram Message Trigger", "Send", "trigger"),
	"agent.run": ("Run Agent", "SquareAsterisk", "ai"),
	"tool.call": ("Call Tool", "Wrench", "ai"),
	"router.llm": ("LLM Router", "GitBranch", "control"),
	"router.decision": ("Choose by rules", "Split", "control"),
	"human.approval": ("Human Approval", "UserCheck", "control"),
	"wait": ("Wait", "Hourglass", "control"),
	"stop": ("Stop with error", "OctagonX", "control"),
	"doc.get": ("Find document", "FileSearch", "data"),
	"doc.update": ("Update document", "FilePen", "data"),
	"flow.call": ("Run another flow", "Workflow", "advanced"),
	"member.set": ("Remember for this person", "UserPen", "data"),
	"send.message": ("Send message", "Send", "data"),
	"split": ("Split / holdout", "Split", "control"),
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
	"knowledge.search": ("Search knowledge", "BookOpen", "ai"),
	"handoff": ("Hand to a person", "UserRound", "control"),
}

_NODE_ID = {"$ref": "#/$defs/NodeId"}
_EXPR = {"$ref": "#/$defs/Expression"}

#: ``router.decision`` Decision mode (``nodes/router_decision.py``). When ``decision`` is set the rule
#: settings (``options``, ``default``) are not used, so neither is required in the form.
_DECISION_PROPERTY = {
	"type": "object",
	"description": "Let the Decision runtime choose the next step. Leave empty to choose by rules.",
	"additionalProperties": False,
	"required": ["candidates", "uncertain_next"],
	"properties": {
		"candidates": {
			"type": "array",
			"minItems": 2,
			"description": "The steps the decision may choose from.",
			"items": {
				"type": "object",
				"additionalProperties": False,
				"required": ["node_id"],
				"properties": {"node_id": _NODE_ID, "label": {"type": "string"}},
			},
		},
		"instructions": {"type": "string", "description": "What the decision should pick."},
		"minimum_confidence": {"type": "number", "minimum": 0, "maximum": 1},
		"uncertain_next": {**_NODE_ID, "description": "Step taken on any doubt or failure."},
		"backend": {"type": "string", "description": "Registered Decision backend id."},
		"policy_id": {"type": "string"},
		"state": {"type": "object"},
	},
}

#: Node types whose module is merged but which ``graph_ir.schema.json`` does not list yet:
#: ``(description, config schema, forbids_next)``. Keys match each module's config exactly.
_EXTRA_NODE_CONFIGS = {
	"knowledge.search": (
		"Search one knowledge source as the run's user and return the best passages.",
		{
			"type": "object",
			"additionalProperties": False,
			"required": ["query", "knowledge_source"],
			"properties": {
				"query": {**_EXPR, "description": "The text to search for."},
				"knowledge_source": {"type": "string", "minLength": 1, "description": "Knowledge Source name."},
				"top_k": {"type": "integer", "minimum": 1, "maximum": 20, "default": 5},
				"filters": {"type": "object", "description": "Optional metadata filters."},
			},
		},
		False,
	),
	"handoff": (
		"Hand the conversation to a person and wait until they release it.",
		{
			"type": "object",
			"additionalProperties": False,
			"properties": {
				"conversation": {"$ref": "#/$defs/Value", "description": "Channel Conversation to hand over."},
				"gateway": {"$ref": "#/$defs/Value", "description": "Channel of the contact (with recipient)."},
				"recipient": {"$ref": "#/$defs/Value", "description": "Contact whose open conversation is handed over."},
				"reason": {"type": "string", "description": "Reason code stored on the run."},
				"target": {"type": "string", "description": "Queue or person to hand to."},
				"summary": {**_EXPR, "description": "Short note for the person taking over."},
				"priority": {"type": "string", "enum": ["low", "normal", "high", "urgent"], "default": "normal"},
				"message": {"type": "string", "description": "Message sent to the contact on handoff."},
				"timeout_ms": {"type": "integer", "minimum": 1},
				"timeout_next": {**_NODE_ID, "description": "Step taken when nobody releases it in time."},
			},
		},
		False,
	),
}

#: Types only an app can start (start_flow_for_member); the palette marks them "app only".
APP_ONLY_TYPES = frozenset({"trigger.app"})

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
	if kind in ("integer", "number"):
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


def _with_decision(config: dict) -> dict:
	"""``router.decision`` config with the optional Decision mode added (rule fields no longer required)."""
	props = dict(config.get("properties") or {})
	props.setdefault("decision", _DECISION_PROPERTY)
	required = [r for r in config.get("required", []) if r not in ("options", "default")]
	return {**config, "properties": props, "required": required}


def _descriptor(node_type: str, description: str | None, config: dict, forbids_next: bool) -> dict:
	required = set(config.get("required", []))
	fields = []
	for name, prop in (config.get("properties") or {}).items():
		descriptor = _field_type(prop)
		descriptor.update({"name": name, "label": name.replace("_", " ").title(), "required": name in required})
		if prop.get("description"):
			descriptor["description"] = prop["description"]
		if "default" in prop:
			descriptor["default"] = prop["default"]
		fields.append(descriptor)
	label, icon, category = _NODE_DISPLAY.get(node_type, (node_type, "Circle", "other"))
	return {
		"label": label,
		"icon": icon,
		"category": category,
		"description": description or label,
		"has_backend": True,
		"routing": {"next": not forbids_next, "on_error": True},
		"config_schema": fields,
		"json_schema": config,
	}


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
		if node_type == "router.decision":
			config = _with_decision(config)
		out[node_type] = _descriptor(node_type, node_def.get("description"), config, forbids_next)
		if node_type in APP_ONLY_TYPES:
			out[node_type]["app_only"] = True
	for node_type, (description, config, forbids_next) in _EXTRA_NODE_CONFIGS.items():
		out.setdefault(node_type, _descriptor(node_type, description, config, forbids_next))
	return out
