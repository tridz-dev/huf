# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Runtime exposure of bound Agent Procedures as tool-like capabilities (T-31).

GOAL.md ss3.1 is explicit: a bound Procedure is NOT materialised as an ``Agent Tool
Function`` row per (agent, procedure) pair -- that would put a hand-authored tool
definition in the model's static tool list forever, for every binding, forever. Instead
this module computes the exposure at request time, straight from the set of *enabled*
``Agent Procedure Binding`` rows for the agent, and ``huf.ai.sdk_tools.create_agent_tools``
folds the result into the tool list it already builds.

Two invariants enforced here, in addition to (defence in depth against) the ones the
``Agent Procedure Binding`` controller already enforces at save time:

  I8 -- a binding whose pinned Procedure is not ``is_read_only`` is never exposed, even if
  it somehow got saved as enabled (e.g. the read-only flag on the Procedure changed after
  the binding was created -- Procedure versions are immutable, but this module treats the
  controller's write-time check as advisory, not load-bearing, and re-verifies here).

  Per-agent cap -- ``get_binding_cap()`` bounds how many bound-procedure schemas ever enter
  model context, regardless of how many bindings exist. Enabled bindings beyond the cap are
  dropped, highest ``priority`` first (ties broken by ``modified`` descending), and this is
  logged, not silently swallowed -- exceeding the cap is a fail-closed condition, not "expose
  everything and hope."

Invoking a bound procedure never bypasses ``huf.ai.graph.procedure_runtime.run_agent_procedure_run``:
this module's invocation path only ever (a) inserts a fresh ``Agent Procedure Run`` pinned
to the binding's ``procedure`` and (b) calls ``run_agent_procedure_run`` on it. That is the
same function real Procedure Runs already go through, so the run lock (GT-08), I1
authorization, and I5 telemetry are unconditionally exercised -- there is no direct call
into ``execute_procedure`` from here.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

import frappe

DEFAULT_BINDING_CAP = 8
BINDING_CAP_CONF_KEY = "agent_procedure_binding_max_per_agent"

TOOL_NAME_PREFIX = "procedure__"


def get_binding_cap() -> int:
	"""Configurable hard per-agent cap on bound-procedure exposure.

	Reads ``frappe.conf`` (site/common config), falling back to
	``DEFAULT_BINDING_CAP``. Any non-positive or unparsable configured value is treated
	as absent (fail closed to the sane default, never to "unlimited").
	"""
	try:
		configured = frappe.conf.get(BINDING_CAP_CONF_KEY)
	except (AttributeError, TypeError):
		configured = None

	try:
		cap = int(configured) if configured is not None else DEFAULT_BINDING_CAP
	except (TypeError, ValueError):
		cap = DEFAULT_BINDING_CAP

	return cap if cap > 0 else DEFAULT_BINDING_CAP


@dataclass(frozen=True)
class BoundProcedure:
	"""One enabled binding, resolved and ready to expose as a tool-like capability."""

	binding_name: str
	agent: str
	procedure: str
	procedure_id: str
	procedure_name: str
	input_schema: dict
	priority: int = 0
	fallback_enabled: bool = False
	"""``Agent Procedure Binding.fallback_enabled``. Controls only how much *detail* a
	failure hands back to the calling Agent (structured GOAL.md ss2.4 payload vs. a plain
	error) -- never whether a failure is survivable. Under either setting
	:func:`invoke_bound_procedure` returns a result dict; it never lets an exception out
	(I9).
	"""


def _parse_schema(raw) -> dict:
	if not raw:
		return {"type": "object", "properties": {}}
	if isinstance(raw, dict):
		schema = raw
	else:
		try:
			schema = json.loads(raw)
		except (TypeError, ValueError):
			return {"type": "object", "properties": {}}
	if not isinstance(schema, dict):
		return {"type": "object", "properties": {}}
	return schema


def get_bound_procedures_for_agent(agent_name: str) -> list[BoundProcedure]:
	"""Resolve the exposable bound procedures for one agent, cap already applied.

	Re-checks ``is_read_only`` (I8) and re-applies :func:`get_binding_cap` at read time
	regardless of what the ``Agent Procedure Binding`` controller already enforced at
	save time -- this is the function the runtime path actually trusts.
	"""
	if not agent_name:
		return []

	bindings = frappe.get_all(
		"Agent Procedure Binding",
		filters={"agent": agent_name, "enabled": 1},
		fields=["name", "procedure", "procedure_id", "priority", "fallback_enabled", "modified"],
		order_by="priority desc, modified desc",
	)
	if not bindings:
		return []

	cap = get_binding_cap()
	resolved: list[BoundProcedure] = []

	for binding in bindings:
		if len(resolved) >= cap:
			frappe.logger("huf").warning(
				f"Agent Procedure Binding cap ({cap}) reached for agent {agent_name}; "
				f"binding {binding.name} (procedure {binding.procedure_id}) not exposed."
			)
			break

		procedure = frappe.db.get_value(
			"Agent Procedure",
			binding.procedure,
			["procedure_id", "procedure_name", "is_read_only", "input_schema"],
			as_dict=True,
		)
		if not procedure:
			frappe.logger("huf").debug(
				f"Agent Procedure Binding {binding.name} points at missing procedure "
				f"{binding.procedure}; skipping."
			)
			continue

		if not procedure.is_read_only:
			# I8, re-checked at read time -- see module docstring.
			frappe.logger("huf").warning(
				f"Agent Procedure Binding {binding.name} pins a non-read-only procedure "
				f"({binding.procedure}); refusing to expose it (I8)."
			)
			continue

		resolved.append(
			BoundProcedure(
				binding_name=binding.name,
				agent=agent_name,
				procedure=binding.procedure,
				procedure_id=procedure.procedure_id,
				procedure_name=procedure.procedure_name or procedure.procedure_id,
				input_schema=_parse_schema(procedure.input_schema),
				priority=binding.priority or 0,
				fallback_enabled=bool(binding.get("fallback_enabled")),
			)
		)

	return resolved


def _tool_name_for(bound: BoundProcedure) -> str:
	safe = re.sub(r"[^a-zA-Z0-9_-]", "_", bound.procedure_id or bound.binding_name)
	return f"{TOOL_NAME_PREFIX}{safe}"


def invoke_bound_procedure(bound: BoundProcedure, args: dict, *, agent_run_id: str | None = None) -> dict:
	"""Run a bound procedure end to end, always through ``run_agent_procedure_run``.

	Creates a fresh ``Agent Procedure Run`` pinned to ``bound.procedure`` (the exact
	version this binding names) and advances it with
	``huf.ai.graph.procedure_runtime.run_agent_procedure_run`` -- the same function every
	other Procedure Run goes through, so the run lock, I1 authorization and I5 telemetry
	are never skipped for a bound invocation.

	**Never raises** (I9 -- "a failing Procedure never fails the Agent"). Every path,
	including a run that could not even be inserted, returns a result dict the caller can
	branch on:

	  ``{"ok": bool, "status": str, "run": str|None, "output": any, "error": str|None,
	    "fallback": dict|None, "fallback_enabled": bool}``

	``ok`` is the single field a caller must branch on; ``status`` is the finer-grained
	``ProcedureOutcome`` status (or ``"error"`` when the invocation itself blew up before
	producing an outcome). ``bound.fallback_enabled`` decides ONLY whether ``fallback``
	carries the structured GOAL.md ss2.4 payload (``True``) or stays ``None`` so the caller
	sees a plain, catchable error result (``False``). It never decides survivability: the
	Agent keeps running either way and can fall back to atomic tools.
	"""
	from huf.ai.graph.procedure_runtime import ProcedureOutcome, run_agent_procedure_run

	run_name = None
	try:
		run = frappe.get_doc(
			{
				"doctype": "Agent Procedure Run",
				"procedure": bound.procedure,
				"agent_run": agent_run_id,
				"input_payload": json.dumps(args or {}, default=str),
			}
		)
		run.insert(ignore_permissions=True)
		run_name = run.name

		agent_doc = frappe.get_cached_doc("Agent", bound.agent) if bound.agent else None
		outcome = run_agent_procedure_run(run.name, agent_doc=agent_doc)
	except Exception as exc:  # noqa: BLE001 -- I9: converted to a return value, never re-raised
		frappe.logger("huf").warning(
			f"Bound procedure {bound.procedure_id} ({bound.binding_name}) raised; "
			f"degrading to agentic execution.\n{frappe.get_traceback()}"
		)
		return {
			"ok": False,
			"status": "error",
			"run": run_name,
			"output": None,
			"error": str(exc),
			"fallback": None,
			"fallback_enabled": bool(bound.fallback_enabled),
		}

	ok = outcome.status == ProcedureOutcome.SUCCESS
	# The structured payload is withheld -- not the survivability. With fallback disabled
	# the caller still gets ok=False plus a plain error string, which is a normal,
	# catchable result, not an exception.
	fallback = outcome.fallback if (bound.fallback_enabled and not ok) else None

	return {
		"ok": ok,
		"status": outcome.status,
		"run": run_name,
		"output": outcome.output,
		"error": outcome.error,
		"fallback": fallback,
		"fallback_enabled": bool(bound.fallback_enabled),
	}


def build_procedure_binding_tools(agent, **kwargs) -> list:
	"""Build one ``FunctionTool`` per enabled, capped, read-only-verified binding.

	Returned tools' ``params_json_schema`` is exactly the pinned procedure version's
	``input_schema`` (falling back to an empty object schema) -- nothing richer, so the
	binding never re-introduces the context bloat lazy discovery (GT-07) already removed
	for the eager Agent Tool Function path.
	"""
	agent_name = getattr(agent, "name", None)
	bound_procedures = get_bound_procedures_for_agent(agent_name)
	if not bound_procedures:
		return []

	tools = []
	for bound in bound_procedures:
		tools.append(_make_binding_tool(bound, agent_run_id=(kwargs or {}).get("agent_run_id")))
	return tools


def _make_binding_tool(bound: BoundProcedure, *, agent_run_id: str | None = None):
	import asyncio
	import json as _json

	from agents import FunctionTool

	async def on_invoke_tool(ctx=None, args_json: str | None = None) -> str:
		try:
			if args_json is None and isinstance(ctx, str):
				args_json = ctx
				ctx = None

			args_dict = _json.loads(args_json or "{}")

			run_agent_run_id = agent_run_id
			inner = getattr(ctx, "context", None)
			if isinstance(inner, dict) and inner.get("agent_run_id"):
				run_agent_run_id = inner.get("agent_run_id")

			result = await asyncio.to_thread(
				invoke_bound_procedure, bound, args_dict, agent_run_id=run_agent_run_id
			)
			return _json.dumps(result, default=str)
		except Exception as e:
			frappe.logger("huf").debug(
				f"Error invoking bound procedure {bound.procedure_id} ({bound.binding_name}): {e!s}\n"
				f"{frappe.get_traceback()}"
			)
			# Same actionable shape invoke_bound_procedure returns, so the model never
			# sees two different failure vocabularies from one tool (I9).
			return _json.dumps({"ok": False, "status": "error", "error": str(e), "fallback": None})

	return FunctionTool(
		name=_tool_name_for(bound),
		description=(
			f"Run the '{bound.procedure_name}' procedure (deterministic, read-only). "
			f"Bound via Agent Procedure Binding {bound.binding_name}, pinned version "
			f"{bound.procedure}."
		),
		params_json_schema=bound.input_schema,
		on_invoke_tool=on_invoke_tool,
		strict_json_schema=False,
	)
