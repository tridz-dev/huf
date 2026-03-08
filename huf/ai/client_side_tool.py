import frappe

@frappe.whitelist()
def client_side_function(conversation_id=None, agent_run_id=None, function_name=None, message_id=None, **kwargs):
    frappe.publish_realtime(
        event=f'conversation:{conversation_id}',
        message={
            "type": "frontend_tool_call_initiated",
            "conversation_id": conversation_id,
            "agent_run_id": agent_run_id,
            "message_id": message_id,
            "function_name": function_name,
            "tool_params": kwargs      
        },
    )
    return {"message": "Tool execution requested on frontend"}
