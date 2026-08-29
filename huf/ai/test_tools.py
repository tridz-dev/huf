"""Deterministic tool handlers used ONLY by the regression-safety test suite.

These are real, importable ``Agent Tool Function`` handler functions — the
same kind of plain Python function that ``huf/ai/tool_functions.py`` defines
for CRUD tools — wired to real DocType records via the factories in
``huf/ai/tests/factories.py``. They exist so tests can exercise the REAL
tool-execution path (assembly -> permission check -> handler resolution ->
handler call -> result -> persistence) end to end, instead of the
provider-level simulation in ``huf/ai/providers/test_provider.py``.

Handler signature/return-type convention matched from
``huf/ai/tool_functions.py`` (see e.g. ``get_document``/``update_document``
there):
  - plain function, typed positional/keyword params (no ``self``)
  - returns a JSON-serializable ``dict`` (commonly with a ``success`` key and
    an ``error``/``permission_denied`` key on the failure path — see
    ``update_document``, huf/ai/tool_functions.py:90-113)
  - permission checks (when relevant) are done inline with
    ``frappe.has_permission(...)``, returning
    ``{"success": False, "error": ..., "permission_denied": True}`` rather
    than raising, mirroring ``update_document``'s write-permission check.
  - exceptions escape only when the tool is deliberately built to test the
    handler-exception path (``deterministic_fail`` below); the real failure
    path is exercised via ``create_function_tool``'s ``on_invoke_tool``
    closure (huf/ai/sdk_tools.py:506-510), which catches ``Exception`` and
    returns ``json.dumps({"error": str(e)})`` to the model.
"""

import time

import frappe


class DeterministicTestToolFailure(Exception):
    """Raised by ``deterministic_fail`` — a known, stable exception type/message
    used to test the tool-handler-exception failure path end to end."""


@frappe.whitelist()
def echo(**kwargs) -> dict:
    """Return the input arguments unchanged (JSON-serializable).

    Any keys injected by the run context (``conversation_id``,
    ``agent_run_id``, ``agent_name``, ``call_id`` — see
    ``huf.ai.sdk_tools._merge_run_context``) are echoed back too, since the
    handler has no way to distinguish them from LLM-supplied arguments and
    the point of this tool is to prove "what came in is what goes out."
    """
    return {"echoed": dict(kwargs)}


@frappe.whitelist()
def deterministic_add(numbers: list = None) -> dict:
    """Deterministic arithmetic: sum a list of numbers, returning a fixed,
    computable result. No randomness, no clock, no I/O.
    """
    values = numbers or []
    total = sum(values)
    return {"success": True, "sum": total, "count": len(values)}


@frappe.whitelist()
def deterministic_fail(**kwargs) -> dict:
    """Always raises a known exception type/message.

    Used to test the tool-handler-exception failure path: the exception
    must propagate out of this function so ``on_invoke_tool``
    (huf/ai/sdk_tools.py:506-510) is the thing that catches it and turns it
    into ``{"error": ...}`` fed back to the model — not this function
    swallowing it itself.
    """
    raise DeterministicTestToolFailure("deterministic_fail: intentional test failure")


@frappe.whitelist()
def permission_protected_mutation(record_id: str, value: str) -> dict:
    """A mutation gated by a specific required permission.

    Mirrors ``update_document``'s inline permission-check convention
    (huf/ai/tool_functions.py:107-112): this handler does its own
    defense-in-depth ``frappe.has_permission`` check on top of whatever
    gate already ran at assembly time
    (``PermissionAwareToolRegistry._can_use_tool``, huf/ai/tool_registry.py:70-106)
    and at invocation time (``on_invoke_tool``, huf/ai/sdk_tools.py:437-441).

    The corresponding ``Agent Tool Function`` fixture
    (``huf.ai.tests.factories.build_permission_protected_mutation_tool_spec`` /
    ``create_test_tool_doc``) sets ``required_permission="write"`` and a
    ``reference_doctype`` so the
    real ``TOOL_PERMISSIONS``/``required_permission`` gate in
    ``tool_registry.py`` is actually exercised (that gate only fires when
    ``reference_doctype`` is set — huf/ai/tool_registry.py:91-105).
    """
    reference_doctype = "ToDo"

    if not frappe.has_permission(reference_doctype, "write"):
        return {
            "success": False,
            "error": f"You do not have write permission on {reference_doctype}",
            "permission_denied": True,
        }

    return {"success": True, "record_id": record_id, "value": value}


# Hard cap so a misconfigured/malicious duration argument can never hang a
# test suite. Kept small and explicit rather than reading it from config.
MAX_SLEEP_SECONDS = 2.0


@frappe.whitelist()
def slow_or_timeout(duration=0.1) -> dict:
    """Sleep for a deterministic, test-controllable duration (capped) to
    exercise timeout-path testing without ever hanging the suite.

    Deliberately untyped on ``duration``: a newer Frappe framework version
    (pulled in via the pre-develop merge) added parameter-type coercion/
    validation on `@frappe.whitelist()`-decorated functions driven by their
    type hints, which runs BEFORE this function's own body -- a `duration:
    float` hint made an invalid value (e.g. a non-numeric string, the exact
    case `test_invalid_duration_falls_back_to_default` exercises) raise
    `FrappeTypeError` at the decorator layer instead of ever reaching the
    `try/except (TypeError, ValueError)` fallback below. Leaving this
    parameter untyped keeps that fallback in charge of invalid input.
    """
    try:
        requested = float(duration)
    except (TypeError, ValueError):
        requested = 0.1

    actual = max(0.0, min(requested, MAX_SLEEP_SECONDS))
    capped = actual != requested

    time.sleep(actual)

    return {
        "success": True,
        "requested_duration": requested,
        "slept_duration": actual,
        "capped": capped,
    }
