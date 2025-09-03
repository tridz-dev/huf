import frappe
from frappe.utils.background_jobs import enqueue
from .agent_integration import run_agent_sync

CACHE_KEY = "agentflo:doc_event_agents"


def get_doc_event_agents():
    """Fetch and cache all active Doc Event agents"""
    agents = frappe.cache().hget(CACHE_KEY, "all")
    if agents:
        return frappe.parse_json(agents)

    agents = frappe.get_all(
        "Agent",
        filters={"is_doc_event": 1, "disabled": 0},
        fields=["name", "reference_doctype", "doc_event", "instructions"],
    )

    frappe.cache().hset(CACHE_KEY, "all", frappe.as_json(agents))
    return agents


def clear_doc_event_agents_cache():
    """Clear cache when Agent changes"""
    frappe.cache().hdel(CACHE_KEY, "all")


def run_hooked_agents(doc, event):
    """Generic runner for doc-event driven agents"""
    
    agents = get_doc_event_agents()

    matching = [
        a for a in agents
        if a["reference_doctype"] == doc.doctype and a["doc_event"] == event
    ]

    if not matching:
        return

    
    for agent in matching:
        enqueue(
            run_agent_for_doc,
            queue="long",
            job_id=f"Run Agent {agent['name']} for {doc.doctype} {doc.name} on {event}",
            doc=doc.as_dict(),
            agent_name=agent["name"],
            instructions=agent["instructions"],
            event_name=event,
        )


def run_agent_for_doc(doc, agent_name, instructions, event_name):
    """Background worker to run an agent when a Doc Event triggers"""
    try:
        prompt = f"""
        Document Name: {doc.get('name')}
        Task: {instructions or "Perform the required action for this event."}
        """

        run_agent_sync(agent_name, prompt)

    except Exception:
        frappe.log_error(frappe.get_traceback(), "Hook Triggered Agent Error")
