import frappe
import json
from datetime import datetime, timezone
from typing import Any

# Helper Functions
def _now_iso_utc() -> str:
    return datetime.now(timezone.utc).isoformat()

def _load_state(state_json: str | None | dict) -> dict:
    if not state_json:
        return {"version": 1, "scope": {}, "items": []}
    if isinstance(state_json, dict):
        data = state_json
    else:
        try:
            data = json.loads(state_json)
            if isinstance(data, str): # Handle double encoded
                try: data = json.loads(data)
                except: pass
        except (json.JSONDecodeError, TypeError):
             return {"version": 1, "scope": {}, "items": []}
             
    if "items" not in data or not isinstance(data["items"], list):
        data["items"] = []
    if "version" not in data:
        data["version"] = 1
    return data

# Handler Functions
def handle_get_conversation_data(name: str, default: Any = None, conversation_id: str = None, **kwargs):
    """Get a value from conversation data."""
    if not conversation_id:
        return {"success": False, "error": "No conversation context provided"}
    
    try:
        data_json = frappe.db.get_value("Agent Conversation", conversation_id, "conversation_data")
        state = _load_state(data_json)
        
        value = default
        for item in state["items"]:
            if item.get("name") == name:
                value = item.get("value", default)
                break
                
        return {"success": True, "value": value}
    except Exception as e:
        frappe.log_error(f"Error getting conversation data: {str(e)}", "Conversation Data")
        return {"success": False, "error": str(e)}

def handle_set_conversation_data(
    name: str, 
    value: Any, 
    value_type: str = None, 
    source: str = "agent", 
    conversation_id: str = None, 
    auto_inject: bool = None,
    inject_mode: str = None,
    **kwargs
):
    """Set a value in conversation data."""
    if not conversation_id:
        return {"success": False, "error": "No conversation context provided"}
    
    try:
        # Debug Log
        frappe.logger().info(f"[Conversation Data] Setting {name} for {conversation_id}")

        # Load fresh state
        data_json = frappe.db.get_value("Agent Conversation", conversation_id, "conversation_data")
        state = _load_state(data_json)

        # infer a simple type label if not provided
        if value_type is None:
            if isinstance(value, dict):
                value_type = "object"
            elif isinstance(value, list):
                value_type = "array"
            else:
                value_type = "scalar"

        updated_item = {
            "name": name,
            "value": value,
            "meta": {
                "type": value_type,
                "updated_at": _now_iso_utc(),
                "source": source
            }
        }

        # Update or Append
        found = False
        for i, item in enumerate(state["items"]):
            if item.get("name") == name:
                resolved_auto_inject = auto_inject if auto_inject is not None else kwargs.get("auto_inject")
                if resolved_auto_inject is None:
                    resolved_auto_inject = item.get("auto_inject", True)
                
                resolved_inject_mode = inject_mode if inject_mode is not None else kwargs.get("inject_mode")
                if resolved_inject_mode is None:
                    resolved_inject_mode = item.get("inject_mode", "visible")
                
                updated_item["auto_inject"] = resolved_auto_inject
                updated_item["inject_mode"] = resolved_inject_mode
                state["items"][i] = updated_item
                found = True
                break
        
        if not found:
            resolved_auto_inject = auto_inject if auto_inject is not None else kwargs.get("auto_inject")
            if resolved_auto_inject is None:
                resolved_auto_inject = True
            
            resolved_inject_mode = inject_mode if inject_mode is not None else kwargs.get("inject_mode")
            if resolved_inject_mode is None:
                resolved_inject_mode = "visible"
                
            updated_item["auto_inject"] = resolved_auto_inject
            updated_item["inject_mode"] = resolved_inject_mode
            state["items"].append(updated_item)

        new_json = json.dumps(state, ensure_ascii=False, indent=2)
        
        frappe.db.set_value("Agent Conversation", conversation_id, "conversation_data", new_json)
        frappe.db.commit() # Persist changes immediately
        
        return {"success": True, "message": f"Set '{name}' match successfully"}
    
    except Exception as e:
        frappe.log_error(f"Error setting conversation data: {str(e)}", "Conversation Data")
        return {"success": False, "error": str(e)}

def handle_load_conversation_data(conversation_id: str = None, **kwargs):
    """Load the full conversation data."""
    if not conversation_id:
        return {"success": False, "error": "No conversation context provided"}
    try:
        data_json = frappe.db.get_value("Agent Conversation", conversation_id, "conversation_data")
        state = _load_state(data_json)
        return {"success": True, "data": state}
    except Exception as e:
        return {"success": False, "error": str(e)}

@frappe.whitelist()
def api_get_conversation_data(conversation_id: str, name: str = None):
    """API endpoint to read conversation data."""
    if not frappe.has_permission("Agent Conversation", "read", conversation_id):
        frappe.throw("Not permitted to read Agent Conversation", frappe.PermissionError)
    
    agent = frappe.db.get_value("Agent Conversation", conversation_id, "agent")
    if not agent:
        return {"success": False, "error": "Agent Conversation not found"}
        
    api_permission = frappe.db.get_value("Agent", agent, "conversation_data_api_permission")
    if api_permission not in ("Read", "Write"):
        frappe.throw("Agent does not allow reading conversation data via API", frappe.PermissionError)
        
    if name:
        return handle_get_conversation_data(name=name, conversation_id=conversation_id)
    else:
        return handle_load_conversation_data(conversation_id=conversation_id)

@frappe.whitelist()
def api_set_conversation_data(conversation_id: str, name: str, value: Any, value_type: str = None, auto_inject: bool = None, inject_mode: str = None):
    """API endpoint to write conversation data."""
    if not frappe.has_permission("Agent Conversation", "write", conversation_id):
        frappe.throw("Not permitted to write to Agent Conversation", frappe.PermissionError)
        
    agent = frappe.db.get_value("Agent Conversation", conversation_id, "agent")
    if not agent:
        return {"success": False, "error": "Agent Conversation not found"}
        
    api_permission = frappe.db.get_value("Agent", agent, "conversation_data_api_permission")
    if api_permission != "Write":
        frappe.throw("Agent does not allow writing conversation data via API", frappe.PermissionError)
        
    if isinstance(auto_inject, str):
        auto_inject = frappe.utils.cint(auto_inject) == 1 or auto_inject.lower() in ("true", "yes", "1")
        
    return handle_set_conversation_data(
        name=name, 
        value=value, 
        value_type=value_type, 
        source="api", 
        conversation_id=conversation_id, 
        auto_inject=auto_inject, 
        inject_mode=inject_mode
    )