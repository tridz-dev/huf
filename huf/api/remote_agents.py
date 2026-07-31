import frappe
from frappe import _

@frappe.whitelist(allow_guest=False)
def list_agents():
    # Only return agents that are enabled for remote delegation
    # Placeholder implementation
    agents = frappe.get_all("Agent", filters={"disabled": 0}, fields=["name", "agent_name", "description"])
    return {
        "server_name": frappe.local.site,
        "protocol_versions": ["huf-native-v1"],
        "agents": agents
    }

@frappe.whitelist(allow_guest=False)
def get_agent_manifest(agent_name):
    agent = frappe.get_doc("Agent", agent_name)
    return {
        "id": agent.name,
        "name": agent.agent_name,
        "description": agent.description,
        "input_modes": ["text/markdown", "application/json"],
        "output_modes": ["text/markdown", "application/json"],
        "capabilities": ["chat"],
        "stateful": True,
        "long_running": True,
        "streaming": True
    }

@frappe.whitelist(allow_guest=False)
def create_run(agent_id, prompt, session_id=None, parameters=None):
    # Map to local Agent Run
    return {
        "status": "success",
        "data": {
            "run_id": "dummy_run_123",
            "status": "running",
            "started_at": frappe.utils.now()
        }
    }

@frappe.whitelist(allow_guest=False)
def get_run(run_id):
    return {
        "status": "success",
        "data": {
            "run_id": run_id,
            "status": "completed"
        }
    }

@frappe.whitelist(allow_guest=False)
def get_run_events(run_id, cursor=None):
    return {
        "events": [],
        "next_cursor": None
    }

@frappe.whitelist(allow_guest=False)
def cancel_run(run_id):
    return {"status": "cancelled"}
