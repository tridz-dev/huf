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

    triggers = frappe.get_all(
        "Agent Trigger",
        filters={
            "trigger_type": "Doc Event",
            "disabled": 0,
            "doc_event": event
        },
        fields=["name", "agent", "reference_doctype", "doc_event", "condition", "prompt_field"],
        ignore_permissions=True
    )

    result = []
    
    original_ignore_permissions = frappe.flags.ignore_permissions
    frappe.flags.ignore_permissions = True
    
    try:
        for t in triggers:
            try:
                trigger_doc = frappe.get_doc("Agent Trigger", t["name"])
                agent_doc = frappe.get_doc("Agent", t["agent"])
                from huf.ai.prompt_resolver import resolve_prompt
                prompt = resolve_prompt(agent_doc)
                
                result.append({
                    "name": t["name"],
                    "agent": t["agent"],
                    "reference_doctype": t.get("reference_doctype"),
                    "doc_event": t.get("doc_event"),
                    "condition": t.get("condition"),
                    "prompt_field": t.get("prompt_field"), 
                    "file_attachments": [
                        {
                            "source_type": a.source_type,
                            "child_table": a.child_table,
                            "field_name": a.field_name
                        } for a in (trigger_doc.get("file_attachments") or [])
                    ],
                    "instructions": prompt,
                    "provider": getattr(agent_doc, "provider", None),
                    "model": getattr(agent_doc, "model", None),
                })
            except Exception as e:
                frappe.logger("huf").error(f"Agent Trigger load failed: {t.get('name')} - {str(e)}")
    finally:
        frappe.flags.ignore_permissions = original_ignore_permissions

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

    # Do not fire agents during site install, migrations, or bulk imports.
    if frappe.flags.in_import or frappe.flags.in_patch or frappe.flags.in_install:
        return

    agents = get_doc_event_agents(method)
    matching = [
        a for a in agents
        if a.get("reference_doctype") == doc.doctype and a.get("doc_event") == method
    ]

    if not matching:
        return

    for agent in matching:
        # Evaluate condition immediately during the event phase
        condition = agent.get("condition")
        if condition:
            try:
                if not safe_eval(condition, get_safe_globals(), {"doc": doc}):
                    continue
            except Exception as e:
                frappe.log_error(f"Condition error in Agent {agent.get('agent')}: {e}")
                continue

        # Create a deferred execution handler to queue the agent AFTER the transaction commits
        def _queue_agent_after_commit(a=agent, d=doc, m=method, u=frappe.session.user):
            # doc.name will now be final and populated
            safe_name = d.name or str(id(d))
            
            # 1. Acquire execution lock using the final assigned name
            lock_key = f"huf:lock:{a['agent']}:{d.doctype}:{safe_name}:{m}"
            cache = frappe.cache()
            if cache.get_value(lock_key):
                return
            cache.set_value(lock_key, now_datetime().isoformat(), expires_in_sec=30)
            
            # 2. Enqueue the background agent worker
            enqueue(
                run_agent_for_doc,
                queue="long",
                job_id=f"run-agent-{a['agent']}-{d.doctype}-{safe_name}-{m}-{uuid4()}",
                doc=d.as_dict(),
                agent_name=a["agent"],
                instructions=a.get("instructions"),
                event_name=m,
                provider=a.get("provider"),
                model=a.get("model"),
                include_doc=False,
                initiating_user=u,
                channel_id="doc_event",
                prompt_field=a.get("prompt_field"),
                file_attachments=a.get("file_attachments")
            )

        # Register to run ONLY if the document successfully commits to the database
        frappe.db.after_commit.add(_queue_agent_after_commit)

def run_agent_for_doc(doc, agent_name, instructions, event_name, provider, model, include_doc=False, initiating_user=None, channel_id=None, prompt_field=None, file_attachments=None):
    """Background worker to run an agent when a Doc Event triggers"""

    # Background jobs may not carry the original session user. Run the agent as the
    # user who triggered the document event so permission checks pass.
    if initiating_user and frappe.session.user != initiating_user:
        try:
            frappe.set_user(initiating_user)
        except Exception:
            pass

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

            # Standard truncation: Truncate individual massive fields to maintain valid JSON
            MAX_FIELD_LENGTH = 10000
            for k, v in list(clean_doc.items()):
                if isinstance(v, str) and len(v) > MAX_FIELD_LENGTH:
                    clean_doc[k] = v[:MAX_FIELD_LENGTH] + f"\n... [Content truncated. Full length: {len(v)} chars. Use get_document tool to retrieve full content if needed.]"
            
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

        # File attachments logic
        files = []
        if file_attachments:
            import mimetypes
            file_urls_to_process = []
            for attachment in file_attachments:
                fetch_from = attachment.get("source_type")
                field_name = attachment.get("field_name")
                table_name = attachment.get("child_table")

                if fetch_from == "DocField":
                    if field_name and doc.get(field_name):
                        file_urls_to_process.append(doc.get(field_name))
                elif fetch_from == "Child Table Field":
                    if table_name and field_name and doc.get(table_name):
                        for row in doc.get(table_name):
                            f_url = row.get(field_name)
                            if f_url:
                                file_urls_to_process.append(f_url)

            # Process found URLs
            for f_url in file_urls_to_process:
                if any(f["file_url"] == f_url for f in files):
                    continue

                filename = f_url.split("/")[-1]
                is_image = 0
                mime_type, _ = mimetypes.guess_type(filename)
                if mime_type and mime_type.startswith("image/"):
                    is_image = 1

                # Resolve File document ID to avoid ambiguous file_name lookups later
                file_id = frappe.db.get_value("File", {"file_url": f_url}, "name")

                files.append({
                    "file_id": file_id,
                    "filename": filename,
                    "file_url": f_url,
                    "is_image": is_image
                })

        # Extract Text from non-image files via OCR to augment context
        extracted_content = []
        if any(not f.get("is_image") for f in files):
            from huf.ai.sdk_tools import handle_ocr_document
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                for file in files:
                    if not file.get("is_image"):
                        ocr_result = loop.run_until_complete(
                            handle_ocr_document(
                                file_id=file.get("file_id"),
                                file_url=file["file_url"],
                                agent_name=agent_name
                            )
                        )
                        if ocr_result and ocr_result.get("success"):
                            extracted_content.append(
                                f"--- File: {file['filename']} (hash: {ocr_result.get('file_hash', 'n/a')}) ---\n"
                                f"{ocr_result.get('text')}\n"
                            )
            except Exception as e:
                frappe.log_error(f"Doc Event OCR Error: {str(e)}", "Agent Hooks OCR")
            finally:
                loop.close()
                
        if extracted_content:
            prompt += f"""
            
            Attached File Content (OCR Extracted):
            The following text was extracted from attached files. Use this as context:
            
            {''.join(extracted_content)}
            """

        run_agent_sync(agent_name, prompt, provider, model, channel_id=channel, external_id=external_id, files=files)

    except Exception:
        frappe.log_error(frappe.get_traceback(), "Hook Triggered Agent Error")
