import json

import frappe
from frappe import _

# Bounded wait for the browser to report a result back via
# ``submit_client_tool_result`` before the agent gives up on this call.
CLIENT_TOOL_RESULT_TIMEOUT_SECONDS = 30

# Extra headroom (beyond the wait timeout) on the Redis keys used to hand a
# tool call off to the browser, so a slightly-late submit still finds the
# request stash and a slightly-delayed waiter still finds the pushed result.
CLIENT_TOOL_REDIS_TTL_GRACE_SECONDS = 30

# Redis key prefixes for the dispatch handoff. Keyed on the correlation id
# (see ``client_side_function`` for why that's the SDK call id, not the
# ``Agent Tool Call`` docname).
_REQUEST_KEY_PREFIX = "huf:client_tool:req:"
_RESULT_KEY_PREFIX = "huf:client_tool:res:"
_ALREADY_RECORDED_KEY_PREFIX = "huf:client_tool:done:"


def _request_key(correlation_id):
    return f"{_REQUEST_KEY_PREFIX}{correlation_id}"


def _result_key(correlation_id):
    return f"{_RESULT_KEY_PREFIX}{correlation_id}"


def _already_recorded_key(correlation_id):
    return f"{_ALREADY_RECORDED_KEY_PREFIX}{correlation_id}"


def _get_or_create_call(conversation_id, agent_run_id, function_name, call_id, tool_params):
    """Locate the ``Agent Tool Call`` audit row for this invocation, or create it.

    Mirrors the dispatcher idiom in ``huf.ai.tools.code_execution.run_python``:
    an audit row is created up front (before the frontend has done anything),
    keyed on ``call_id`` so a later result can be correlated back to it.

    This row is intentionally left uncommitted: it lives inside the agent
    run's own transaction and becomes durable naturally when the run ends
    (or is rolled back if the run fails). Correlating the browser's result
    back to this call no longer depends on the row being visible outside
    that transaction -- see ``client_side_function``, which hands the wait
    off to Redis instead.
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

    An ``Agent Tool Call`` row is created (status ``Queued``) purely as an
    audit trail -- it stays inside this request's own transaction and is
    never committed early. Correlating the eventual browser result back to
    this call is done entirely through Redis, keyed on ``call_id`` (the SDK
    tool call id already passed in by the agent loop), falling back to the
    ``Agent Tool Call`` docname only if the SDK didn't supply one. The SDK
    call id is preferred because it is known to both sides (this function
    and the frontend) before the audit row would even be committed, so it
    works without relying on cross-transaction visibility at all.

    The wait itself blocks on ``frappe.cache().blpop`` -- a Redis socket
    wait with no DB access and no polling -- instead of the old loop that
    spun on ``frappe.db.get_value`` and committed the whole transaction on
    every iteration just to see other writers.
    """
    # submit_client_tool_result is not guest-accessible, so a guest session
    # would block here for the full timeout with no way for a result to ever
    # arrive. Fail fast instead of burning CLIENT_TOOL_RESULT_TIMEOUT_SECONDS.
    if frappe.session.user == "Guest":
        return {
            "status": "error",
            "message": "Client-side tools are not available in guest conversations.",
        }

    call = _get_or_create_call(conversation_id, agent_run_id, function_name, call_id, kwargs)
    correlation_id = call_id or call.name

    request_key = _request_key(correlation_id)
    result_key = _result_key(correlation_id)
    ttl = CLIENT_TOOL_RESULT_TIMEOUT_SECONDS + CLIENT_TOOL_REDIS_TTL_GRACE_SECONDS

    try:
        frappe.cache().set_value(
            request_key,
            {"conversation": conversation_id, "agent_run": agent_run_id},
            expires_in_sec=ttl,
        )
    except Exception:
        frappe.log_error(message=frappe.get_traceback(), title="client_side_function: redis stash failed")
        return {
            "status": "error",
            "message": "Could not dispatch the tool call to the frontend (cache unavailable).",
        }

    # Scope this to the conversation's owner. Without ``user=``, Frappe's
    # realtime layer fans this out to every socket subscribed to the
    # ``conversation:<id>`` room -- i.e. anyone who can guess/obtain this
    # conversation_id and subscribe, not just the conversation owner (see
    # ST-R6.6c). The owner is looked up from the DB rather than taken from
    # ``frappe.session.user`` because this can run from a queue-first
    # background worker, where the session user would be the worker's
    # service account, not the human whose browser should receive the
    # dialog.
    conversation_owner = frappe.db.get_value("Agent Conversation", conversation_id, "owner")

    frappe.publish_realtime(
        event=f'conversation:{conversation_id}',
        message={
            "type": "frontend_tool_call_initiated",
            "conversation_id": conversation_id,
            "agent_run_id": agent_run_id,
            "message_id": message_id,
            "function_name": function_name,
            "tool_params": kwargs,
            "call_id": correlation_id,
        },
        user=conversation_owner or frappe.session.user,
    )

    try:
        popped = frappe.cache().blpop(result_key, timeout=CLIENT_TOOL_RESULT_TIMEOUT_SECONDS)
    except Exception:
        frappe.log_error(message=frappe.get_traceback(), title="client_side_function: redis blpop failed")
        call.status = "Failed"
        call.error_message = "Lost connection to the result channel while waiting for the frontend."
        call.save(ignore_permissions=True)
        return {
            "status": "error",
            "message": "Lost connection to the result channel while waiting for the frontend.",
        }
    finally:
        try:
            frappe.cache().delete_value(request_key)
        except Exception:
            pass

    if popped is None:
        call.status = "Failed"
        call.error_message = f"Timed out after {CLIENT_TOOL_RESULT_TIMEOUT_SECONDS}s waiting for frontend."
        call.save(ignore_permissions=True)
        return {
            "status": "timeout",
            "message": (
                f"Timed out after {CLIENT_TOOL_RESULT_TIMEOUT_SECONDS}s waiting for the "
                f"frontend to execute '{function_name}'."
            ),
        }

    try:
        # Raw ``delete``, not ``delete_value``: the result list is written with
        # ``rpush`` and read with ``blpop``, which are plain redis-py calls on the
        # unprefixed key. Frappe's ``*_value`` helpers run the key through
        # ``make_key`` (site prefix), so they would address a different key.
        frappe.cache().delete(result_key)
    except Exception:
        pass

    _, raw_payload = popped
    try:
        payload = json.loads(raw_payload)
    except (TypeError, ValueError):
        payload = {"error": "Malformed result payload from frontend."}

    if payload.get("error"):
        call.status = "Failed"
        call.error_message = str(payload["error"])[:140]
        call.save(ignore_permissions=True)
        return {
            "status": "error",
            "message": payload["error"] or "Frontend tool execution failed.",
        }

    result = payload.get("result")
    call.status = "Completed"
    call.error_message = None
    call.tool_result = result if isinstance(result, (dict, list)) else {"output": "" if result is None else str(result)}
    call.save(ignore_permissions=True)

    return _coerce_result(result)


@frappe.whitelist()
def submit_client_tool_result(call_id, result=None, error=None):
    """Receive the result of a browser-executed tool call.

    ``call_id`` is the correlation key handed to the frontend in the
    ``frontend_tool_call_initiated`` realtime payload (see
    ``client_side_function``) -- the SDK tool call id, or the ``Agent Tool
    Call`` docname as a fallback. This deliberately does NOT read the
    ``Agent Tool Call`` row: that row lives inside the still-open agent-run
    transaction and is invisible here, which is exactly why the old
    implementation needed a commit on every poll iteration. Instead this
    reads the Redis request stash written by ``client_side_function`` to
    learn which conversation to authorize the caller against, then pushes
    the result onto the Redis list the waiter is blocked on.
    """
    request_key = _request_key(call_id)
    result_key = _result_key(call_id)
    already_key = _already_recorded_key(call_id)

    try:
        stash = frappe.cache().get_value(request_key)
    except Exception:
        frappe.log_error(message=frappe.get_traceback(), title="submit_client_tool_result: redis get_value failed")
        return {
            "status": "error",
            "success": False,
            "message": "Could not reach the result channel (cache unavailable).",
        }

    if not stash:
        # Unknown call_id, or the request stash already expired -- e.g. the
        # waiter already timed out and cleaned up, or this is a very late
        # retry. Report a structured result rather than throwing, since a
        # late/duplicate browser submit is not really an error condition.
        return {
            "status": "expired",
            "success": False,
            "message": "This tool call has expired or is unknown.",
        }

    if not frappe.has_permission("Agent Conversation", "write", stash.get("conversation")):
        frappe.throw(
            _("Not permitted to submit a result for this conversation."),
            frappe.PermissionError,
        )

    try:
        if frappe.cache().get_value(already_key):
            # A previous submit for this call_id already pushed a result
            # (the waiter may since have consumed it), so don't push a
            # second one -- mirrors the old Completed/Failed terminal check.
            return {"status": "already_recorded", "success": True}
    except Exception:
        pass  # Non-fatal: worst case a duplicate result is pushed and never read.

    if isinstance(result, str):
        try:
            result = json.loads(result)
        except (TypeError, ValueError):
            pass

    payload = {"error": str(error)[:140]} if error else {"result": result}
    ttl = CLIENT_TOOL_RESULT_TIMEOUT_SECONDS + CLIENT_TOOL_REDIS_TTL_GRACE_SECONDS

    try:
        frappe.cache().rpush(result_key, json.dumps(payload))
        # Raw ``expire``, not ``expire_key``: ``expire_key`` prefixes the key via
        # ``make_key`` while ``rpush`` above does not, so it would set a TTL on a
        # key that does not exist and leave this list to leak forever.
        frappe.cache().expire(result_key, ttl)
        frappe.cache().set_value(already_key, 1, expires_in_sec=ttl)
    except Exception:
        frappe.log_error(message=frappe.get_traceback(), title="submit_client_tool_result: redis rpush failed")
        return {
            "status": "error",
            "success": False,
            "message": "Could not deliver the result (cache unavailable).",
        }

    return {"success": True, "status": "Failed" if error else "Completed"}
