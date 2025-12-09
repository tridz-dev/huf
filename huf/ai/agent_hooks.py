import frappe
from frappe.utils.background_jobs import enqueue
from .agent_integration import run_agent_sync
from frappe.utils.safe_exec import get_safe_globals, safe_eval
from uuid import uuid4
from frappe.utils import now_datetime
import json

CACHE_KEY = "huf:doc_event_agents"


def get_doc_event_agents(event: str):
    """Fetch & cache Doc Event triggers (Agent Trigger doctype)."""
    if not frappe.db.exists("DocType", "Agent Trigger"):
        return []

    cached = frappe.cache().hget(CACHE_KEY, f"doc_event:{event}")
    if cached:
        return frappe.parse_json(cached)

    triggers = frappe.get_list(
        "Agent Trigger",
        filters={
            "trigger_type": "Doc Event",
            "disabled": 0,
            "doc_event": event
        },
        fields=["name", "agent", "reference_doctype", "doc_event", "condition", "prompt_field"] 
    )

    result = []
    for t in triggers:
        try:
            agent_doc = frappe.get_doc("Agent", t["agent"])
            result.append({
                "name": t["name"],
                "agent": t["agent"],
                "reference_doctype": t.get("reference_doctype"),
                "doc_event": t.get("doc_event"),
                "condition": t.get("condition"),
                "prompt_field": t.get("prompt_field"), 
                "instructions": getattr(agent_doc, "instructions", None),
                "provider": getattr(agent_doc, "provider", None),
                "model": getattr(agent_doc, "model", None),
            })
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"Agent Trigger load failed: {t.get('name')}")

    frappe.cache().hset(CACHE_KEY, f"doc_event:{event}", frappe.as_json(result))
    return result


def clear_doc_event_agents_cache(doc=None, method=None):
    """Clear cache when Agent changes."""
    try:
        frappe.cache().delete_key(CACHE_KEY)
    except Exception:
        pass


def run_hooked_agents(doc, method=None, *args, **kwargs):
    if not method:
        return

    agents = get_doc_event_agents(method)
    matching = [
        a for a in agents
        if a.get("reference_doctype") == doc.doctype and a.get("doc_event") == method
    ]

    if not matching:
        return


    cache = frappe.cache()
    for agent in matching:
        lock_key = f"huf:lock:{agent['agent']}:{doc.doctype}:{doc.name}:{method}"
        if cache.get_value(lock_key):
            continue
        cache.set_value(lock_key, now_datetime().isoformat(), expires_in_sec=30)

        condition = agent.get("condition")
        if condition:
            try:
                if not safe_eval(condition, get_safe_globals(), {"doc": doc}):
                    continue
            except Exception as e:
                frappe.log_error(f"Condition error in Agent {agent.get('agent')}: {e}")
                continue
        enqueue(
            run_agent_for_doc,
            queue="long",
            job_id=f"run-agent-{agent['agent']}-{doc.doctype}-{doc.name}-{method}-{uuid4()}",
            doc=doc.as_dict(),
            agent_name=agent["agent"],
            instructions=agent.get("instructions"),
            event_name=method,
            provider=agent.get("provider"),
            model=agent.get("model"),
            include_doc=False,
            initiating_user=frappe.session.user,
            channel_id="doc_event",
            prompt_field=agent.get("prompt_field") 
        )


def run_agent_for_doc(doc, agent_name, instructions, event_name, provider, model, include_doc=False, initiating_user=None, channel_id=None, prompt_field=None):
    """Background worker to run an agent when a Doc Event triggers"""

    custom_instruction = None
    if prompt_field:
        custom_instruction = doc.get(prompt_field)

    try:
        prompt = f"""
            You are an automation agent triggered by a Frappe document event.

            Event: {event_name}

            Use the available tools with these exact identifiers:
            reference_doctype = "{doc.get('doctype')}"
            reference_name   = "{doc.get('name')}"
        """

        # Logic: If the mapped field has text, use it as the PRIMARY instruction.
        if custom_instruction:
            prompt += f"""
            
            USER REQUEST:
            The user has provided the following specific request for this document:
            "{custom_instruction}"
            
            Please prioritize this request over your general instructions.
            """
        else:
            prompt += f"""
            
            Instructions:
            {instructions or "Perform the required action for this event."}
        """

        try:
            clean_doc = doc.copy() if isinstance(doc, dict) else doc.as_dict()
            for key in ["_user_tags", "_comments", "_assign", "_liked_by", "docstatus", "password"]:
                clean_doc.pop(key, None)
            
            json_string = json.dumps(clean_doc, indent=2, default=str)
            prompt += f"""
            
            Document Data (Context):
            ```json
            {json_string}
            ```
            """
        except Exception:
            pass

        external_id = None
        channel = channel_id or "doc_event"

        try:
            agent_doc = frappe.get_doc("Agent", agent_name)
            if getattr(agent_doc, "persist_user_history", False):
                external_id = initiating_user or doc.get("owner") or doc.get("modified_by") or "unknown_user"
            else:
                external_id = f"shared:{agent_name}"
        except Exception:
            external_id = initiating_user or f"shared:{agent_name}"

        run_agent_sync(agent_name, prompt, provider, model, channel_id=channel, external_id=external_id)

    except Exception:
        frappe.log_error(frappe.get_traceback(), "Hook Triggered Agent Error")
