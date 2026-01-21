import asyncio
import json
from types import SimpleNamespace

import frappe
from agents import OpenAIProvider,Agent, Runner, Tool, function_tool,ModelSettings
from frappe.utils.background_jobs import enqueue
from frappe.utils import now_datetime

from frappe import _
from .tool_functions import (
	create_document,
    get_document,
	get_list,
	update_document,
    submit_document,
    cancel_document,
	delete_document,
)
from .conversation_manager import ConversationManager
from .run import RunProvider


class AgentManager:
    """Manages the creation and execution of agents."""
    def __init__(self, agent_name, file_handler=None):
        self.agent_doc = frappe.get_doc("Agent", agent_name)
        self.settings = frappe.get_doc("AI Provider", self.agent_doc.provider)
        # self.file_handler = file_handler
        self.tools = []
        self._setup_client()
        self._setup_tools()

    
    def _setup_tools(self):
        """Create SDK Tools from existing functions"""
        self.tools=[]

        try:
            from huf.ai.sdk_tools import create_agent_tools  
            agent_tools = create_agent_tools(self.agent_doc)
            if agent_tools:
                self.tools.extend(agent_tools)
        except Exception as e:
            frappe.log_error(
                f"Error loading Agent Tool Function: {str(e)}",
                "Agent Tool Function Error",
            )
        
        # Add knowledge_search tool and get_knowledge_sources tool if agent has knowledge
        try:
            from huf.ai.knowledge.tool import (
                create_knowledge_search_tool, 
                handle_knowledge_search,
                create_get_knowledge_sources_tool,
                handle_get_knowledge_sources
            )
            from agents import function_tool
            
            # 1. Knowledge Search Tool
            knowledge_tool_def = create_knowledge_search_tool(self.agent_doc.agent_name)
            if knowledge_tool_def:
                @function_tool
                def knowledge_search_tool(query: str, knowledge_source: str = None, top_k: int = 5) -> str:
                    """Search the agent's knowledge base for relevant information."""
                    return handle_knowledge_search(
                        agent_name=self.agent_doc.agent_name,
                        query=query,
                        knowledge_source=knowledge_source,
                        top_k=top_k,
                    )
                self.tools.append(knowledge_search_tool)

            # 2. Get Knowledge Sources Tool
            sources_tool_def = create_get_knowledge_sources_tool(self.agent_doc.agent_name)
            if sources_tool_def:
                @function_tool
                def get_knowledge_sources_tool() -> str:
                    """List all knowledge sources available to this agent."""
                    return handle_get_knowledge_sources(agent_name=self.agent_doc.agent_name)
                self.tools.append(get_knowledge_sources_tool)

        except Exception as e:
            frappe.log_error(
                f"Error loading knowledge tools: {str(e)}",
                "Knowledge Tool Error",
            )

    def _setup_client(self):
        """Configure OpenAI provider from the AI Provider doc"""
        api_key = self.settings.get_password("api_key")
        if not api_key:
            frappe.throw(_("API key is not configured in AI Provider."))

        self.provider = OpenAIProvider(api_key=api_key, use_responses=True)

        self.client = self.provider


    def create_tools(self) -> list[Tool]:
        
        tools = []

        # Tool for get_document
        @function_tool
        def get_document_tool(doctype: str, document_id: str) -> dict:
            """Get a single document with permissions check

            Args:
                doctype: The DocType name
                document_id: The document ID
            """
            return get_document(doctype, document_id)

        # Tool for create_document
        @function_tool
        def create_document_tool(doctype: str, data: dict) -> dict:
            """Create a new document in the database

            Args:
                doctype: The DocType name
                data: Document data as dictionary
            """
            tool = self._get_agent_tool(doctype)
            return create_document(doctype, data, tool)

        # Tool for update_document
        @function_tool
        def update_document_tool(document_id: str, data: dict, doctype: str) -> dict:
            """Update a document in the database

            Args:
                doctype: The DocType name
                document_id: The document ID
                data: Fields to update
            """
            tool = self._get_agent_tool(doctype)
            return update_document(doctype, document_id, data, tool)

        @function_tool
        def delete_document_tool(doctype: str, document_id: str) -> dict:
            """Delete a document from the database

            Args:
                doctype: The DocType name
                document_id: The document ID
            """
            return delete_document(doctype, document_id)

        # Tool for get_list
        @function_tool
        def search_documents(
            doctype: str, filters: dict | None = None, fields: list[str] | None = None, limit: int = 20
        ) -> list[dict]:
            """Search documents in the database

            Args:
                doctype: The DocType name
                filters: Optional filters dictionary
                fields: Optional list of fields to return
                limit: Maximum number of results
            """
            return get_list(doctype, filters, fields, limit)

        # Tool for submit_document
        @function_tool
        def submit_document_tool(doctype: str, document_id: str) -> dict:
            """Submit a document (for submittable DocTypes)

            Args:
                doctype: The DocType name
                document_id: The document ID
            """
            return submit_document(doctype, document_id)

        # Tool for cancel_document
        @function_tool
        def cancel_document_tool(doctype: str, document_id: str) -> dict:
            """Cancel a submitted document

            Args:
                doctype: The DocType name
                document_id: The document ID
            """
            return cancel_document(doctype, document_id)

        tools.extend(
            [
                get_document_tool,
                create_document_tool,
                update_document_tool,
                delete_document_tool,
                search_documents,
                submit_document_tool,
                cancel_document_tool
            ]
        )

        return tools or []

    
    def _get_agent_tool(self, doctype: str):
        for tool in self.agent_doc.agent_tool:
            tool_doc = frappe.get_doc("Agent Tool Function", tool.tool)
            if tool_doc.reference_doctype == doctype:
                return tool_doc
        return None


    def create_agent(self) -> Agent:
        """Create main agent """

        if not self.agent_doc.model:
            frappe.throw(_("Agent model is not configured"))

        instructions = self.agent_doc.instructions

        # Enhance instructions with tool descriptions
        if self.tools:
            tool_descriptions = []
            for tool in self.tools:
                if hasattr(tool, "description"):
                    tool_descriptions.append(f"- {tool.name}: {tool.description}")
                else:
                    tool_descriptions.append(f"- {tool.name}: {type(tool).__name__}")

            tools_instruction = f"""

    You have access to the following tools/functions that you can use to help answer questions:

    {chr(10).join(tool_descriptions)}

    IMPORTANT: When calling tools, the SDK will handle execution automatically.
    """
            instructions += tools_instruction

        if self.agent_doc.enable_conversation_data:
             instructions += """
    
                SYSTEM INSTRUCTION - MEMORY MANAGEMENT:
                You are equipped with a persistent memory system ('Conversation Data'). 
                1. AUTOMATIC SAVING: Whenever the user provides important information, YOU MUST immediately use the 'set_conversation_data' tool.
                2. DYNAMIC KEYS: You determine the key names (snake_case). E.g., 'student_profile', 'project_requirements'.
                3. DATA STRUCTURE: 
                - If the user gives a simple value (e.g. name), save as a string.
                - If the user gives a list  save as an ARRAY.
                - If the user gives grouped info or a complex entity, save as an OBJECT.
                    Example: set_conversation_data(name="course_preferences", value={"primary": "CS", "alternatives": ["Math", "Physics"]})
                4. MEMORY CHECK: Check 'load_conversation_data' before asking redundant questions.
            """

        model_settings = ModelSettings(
            temperature=self.agent_doc.temperature,
            top_p=self.agent_doc.top_p
        )

        model = self.provider.get_model(self.agent_doc.model)

        agent = Agent(
            name=self.agent_doc.agent_name,
            instructions=instructions,
            model=model,
            tools=self.tools or [],
            model_settings=model_settings,
        )
        
        # Set max_turns from agent configuration
        agent.max_turns = self.agent_doc.max_turns or 20

        if not hasattr(agent, "tools") or agent.tools is None:
            agent.tools = []

        return agent

def safe_commit():
    if not hasattr(frappe.local, "_realtime_log"):
        frappe.local._realtime_log = []
    frappe.db.commit()

def process_tool_call(agent_run, conversation, name=None, args=None, result=None, error=None, is_output=False):
    """Process tool call - handle requests (insert) and outputs (update) separately"""
    try:
        if is_output:
            existing_queued = frappe.get_all(
                "Agent Tool Call",
                filters={
                    "agent_run": agent_run,
                    "status": "Queued"
                },
                pluck="name",
                limit=1,
                order_by="creation asc"
            )

            if existing_queued:
                doc_id = existing_queued[0]
                doc = frappe.get_doc("Agent Tool Call", doc_id)
                
                update_data = {}

                if result is not None:
                    update_data["tool_result"] = json.dumps(result)
                
                if error:
                    update_data["status"] = "Failed"
                    update_data["error_message"] = error
                else:
                    update_data["status"] = "Completed"
                
                doc.update(update_data)
                doc.save()
                return doc.name 
            else:
                frappe.log_error(f"Received tool output for run {agent_run} but no Queued tool call found.", "Agent Tool Call Warning")
                return None

        else:
            is_mcp_tool = 0
            mcp_server = None

            if name:
                mcp_tool_entry = frappe.db.get_value("MCP Server Tool", {"tool_name": name, "enabled": 1}, "parent")
                if mcp_tool_entry:
                    is_mcp_tool = 1
                    mcp_server = mcp_tool_entry

            doc = frappe.get_doc({
                "doctype": "Agent Tool Call",
                "agent_run": agent_run,
                "conversation": conversation,
                "tool": name,
                "is_mcp_tool": is_mcp_tool,
                "mcp_server": mcp_server,
                "tool_args": json.dumps(args) if args else None,
                "tool_result": json.dumps(result) if result else None,
                "error_message": error,
                "status": "Queued"
            })
            doc.insert()
            return doc.name

        frappe.db.commit()
    except Exception as e:
        frappe.log_error(f"Error processing tool call: {str(e)}", "Agent Tool Call Error")
        return None

def log_tool_call(run_doc, conversation, raw_call, tool_result=None, error=None, is_output=False):
    return process_tool_call(
        agent_run=run_doc.name,
        conversation=conversation.name,
        name=getattr(raw_call, "name", None),
        args=getattr(raw_call, "arguments", None) if not is_output else None,
        result=tool_result,
        error=error,
        is_output=is_output
    )

@frappe.whitelist()
def run_background_summarization(conversation_name, agent_name):
    """
    Background job to summarize conversation history.
    """
    try:
        agent_doc = frappe.get_doc("Agent", agent_name)
        conv_manager = ConversationManager(agent_name=agent_name)
        
        history_limit = agent_doc.history_limit or 20
        # Fetch slightly more than limit to check for overflow
        history = conv_manager.get_conversation_history(conversation_name, limit=history_limit + 20)
        
        if len(history) <= history_limit:
            return

        stored_summary = conv_manager.get_stored_summary(conversation_name)
        
        # Calculate overflow
        overflow_count = len(history) - history_limit
        to_summarize = history[:overflow_count]
        
        from huf.ai.providers.litellm import get_simple_completion
        summary_model = agent_doc.summary_model or agent_doc.model
        summary_provider = agent_doc.provider
        
        if agent_doc.summary_model:
            summary_provider = frappe.db.get_value("AI Model", agent_doc.summary_model, "provider")

        # Prepare input: Previous Summary + Overflow Messages
        summary_input_data = {
            "existing_summary": stored_summary or "None",
            "new_messages_to_incorporate": to_summarize
        }
        
        summary_prompt = f"""
        You are maintaining a rolling summary of a conversation.
        
        1. Update the 'Existing Summary' by incorporating the 'New Messages'.
        2. Keep the summary concise but retain key details (names, decisions, technical context).
        3. Output ONLY the new summary text.

        Data:
        {json.dumps(summary_input_data, indent=2)}
        """
        
        messages = [{"role": "user", "content": summary_prompt}]
        
        # Run completion (sync in this background job context)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            new_summary_text = loop.run_until_complete(
                get_simple_completion(summary_model, messages, summary_provider)
            )
            if new_summary_text:
                conv_manager.update_stored_summary(conversation_name, new_summary_text)
                frappe.db.commit()
        finally:
            loop.close()
            
    except Exception as e:
        frappe.log_error(f"Background summarization failed: {str(e)}", "Agent Background Summarization")

@frappe.whitelist(allow_guest=True)
def run_agent_sync(
    agent_name: str,
    prompt: str,
    provider : str,
    model : str,
    channel_id: str = None,
    external_id: str = None,
    conversation_id: str = None,
    parent_run_id: str = None,
    orchestration_id: str = None,
    response_format = None
):

    if not agent_name or not prompt:
        frappe.throw(_("Both agent_name and prompt are required"))
    if not channel_id:
        channel_id = "api"

    agent_doc = frappe.get_doc("Agent", agent_name)

    if frappe.session.user == "Guest" and not agent_doc.allow_guest:
        frappe.throw(_("Access denied. This agent does not allow guest access."), frappe.PermissionError)

    conv_manager = ConversationManager(
        agent_name=agent_name,
        channel=channel_id,
        external_id=external_id
    )
    if agent_doc.persist_conversation:
        conversation = conv_manager.get_or_create_conversation(
            title=f"Chat with {agent_name}",
            conversation_id=conversation_id
        )

    else:
        conversation = conv_manager.create_new_conversation(
            title=f"Chat with {agent_name}"
        )

    if conversation.model:
        if conversation.model != model:
             frappe.throw(
                 _("Agent model has changed from {0} to {1}. Please start a new conversation.").format(conversation.model, model),
                 frappe.ValidationError
             )
    else:
        frappe.db.set_value("Agent Conversation", conversation.name, "model", model)


    # Optimized history fetching with dynamic limit + buffer
    fetch_limit = (agent_doc.history_limit or 20) + 10
    history = conv_manager.get_conversation_history(conversation.name, limit=fetch_limit)
    run_doc = frappe.get_doc({
        "doctype": "Agent Run",
        "agent": agent_name,
        "status": "Queued",
        "conversation": conversation.name,
        "prompt": prompt,
        "model": model,
        "provider": provider,
        "parent_run": parent_run_id,
        "is_child": 1 if parent_run_id else 0,
        "agent_orchestration": orchestration_id
    })
    run_doc.insert()  
    conv_manager.add_message(conversation, "user", prompt, provider, model, agent_name, run_doc.name)
    run_doc.db_set("start_time", now_datetime())
    safe_commit()

    # Check for multi-run orchestration mode
    # Skip if already called from orchestration to prevent infinite loop
    if agent_doc.enable_multi_run and channel_id not in ("orchestration", "orchestration_planning"):
        from huf.ai.orchestration.orchestrator import create_orchestration
        orch_name = create_orchestration(
            agent_name, 
            prompt, 
            parent_run_id=run_doc.name,
            conversation_id=run_doc.conversation
        )        
        
        run_doc.db_set({
            "agent_orchestration": orch_name,
            "status": "Started", # Mark as started, but not "Success" yet
            "response": f"Orchestration started. Job ID: {orch_name}"
        })
        safe_commit()
        return {
            "success": True,
            "response": f"Orchestration started: {orch_name}",
            "orchestration_id": orch_name,
            "mode": "multi_run",
            "agent_run_id": run_doc.name
        }

    
    try:
        frappe.db.set_value("Agent Run", run_doc.name, "status", "Started", update_modified=True)
        safe_commit()

        total_runs = frappe.db.count("Agent Run", filters={"agent": agent_name})
        last_run_time = frappe.db.get_value("Agent Run", {"agent": agent_name}, "start_time", order_by="start_time DESC")

        frappe.db.set_value("Agent", agent_name, {
            "total_run": total_runs,
            "last_run": last_run_time
        },update_modified=False)
        safe_commit()

        manager = AgentManager(agent_name)
        agent = manager.create_agent()

        # Build knowledge context for mandatory sources
        knowledge_context = None
        try:
            from huf.ai.knowledge.context_builder import build_knowledge_context, inject_knowledge_context
            
            knowledge_context = build_knowledge_context(
                agent_name=agent_name,
                user_query=prompt,
                max_tokens=agent_doc.max_knowledge_tokens or 4000
            )
        except Exception as e:
            frappe.log_error(
                f"Error building knowledge context: {str(e)}",
                "Knowledge Context Error"
            )

        # Parse response_format if string
        if response_format and isinstance(response_format, str):
            try:
                response_format = json.loads(response_format)
            except Exception:
                pass

        context = {
            "channel": channel_id,
            "external_id": external_id,
            "conversation_history": history,
            "agent_name": agent_name,
            "response_format": response_format,
            "conversation_id": conversation.name,
            "agent_run_id": run_doc.name
        }

        context_strategy = agent_doc.context_strategy or "Summarize"
        history_limit = agent_doc.history_limit or 20
        stored_summary = conv_manager.get_stored_summary(conversation.name)
        
        if context_strategy == "Summarize":
            # Just inject the stored summary. Actual summarization happens in background.
            if stored_summary:
                history = [{"role": "system", "content": f"Context Summary: {stored_summary}"}] + history
        
        # Inject Conversation Data Snapshot if enabled
        if agent_doc.enable_conversation_data and conversation.conversation_data:
             try:
                data_snapshot = json.loads(conversation.conversation_data)
                # Filter to only show name/value to save tokens
                simplified_items = {item["name"]: item["value"] for item in data_snapshot.get("items", [])}
                if simplified_items:
                    data_msg = f"CURRENT MEMORY STATE (Conversation Data): {json.dumps(simplified_items, ensure_ascii=False)}"
                    # Insert right after summary but before user messages
                    insert_idx = 1 if stored_summary else 0
                    history.insert(insert_idx, {"role": "system", "content": data_msg})
             except:
                 pass
        
        elif context_strategy == "FIFO":
            if len(history) > history_limit:
                history = history[-history_limit:]
        
        base_prompt = f"""
            Current user message:
            {prompt}
        """
        
        # Inject knowledge context if available
        if knowledge_context and knowledge_context.get("context_text"):
            enhanced_prompt = inject_knowledge_context(base_prompt, knowledge_context)
            
            # Store knowledge usage in run document
            if knowledge_context.get("sources_used"):
                run_doc.db_set({
                    "knowledge_sources_used": json.dumps(knowledge_context["sources_used"]),
                    "chunks_injected": len(knowledge_context.get("chunks_used", []))
                })
        else:
            enhanced_prompt = base_prompt

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            context = {
                "channel": channel_id,
                "external_id": external_id,
                "conversation_history": history,
                "agent_name": agent_name,
                "response_format": response_format,
                "conversation_id": conversation.name,
                "agent_run_id": run_doc.name
            }
            run = RunProvider.run(agent, enhanced_prompt, provider, model,context)

            result = loop.run_until_complete(run)
        finally:
            loop.close()

        client_side_tool_calls = []

        for item in getattr(result, "new_items", []):
            if item.type == "tool_call_item":
                raw = item.raw_item  
                tool_call_id = log_tool_call(run_doc, conversation, raw, is_output=False)

                tool_name = getattr(raw, "name", "Unknown Tool")
                tool_args = getattr(raw, "arguments", "{}")
                
                tool_type = frappe.db.get_value("Agent Tool Function", {"tool_name": tool_name}, "types")
                if tool_type == "Client Side Tool":
                    call_id = getattr(raw, "id", None)
                     
                    client_side_tool_calls.append({
                         "id": call_id,
                         "type": "function", 
                         "function": {
                             "name": tool_name,
                             "arguments": tool_args 
                        }
                    })

                msg_content = f"Requesting Tool: {tool_name}\nArguments: {tool_args}"
                
                message_doc = conv_manager.add_message(
                    conversation, 
                    role="agent", 
                    content=msg_content, 
                    provider=provider, 
                    model=model, 
                    agent=agent_name, 
                    run_name=run_doc.name,
                    kind="Tool Call",
                    tool_call_id=tool_call_id 
                )

                # Emit socket event for tool call started
                frappe.publish_realtime(
                    event=f'conversation:{conversation.name}',
                    message={
                        "type": "tool_call_started",
                        "conversation_id": conversation.name,
                        "agent_run_id": run_doc.name,
                        "tool_call_id": tool_call_id,
                        "message_id": message_doc.name,
                        "tool_name": tool_name,
                        "tool_status": "Queued",
                        "tool_args": tool_args if isinstance(tool_args, dict) else json.loads(tool_args) if isinstance(tool_args, str) else {},
                    },
                    user=frappe.session.user
                )

            elif item.type == "tool_call_output_item":
                raw = item.raw_item
                try:
                    tool_result = json.loads(raw.get("output")) if raw and raw.get("output") else None
                except Exception:
                    tool_result = raw.get("output")

                updated_tool_call_id = log_tool_call(run_doc, conversation, raw, tool_result=tool_result, is_output=True)

                if updated_tool_call_id:
                    # Get tool call doc to check status
                    tool_call_doc = frappe.get_doc("Agent Tool Call", updated_tool_call_id)
                    tool_status = tool_call_doc.status or "Completed"
                    tool_name = tool_call_doc.tool or "Unknown Tool"

                    message_name = frappe.db.get_value("Agent Message", {"tool_calll": updated_tool_call_id}, "name")

                    if message_name:
                        msg_doc = frappe.get_doc("Agent Message", message_name)
                        
                        result_str = json.dumps(tool_result) if not isinstance(tool_result, str) else tool_result
                        new_content = msg_doc.content + f"\n\n**Tool Result:**\n{result_str}"
                        
                        msg_doc.content = new_content
                        msg_doc.kind = "Tool Result"
                        msg_doc.save(ignore_permissions=True)

                        # Emit socket event for tool call completed/failed
                        event_type = "tool_call_completed" if tool_status == "Completed" else "tool_call_failed"
                        frappe.publish_realtime(
                            event=f'conversation:{conversation.name}',
                            message={
                                "type": event_type,
                                "conversation_id": conversation.name,
                                "agent_run_id": run_doc.name,
                                "tool_call_id": updated_tool_call_id,
                                "message_id": message_name,
                                "tool_name": tool_name,
                                "tool_status": tool_status,
                                "tool_result": tool_result if tool_status == "Completed" else None,
                                "error": tool_call_doc.error_message if tool_status == "Failed" else None,
                            },
                            user=frappe.session.user,
                        )
        
        final_output = getattr(result, "final_output", str(result))
        usage = getattr(result, "usage", None)
        cost = getattr(result, "cost", 0)  
        input_tokens = 0
        output_tokens = 0
        cached_tokens = 0

        if usage:
            
            if isinstance(usage, dict):
                input_tokens = getattr(usage, "prompt_tokens", usage.get("input_tokens", 0) if isinstance(usage, dict) else 0)
                output_tokens = getattr(usage, "completion_tokens", usage.get("output_tokens", 0) if isinstance(usage, dict) else 0)
                
                details = getattr(usage, "prompt_tokens_details", None)
                if details:
                    cached_tokens = getattr(details, "cached_tokens", 0)
                elif isinstance(usage, dict):
                    cached_tokens = usage.get("cached_tokens", 0)
                
            else: 
                input_tokens = getattr(usage, "input_tokens", 0) or getattr(usage, "prompt_tokens", 0)
                output_tokens = getattr(usage, "output_tokens", 0) or getattr(usage, "completion_tokens", 0)
                cached_tokens = getattr(usage, "cached_tokens", 0)

            # --- UPDATE CONVERSATION METRICS ---
            try:
                total_tokens = getattr(usage, "total_tokens", (input_tokens + output_tokens)) if usage else (input_tokens + output_tokens)
                
                frappe.db.sql("""
                    UPDATE `tabAgent Conversation`
                    SET 
                        total_input_tokens = total_input_tokens + %s,
                        total_output_tokens = total_output_tokens + %s,
                        total_tokens = total_tokens + %s,
                        total_cost = total_cost + %s
                    WHERE name = %s
                """, (input_tokens, output_tokens, total_tokens, cost, conversation.name))
            except Exception as e:
                frappe.log_error(f"Failed to update conversation metrics: {str(e)}")
            # -----------------------------------
            frappe.db.set_value("Agent Run", run_doc.name, {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cached_tokens": cached_tokens,
                "cost": cost
            })

        conv_manager.add_message(conversation, "agent", final_output, provider, model, agent_name, run_doc.name)

        frappe.db.set_value("Agent Run", run_doc.name, {
            "status": "Success",
            "response": final_output,
            "prompt": prompt,
            "model": model,
            "provider": provider,
            "end_time": now_datetime()
        }, update_modified=True)
        safe_commit()

        if context_strategy == "Summarize":
            current_history_len = len(history)
            if current_history_len >= history_limit:
                 frappe.enqueue(
                    "huf.ai.agent_integration.run_background_summarization",
                    queue="default", 
                    conversation_name=conversation.name,
                    agent_name=agent_name
                )

        structured = None
        try:
            structured = json.loads(final_output)
        except (TypeError, ValueError):
            pass

        return {
            "success": True,
            "response": final_output,
            "client_side_tool_calls": client_side_tool_calls,
            "structured": structured,
            "provider": manager.agent_doc.provider,
            "agent_run_id": run_doc.name,
            "conversation_id": conversation.name,
            "session_id": conv_manager.session_id
        }

    except Exception as e:
        error_msg = str(e)
        run_doc.db_set("status", "Failed", update_modified=True)
        run_doc.db_set("error_message", error_msg)
        frappe.log_error(f"Agent Run Error: {frappe.get_traceback()}", "Huf")

        return {
            "success": False,
            "error": error_msg,
            "agent_run_id": run_doc.name,
            "conversation_id": conversation.name,
            "session_id": conv_manager.session_id
        }


async def run_agent_stream(
    agent_name: str,
    prompt: str,
    provider: str,
    model: str,
    channel_id: str = None,
    external_id: str = None,
    conversation_id: str = None
):
    """
    Streaming version of run_agent_sync.
    
    Yields chunks of the agent's response as they arrive from the LLM.
    Uses the same conversation management and run tracking as run_agent_sync.
    
    Args:
        agent_name: Name of the agent to run
        prompt: User prompt
        provider: Provider name
        model: Model name
        channel_id: Channel identifier (default: "api")
        external_id: External identifier for conversation tracking
        conversation_id: Optional conversation ID to continue
        
    Yields:
        dict: Streaming chunks with structure:
            - type: "delta" | "complete" | "tool_call" | "error"
            - content: str (for delta)
            - full_response: str (accumulated response)
            - tool_call: dict (for tool_call type)
            - error: str (for error type)
    """
    if not agent_name or not prompt:
        yield {
            "type": "error",
            "error": "Both agent_name and prompt are required"
        }
        return
    
    if not channel_id:
        channel_id = "sse_stream"
    
    try:
        agent_doc = frappe.get_doc("Agent", agent_name)
        
        # Validate agent allows chat (for streaming UI)
        if not agent_doc.allow_chat:
            yield {
                "type": "error",
                "error": f"Agent '{agent_name}' does not allow chat/streaming. Enable 'Allow Chat' in agent settings."
            }
            return
        
        conv_manager = ConversationManager(
            agent_name=agent_name,
            channel=channel_id,
            external_id=external_id
        )
        
        if agent_doc.persist_conversation:
            conversation = conv_manager.get_or_create_conversation(
                title=f"Streaming chat with {agent_name}",
                conversation_id=conversation_id
            )
        else:
            conversation = conv_manager.create_new_conversation(
                title=f"Streaming chat with {agent_name}"
            )
        
        # Model Validation
        if conversation.model:
            if conversation.model != model:
                 yield {
                     "type": "error",
                     "error": f"Agent model has changed from {conversation.model} to {model}. Please start a new conversation."
                 }
                 return
        else:
            # Legacy: Lock to current model
            frappe.db.set_value("Agent Conversation", conversation.name, "model", model)
        
        history = conv_manager.get_conversation_history(conversation.name, limit=1000)
        
        # Create Agent Run document
        run_doc = frappe.get_doc({
            "doctype": "Agent Run",
            "agent": agent_name,
            "status": "Started",
            "conversation": conversation.name,
            "prompt": prompt,
            "model": model,
            "provider": provider
        })
        run_doc.insert()
        conv_manager.add_message(conversation, "user", prompt, provider, model, agent_name, run_doc.name)
        run_doc.db_set("start_time", now_datetime())
        safe_commit()
        
        # Update agent stats
        total_runs = frappe.db.count("Agent Run", filters={"agent": agent_name})
        last_run_time = frappe.db.get_value("Agent Run", {"agent": agent_name}, "start_time", order_by="start_time DESC")
        
        frappe.db.set_value("Agent", agent_name, {
            "total_run": total_runs,
            "last_run": last_run_time
        },update_modified=False)
        safe_commit()
        
        manager = AgentManager(agent_name)
        agent = manager.create_agent()
        
        context = {
            "channel": channel_id,
            "external_id": external_id,
            "conversation_history": history,
            "agent_name": agent_name,
            "conversation_id": conversation.name,
            "agent_run_id": run_doc.name
        }
        
        # SUMMARIZATION LOGIC
        to_summarize, remaining = conv_manager.summarize_conversation(
            conversation.name, history, provider, model, agent_name, limit=20
        )

        if to_summarize:
            try:
                summary_agent = Agent(
                    name=agent_name, 
                    instructions="You are a helpful assistant. Summarize the provided conversation history concisely, capturing key decisions and context.",
                    model=agent.model,
                    tools=[],
                    model_settings=agent.model_settings,
                )
                
                summary_input = json.dumps(to_summarize, indent=2)
                summary_prompt = f"Summarize this conversation history:\n{summary_input}"

                sum_context = {"agent_name": agent_name, "is_system_op": True} 
                sum_result = await RunProvider.run(summary_agent, summary_prompt, provider, model, sum_context)
                summary_text = getattr(sum_result, "final_output", "Could not generate summary.")

                history = [{"role": "system", "content": f"Previous Conversation Summary: {summary_text}"}] + remaining
            except Exception as e:
                frappe.log_error(f"Summarization failed: {str(e)}", "Agent Summarization Error")
                pass

        enhanced_prompt = f"""
            Current user message:
            {prompt}
        """

        context["conversation_history"] = history
        
        # Stream from provider
        full_response = ""
        try:
            stream = RunProvider.run_stream(agent, enhanced_prompt, provider, model, context)
            
            async for chunk in stream:
                chunk_type = chunk.get("type")
                
                if chunk_type == "delta":
                    full_response = chunk.get("full_response", full_response)
                    yield chunk
                
                elif chunk_type == "tool_call":
                    # Log tool call
                    tool_call = chunk.get("tool_call", {})
                    if tool_call:
                        raw_item = SimpleNamespace(
                            name=tool_call.get("function", {}).get("name", ""),
                            arguments=tool_call.get("function", {}).get("arguments", "{}")
                        )
                        log_tool_call(run_doc, conversation, raw_item, is_output=False)
                    yield chunk
                
                elif chunk_type == "complete":
                    full_response = chunk.get("full_response", full_response)
                    usage = chunk.get("usage", {})
                    
                    # Calculate metrics
                    cost = 0.0
                    input_tokens = 0
                    output_tokens = 0
                    cached_tokens = 0
                    
                    if usage:
                        # Try to calculate cost if possible or use 0
                        # LiteLLM usually provides cost in response object, not always in usage dict
                        # We might need to rely on what we have.
                        # For stream, cost calculation might be tricky without response object.
                        # We will skip cost calc for now or assume 0 until we have a better way.
                        # Wait, litellm.completion_cost takes response object.
                        
                        if isinstance(usage, dict):
                            input_tokens = getattr(usage, "prompt_tokens", usage.get("prompt_tokens", 0))
                            output_tokens = getattr(usage, "completion_tokens", usage.get("completion_tokens", 0))
                            total_tokens = getattr(usage, "total_tokens", (input_tokens + output_tokens))
                        else:
                             input_tokens = getattr(usage, "prompt_tokens", 0)
                             output_tokens = getattr(usage, "completion_tokens", 0)
                             total_tokens = getattr(usage, "total_tokens", (input_tokens + output_tokens))

                        # COST NOTE: LiteLLM stream chunks usage doesn't include cost. 
                        # We would need to calculate it manually using completion_cost(model=model, rx=usage)
                        # but that requires importing completion_cost and model prices.
                        # For now, we will leave cost as 0.0 for streams to avoid errors, 
                        # or try to calculate if we really need it. User asked for total context.

                        # Update Conversation Metrics
                        try:
                            frappe.db.sql("""
                                UPDATE `tabAgent Conversation`
                                SET 
                                    total_input_tokens = total_input_tokens + %s,
                                    total_output_tokens = total_output_tokens + %s,
                                    total_tokens = total_tokens + %s,
                                    total_cost = total_cost + %s
                                WHERE name = %s
                            """, (input_tokens, output_tokens, total_tokens, cost, conversation.name))
                        except Exception as e:
                            frappe.log_error(f"Failed to update conv metrics stream: {str(e)}")

                    # Save final response
                    conv_manager.add_message(conversation, "agent", full_response, provider, model, agent_name, run_doc.name)
                    
                    frappe.db.set_value("Agent Run", run_doc.name, {
                        "status": "Success",
                        "response": full_response,
                        "prompt": prompt,
                        "model": model,
                        "provider": provider,
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                        "end_time": now_datetime()
                    }, update_modified=True)
                    safe_commit()
                    
                    yield chunk
                    return
                
                elif chunk_type == "error":
                    error_msg = chunk.get("error", "Unknown error")
                    
                    frappe.db.set_value("Agent Run", run_doc.name, {
                        "status": "Failed",
                        "error_message": error_msg,
                        "end_time": now_datetime()
                    }, update_modified=True)
                    safe_commit()
                    
                    yield chunk
                    return
        
        except Exception as e:
            error_msg = str(e)
            frappe.log_error(f"Agent Stream Error: {frappe.get_traceback()}", "Huf Streaming")
            
            frappe.db.set_value("Agent Run", run_doc.name, {
                "status": "Failed",
                "error_message": error_msg,
                "end_time": now_datetime()
            }, update_modified=True)
            safe_commit()
            
            yield {
                "type": "error",
                "error": error_msg
            }
    
    except Exception as e:
        error_msg = str(e)
        frappe.log_error(f"Agent Stream Setup Error: {frappe.get_traceback()}", "Huf Streaming")
        yield {
            "type": "error",
            "error": error_msg
        }