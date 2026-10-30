# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Two strengths of flow validation: saving a draft never blocks, publishing and running need a finished flow.

``validate_flow(defn, mode)`` is the single entry point (UX-17, design decision (a)):

``mode="draft"``
    What a save needs. The document must be structurally sound: readable shape, known step types,
    unique ids, links only to steps that exist, limits inside policy. Steps may still be missing
    required settings, may be loose (nothing leads to them) and may have no trigger yet.

``mode="publish"``
    What a run, a publish and an Active save need. Everything in draft mode, plus every step finished
    and connected: ``result.issues`` must be empty.

Nothing is stored about incompleteness. The list of unfinished things is computed from the definition
each time, so it can never go stale: ``result.issues`` is that list, as ``(node_id, field, message)``.

Pure functions over a parsed definition (the only database access is the tool classifier the shared
validator already uses), so every rule is unit-testable in isolation.
"""

from __future__ import annotations

import dataclasses
import json
import re

import frappe
from frappe import _

from huf.ai.graph.error_copy import describe_error, describe_errors
from huf.ai.graph.validation.result import ValidationError
from huf.ai.graph.validator import MODE_DRAFT, MODE_PUBLISH, validate_graph

MODES = (MODE_DRAFT, MODE_PUBLISH)


@dataclasses.dataclass(frozen=True)
class FlowIssue:
	"""One thing left to finish: which step, which setting, and a sentence a flow author can act on."""

	node_id: str | None
	field: str | None
	code: str
	message: str


@dataclasses.dataclass(frozen=True)
class FlowValidation:
	"""Outcome of :func:`validate_flow`.

	``errors`` are structural problems: the definition cannot be stored at all (in any mode).
	``issues`` are unfinished things: fine in a draft, blocking for publish, run and activation.
	"""

	mode: str
	errors: tuple[ValidationError, ...] = ()
	issues: tuple[FlowIssue, ...] = ()

	@property
	def structure_ok(self) -> bool:
		return not self.errors

	@property
	def finished(self) -> bool:
		"""Nothing left to finish: the flow may run and be published."""
		return not self.errors and not self.issues

	@property
	def ok(self) -> bool:
		"""Whether the definition passes in the mode it was checked in."""
		return self.structure_ok if self.mode == MODE_DRAFT else self.finished

	def messages(self, defn: dict | None = None) -> list[str]:
		"""Plain sentences for everything that fails in this mode (structure first)."""
		out = [describe_error(defn, e) for e in self.errors]
		if self.mode == MODE_PUBLISH:
			out.extend(i.message for i in self.issues)
		seen: list[str] = []
		for m in out:
			if m not in seen:
				seen.append(m)
		return seen

	def to_dict(self, defn: dict | None = None) -> dict:
		return {
			"mode": self.mode,
			"ok": self.ok,
			"structure_ok": self.structure_ok,
			"finished": self.finished,
			"errors": [{"node_id": e.node_id, "field": e.field, "message": describe_error(defn, e)} for e in self.errors],
			"issues": [{"node_id": i.node_id, "field": i.field, "message": i.message} for i in self.issues],
		}


def _leaf(field: str | None) -> str:
	if not field:
		return ""
	parts = [p for p in field.split(".") if not p.isdigit()]
	return parts[-1].split("[")[0] if parts else ""


_REQUIRED_RE = re.compile(r"^'([^']+)' is a required property")


def _issue_field(err: ValidationError) -> str | None:
	"""The setting an error is about. A missing setting is reported on its step's ``config``; name the setting."""
	m = _REQUIRED_RE.match(err.message or "")
	if m and err.code == "SCHEMA":
		return f"{err.field}.{m.group(1)}" if err.field else m.group(1)
	return err.field


def _unset_and_blank_issues(defn: dict, check_people: bool = True) -> list[FlowIssue]:
	"""Things the schema cannot see: no trigger, a trigger nobody chose, a required text that is only spaces."""
	from huf.huf.doctype.flow_definition.activation_rules import REQUIRED_CONFIG_KEYS, UNSET_TRIGGER_TYPE, _is_blank

	issues: list[FlowIssue] = []
	nodes = [n for n in (defn.get("nodes") or []) if isinstance(n, dict)]
	if not any(str(n.get("type", "")).startswith("trigger.") for n in nodes):
		issues.append(FlowIssue(None, "trigger", "NO_TRIGGER", _("Add a trigger so the flow knows when to start.")))
	for n in nodes:
		if n.get("type") == UNSET_TRIGGER_TYPE:
			issues.append(FlowIssue(n.get("id"), "type", "UNSET_TRIGGER", _("Choose what starts this flow.")))
			continue
		config = n.get("config") if isinstance(n.get("config"), dict) else {}
		for key in REQUIRED_CONFIG_KEYS.get(n.get("type"), ()):
			if _is_blank(config.get(key)):
				issues.append(
					FlowIssue(n.get("id"), f"config.{key}", "BLANK", describe_error(defn, ValidationError("SCHEMA", n.get("id"), f"config.{key}", f"'{key}' is a required property")))
				)
		if check_people:
			issues.extend(_unknown_approver_issues(n))
	return issues


def _unknown_approver_issues(node: dict) -> list[FlowIssue]:
	"""A "wait for approval" step that names people: every name must be a real, enabled person (a typo would stall the run)."""
	config = node.get("config") if isinstance(node.get("config"), dict) else {}
	if node.get("type") != "human.approval" or config.get("approver_type") != "user":
		return []
	from huf.ai.graph.error_copy import step_title

	issues: list[FlowIssue] = []
	for name in config.get("approver_users") or []:
		if not isinstance(name, str) or not name.strip():
			continue
		if not frappe.db.exists("User", {"name": name.strip(), "enabled": 1}):
			issues.append(
				FlowIssue(
					node.get("id"), "config.approver_users", "UNKNOWN_APPROVER",
					_('{0}: no one here is called "{1}". Pick each approver from the list.').format(step_title(node), name),
				)
			)
	return issues


def validate_flow(defn, mode: str = MODE_PUBLISH, *, classify_tool=None, check_people: bool = True) -> FlowValidation:
	"""Check ``defn`` (a parsed flow definition) in ``mode`` (``"draft"`` or ``"publish"``).

	Always returns a result; read ``result.ok`` for "passes in this mode", ``result.errors`` for the structural
	problems (never storable) and ``result.issues`` for what is left to finish.
	"""
	if mode not in MODES:
		raise ValueError(f"mode must be one of {MODES}, got {mode!r}")
	kwargs = {"classify_tool": classify_tool} if classify_tool is not None else {}
	draft = validate_graph(defn, "flow", mode=MODE_DRAFT, **kwargs)
	if not draft.ok:
		return FlowValidation(mode=mode, errors=draft.errors)

	full = validate_graph(defn, "flow", mode=MODE_PUBLISH, **kwargs)
	issues: list[FlowIssue] = []
	seen: set[tuple[str | None, str]] = set()

	def add(issue: FlowIssue) -> None:
		key = (issue.node_id, _leaf(issue.field))
		if issue.code in ("UNREACHABLE_NODE",) or key not in seen or not issue.field:
			seen.add(key)
			issues.append(issue)

	for err in full.errors:
		add(FlowIssue(err.node_id, _issue_field(err), err.code, describe_error(defn, err)))
	for issue in _unset_and_blank_issues(defn, check_people):
		# The schema already reports an empty required setting; do not list it twice.
		if issue.code == "BLANK" and (issue.node_id, _leaf(issue.field)) in seen:
			continue
		add(issue)
	return FlowValidation(mode=mode, issues=tuple(issues))


def load_definition(raw) -> dict:
	"""The definition as a dict, from a JSON string or an already parsed value."""
	if isinstance(raw, str):
		return json.loads(raw)
	return raw


def check_runnable(defn) -> None:
	"""Refuse to start a run of a flow with anything left to finish (a draft may be saved half-built, a run may not)."""
	# People are checked when a flow is saved or made live, not at every run (a test run of a draft may name anyone).
	finished = validate_flow(defn, MODE_PUBLISH, check_people=False)
	if not finished.ok:
		frappe.throw(
			_("Finish setting up this flow before running it. {0}").format(" ".join(finished.messages(defn))),
			title=_("This flow is not finished"),
		)


def unfinished_count(definition_json) -> int:
	"""How many things are left to finish in a stored definition (what ``save_flow_definition`` reports back)."""
	return len(validate_flow(load_definition(definition_json), MODE_PUBLISH).issues)


def explain(defn, errors) -> str:
	"""All ``errors`` as readable sentences, for a save or publish dialog."""
	return describe_errors(defn, errors)


@frappe.whitelist()
def validate_flow_definition(flow_id: str, mode: str = MODE_DRAFT) -> dict:
	"""What is left to finish in a stored flow, computed now: ``{ok, structure_ok, finished, errors, issues}``."""
	frappe.has_permission("Flow Definition", "read", doc=flow_id, throw=True)
	if mode not in MODES:
		frappe.throw(_("Mode must be draft or publish."))
	raw = frappe.db.get_value("Flow Definition", flow_id, "definition_json")
	if not raw:
		frappe.throw(_("This flow has no steps yet."))
	defn = load_definition(raw)
	return validate_flow(defn, mode).to_dict(defn)
