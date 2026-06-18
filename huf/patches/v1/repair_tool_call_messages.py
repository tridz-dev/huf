import frappe
import json


def execute():
    """
    Back-fill the new tool_call_id and tool_calls columns on existing
    Agent Message records that already link to an Agent Tool Call.

    This allows the conversation manager to reconstruct OpenAI-compatible
    assistant/tool-call pairs without relying solely on the link lookup.
    """
    messages = frappe.get_all(
        "Agent Message",
        filters={"tool_call": ["is", "set"]},
        fields=["name", "tool_call", "role", "kind", "tool_call_id", "tool_calls"],
    )

    for msg in messages:
        tool_call_doc = frappe.db.get_value(
            "Agent Tool Call",
            msg.tool_call,
            ["call_id", "tool", "tool_args"],
            as_dict=True,
        )
        if not tool_call_doc:
            continue

        updates = {}

        if not msg.tool_call_id and tool_call_doc.call_id:
            updates["tool_call_id"] = tool_call_doc.call_id

        if msg.kind == "Tool Call" and not msg.tool_calls:
            updates["tool_calls"] = json.dumps(
                [
                    {
                        "id": tool_call_doc.call_id or msg.tool_call,
                        "type": "function",
                        "function": {
                            "name": tool_call_doc.tool or "",
                            "arguments": tool_call_doc.tool_args or "{}",
                        },
                    }
                ]
            )

        if updates:
            frappe.db.set_value("Agent Message", msg.name, updates, update_modified=False)

    frappe.db.commit()
