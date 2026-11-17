"""Tool-result de-duplication for conversation message history."""
from collections import defaultdict

import frappe


def supersede_duplicate_tool_results(messages: list) -> list:
    """One tool message per tool_call_id. A parked tool call stores an 'awaiting approval' result under the
    call id, and the approval follow-up later stores the real outcome under the SAME id; the model API
    rejects two tool messages for one call. The earliest row keeps its position (right after the assistant
    declaration) and takes the latest content; the later duplicates are dropped."""
    last_content = {}
    counts = defaultdict(int)
    for msg in messages:
        if isinstance(msg, dict) and msg.get("role") == "tool" and msg.get("tool_call_id"):
            counts[msg["tool_call_id"]] += 1
            last_content[msg["tool_call_id"]] = msg.get("content")
    if not any(n > 1 for n in counts.values()):
        return messages
    seen, out = set(), []
    for msg in messages:
        if isinstance(msg, dict) and msg.get("role") == "tool" and counts.get(msg.get("tool_call_id"), 0) > 1:
            cid = msg["tool_call_id"]
            if cid in seen:
                continue
            seen.add(cid)
            msg = {**msg, "content": last_content[cid]}
        out.append(msg)
    return out


def _synthesize_assistant_tool_call(tool_call_id: str, conversation_name: str | None) -> dict | None:
    """
    Try to rebuild an assistant tool_calls message from the persisted
    Agent Tool Call document. Returns None if no matching record exists.
    """
    if not tool_call_id or not conversation_name:
        return None
    try:
        doc = frappe.db.get_value(
            "Agent Tool Call",
            {"conversation": conversation_name, "call_id": tool_call_id},
            ["tool", "tool_args"],
            as_dict=True,
        )
        if not doc:
            return None
        return {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": tool_call_id,
                    "type": "function",
                    "function": {
                        "name": doc.tool or "",
                        "arguments": doc.tool_args or "{}",
                    },
                }
            ],
        }
    except (frappe.DoesNotExistError, frappe.DataError):
        return None
