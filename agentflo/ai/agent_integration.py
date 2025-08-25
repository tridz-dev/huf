import asyncio
import json
import openai

import frappe
from pydantic import BaseModel
from agents.exceptions import InputGuardrailTripwireTriggered
from agents import OpenAIProvider,Agent, Runner,RunConfig, Tool, function_tool,ModelSettings

from frappe import _
from frappe.client import get
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


class AgentManager:
    """Manages the creation and execution of agents."""
    def __init__(self, agent_name, file_handler=None):
        self.agent_doc = frappe.get_doc("Agent", agent_name)
        self.settings = frappe.get_doc("AI Provider", self.agent_doc.provider)
        self.file_handler = file_handler
        self.tools = []
        self._setup_client()
        self._setup_tools()

    
    def _setup_tools(self):
        """Create SDK Tools from existing functions"""
        # Always include built-in CRUD tools first
        self.tools.extend(self.create_tools())

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

        # Directly use OpenAIProvider — no need for AsyncOpenAI
        self.provider = OpenAIProvider(api_key=api_key, use_responses=True)

        # Keep reference if you want backward compatibility
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
                cancel_document_tool,
            ]
        )

        return self.tools or []

    
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



async def run_agent(agent_name: str, prompt: str):
    try:
        manager = AgentManager(agent_name=agent_name)
        agent = manager.create_agent()

        run_config = RunConfig(model_provider=manager.provider)
        result = await Runner.run(agent, prompt, run_config=run_config)

        return result.final_output if hasattr(result, "final_output") else str(result)

    except InputGuardrailTripwireTriggered as e:
        frappe.log_error(f"Guardrail blocked this input: {e}", "Agent Integration Error")
        return _("Guardrail blocked this input.")
    except Exception as e:
        frappe.log_error(f"Error running agent: {frappe.get_traceback()}", "Agent Integration Error")
        return _("An error occurred while running the agent.")



@frappe.whitelist()
def run_agent_sync(
    agent_name: str,
    prompt: str,
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

    # Add user message to conversation
    conv_manager.add_message(conversation, "user", prompt)

    # Get history for context
    history = conv_manager.get_conversation_history(conversation.name)
    run_doc = frappe.get_doc({
        "doctype": "Agent Run",
        "agent": agent_name,
        "status": "Queued",
        "conversation": conversation.name,
        "prompt": prompt,
    })
    run_doc.insert()
    frappe.db.commit()

    try:
        frappe.db.set_value("Agent Run", run_doc.name, "status", "Started", update_modified=True)
        frappe.db.commit()

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
        result = loop.run_until_complete(
            Runner.run(agent, enhanced_prompt, max_turns=8, context=context)
        )
        loop.close()

        final_output = getattr(result, "final_output", str(result))

        conv_manager.add_message(conversation, "agent", final_output, run_doc.name)

        # Update run status to Success
        frappe.db.set_value("Agent Run", run_doc.name, {
            "status": "Success",
            "response": final_output,
            "prompt": prompt
        }, update_modified=True)
        frappe.db.commit()

        return {
            "success": True,
            "response": final_output,
            "provider": manager.agent_doc.provider,
            "agent_run_id": run_doc.name,
            "conversation_id": conversation.name,
            "session_id": conv_manager.session_id
        }

    except Exception as e:
        error_msg = str(e)
        run_doc.db_set("status", "Failed", update_modified=True)
        run_doc.db_set("error_message", error_msg)

        frappe.log_error(f"Agent Run Error: {frappe.get_traceback()}", "AgentFlo")

        return {
            "success": False,
            "error": error_msg,
            "agent_run_id": run_doc.name,
            "conversation_id": conversation.name,
            "session_id": conv_manager.session_id
        }