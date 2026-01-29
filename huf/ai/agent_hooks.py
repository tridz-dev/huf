import frappe
from frappe.utils.background_jobs import enqueue
from .agent_integration import run_agent_sync
from frappe.utils.safe_exec import get_safe_globals, safe_eval
from uuid import uuid4
import io
import requests
from pypdf import PdfReader
from frappe.utils import now_datetime
import json

def extract_text_from_file(file_url):
    """
    Downloads file from file_url and extracts text if it's a PDF or text file.
    Returns: Extracted text or None.
    """
    try:
        content = None
        content_type = ""
        filename = file_url.split("/")[-1]

        if file_url.startswith("/"):
            relative_path = file_url.lstrip("/")
            local_path = frappe.get_site_path(relative_path)
            
            import os
            if os.path.exists(local_path):
                with open(local_path, "rb") as f:
                    content = f.read()
            else:
                if not file_url.startswith("http"):
                    file_url = frappe.utils.get_url(file_url)

        if not content:
            if not file_url.startswith("http"):
                file_url = frappe.utils.get_url(file_url)

            timeout = 10
            response = requests.get(file_url, timeout=timeout)
            response.raise_for_status()
            content = response.content
            content_type = response.headers.get("Content-Type", "")

        
        import mimetypes
        if not content_type or content_type == "application/octet-stream":
            mime_type, _ = mimetypes.guess_type(filename)
            if mime_type:
                content_type = mime_type

        file_content = io.BytesIO(content)

        if "application/pdf" in content_type or filename.lower().endswith(".pdf"):
            try:
                reader = PdfReader(file_content)
                text = ""
                for page in reader.pages:
                    text += page.extract_text() + "\n"
                return text.strip()
            except Exception as e:
                msg = f"PDF extraction failed for {filename}: {str(e)}"
                frappe.log_error(msg[:140], "File Extraction Error")
                return None

        elif "text/" in content_type or filename.lower().endswith((".txt", ".md", ".csv", ".json", ".py", ".js")):
             return content.decode("utf-8", errors="ignore")

    except Exception as e:
        msg = f"Error processing file {filename}: {str(e)}"
        frappe.log_error(msg[:140], "File Extraction Error")
    
    return None

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
        fields=["name", "agent", "reference_doctype", "doc_event", "condition", "prompt_field", "process_standard_attachments"] 
    )

    if frappe.db.exists("DocType", "Agent Trigger Attachment"):
        for t in triggers:
            try:
                t["file_attachments"] = frappe.get_all("Agent Trigger Attachment", filters={"parent": t["name"]}, fields=["source_type", "child_table", "field_name"])
            except Exception:
                t["file_attachments"] = []
    else:
         for t in triggers:
            t["file_attachments"] = []

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
                "file_attachments": t.get("file_attachments"),
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
            prompt_field=agent.get("prompt_field"),
            file_attachments=agent.get("file_attachments")
        )


def run_agent_for_doc(doc, agent_name, instructions, event_name, provider, model, include_doc=False, initiating_user=None, channel_id=None, prompt_field=None,  file_attachments=None):
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

        files = []
        import mimetypes

        if file_attachments:
            for attach_config in file_attachments:
                file_urls_to_process = []
                
                # A. DocField
                if attach_config.get("source_type") == "DocField":
                    field_name = attach_config.get("field_name")
                    f_url = doc.get(field_name)
                    if f_url:
                        file_urls_to_process.append(f_url)
                
                # B. Child Table
                elif attach_config.get("source_type") == "Child Table Field":
                    table_name = attach_config.get("child_table")
                    field_name = attach_config.get("field_name")
                    if table_name and field_name and doc.get(table_name):
                        for row in doc.get(table_name):
                            f_url = row.get(field_name)
                            if f_url:
                                file_urls_to_process.append(f_url)

                # Process found URLs
                for f_url in file_urls_to_process:
                     # Check duplication
                    if any(f["file_url"] == f_url for f in files):
                        continue
                    
                    # Deduce filename/is_image
                    filename = f_url.split("/")[-1]
                    is_image = 0
                    mime_type, _ = mimetypes.guess_type(filename)
                    if mime_type and mime_type.startswith("image/"):
                        is_image = 1
                    
                    files.append({
                        "filename": filename,
                        "file_url": f_url,
                        "is_image": is_image
                    })



        # 3. Extract Text from Files to augment context
        extracted_content = []
        for file in files:
            # Skip images here as they are handled by vision models via file_url
            if not file.get("is_image"):
                text = extract_text_from_file(file["file_url"])
                if text:
                    extracted_content.append(f"--- File: {file['filename']} ---\n{text}\n")
        
        if extracted_content:
            prompt += f"""
            
            Attached File Content:
            The following text was extracted from attached files (PDF/Text). Use this as context:
            
            {''.join(extracted_content)}
            """

        run_agent_sync(agent_name, prompt, provider, model, channel_id=channel, external_id=external_id, files=files)

    except Exception:
        frappe.log_error(frappe.get_traceback(), "Hook Triggered Agent Error")
