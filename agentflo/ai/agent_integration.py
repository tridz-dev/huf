import asyncio
import json

import frappe
from agents import OpenAIProvider,Agent, Runner, Tool, function_tool,ModelSettings
from frappe.utils.background_jobs import enqueue

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
            from agentflo.ai.sdk_tools import create_agent_tools  
            agent_tools = create_agent_tools(self.agent_doc)
            if agent_tools:
                self.tools.extend(agent_tools)
        except Exception as e:
            frappe.log_error(
                f"Error loading Agent Tool Function: {str(e)}",
                "Agent Tool Function Error",
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

        if not hasattr(agent, "tools") or agent.tools is None:
            agent.tools = []

        return agent

def safe_commit():
    if not hasattr(frappe.local, "_realtime_log"):
        frappe.local._realtime_log = []
    frappe.db.commit()

def process_tool_call(agent_run, conversation, name=None, args=None, result=None, error=None, is_output=False):
    """Process tool call - update existing record or create new one"""
    try:
        existing = frappe.get_all(
            "Agent Tool Call",
            filters={"agent_run": agent_run},
            pluck="name"
        )
        if existing:
            doc = frappe.get_doc("Agent Tool Call", existing[0])
            update_data = {}
            if result is not None:
                update_data["tool_result"] = json.dumps(result)
            if error:
                update_data["status"] = "Failed"
                update_data["error_message"] = error
            else:
                update_data["status"] = "Completed"
            
            doc.update(update_data)
            doc.save(ignore_permissions=True)
        else:
            doc = frappe.get_doc({
                "doctype": "Agent Tool Call",
                "agent_run": agent_run,
                "conversation": conversation,
                "tool_name": name,
                "tool_args": json.dumps(args) if args else None,
                "tool_result": json.dumps(result) if result else None,
                "error_message": error,
                "status": "Queued" if not is_output else "Completed"
            })
            doc.insert(ignore_permissions=True)

        frappe.db.commit()
    except Exception as e:
        frappe.log_error(f"Error processing tool call: {str(e)}", "Agent Tool Call")

def log_tool_call(run_doc, conversation, raw_call, tool_result=None, error=None, is_output=False):
    frappe.enqueue(process_tool_call, queue='long', job_name='tool_call',
        agent_run=run_doc.name,
        conversation=conversation.name,
        name=getattr(raw_call, "name", None),
        args=getattr(raw_call, "arguments", None) if not is_output else None,
        result=tool_result,
        error=error,
        is_output=is_output
    )

@frappe.whitelist()
def run_agent_sync(
    agent_name: str,
    prompt: str,
    provider : str,
    model : str,
    channel_id: str = None,
    external_id: str = None,
    conversation_id: str = None
):

    if not agent_name or not prompt:
        frappe.throw(_("Both agent_name and prompt are required"))
    if not channel_id:
        channel_id = "api"
    conv_manager = ConversationManager(
        agent_name=agent_name,
        channel=channel_id,
        external_id=external_id
    )

    conversation = conv_manager.get_or_create_conversation(
        title=f"Chat with {agent_name}",
        conversation_id=conversation_id
    )

    conv_manager.add_message(conversation, "user", prompt, provider, model)

    history = conv_manager.get_conversation_history(conversation.name)
    run_doc = frappe.get_doc({
        "doctype": "Agent Run",
        "agent": agent_name,
        "status": "Queued",
        "conversation": conversation.name,
        "prompt": prompt,
    })
    run_doc.insert()
    safe_commit()
    try:
        frappe.db.set_value("Agent Run", run_doc.name, "status", "Started", update_modified=True)
        safe_commit()

        manager = AgentManager(agent_name)
        agent = manager.create_agent()

        context = {
            "channel": channel_id,
            "external_id": external_id,
            "conversation_history": history
        }

        enhanced_prompt = f"""
            Conversation history:
            {json.dumps(history, indent=2)}
            Current user message:
            {prompt}
        """

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            run = RunProvider.run(agent, enhanced_prompt, provider, model,context)

            result = loop.run_until_complete(run)
        finally:
            loop.close()

        for item in getattr(result, "new_items", []):
            if item.type == "tool_call_item":
                raw = item.raw_item  
                log_tool_call(run_doc, conversation, raw, is_output=False)

            elif item.type == "tool_call_output_item":
                raw = item.raw_item
                try:
                    tool_result = json.loads(raw.get("output")) if raw and raw.get("output") else None
                except Exception:
                    tool_result = raw.get("output")

                log_tool_call(run_doc, conversation, raw, tool_result=tool_result, is_output=True)
        
        final_output = getattr(result, "final_output", str(result))

        conv_manager.add_message(conversation, "agent", final_output, provider, model, run_doc.name)

        frappe.db.set_value("Agent Run", run_doc.name, {
            "status": "Success",
            "response": final_output,
            "prompt": prompt
        }, update_modified=True)
        safe_commit()

        structured = None
        try:
            structured = json.loads(final_output)
        except (TypeError, ValueError):
            pass

        return {
            "success": True,
            "response": final_output,
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
        conv_manager.add_message(conversation, role="system", content=error_msg, provider=provider, model=model, run_name=run_doc.name)

        frappe.log_error(f"Agent Run Error: {frappe.get_traceback()}", "AgentFlo")

        return {
            "success": False,
            "error": error_msg,
            "agent_run_id": run_doc.name,
            "conversation_id": conversation.name,
            "session_id": conv_manager.session_id
        }