# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Plain product copy for graph validation failures.

``huf.ai.graph.validator`` reports machine-oriented ``ValidationError`` rows
(``[UNREACHABLE_NODE] n3: node 'n3' is not reachable from entry``,
``[SCHEMA] n2.config: 'approver_type' is a required property``). Those are right for logs and
tests but must never reach a Flow author in the save dialog. :func:`describe_errors` turns the
rows into one readable sentence each, naming the step the way the canvas does and the field the
way the inspector labels it.
"""

from __future__ import annotations

import re

NODE_TYPE_LABELS: dict[str, str] = {
	"trigger.webhook": "Webhook Trigger",
	"trigger.schedule": "Schedule Trigger",
	"trigger.doc-event": "Doc Event Trigger",
	"trigger.unset": "Unset Trigger",
	"agent.run": "Run Agent",
	"tool.call": "Call Tool",
	"router.llm": "LLM Router",
	"router.decision": "Decision Router",
	"human.approval": "Human Approval",
	"condition": "Condition",
	"foreach": "Loop",
	"validate": "Validate",
	"output": "End",
	"transform": "Transform Data",
	"state.get": "Get State",
	"state.set": "Set State",
	"state.delete": "Delete State",
	"doc.create": "Create Document",
}

FIELD_LABELS: dict[str, str] = {
	"approver_type": "who can approve",
	"approver_role": "approver role",
	"approver_users": "approver users",
	"approve_next": "the step after Approve",
	"reject_next": "the step after Reject",
	"timeout_next": "the step after a timeout",
	"timeout_ms": "wait time",
	"message": "message",
	"prompt": "prompt",
	"options": "routes",
	"default": "fallback route",
	"model": "model",
	"agent": "agent",
	"tool_id": "tool",
	"input": "inputs",
	"on_true": "the step when true",
	"on_false": "the step when false",
	"cron": "schedule",
	"doctype": "document type",
	"event": "event",
	"secret": "secret",
	"next": "next step",
	"on_error": "error step",
}

_REQUIRED_RE = re.compile(r"^'([^']+)' is a required property")
_EXTRA_RE = re.compile(r"Additional properties are not allowed \((.+) (?:was|were) unexpected\)")
_ENUM_RE = re.compile(r"is not one of")
_SHORT_RE = re.compile(r"is too short|should be non-empty")
_TYPE_RE = re.compile(r"is not of type")


def _label(field: str) -> str:
	return FIELD_LABELS.get(field, field.replace("_", " "))


def _step(graph: dict | None, node_id: str | None) -> str:
	if not node_id:
		return "The flow"
	ntype = None
	for node in (graph or {}).get("nodes") or []:
		if isinstance(node, dict) and node.get("id") == node_id:
			ntype = node.get("type")
			break
	kind = NODE_TYPE_LABELS.get(ntype or "")
	return f"Step '{node_id}' ({kind})" if kind else f"Step '{node_id}'"


def _leaf(field: str | None) -> str:
	if not field:
		return ""
	parts = [p for p in field.split(".") if not p.isdigit()]
	return parts[-1].split("[")[0] if parts else ""


def _schema_sentence(graph: dict | None, err) -> str:
	if not err.node_id:
		return "The flow definition is incomplete or out of date. Reload the page and try again."
	who = _step(graph, err.node_id)
	msg = err.message or ""
	if "is not a supported node type" in msg:
		return f"{who} uses a step type that flows do not support. Delete it."
	m = _REQUIRED_RE.match(msg)
	if m:
		return f"{who}: {_label(m.group(1))} is required. Open the step and fill it in."
	m = _EXTRA_RE.search(msg)
	if m:
		names = ", ".join(n.strip(" '") for n in m.group(1).split(","))
		return f"{who}: '{names}' is not a setting this step supports. Remove it."
	field = _label(_leaf(err.field)) if err.field else ""
	about = f" ({field})" if field else ""
	if _ENUM_RE.search(msg):
		return f"{who}: choose a valid option{about}."
	if _SHORT_RE.search(msg):
		return f"{who}: {field or 'a field'} cannot be empty."
	if _TYPE_RE.search(msg):
		return f"{who}: the value{about} has the wrong format."
	if "not valid under any of the given schemas" in msg or "is not valid under" in msg:
		return f"{who}: its settings are incomplete or not valid{about}. Open the step and check its fields."
	return f"{who}: a setting{about} is not valid. Open the step and check its fields."


def describe_error(graph: dict | None, err) -> str:
	"""One plain-language sentence for a single ``ValidationError``."""
	code = err.code
	who = _step(graph, err.node_id)
	if code == "SCHEMA":
		return _schema_sentence(graph, err)
	if code == "UNREACHABLE_NODE":
		return f"{who} is not connected to the start of the flow. Connect it or delete it."
	if code in {"DANGLING_TARGET", "DANGLING_ENTRY"}:
		return f"{who} points at a step that no longer exists. Reconnect it or remove the link."
	if code == "DUPLICATE_NODE_ID":
		return f"{who} appears more than once. Each step needs its own name."
	if code == "CYCLE":
		return f"{who} is part of a loop of steps that never ends. Use a Loop step to repeat work."
	if code in {"FORWARD_REFERENCE", "SELF_REFERENCE", "DANGLING_REFERENCE"}:
		return f"{who} uses a value from a step that has not run yet. Pick a value from an earlier step."
	if code == "PROFILE_VIOLATION":
		return f"{who} uses a step type that flows do not support. Delete it."
	if code == "BAD_EXPRESSION":
		return f"{who} has an expression that cannot be read. Check the value you typed."
	if code == "NOT_AN_OBJECT":
		return "The flow definition is not valid. Reload the page and try again."
	return f"{who}: {err.message}"


def describe_errors(graph: dict | None, errors) -> str:
	"""All errors joined as readable sentences (duplicates removed, order kept)."""
	seen: list[str] = []
	for err in errors:
		sentence = describe_error(graph, err)
		if sentence not in seen:
			seen.append(sentence)
	return " ".join(seen)
