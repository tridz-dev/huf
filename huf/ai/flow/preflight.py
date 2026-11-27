# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Checks run before a flow goes live, as structured findings.

A finding is ``{code, node_id, severity}`` and nothing else, so no message text, definition value or
recipient can travel in it (no PII). Any ``error`` finding blocks publishing
(:func:`huf.ai.flow.publish_guard.check_preflight`).

Apps add checks through the ``huf_flow_preflight`` hook, a list of dotted paths::

        huf_flow_preflight = ["myapp.flows.preflight"]  # fn(defn: dict, flow_id: str | None) -> list[dict]

Each returns a list of ``{"code": str, "severity": "error" | "warning" | "info", "node_id": str | None}``.
Everything fails closed: a hook that cannot be imported, raises, or answers anything else is an ``error``
finding, never a pass.
"""

from __future__ import annotations

import copy
import dataclasses
import re

import frappe

from huf.ai.channels import guard_steps
from huf.ai.flow.support import facts
from huf.ai.graph.expressions import ExpressionError, parse_expression

HOOK = "huf_flow_preflight"

ERROR = "error"
WARNING = "warning"
INFO = "info"
SEVERITIES = (ERROR, WARNING, INFO)

#: Step types that send a message to a person.
SEND_NODE_TYPES = frozenset({"send.message"})
#: Gateway providers a send step can send through.
SEND_CHANNELS = frozenset({"whatsapp"})
TEMPLATE_DOCTYPES = ("WhatsApp Templates", "Telegram Message Template")

_CODE_RE = re.compile(r"^[A-Za-z0-9_.]{1,64}$")


@dataclasses.dataclass(frozen=True)
class Finding:
	code: str
	node_id: str | None = None
	severity: str = ERROR

	def to_dict(self) -> dict:
		return dataclasses.asdict(self)


def _nodes(defn) -> list[dict]:
	nodes = defn.get("nodes") if isinstance(defn, dict) else None
	return [n for n in nodes if isinstance(n, dict)] if isinstance(nodes, list) else []


def _config(node: dict) -> dict:
	config = node.get("config")
	return config if isinstance(config, dict) else {}


def _blank(value) -> bool:
	return value is None or (isinstance(value, str) and not value.strip())


def _lint(defn, flow_id: str | None) -> list[Finding]:
	"""The publish-mode graph check (includes reachability)."""
	from huf.ai.graph.validation.flow_validation import MODE_PUBLISH, validate_flow

	result = validate_flow(defn, MODE_PUBLISH, check_people=False, flow_id=flow_id)
	return [Finding(item.code, item.node_id) for item in (*result.errors, *result.issues)]


def template_exists(name: str) -> bool:
	return any(
		frappe.db.exists("DocType", doctype) and frappe.db.exists(doctype, name)
		for doctype in TEMPLATE_DOCTYPES
	)


def gateway_channel(name: str) -> str:
	"""Lowercase provider of the Gateway (``whatsapp``), or "" when it does not exist."""
	return (frappe.db.get_value("Gateway", name.strip(), "provider") or "").strip().lower()


def _send_checks(defn, flow_id: str | None) -> list[Finding]:
	found: list[Finding] = []
	sends = [n for n in _nodes(defn) if n.get("type") in SEND_NODE_TYPES]
	for node in sends:
		node_id, config = node.get("id"), _config(node)
		if "retry" in config or "retry" in node:
			# A blocked send is final (G2); a retry would also park around the send's own deferral.
			found.append(Finding("SEND_RETRY_FORBIDDEN", node_id))
		category = config.get("category")
		if (
			_blank(config.get("gateway"))
			or _blank(config.get("recipient"))
			or category not in ("marketing", "service")
		):
			# What the guard chain needs to judge the send: without it the send cannot be checked.
			found.append(Finding("SEND_GUARD_CONFIG_MISSING", node_id))
		elif (
			isinstance(config.get("gateway"), str) and gateway_channel(config["gateway"]) not in SEND_CHANNELS
		):
			# Only WhatsApp has a send transport and guard chain; any other (or unknown) gateway cannot send.
			found.append(Finding("SEND_GATEWAY_UNSUPPORTED", node_id))
		# "$member" (the run's member, resolved at send time) is a reference, never a literal number.
		if guard_steps.normalise_recipient(config.get("recipient")):
			# A phone number written into the definition: the outbox stores references only (G4).
			found.append(Finding("SEND_RECIPIENT_LITERAL", node_id))
		template = config.get("template")
		if _blank(template):
			if _blank(config.get("text")):
				found.append(Finding("TEMPLATE_MISSING", node_id))
		elif not isinstance(template, str):
			# Chosen while the flow runs: nothing to look up now; the guard chain judges it at send time.
			found.append(Finding("TEMPLATE_UNCHECKED", node_id, WARNING))
		elif not template_exists(template):
			found.append(Finding("TEMPLATE_MISSING", node_id))
	if sends:
		# Stub: no audience estimator exists yet; say so rather than report a number.
		found.append(Finding("AUDIENCE_ESTIMATE_UNAVAILABLE", None, INFO))
	return found


def _facts_checks(defn, flow_id: str | None) -> list[Finding]:
	"""Conditions that read ``facts.<name>``: every name must be offered and a fallback step chosen."""
	found: list[Finding] = []
	offered = None
	for node in _nodes(defn):
		config = _config(node)
		if node.get("type") != "condition" or _blank(config.get("expression")):
			continue
		try:
			names, dynamic = facts.names_used(parse_expression(config["expression"]))
		except ExpressionError:
			continue  # the lint above reports it
		if not names and not dynamic:
			continue
		node_id = node.get("id")
		if offered is None:
			offered = facts.offered_names()
		if dynamic or any(name not in offered for name in names):
			found.append(Finding("CONDITION_FACT_UNKNOWN", node_id))
		if _blank(config.get("fallback_next")):
			found.append(Finding("CONDITION_FALLBACK_MISSING", node_id))
	return found


def _hook_paths() -> list[str]:
	return list(frappe.get_hooks(HOOK) or [])


def _app_finding(item, node_ids: set) -> Finding:
	if not isinstance(item, dict):
		return Finding("PREFLIGHT_HOOK_BAD_RESULT")
	code, severity, node_id = item.get("code"), item.get("severity"), item.get("node_id")
	if not isinstance(code, str) or not _CODE_RE.match(code) or severity not in SEVERITIES:
		return Finding("PREFLIGHT_HOOK_BAD_RESULT")
	# Only ids of this graph's steps are passed on, so an app cannot put a person's data in the field.
	return Finding(code, node_id if isinstance(node_id, str) and node_id in node_ids else None, severity)


def _log_failure(what: str, exc: Exception) -> None:
	# Only the check's name and the exception class: a message or traceback could carry personal data.
	frappe.log_error(title="Flow preflight check failed", message=f"{what}: {type(exc).__name__}")


def _app_checks(defn, flow_id: str | None) -> list[Finding]:
	try:
		paths = _hook_paths()
	except Exception as exc:  # noqa: BLE001 -- a broken check becomes an error finding
		_log_failure(HOOK, exc)
		return [Finding("PREFLIGHT_HOOK_ERROR")]
	node_ids = {n.get("id") for n in _nodes(defn) if isinstance(n.get("id"), str)}
	found: list[Finding] = []
	for path in paths:
		try:
			result = frappe.get_attr(path)(copy.deepcopy(defn), flow_id)
			if not isinstance(result, (list, tuple)):
				found.append(Finding("PREFLIGHT_HOOK_BAD_RESULT"))
				continue
			found.extend(_app_finding(item, node_ids) for item in result)
		except Exception as exc:  # noqa: BLE001 -- a broken check becomes an error finding
			_log_failure(str(path), exc)
			found.append(Finding("PREFLIGHT_HOOK_ERROR"))
	return found


def run_preflight(defn, flow_id: str | None = None) -> list[Finding]:
	"""Every finding for ``defn``, built-in checks first. Never raises: a check that breaks is a finding."""
	found: list[Finding] = []
	for check in (_lint, _send_checks, _facts_checks):
		try:
			found.extend(check(defn, flow_id))
		except Exception as exc:  # noqa: BLE001 -- a broken check becomes an error finding
			_log_failure(check.__name__, exc)
			found.append(Finding("PREFLIGHT_CHECK_ERROR"))
	found.extend(_app_checks(defn, flow_id))
	return found


def blocking(findings: list[Finding]) -> list[Finding]:
	return [f for f in findings if f.severity == ERROR]
