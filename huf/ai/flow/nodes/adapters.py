"""Bridges from the engine's executor signature ``(flow_run, node, config, settings)`` to the node modules.

Each node module takes the run context it needs; these adapters read it from the engine's settings.
"""

from __future__ import annotations

import frappe

from huf.ai.flow import create_doc as flow_create_doc
from huf.ai.graph.error_copy import plain_error, step_ref
from huf.ai.graph.permissions import envelope_declares


def _ctx(flow_run, settings):
	from huf.ai.flow.engine import _context_of

	return _context_of(flow_run, settings)


def exec_router_decision(flow_run, node: dict, config: dict, settings: dict) -> dict:
	"""``router.decision``: Decision mode when ``decision`` is configured, else the rule mode, see ``nodes/router_decision.py``."""
	from huf.ai.flow.nodes.router_decision import exec_router_decision as run_router_decision

	return run_router_decision(flow_run, node, config, settings, _ctx(flow_run, settings))


def exec_knowledge_search(flow_run, node: dict, config: dict, settings: dict) -> dict:
	"""``knowledge.search``: search one Knowledge Source as the run's user, see ``nodes/knowledge.py``."""
	from huf.ai.flow.engine import _run_context
	from huf.ai.flow.nodes.knowledge import exec_knowledge_search as run_knowledge_search

	return run_knowledge_search(node, config, _ctx(flow_run, settings), _run_context(settings))


def exec_handoff(flow_run, node: dict, config: dict, settings: dict):
	"""``handoff``: hand the conversation to a person and park until released, see ``nodes/handoff.py``."""
	from huf.ai.flow.nodes.handoff import exec_handoff as run_handoff

	return run_handoff(flow_run, node, config, settings)


def exec_split(flow_run, node: dict, config: dict, settings: dict) -> dict:
	"""Execute split node: weighted branches plus holdout, see ``nodes/split.py``."""
	from huf.ai.flow.nodes.split import exec_split as run_split

	return run_split(flow_run, node, config, settings)


def exec_stop(flow_run, node: dict, config: dict, settings: dict) -> dict:
	"""Execute stop node: fail the run with its message, see ``nodes/stop.py``."""
	from huf.ai.flow.nodes.stop import exec_stop as run_stop

	return run_stop(flow_run, node, config, settings, _ctx(flow_run, settings))


def exec_member_set(flow_run, node: dict, config: dict, settings: dict) -> dict:
	"""``member.set``: save values on the run's member, see ``nodes/member.py``."""
	from huf.ai.flow.nodes.member import exec_member_set as run_member_set

	return run_member_set(flow_run, node, config, _ctx(flow_run, settings))


def exec_send_message(flow_run, node: dict, config: dict, settings: dict):
	"""``send.message``: bind, guard chain, transport, see ``nodes/send.py``."""
	from huf.ai.flow.nodes.send import exec_send_message as run_send

	return run_send(flow_run, node, config, settings)


def exec_doc_get(flow_run, node: dict, config: dict, settings: dict) -> dict:
	"""``doc.get``: read one document as the run user, see ``nodes/docops.py``."""
	from huf.ai.flow.engine import _run_context
	from huf.ai.flow.nodes.docops import exec_doc_get as run_doc_get

	return run_doc_get(node, config, _ctx(flow_run, settings), _run_context(settings))


def exec_doc_update(flow_run, node: dict, config: dict, settings: dict) -> dict:
	"""``doc.update``: change fields of one document as the run user, see ``nodes/docops.py``."""
	from huf.ai.flow.engine import _run_context
	from huf.ai.flow.nodes.docops import exec_doc_update as run_doc_update

	return run_doc_update(node, config, _ctx(flow_run, settings), _run_context(settings))


def exec_flow_call(flow_run, node: dict, config: dict, settings: dict) -> dict:
	"""``flow.call``: start another published flow, optionally waiting for it, see ``nodes/subflow.py``."""
	from huf.ai.flow.nodes.subflow import exec_flow_call as run_flow_call

	return run_flow_call(flow_run, node, config, settings, _ctx(flow_run, settings))


def exec_doc_create(flow_run, node: dict, config: dict, settings: dict) -> dict:
	"""
	``doc.create``: config ``doctype`` (literal) and ``fields`` (object of values / references).
	Output ``{"doctype", "name"}`` so later nodes can use ``{"$from": "<node>.name"}``.

	Policy lives in :mod:`huf.ai.flow.create_doc` (allow-list, field validation, no
	``ignore_permissions``). Each created document also counts against the graph contract's
	``limits.max_writes`` for the run (absent or 0 means no writes are allowed).
	"""
	from huf.ai.flow import engine
	from huf.ai.flow.engine import _context_of, _run_context
	unknown = sorted(set(config) - {"doctype", "fields"})
	if unknown or "doctype" not in config or "fields" not in config:
		return {"status": "failed", "error": f'{step_ref(node, True)} is missing its record type or fields, or has settings it does not use. Open the step and check it.'}
	ctx = _context_of(flow_run, settings)
	run_ctx = _run_context(settings)
	limits = ((run_ctx.definition.get("contract") or {}).get("limits") or {}) if run_ctx is not None else {}
	max_writes = limits.get("max_writes") or 0
	envelope = ((run_ctx.definition.get("contract") or {}).get("permission_envelope") or {}) if run_ctx is not None else {}
	doctype = config["doctype"]
	try:  # the site allow-list first: its message is the clearer one for an unsupported doctype
		flow_create_doc.check_doctype(doctype, flow_create_doc.allowed_doctypes(frappe.conf))
	except flow_create_doc.CreateDocError as exc:
		return {"status": "failed", "error": plain_error(str(exc))}
	if not isinstance(doctype, str) or not envelope_declares(envelope, ptype="create", doctype=doctype):
		return {"status": "failed", "error": f'{step_ref(node, True)} is not allowed to create "{doctype}" records. Ask an admin to allow it for this flow.'}
	done = ctx.data.get(engine._WRITES_KEY) or 0
	if done >= max_writes:
		return {"status": "failed", "error": f'{step_ref(node, True)} would create more records than this flow is allowed to ({max_writes}). Ask an admin to raise the limit.'}
	try:
		result = flow_create_doc.create_document(config["doctype"], ctx.resolve(config["fields"]))
	except flow_create_doc.CreateDocError as exc:
		return {"status": "failed", "error": plain_error(str(exc))}
	except frappe.PermissionError:
		return {"status": "failed", "error": f'You do not have permission to create "{doctype}" records. Ask an admin for access.'}
	ctx.set(engine._WRITES_KEY, done + 1)
	return {"status": "success", "result": result, "output": result}
