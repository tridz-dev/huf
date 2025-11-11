import frappe
from frappe.utils.background_jobs import enqueue
from .agent_integration import run_agent_sync
from frappe.utils.safe_exec import get_safe_globals,safe_eval
from uuid import uuid4
from frappe.utils import now_datetime

CACHE_KEY = "agentflo:doc_event_agents"


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
        fields=["name", "agent", "reference_doctype", "doc_event", "condition"]
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
        lock_key = f"agentflo:lock:{agent['agent']}:{doc.doctype}:{doc.name}:{method}"
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
            include_doc=False
        )


def run_agent_for_doc(doc, agent_name, instructions, event_name, provider,model,include_doc=False):
    """Background worker to run an agent when a Doc Event triggers"""

    #Add logic to inlude/not include full doctype data dict. If not, only name will be passed. 

    try:
        prompt = f"""
            You are an automation agent triggered by a Frappe document event.

            Event: {event_name}

            Use the available tools with these exact identifiers:
            reference_doctype = "{doc.get('doctype')}"
            reference_name   = "{doc.get('name')}"

            Instructions:
            {instructions or "Perform the required action for this event."}
        """
        # if include_doc:
        #     doc_data = doc.as_dict()
        #     json_string = json.dumps(doc_data, indent=2, default=str)
        #     prompt += f"""
            
        # Document Data (JSON):
        # ```json
        #     {json_string}
        # ```
        # """

        run_agent_sync(agent_name, prompt,provider,model)

    except Exception:
        frappe.log_error(frappe.get_traceback(), "Hook Triggered Agent Error")
