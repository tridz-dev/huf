# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""HUF integration evidence via the REAL Procedure runtime (Track-Item: v3-issue-d).

Everything in `benchmarks/safe-deopt/faults.py` wraps a workload store's write method
directly (the in-memory-store boundary). This module adapts that same fault-injection
mechanism to intercept at the `tool_invoker` boundary instead -- the seam
`huf.ai.graph.procedure_runtime.execute_procedure` actually calls through
(`ToolInvoker = Callable[[str, dict], ToolInvocation]`) -- so the SAME `FaultInjector`
faults (F1/F3/F5/F7 here) can be exercised against a real `tool_invoker` wired to real
Frappe writes, driven through the real `execute_procedure`, with the real
`huf.ai.graph.fallback.build_mid_run_fallback` reading the real `ProcedureOutcome` that
run actually produced.

This module is frappe-free by itself (no top-level `import frappe`): the real Frappe
write functions are supplied by the caller (a bench console script), exactly the same
"caller supplies the tool_invoker" contract `execute_procedure` already requires. This
keeps the module importable and unit-testable (see
`benchmarks/safe-deopt/tests/test_real_procedure_integration.py`) without a live bench,
using a hand-written fake write function -- the fault-injection-at-the-boundary logic
itself has nothing Frappe-specific in it.

Design of the minimal Procedure graph
--------------------------------------
`execute_procedure` needs a `PinnedVersion` (an immutable `(graph, fingerprint)` pair --
see `huf.ai.graph.executor.PinnedVersion.pin`) whose `graph` is a dict with `entry` and
`nodes`, each node `{"id", "type", "config", "next"?, "on_error"?}`. The smallest
non-trivial write-bearing shape that mirrors W1's CRM-followup read -> write A -> write B
chain (see `benchmarks/safe-deopt/workloads.py`'s `CrmStore` / W3's `OrderProcessingStore`)
is built by `build_two_write_procedure_graph` below:

    read_target (tool.call, read)
      -> write_a (tool.call, write, recovery=resume)
        -> write_b (tool.call, write, recovery=resume)
          -> output (output)

Every write node carries a content-derived `operation_key` in its static `input` config
(D5: procedure name + node id + target identity -- computed once, at graph-build time,
not inferred at call time) and a `recovery` mode, exactly as
`_Runner._handle_tool_call` requires (both are validated top of that function; a write
node missing either fails closed before the tool is ever invoked).

`classify_tool` is a small dict-backed classifier (`{tool_id: "read"|"write"}`) so
`execute_procedure`'s own `_is_write_tool` correctly threads idempotency/recovery
handling for `write_a`/`write_b` and `huf.ai.graph.fallback.build_mid_run_fallback`'s own
`classify_tool` argument can reuse the identical mapping -- one source of truth for which
tools are writes in this graph, never duplicated.

Fault injection at the tool_invoker boundary
---------------------------------------------
`wrap_tool_invoker_with_fault` takes a real `tool_invoker` (the actual callable
`execute_procedure` will call: `(tool_id, args) -> ToolInvocation`), the `tool_id` to
target (normally `write_b`'s tool, mirroring where the workload's faults intentionally
land -- see `faults.py`'s own module docstring: "wraps a workload store's write-B call"),
a `benchmarks.safe_deopt.faults.FaultInjector`, a fault id, and a guarantee level. It
returns a NEW `ToolInvoker` that:

  * passes every OTHER tool_id straight through to the real invoker, unmodified;
  * for the targeted tool_id, builds a `real_write_fn` closure over the real invoker call
    (so the fault decides WHETHER that call actually happens: `FaultInjector._inject_f3`
    never calls `real_write_fn` at all, so `write_b`'s real Frappe write never fires --
    while `_inject_f5`/`_inject_f7`/`_inject_f2`/`_inject_f6` DO call it, so the real write
    lands even though the caller (here: `execute_procedure`) is told something else);
  * translates the resulting `ObservedResult` (`faults.py`'s own return shape -- `ok`,
    `value`, `error`) into a `ToolInvocation` (`procedure_runtime.py`'s own return shape --
    `success`, `result`, `error`), which is the only place this module bridges the two
    modules' independently-designed vocabularies.

This is deliberately NOT a rewrite of `FaultInjector` -- the same fault semantics
(F1 clean rejection, F3 uncommitted timeout, F5 lost result, F7 late commit) apply
unchanged; only the boundary they intercept moves from "a store's write method" to
"a tool_invoker's call for one specific tool_id".
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))

from faults import FAULT_IDS, GUARANTEE_LEVELS, FaultInjector  # noqa: E402

# execute_procedure / fallback are only imported lazily inside functions that need them,
# so this module stays importable (and its pure logic testable) even in an environment
# that has huf/frappe on sys.path but no live bench -- see the module docstring.


TOOL_READ_TARGET = "read_target"
TOOL_WRITE_A = "write_a_create_todo"
TOOL_WRITE_B = "write_b_update_status"


@dataclass(frozen=True)
class SimpleToolPermission:
    """Duck-typed `ToolPermission`-shaped object: `execute_procedure._is_write_tool` and
    `fallback.classify_write_tool` both only look at `.ptype` (see procedure_runtime.py's
    `_is_write_tool` and fallback.py's `classify_write_tool`).
    """

    ptype: str


def make_classifier() -> Callable[[str], SimpleToolPermission]:
    """A minimal, frappe-free `classify_tool` for this graph's three tools -- used both as
    `execute_procedure(..., classify_tool=...)` and as
    `build_mid_run_fallback(..., classify_tool=...)`'s argument, one source of truth.
    """

    mapping = {
        TOOL_READ_TARGET: "read",
        TOOL_WRITE_A: "create",
        TOOL_WRITE_B: "write",
    }

    def _classify(tool_id: str) -> SimpleToolPermission:
        return SimpleToolPermission(ptype=mapping.get(tool_id, "read"))

    return _classify


def build_two_write_procedure_graph(*, procedure_name: str, target_identity: str) -> dict:
    """The minimal real graph: read -> write A -> write B -> output.

    `target_identity` (e.g. the ToDo name/description this run will operate on) feeds each
    write node's content-derived `operation_key`, per D5 -- computed once here, not
    inferred by the runtime.
    """

    op_key_a = f"{procedure_name}:write_a:{target_identity}"
    op_key_b = f"{procedure_name}:write_b:{target_identity}"

    return {
        "entry": "read_target",
        "contract": {"limits": {"max_nodes": 20, "max_external_calls": 10}},
        "nodes": [
            {
                "id": "read_target",
                "type": "tool.call",
                "config": {"tool_id": TOOL_READ_TARGET, "input": {"target_identity": target_identity}},
                "next": "write_a",
            },
            {
                "id": "write_a",
                "type": "tool.call",
                "config": {
                    "tool_id": TOOL_WRITE_A,
                    "input": {
                        "target_identity": target_identity,
                        "idempotency_key": op_key_a,
                        "operation_key": op_key_a,
                    },
                    "recovery": "resume",
                },
                "next": "write_b",
                "on_error": None,
            },
            {
                "id": "write_b",
                "type": "tool.call",
                "config": {
                    "tool_id": TOOL_WRITE_B,
                    "input": {
                        "target_identity": target_identity,
                        "idempotency_key": op_key_b,
                        "operation_key": op_key_b,
                    },
                    "recovery": "resume",
                },
                "next": "output",
                "on_error": None,
            },
            {
                "id": "output",
                "type": "output",
                "config": {"value": {"target_identity": target_identity, "status": "done"}},
            },
        ],
    }


def build_two_write_procedure_graph_with_authority_gate(
    *, procedure_name: str, target_identity: str
) -> dict:
    """Same shape as `build_two_write_procedure_graph`, but write B's tool_id is a
    distinct, permission-gated tool (see `run_authority_denial_case` below): the real
    `tool_invoker` this graph is run against must consult `frappe.has_permission` for this
    tool_id and DENY it for a low-privileged acting user -- exercised through
    `execute_procedure`'s real path, not a separate authorization layer.
    """

    graph = build_two_write_procedure_graph(procedure_name=procedure_name, target_identity=target_identity)
    for node in graph["nodes"]:
        if node["id"] == "write_b":
            node["config"]["tool_id"] = TOOL_WRITE_B_PRIVILEGED
    return graph


TOOL_WRITE_B_PRIVILEGED = "write_b_privileged_status_update"


def make_classifier_with_privileged_write_b() -> Callable[[str], SimpleToolPermission]:
    mapping = {
        TOOL_READ_TARGET: "read",
        TOOL_WRITE_A: "create",
        TOOL_WRITE_B_PRIVILEGED: "write",
    }

    def _classify(tool_id: str) -> SimpleToolPermission:
        return SimpleToolPermission(ptype=mapping.get(tool_id, "read"))

    return _classify


ToolInvoker = Callable[[str, dict], Any]  # Any = huf.ai.graph.procedure_runtime.ToolInvocation


def wrap_tool_invoker_with_fault(
    real_invoker: ToolInvoker,
    *,
    target_tool_id: str,
    injector: FaultInjector,
    fault_id: str,
    guarantee_level: str,
    operation_key_arg: str = "operation_key",
) -> ToolInvoker:
    """Returns a new tool_invoker that fault-injects only `target_tool_id` calls.

    Every other tool_id is passed straight through untouched. This is the adapter the
    task brief calls for: "fault-injection wrappers from faults.py ... intercept AT THE
    tool_invoker BOUNDARY ... instead of the in-memory store boundary they wrap today."
    """

    if fault_id not in FAULT_IDS:
        raise ValueError(f"unknown fault_id {fault_id!r}, expected one of {FAULT_IDS}")
    if guarantee_level not in GUARANTEE_LEVELS:
        raise ValueError(f"unknown guarantee_level {guarantee_level!r}, expected one of {GUARANTEE_LEVELS}")

    # Imported lazily: this module must stay importable without huf/frappe on sys.path
    # for its pure/testable parts (see module docstring); ToolInvocation is only needed
    # once we actually build a wrapped invoker to hand to execute_procedure.
    from huf.ai.graph.procedure_runtime import ToolInvocation

    def _wrapped(tool_id: str, args: dict) -> ToolInvocation:
        if tool_id != target_tool_id:
            return real_invoker(tool_id, args)

        operation_key = args.get(operation_key_arg) or args.get("idempotency_key") or "<unknown>"

        def real_write_fn(**kwargs: Any) -> Any:
            # `kwargs` mirrors `args` (FaultInjector.inject passes back through **kwargs);
            # this closure is what a fault decides whether to call AT ALL.
            invocation = real_invoker(tool_id, kwargs)
            if not invocation.success:
                # Surface the real invoker's own failure as a raised exception so
                # FaultInjector's F4 (natural-validation-error) path and generic
                # exception handling see it uniformly; other faults here (F1/F3/F5/F7)
                # never depend on this branch since they don't call through on a normal
                # first attempt in this experiment's usage.
                raise RuntimeError(invocation.error or f"real tool_invoker denied/failed {tool_id}")
            return invocation.result

        # `operation_key` is passed to `inject` via `**call_kwargs` (it is already the
        # `operation_key_arg` key in `args`) rather than as a duplicate explicit kwarg --
        # `FaultInjector.inject` reads it from kwargs itself when not passed positionally.
        call_kwargs = dict(args)
        observed = injector.inject(
            fault_id,
            guarantee_level,
            real_write_fn,
            action=tool_id,
            **call_kwargs,
        )

        if observed.ok:
            return ToolInvocation(tool_id=tool_id, args=args, success=True, result=observed.value, error=None)
        return ToolInvocation(
            tool_id=tool_id, args=args, success=False, result=None, error=str(observed.error)
        )

    return _wrapped


def run_fault_case(
    *,
    procedure_name: str,
    target_identity: str,
    real_invoker: ToolInvoker,
    fault_id: str,
    guarantee_level: str = "none",
) -> dict:
    """Drive the real `execute_procedure`, with `write_b`'s tool_id fault-injected at the
    tool_invoker boundary, and build the real `build_mid_run_fallback` payload for any
    non-SUCCESS outcome. Returns a dict summary (never raises on an ordinary Procedure
    failure -- that IS the expected shape for F1/F3/F5/F7, which are all failures/
    ambiguous-successes by design).
    """

    from huf.ai.graph.executor import PinnedVersion
    from huf.ai.graph.fallback import build_mid_run_fallback
    from huf.ai.graph.procedure_runtime import ProcedureOutcome, execute_procedure

    graph = build_two_write_procedure_graph(procedure_name=procedure_name, target_identity=target_identity)
    version = PinnedVersion.pin(graph)
    classify_tool = make_classifier()

    injector = FaultInjector()
    wrapped_invoker = wrap_tool_invoker_with_fault(
        real_invoker,
        target_tool_id=TOOL_WRITE_B,
        injector=injector,
        fault_id=fault_id,
        guarantee_level=guarantee_level,
    )

    outcome: ProcedureOutcome = execute_procedure(
        version,
        {"target_identity": target_identity},
        tool_invoker=wrapped_invoker,
        run_id=f"{procedure_name}-{fault_id}",
        classify_tool=classify_tool,
        procedure_name=procedure_name,
    )

    summary: dict[str, Any] = {
        "fault_id": fault_id,
        "guarantee_level": guarantee_level,
        "outcome_status": outcome.status,
        "outcome_error": outcome.error,
        "node_visits": outcome.node_visits,
        "tool_invocations": outcome.tool_invocations,
    }

    if outcome.status == ProcedureOutcome.FAILED:
        fallback_payload = build_mid_run_fallback(
            procedure_id=procedure_name,
            version=version.fingerprint,
            run=None,
            graph=graph,
            outcome=outcome,
            classify_tool=classify_tool,
        )
        summary["fallback_payload"] = fallback_payload
    else:
        summary["fallback_payload"] = None

    return summary


def run_authority_denial_case(
    *,
    procedure_name: str,
    target_identity: str,
    real_invoker: ToolInvoker,
) -> dict:
    """Run `write_b` as a permission-gated tool through the REAL `execute_procedure`, with
    NO fault injected -- the denial must come from `real_invoker` itself consulting
    `frappe.has_permission` inside its own closure (per the task brief: "authorization is
    folded into the tool_invoker closure, not a separate execute_procedure parameter").
    This function does not build the invoker's authorization logic -- the caller (a bench
    console script) is responsible for that, exactly mirroring how
    `run_agent_procedure_run` builds its own real, authorizing `tool_invoker` via
    `huf.ai.graph.permissions.authorize_tool_call` (see procedure_runtime.py's own module
    docstring).
    """

    from huf.ai.graph.executor import PinnedVersion
    from huf.ai.graph.fallback import build_mid_run_fallback
    from huf.ai.graph.procedure_runtime import ProcedureOutcome, execute_procedure

    graph = build_two_write_procedure_graph_with_authority_gate(
        procedure_name=procedure_name, target_identity=target_identity
    )
    version = PinnedVersion.pin(graph)
    classify_tool = make_classifier_with_privileged_write_b()

    outcome: ProcedureOutcome = execute_procedure(
        version,
        {"target_identity": target_identity},
        tool_invoker=real_invoker,
        run_id=f"{procedure_name}-authority",
        classify_tool=classify_tool,
        procedure_name=procedure_name,
    )

    summary: dict[str, Any] = {
        "outcome_status": outcome.status,
        "outcome_error": outcome.error,
        "node_visits": outcome.node_visits,
        "tool_invocations": outcome.tool_invocations,
    }

    if outcome.status == ProcedureOutcome.FAILED:
        summary["fallback_payload"] = build_mid_run_fallback(
            procedure_id=procedure_name,
            version=version.fingerprint,
            run=None,
            graph=graph,
            outcome=outcome,
            classify_tool=classify_tool,
        )
    else:
        summary["fallback_payload"] = None

    return summary
