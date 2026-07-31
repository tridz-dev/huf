import frappe
from huf.ai.remote_agents.adapter import get_adapter

def execute_remote_tool(agent_run, tool_call, parameters):
    """
    Executes a remote agent tool.
    Creates a Delegated Agent Run and delegates to the remote adapter.
    """
    connection_name = parameters.get("connection_name")
    remote_agent_id = parameters.get("remote_agent_id")
    prompt = parameters.get("prompt")
    
    if not connection_name or not remote_agent_id:
        return {"status": "failed", "error": "Missing connection_name or remote_agent_id"}
        
    connection = frappe.get_doc("Remote Agent Connection", connection_name)
    
    if not connection.enabled:
        return {"status": "failed", "error": "Remote Agent Connection is disabled"}
        
    # Check basic permissions (placeholder)
    if not frappe.has_permission("Remote Agent Connection", "read", doc=connection):
        return {"status": "failed", "error": "Permission denied for remote connection"}
        
    # Create local Delegated Agent Run
    delegated_run = frappe.get_doc({
        "doctype": "Delegated Agent Run",
        "local_agent_run": agent_run.name,
        "connection": connection.name,
        "remote_agent_id": remote_agent_id,
        "status": "queued",
        "request_json": frappe.as_json({"prompt": prompt})
    })
    delegated_run.insert(ignore_permissions=True)
    
    try:
        adapter = get_adapter(connection.protocol_type, connection=connection)
        
        # Initiate remote run
        delegated_run.db_set("status", "running")
        remote_response = adapter.create_run(remote_agent_id, {"prompt": prompt})
        
        # In a real implementation we would stream/poll, for v1 we just get result
        delegated_run.db_set("remote_run_id", remote_response.get("run_id"))
        delegated_run.db_set("status", "completed")
        delegated_run.db_set("response_json", frappe.as_json(remote_response))
        
        return {
            "status": "completed",
            "remote_run_id": remote_response.get("run_id"),
            "content": remote_response.get("content", "Remote execution completed successfully."),
            "events_summary": []
        }
        
    except Exception as e:
        delegated_run.db_set("status", "failed")
        delegated_run.db_set("error", str(e))
        return {"status": "failed", "error": str(e)}
