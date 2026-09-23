"""Adapter wiring Flow's ``router.decision`` node to ``huf.ai.decision.service.run_policy``.

PLAN.md §3.11 point 4 / D10. ``huf/ai/flow_engine.py:_exec_router_decision`` (~line 1099-1130)
calls whatever callable it finds at ``settings["decision_router"]`` with the fixed signature
``decision_router(flow_run, node, config, ctx_dict, candidates)`` and expects a
:class:`~huf.ai.decision.types.DecisionResponse` back -- it never imports anything from
``huf.ai.decision`` itself, so Flow stays decision-runtime-agnostic when the site switch is off.
:func:`make_flow_decision_router` builds that callable; T3.02 injects it into the run context in
``_build_run_context`` (``huf/ai/flow_engine.py:402``) with
``ctx["decision_router"] = make_flow_decision_router(flow_run, version)`` when the pinned graph
contains a ``router.decision`` node and the site switch is on.

Candidate provenance (I-DR1): the candidate/option set handed to ``run_policy`` is always built
from ``candidates`` -- the node's actual outgoing edges, exactly as
``huf.ai.flow_engine._get_outgoing_edges`` derives them and exactly what
``huf.ai.decision.flow_router.resolve_decision_route`` validates the answer against -- never from
``config["options"]`` alone (that dict only supplies optional per-branch label/criteria text, and
a branch declared there with no matching outgoing edge is silently ignored).

Policy version pinning (D10): a Flow Run pins the ``Decision Policy``'s currently published
``Decision Policy Version`` the first time each ``router.decision`` node runs, and every later
call from that run -- including after a pause/resume, which rebuilds the whole run context from
scratch (see ``resume_flow_run`` / ``_build_run_context``) -- reuses the pinned version rather
than whatever is published by then. The pin has to survive that rebuild, so it is stored in the
run's *persisted* context (``ctx_dict``, i.e. ``GraphContext.data`` / ``Flow Run.context_json``)
under :data:`PIN_CONTEXT_KEY` rather than in ``GraphContext.metadata``, which is only ever
recomputed from the ``Flow Run`` document fields on each ``_build_run_context`` call and is never
written back to ``context_json`` (see ``GraphContext.to_json``) -- so anything pinned only in
``.metadata`` would be forgotten across a resume.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import frappe

from huf.ai.decision import service
from huf.ai.decision.types import CandidateSource, DecisionOrigin, DecisionResponse, DecisionStatus, Option
from huf.ai.graph.executor import resolve_path
from huf.ai.transaction import commit_if_background

#: Reserved key in the run's persisted context dict (``ctx_dict`` / ``GraphContext.data``) that
#: holds, per node id, the ``Decision Policy Version`` this Flow Run pinned for that node (D10).
PIN_CONTEXT_KEY = "__decision_policy_pins__"

#: ``huf.ai.decision.service.run_policy``'s ``surface`` argument for this adapter's calls, per
#: the surface list ``service.py``'s own ``_SURFACE_LATENCY_BUDGET_MS`` comment enumerates.
SURFACE = "Flow Decision Router"

#: ``origin.origin_type`` for this adapter's calls -- one of ``Decision Call.origin_type``'s
#: fixed options (``huf/huf/doctype/decision_call/decision_call.json``).
ORIGIN_TYPE = "Flow"

FlowDecisionRouter = Callable[[Any, dict, dict, dict, list], DecisionResponse]


def make_flow_decision_router(flow_run, version) -> FlowDecisionRouter:
	"""Build the callable ``_exec_router_decision`` (``flow_engine.py:1117``) invokes.

	``flow_run`` and ``version`` (the Flow Run's pinned graph version, from
	``_build_run_context`` -- distinct from the *Decision Policy* version D10 pins) are accepted
	to match how the caller constructs this factory and to fail fast if either is missing; the
	returned closure otherwise ignores them and uses whatever ``flow_run``/``node``/``config``/
	``ctx_dict``/``candidates`` it is actually called with, since ``_exec_router_decision`` always
	passes the live values for the node currently executing.
	"""
	if flow_run is None:
		raise ValueError("make_flow_decision_router requires a Flow Run")

	def decision_router(flow_run, node: dict, config: dict, ctx_dict: dict, candidates: list) -> DecisionResponse:
		config = config or {}
		policy = config.get("policy")
		if not policy or not isinstance(policy, str):
			return DecisionResponse(status=DecisionStatus.FAILED, error_code="decision_router_no_policy")

		node_id = (node or {}).get("id") or ""
		options = _build_candidates(config, candidates or [])
		if not options:
			return DecisionResponse(status=DecisionStatus.FAILED, error_code="decision_router_no_candidates")

		ctx_dict = ctx_dict if isinstance(ctx_dict, dict) else {}
		# State first: it must reflect the run's context as the node sees it, never the
		# PIN_CONTEXT_KEY bookkeeping _pinned_version is about to add to that same dict.
		state = _build_state(config, ctx_dict)
		policy_version = _pinned_version(flow_run, ctx_dict, node_id, policy)

		try:
			result = service.run_policy(
				policy,
				state=state,
				candidates=options,
				candidate_source=CandidateSource.POLICY_OPTIONS,
				mode=service.MODE_ENFORCE,
				surface=SURFACE,
				origin=DecisionOrigin(
					origin_type=ORIGIN_TYPE,
					flow_run=getattr(flow_run, "name", None),
					flow_node_id=node_id or None,
				),
				policy_version=policy_version,
			)
		except (ValueError, frappe.ValidationError) as exc:
			return DecisionResponse(status=DecisionStatus.FAILED, error_code=str(exc))

		if result.status == service.DISABLED:
			return DecisionResponse(status=DecisionStatus.FAILED, error_code="decision_runtime_disabled")
		if result.status == service.SHADOW_ENQUEUED:
			# Flow's router.decision needs an inline route now; a policy bound Shadow has no
			# synchronous answer to route on, so this is treated like any other non-success.
			return DecisionResponse(status=DecisionStatus.FAILED, error_code="decision_router_shadow_mode")
		if result.response is not None:
			return result.response
		return DecisionResponse(status=DecisionStatus.FAILED, error_code="decision_router_no_response")

	return decision_router


def _build_candidates(config: dict, candidates: list) -> tuple[Option, ...]:
	"""Options for ``run_policy``, from the node's actual outgoing edges (I-DR1).

	``config["options"]`` (``RouterDecisionNode.config.options`` in the graph-IR schema: a
	``label``/``node_id`` pair per declared branch, optionally carrying free-text selection
	criteria once the schema grows that field) supplies description text per branch when present;
	it is never the source of the candidate id set itself -- that is always ``candidates``, the
	node's outgoing edges as ``huf.ai.flow_engine._get_outgoing_edges`` builds them, which is also
	exactly what ``flow_router.resolve_decision_route`` checks the answer against.
	"""
	declared = {}
	for entry in config.get("options") or ():
		if isinstance(entry, dict) and entry.get("node_id"):
			declared[entry["node_id"]] = entry

	options: list[Option] = []
	seen: set[str] = set()
	for candidate in candidates:
		target = candidate.get("to") if isinstance(candidate, dict) else None
		if not target or target in seen:
			continue
		seen.add(target)
		declared_entry = declared.get(target, {})
		description = (
			declared_entry.get("criteria")
			or declared_entry.get("label")
			or (candidate.get("label") if isinstance(candidate, dict) else None)
			or target
		)
		options.append(Option(target, description))
	return tuple(options)


def _build_state(config: dict, ctx_dict: dict) -> Any:
	"""Provider-visible ``state`` for ``run_policy``, from the node's ``state_bindings``.

	Each binding is ``{"name": ..., "path": ...}`` (the same ``name``/``path`` shape as
	``huf.ai.decision.types.StateBinding``, resolved here with the same dotted/indexed-path
	grammar as ``huf.ai.graph.executor.resolve_path`` against ``ctx_dict`` -- the run's flat
	context dict, i.e. what ``FlowRunContext.context.as_dict()`` returns). ``path == "$"``
	projects the whole context, matching the ``"$"`` convention ``huf.ai.decision.state`` already
	uses for a policy's own state bindings. A node with no ``state_bindings`` configured falls
	back to passing the whole context through -- the Decision Policy Version's own
	``state_bindings`` still project only what it declared before anything reaches a backend.

	Returns a fresh dict (or fresh nested dict for a ``"$"`` binding) that never aliases
	``ctx_dict`` and never carries :data:`PIN_CONTEXT_KEY` -- ``_pinned_version`` mutates
	``ctx_dict`` in place to record the D10 pin, and that bookkeeping key must never leak into
	provider-visible state, whichever of the two runs first.
	"""
	visible_ctx = {key: value for key, value in ctx_dict.items() if key != PIN_CONTEXT_KEY}
	bindings = config.get("state_bindings") or ()
	if not bindings:
		return visible_ctx

	state: dict[str, Any] = {}
	for binding in bindings:
		if not isinstance(binding, dict):
			continue
		name, path = binding.get("name"), binding.get("path")
		if not name or not path:
			continue
		state[name] = dict(visible_ctx) if path == "$" else resolve_path(visible_ctx, path)
	return state


def _pinned_version(flow_run, ctx_dict: dict, node_id: str, policy: str) -> str | None:
	"""Resolve, pinning on first use, the Decision Policy Version this node runs against (D10).

	Reusing a pin recorded for a *different* policy under the same ``node_id`` (a node whose
	``config.policy`` changed between two runs sharing one persisted pin key -- not possible for a
	single Flow Run, since its graph is pinned at creation, but cheap to guard) falls through to
	re-pinning instead of returning a stale, unrelated version.
	"""
	pin_key = node_id or policy
	pins = ctx_dict.get(PIN_CONTEXT_KEY)
	if not isinstance(pins, dict):
		pins = {}

	pinned = pins.get(pin_key)
	if isinstance(pinned, dict) and pinned.get("policy") == policy and pinned.get("version"):
		return pinned["version"]

	current_version = _current_published_version(policy)
	if not current_version:
		# No published version yet -- let run_policy raise its own "no published version and
		# none was pinned" error rather than pinning nothing.
		return None

	pins[pin_key] = {"policy": policy, "version": current_version}
	ctx_dict[PIN_CONTEXT_KEY] = pins
	_persist_pin(flow_run, ctx_dict)
	return current_version


def _current_published_version(policy: str) -> str | None:
	"""``Decision Policy.current_version`` -- the same field ``service._resolve_policy`` reads
	when no ``policy_version`` is pinned. Isolated in its own function (rather than inlined as
	``frappe.db.get_value(...)``) so tests can monkeypatch policy resolution without a real site.
	"""
	return frappe.db.get_value("Decision Policy", policy, "current_version")


def _persist_pin(flow_run, ctx_dict: dict) -> None:
	"""Flush the pin to ``Flow Run.context_json`` immediately so a resume sees it.

	``ctx_dict`` is the same dict object as the run's ``GraphContext.data`` (``ctx.as_dict()``
	returns it by reference, not a copy), so this mutation is already visible in-memory for the
	rest of the current run; the explicit ``db_set`` is what makes it survive a pause/resume,
	which rebuilds the run context (and this adapter's closure) from ``Flow Run.context_json``
	from scratch rather than reusing the in-memory object.
	"""
	if flow_run is None or not hasattr(flow_run, "db_set"):
		return
	flow_run.db_set("context_json", json.dumps(ctx_dict, default=str))
	commit_if_background()
