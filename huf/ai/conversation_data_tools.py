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
                state["items"][i] = updated_item
                found = True
                break
        
        if not found:
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