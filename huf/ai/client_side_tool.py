import json
import time

import frappe
from frappe import _

from huf.ai.transaction import safe_commit

# Bounded wait for the browser to report a result back via
# ``submit_client_tool_result`` before the agent gives up on this call.
CLIENT_TOOL_RESULT_TIMEOUT_SECONDS = 30

# How often to re-poll ``Agent Tool Call.status`` while waiting.
CLIENT_TOOL_POLL_INTERVAL_SECONDS = 0.5


def _get_or_create_call(conversation_id, agent_run_id, function_name, call_id, tool_params):
    """Locate the ``Agent Tool Call`` audit row for this invocation, or create it.

    Mirrors the dispatcher idiom in ``huf.ai.tools.code_execution.run_python``:
    an audit row is created up front (before the frontend has done anything),
    keyed on ``call_id`` so a later result can be correlated back to it.
    """
    existing_name = (
        frappe.db.get_value(
            "Agent Tool Call",
            {"call_id": call_id, "agent_run": agent_run_id, "conversation": conversation_id},
            "name",
        )
        if call_id
        else None
    )

    if existing_name:
        call = frappe.get_doc("Agent Tool Call", existing_name)
        call.status = "Queued"
        call.error_message = None
        call.save(ignore_permissions=True)
        # Cross-transaction visibility: the browser's submit_client_tool_result
        # request runs in a separate transaction and must be able to see this
        # row (and its reset status) as soon as the realtime event fires.
        safe_commit()
        return call

    call = frappe.get_doc({
        "doctype": "Agent Tool Call",
        "agent_run": agent_run_id,
        "conversation": conversation_id,
        "tool": function_name,
        "tool_args": json.dumps(tool_params) if tool_params else None,
        "status": "Queued",
        "call_id": call_id,
    })
    call.insert(ignore_permissions=True)
    # Cross-transaction visibility: without this commit the row only exists
    # inside the agent run's still-open transaction, so the frontend's
    # separate submit_client_tool_result request would find no matching row
    # ("Tool call not found.") even though it was just created here.
    safe_commit()
    return call


def _coerce_result(raw_result):
    """Normalize a stored/submitted result into a JSON-serializable value for the LLM."""
    if raw_result is None:
        return {}
    if isinstance(raw_result, (dict, list)):
        return raw_result
    if isinstance(raw_result, str):
        try:
            return json.loads(raw_result)
        except (TypeError, ValueError):
            return raw_result
    return raw_result


@frappe.whitelist()
def client_side_function(conversation_id=None, agent_run_id=None, function_name=None, message_id=None, call_id=None, **kwargs):
    """Dispatch a tool call to the browser and block until it reports a result.

    An ``Agent Tool Call`` row is created (status ``Queued``) so the frontend
    has something concrete to write its result onto, then the SAME
    ``frontend_tool_call_initiated`` realtime event as before is published on
    ``conversation:<conversation_id>`` — now carrying ``call_id`` so the
    frontend can correlate its result back via ``submit_client_tool_result``.

    This call then polls ``Agent Tool Call.status`` (fresh from the database
    on every iteration — never a cached document) until the frontend reports
    Completed/Failed, or until ``CLIENT_TOOL_RESULT_TIMEOUT_SECONDS`` elapses.
    On timeout a structured ``{"status": "timeout", ...}`` dict is returned so
    the model can tell it never got a real answer.
    """
    call = _get_or_create_call(conversation_id, agent_run_id, function_name, call_id, kwargs)

    frappe.publish_realtime(
        event=f'conversation:{conversation_id}',
        message={
            "type": "frontend_tool_call_initiated",
            "conversation_id": conversation_id,
            "agent_run_id": agent_run_id,
            "message_id": message_id,
            "function_name": function_name,
            "tool_params": kwargs,
            "call_id": call.name,
        },
    )

    deadline = time.monotonic() + CLIENT_TOOL_RESULT_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        status = frappe.db.get_value("Agent Tool Call", call.name, "status")

        if status == "Completed":
            result = frappe.db.get_value("Agent Tool Call", call.name, "tool_result")
            return _coerce_result(result)

        if status == "Failed":
            error_message = frappe.db.get_value("Agent Tool Call", call.name, "error_message")
            return {
                "status": "error",
                "message": error_message or "Frontend tool execution failed.",
            }

        time.sleep(CLIENT_TOOL_POLL_INTERVAL_SECONDS)
        # Cross-transaction visibility: this loop runs inside one long-lived
        # transaction, so under MariaDB's default REPEATABLE READ isolation
        # every frappe.db.get_value above would keep re-reading the snapshot
        # taken at transaction start. Committing here (even though nothing
        # was written) starts a fresh transaction/snapshot so the next
        # iteration can observe the frontend's committed status update.
        safe_commit()

    return {
        "status": "timeout",
        "message": (
            f"Timed out after {CLIENT_TOOL_RESULT_TIMEOUT_SECONDS}s waiting for the "
            f"frontend to execute '{function_name}'."
        ),
    }


@frappe.whitelist()
def submit_client_tool_result(call_id, result=None, error=None):
    """Receive the result of a browser-executed tool call.

    ``call_id`` is the ``Agent Tool Call`` docname handed to the frontend in
    the ``frontend_tool_call_initiated`` realtime payload (see
    ``client_side_function``). Modeled on
    ``huf.ai.tools.code_execution._apply_result``: write the result onto the
    audit row and flip its status so the poller in ``client_side_function``
    picks it up.
    """
    if not frappe.db.exists("Agent Tool Call", call_id):
        frappe.throw(_("Tool call not found."), frappe.DoesNotExistError)

    call = frappe.get_doc("Agent Tool Call", call_id)

    if not frappe.has_permission("Agent Conversation", "write", call.conversation):
        frappe.throw(
            _("Not permitted to submit a result for this conversation."),
            frappe.PermissionError,
        )

    # A late or replayed submit (e.g. a retrying browser) must not clobber a
    # result the agent has already consumed. Once the row is Completed/Failed
    # it is terminal — report that the result was already recorded instead of
    # overwriting it or raising, since a duplicate submit is not an error.
    if call.status in ("Completed", "Failed"):
        return {"status": "already_recorded", "success": True, "call_status": call.status}

    if isinstance(result, str):
        try:
            result = json.loads(result)
        except (TypeError, ValueError):
            pass

    if error:
        call.status = "Failed"
        call.error_message = str(error)[:140]
    else:
        call.status = "Completed"
        call.error_message = None
        call.tool_result = result if isinstance(result, (dict, list)) else {"output": "" if result is None else str(result)}

    if not frappe.has_permission("Agent Tool Call", "write", doc=call):
        frappe.throw(
            _("Not permitted to update Agent Tool Call records."),
            frappe.PermissionError,
        )

    call.save(ignore_permissions=True)
    # Cross-transaction visibility: client_side_function polls this row from
    # a different long-lived transaction/process. Commit immediately rather
    # than waiting on this request's own teardown so that poller observes
    # the new status without stalling out the remainder of its timeout.
    safe_commit()

    return {"success": True, "status": call.status}
