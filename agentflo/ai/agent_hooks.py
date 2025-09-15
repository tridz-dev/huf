import frappe
from frappe.utils.background_jobs import enqueue
from .agent_integration import run_agent_sync

CACHE_KEY = "agentflo:doc_event_agents"


def get_doc_event_agents(event):
    """Fetch and cache all active Doc Event agents"""
    agents = frappe.cache().hget(CACHE_KEY, "agentflo_doc_event_agents") #ADD EXPIRY
    if agents:
        return frappe.parse_json(agents)

    agents = frappe.get_list(
        "Agent",
        filters={"is_doc_event": 1, "disabled": 0, "doc_event":event},
        fields=["name", "reference_doctype", "doc_event", "instructions","provider","model"],
    )

    frappe.cache().hset(CACHE_KEY, "agentflo_doc_event_agents", frappe.as_json(agents))
    return agents


def clear_doc_event_agents_cache():
    """Clear cache when Agent changes"""
    frappe.cache().hdel(CACHE_KEY, "agentflo_doc_event_agents")


def run_hooked_agents(doc, event):
    """Generic runner for doc-event driven agents"""
    agents = get_doc_event_agents(event)

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
            provider=agent["provider"],
            model=agent["model"],
            include_doc=False
        )


def run_agent_for_doc(doc, agent_name, instructions, event_name, provider,model,include_doc=False):
    """Background worker to run an agent when a Doc Event triggers"""

    #Add logic to inlude/not include full doctype data dict. If not, only name will be passed. 

    try:
        prompt = f"""
        ```
        Doctype Name: { doc.doctype }
        Document Name: {doc.get('name')}
        Task: {instructions or "Perform the required action for this event."}
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
