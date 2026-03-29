"""
HUF Flow Engine - Doc Event Hooks

Dynamic hook registration system for triggering flows based on document events.
This module maintains an in-memory registry of flows that should be triggered
when specific doc events occur (after_insert, on_update, on_delete, etc.).

The registry is populated at startup from Flow Definition documents that have
trigger.doc-event as their entry node type.
"""

import json
import frappe
from typing import Dict, List, Optional

# In-memory registry: key = "Doctype:event", value = list of flow configs
_doc_event_registry: Dict[str, List[dict]] = {}

# Track if registry has been bootstrapped
_registry_bootstrapped = False


def bootstrap_doc_event_registry():
    """
    Load all active doc-event flows from database into memory.
    Called at module initialization and after any flow definition changes.
    """
    global _doc_event_registry, _registry_bootstrapped
    
    _doc_event_registry = {}
    
    try:
        # Get all active flow definitions
        active_flows = frappe.get_all(
            "Flow Definition",
            filters={"status": "Active"},
            fields=["flow_id", "definition_json"]
        )
        
        for flow in active_flows:
            try:
                definition = json.loads(flow.definition_json) if isinstance(flow.definition_json, str) else flow.definition_json
                entry_node = next(
                    (n for n in definition.get("nodes", []) if n["id"] == definition.get("entry")),
                    None
                )
                
                if entry_node and entry_node.get("type") == "trigger.doc-event":
                    config = entry_node.get("config", {})
                    doctype = config.get("doctype")
                    event = config.get("event")
                    
                    if doctype and event:
                        key = f"{doctype}:{event}"
                        if key not in _doc_event_registry:
                            _doc_event_registry[key] = []
                        _doc_event_registry[key].append({
                            "flow_id": flow.flow_id,
                            "config": config
                        })
                        
            except (json.JSONDecodeError, TypeError, KeyError) as e:
                frappe.log_error(
                    f"Failed to parse flow definition for doc event registry: {flow.flow_id}",
                    "Flow Hooks Bootstrap"
                )
                continue
                
        _registry_bootstrapped = True
        
    except Exception as e:
        frappe.log_error(f"Failed to bootstrap doc event registry: {str(e)}", "Flow Hooks")


def register_doc_event_flow(flow_id: str, doctype: str, event: str, config: Optional[dict] = None):
    """
    Register a flow to be triggered by doc events.
    
    Args:
        flow_id: The unique flow identifier
        doctype: DocType to listen on (e.g., "Sales Invoice")
        event: Event to listen for (e.g., "after_insert", "on_update")
        config: Optional additional configuration from the node
    """
    global _doc_event_registry
    
    if not _registry_bootstrapped:
        bootstrap_doc_event_registry()
        return
    
    key = f"{doctype}:{event}"
    if key not in _doc_event_registry:
        _doc_event_registry[key] = []
    
    # Remove existing entry for this flow if present
    _doc_event_registry[key] = [
        f for f in _doc_event_registry[key] 
        if f["flow_id"] != flow_id
    ]
    
    # Add new entry
    _doc_event_registry[key].append({
        "flow_id": flow_id,
        "config": config or {}
    })


def unregister_doc_event_flow(flow_id: str, doctype: Optional[str] = None, event: Optional[str] = None):
    """
    Unregister a flow from doc events.
    
    Args:
        flow_id: The flow to unregister
        doctype: Optional - specific doctype to unregister from
        event: Optional - specific event to unregister from
    """
    global _doc_event_registry
    
    if not _registry_bootstrapped:
        return
    
    if doctype and event:
        # Unregister from specific key
        key = f"{doctype}:{event}"
        if key in _doc_event_registry:
            _doc_event_registry[key] = [
                f for f in _doc_event_registry[key] 
                if f["flow_id"] != flow_id
            ]
            if not _doc_event_registry[key]:
                del _doc_event_registry[key]
    else:
        # Unregister from all keys
        for key in list(_doc_event_registry.keys()):
            _doc_event_registry[key] = [
                f for f in _doc_event_registry[key] 
                if f["flow_id"] != flow_id
            ]
            if not _doc_event_registry[key]:
                del _doc_event_registry[key]


def get_registered_flows(doctype: str, event: str) -> List[dict]:
    """
    Get all flows registered for a specific doctype and event.
    
    Args:
        doctype: The DocType
        event: The event name
        
    Returns:
        List of flow configurations
    """
    if not _registry_bootstrapped:
        bootstrap_doc_event_registry()
    
    key = f"{doctype}:{event}"
    return _doc_event_registry.get(key, [])


def run_doc_event_flows(doc, event: str, method: Optional[str] = None):
    """
    Called by Frappe hooks when doc events occur.
    Triggers all registered flows for this doctype and event.
    
    Args:
        doc: The document that triggered the event
        event: The event name (e.g., "after_insert", "on_update")
        method: The hook method name (optional)
    """
    if not doc or not doc.doctype:
        return
    
    flows = get_registered_flows(doc.doctype, event)
    
    if not flows:
        return
    
    for flow_config in flows:
        try:
            from huf.ai.flow_engine import create_flow_run, run_flow
            
            flow_id = flow_config["flow_id"]
            node_config = flow_config.get("config", {})
            
            # Prepare payload with doc context
            payload = {
                "doctype": doc.doctype,
                "docname": doc.name,
                "event": event,
                "doc": doc.as_dict(),
                "trigger": {
                    "type": "doc_event",
                    "doctype": doc.doctype,
                    "docname": doc.name,
                    "event": event,
                }
            }
            
            # Add any filters from node config
            if node_config.get("filters"):
                payload["filters"] = node_config.get("filters")
            
            # Create flow run
            flow_run = create_flow_run(
                flow_id=flow_id,
                payload=payload,
                trigger_type="Doc Event"
            )
            
            # Run in background to avoid blocking the doc event
            frappe.enqueue(
                "huf.ai.flow_engine.run_flow",
                queue="default",
                flow_run_name=flow_run.name,
                enqueue_after_commit=True
            )
            
        except Exception as e:
            frappe.log_error(
                f"Failed to trigger flow {flow_config.get('flow_id')} on {doc.doctype}:{event}: {str(e)}",
                "Doc Event Flow Trigger"
            )


# ---------------------------------------------------------------------------
# Hook handlers that Frappe will call
# ---------------------------------------------------------------------------

def on_doc_insert(doc, method=None):
    """Handle after_insert doc events."""
    run_doc_event_flows(doc, "after_insert", method)


def on_doc_update(doc, method=None):
    """Handle on_update doc events."""
    run_doc_event_flows(doc, "on_update", method)


def on_doc_delete(doc, method=None):
    """Handle on_delete doc events."""
    run_doc_event_flows(doc, "on_delete", method)


def on_doc_submit(doc, method=None):
    """Handle on_submit doc events."""
    run_doc_event_flows(doc, "on_submit", method)


def on_doc_cancel(doc, method=None):
    """Handle on_cancel doc events."""
    run_doc_event_flows(doc, "on_cancel", method)


# ---------------------------------------------------------------------------
# Registry management API
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_doc_event_registry() -> dict:
    """
    Get current state of the doc event registry.
    For debugging/admin purposes.
    """
    if not frappe.has_permission("Flow Definition", "read"):
        frappe.throw(_("Not permitted"), frappe.PermissionError)
    
    if not _registry_bootstrapped:
        bootstrap_doc_event_registry()
    
    return {
        "bootstrapped": _registry_bootstrapped,
        "registered_events": list(_doc_event_registry.keys()),
        "flow_count": sum(len(flows) for flows in _doc_event_registry.values()),
        "details": _doc_event_registry
    }


@frappe.whitelist()
def refresh_doc_event_registry():
    """
    Force refresh the doc event registry from database.
    """
    if not frappe.has_permission("Flow Definition", "write"):
        frappe.throw(_("Not permitted"), frappe.PermissionError)
    
    bootstrap_doc_event_registry()
    return {"status": "success", "message": "Registry refreshed"}


# Bootstrap on module load
bootstrap_doc_event_registry()
