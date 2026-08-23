import asyncio
import json
import threading
import random
import time
from types import SimpleNamespace
import litellm
from litellm import token_counter

import frappe
from agents import OpenAIProvider,Agent, Runner, Tool, function_tool,ModelSettings
from frappe.utils.background_jobs import enqueue
from frappe.utils import now_datetime, add_to_date

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
from .conversation_manager import ConversationManager, safe_history_slice, safe_history_split
from .run import RunProvider
from huf.ai.knowledge.context_builder import build_knowledge_context, inject_knowledge_context
from huf.ai.providers.litellm import _normalize_model_name, ProviderUnavailableError
from huf.ai.transaction import safe_commit, transaction_checkpoint
from huf.ai.agent_access import assert_agent_access, check_agent_access as _check_agent_access
from huf.permissions import has_capability

class _LazyLogger:
	"""Defer frappe.logger() until first use so test discovery can import this module."""

	def __getattr__(self, name):
		return getattr(frappe.logger("huf"), name)


logger = _LazyLogger()


def _resolve_effective_model(agent_doc, model=None, provider=None):
    """Resolve the effective provider and model for an agent run.

    Args:
        agent_doc: The Agent document.
        model: Optional AI Model link name to override the agent's default model.
        provider: Optional provider link name. If omitted and model is provided,
            the provider is resolved from the AI Model doc.

    Returns:
        Tuple of (provider_link, model_link, model_name).

    Raises:
        frappe.ValidationError: if the override model or its provider is missing/invalid.
    """
    effective_model = model if model else agent_doc.model
    if not effective_model:
        frappe.throw(_("Agent model is not configured"))

    if model and model != agent_doc.model:
        model_doc = frappe.get_cached_doc("AI Model", model)
        if not model_doc.provider:
            frappe.throw(
                _("AI Model '{0}' has no provider configured.").format(model),
                frappe.ValidationError,
            )
        effective_provider = provider if provider else model_doc.provider
        # If caller passed a provider that does not match the override model,
        # trust the model's own provider so the right API key/base URL is used.
        if provider and provider != model_doc.provider:
            frappe.logger("huf").warning(
                f"Provider mismatch for model override: requested {provider}, "
                f"model {model} belongs to {model_doc.provider}. Using {model_doc.provider}."
            )
            effective_provider = model_doc.provider
    else:
        effective_provider = provider if provider else agent_doc.provider

    if not effective_provider:
        frappe.throw(_("Provider is not configured"))

    model_name = frappe.get_cached_value("AI Model", effective_model, "model_name")
    if not model_name:
        frappe.throw(
            _("AI Model '{0}' has no model name configured.").format(effective_model),
            frappe.ValidationError,
        )

    return effective_provider, effective_model, model_name


class AgentManager:
    """Manages the creation and execution of agents."""
    def __init__(self, agent_name, file_handler=None, provider_override=None, model_override=None, conversation_id=None):
        self.agent_doc = frappe.get_cached_doc("Agent", agent_name)
        self.conversation_id = conversation_id
        (
            self.effective_provider,
            self.effective_model,
            self.effective_model_name,
        ) = _resolve_effective_model(
            self.agent_doc,
            model=model_override,
            provider=provider_override,
        )
        self.settings = frappe.get_cached_doc("AI Provider", self.effective_provider)
        self.provider_override = provider_override
        self.model_override = model_override
        # self.file_handler = file_handler
        self.tools = []
        self._setup_client()
        self._setup_tools()


    def _setup_tools(self):
        """Create SDK Tools from existing functions, skills, and MCP servers."""
        self.tools=[]

        try:
            from huf.ai.sdk_tools import create_agent_tools
            agent_tools = create_agent_tools(
                self.agent_doc,
                model_name=self.effective_model,
                conversation_id=self.conversation_id,
                agent_name=self.agent_doc.name,
            )
            if agent_tools:
                self.tools.extend(agent_tools)
        except (ImportError, AttributeError, TypeError, ValueError, RuntimeError) as e:
            logger.warning(f"Failed to load agent tools: {e!s}")

        # Merge skill MCP servers with agent-level MCP servers so attached
        # skills can contribute runtime tools without replacing direct tools.
        try:
            from huf.ai.mcp_client import create_mcp_tools
            from huf.ai.skills.loader import get_agent_skill_mcp_servers

            agent_mcp_servers = [
                row.mcp_server
                for row in getattr(self.agent_doc, "agent_mcp_server", [])
                if getattr(row, "enabled", True)
            ]
            skill_mcp_servers = get_agent_skill_mcp_servers(self.agent_doc.agent_name)

            merged_server_names = []
            seen_servers = set()
            for name in agent_mcp_servers + skill_mcp_servers:
                if name and name not in seen_servers:
                    seen_servers.add(name)
                    merged_server_names.append(name)

            if merged_server_names:
                merged_mcp_tools = create_mcp_tools(
                    self.agent_doc, mcp_server_names=merged_server_names
                )
                tool_map = {tool.name: tool for tool in self.tools}
                for tool in merged_mcp_tools:
                    tool_map[tool.name] = tool
                self.tools = list(tool_map.values())
        except Exception as e:
            logger.warning(f"Failed to load skill MCP tools: {e!s}")

        try:
            from huf.ai.skills.loader import create_list_skills_tool

            list_skills_tool = create_list_skills_tool(self.agent_doc.agent_name)
            if list_skills_tool:
                existing_names = {tool.name for tool in self.tools}
                if list_skills_tool.name not in existing_names:
                    self.tools.append(list_skills_tool)
        except Exception as e:
            logger.warning(f"Failed to load skills listing tool: {e!s}")

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

        except (ImportError, AttributeError, TypeError, ValueError, RuntimeError) as e:
            logger.warning(f"Failed to load knowledge tools: {e!s}")

    def _setup_client(self):
        """Configure OpenAI provider from the AI Provider doc"""
        api_key = self.settings.get_password("api_key")
        if not api_key:
            frappe.throw(_("API key is not configured in AI Provider."))

        provider_kwargs = {"api_key": api_key, "use_responses": True}
        # Support local/custom OpenAI-compatible endpoints (e.g. Kimi Code API)
        if getattr(self.settings, "is_local_llm", False) and getattr(self.settings, "url", None):
            base_url = self.settings.url
            if getattr(self.settings, "port", None):
                base_url = f"{base_url.rstrip('/')}:{self.settings.port}"
            provider_kwargs["base_url"] = base_url

        self.provider = OpenAIProvider(**provider_kwargs)

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


    def create_agent(self, memory_query: str = None, conversation_id: str = None) -> Agent:
        """Create main agent

        memory_query/conversation_id are the current turn's user text and
        conversation, used to narrow "Relevant Only" memory injection.
        """

        if not self.effective_model:
            frappe.throw(_("Agent model is not configured"))

        from huf.ai.prompt_resolver import resolve_prompt
        instructions = resolve_prompt(self.agent_doc) or ""

        # Append skill instructions, optional skill preamble, and skill prompts
        # (System usage) to the system prompt.
        try:
            from huf.ai.skills.loader import (
                get_skill_instructions,
                get_optional_skills_preamble,
                get_skill_prompts,
            )

            skill_instructions = get_skill_instructions(self.agent_doc.agent_name)
            if skill_instructions:
                instructions += "\n\n" + skill_instructions

            optional_preamble = get_optional_skills_preamble(self.agent_doc.agent_name)
            if optional_preamble:
                instructions += "\n\n" + optional_preamble

            skill_prompts = get_skill_prompts(self.agent_doc.agent_name)
            system_prompts = [p["body"] for p in skill_prompts if p["usage"] == "System"]
            if system_prompts:
                instructions += "\n\n" + "\n\n".join(system_prompts)
        except Exception as e:
            frappe.log_error(
                f"Error injecting skill instructions: {str(e)}",
                "Skill Instruction Error",
            )

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

        instructions += """
            SYSTEM INSTRUCTION - LARGE CONTEXT REFERENCES:
            If you see a data payload or result formatted as a reference like [record_kind: summary · handle=DocType/Name], it means the full massive data payload was truncated to save space.
            You MUST use the `get_result_context` tool with that exact handle (e.g. DocType/Name) to fetch the full data if you need more details to answer the user's question.
            """

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

        if getattr(self.agent_doc, "enable_memory", False):
            instructions += """

                SYSTEM INSTRUCTION - LONG-TERM MEMORY:
                You have access to a persistent memory system across sessions.
                1. AUTOMATIC RECALL: Use the 'search_memory_records' tool whenever the user refers to past interactions, preferences, or context.
                2. PROACTIVE SAVING: Use the 'save_memory_record' tool when the user shares new facts, preferences, or important details about themselves or a project.
                3. ACCURACY: When saving, provide a clear 'title' and detailed 'summary_text'. Set 'record_type' and 'scope_type' appropriately.
            """

            if getattr(self.agent_doc, "memory_policy", None):
                try:
                    policy = frappe.get_doc("Memory Policy", self.agent_doc.memory_policy)
                    from huf.ai.memory_tools import get_injected_memory_text

                    injected_memory = get_injected_memory_text(
                        self.agent_doc.name, policy, conversation_id=conversation_id, query=memory_query
                    )
                    if injected_memory:
                        instructions += f"\n\n{injected_memory}\n"
                except Exception as e:
                    frappe.log_error(title="Memory Injection Failed", message=str(e))

        if self.agent_doc.allow_chat:
            from huf.ai.capabilities import capability_enabled

            if capability_enabled(self.agent_doc, self.effective_model, "rich_elements"):
                from huf.ai.chart_artifact_instructions import (
                    CHART_ARTIFACT_INSTRUCTIONS,
                    CHART_ARTIFACT_INSTRUCTIONS_WITH_TOOL,
                )
                from huf.ai.artifact_instructions import (
                    AI_ELEMENT_INSTRUCTIONS,
                    MEDIA_ELEMENT_INSTRUCTIONS,
                    MERMAID_ARTIFACT_INSTRUCTIONS,
                    MERMAID_ARTIFACT_INSTRUCTIONS_WITH_TOOL,
                    agent_has_media_tools,
                )

                resolved_tool_names = {tool.name for tool in self.tools}

                if "render_chart" in resolved_tool_names:
                    instructions += CHART_ARTIFACT_INSTRUCTIONS_WITH_TOOL
                else:
                    instructions += CHART_ARTIFACT_INSTRUCTIONS

                element_instructions = AI_ELEMENT_INSTRUCTIONS
                if "render_mermaid" in resolved_tool_names:
                    element_instructions = element_instructions.replace(
                        MERMAID_ARTIFACT_INSTRUCTIONS,
                        MERMAID_ARTIFACT_INSTRUCTIONS_WITH_TOOL,
                    )
                instructions += element_instructions

                if agent_has_media_tools(self.agent_doc):
                    instructions += MEDIA_ELEMENT_INSTRUCTIONS

            if capability_enabled(self.agent_doc, self.effective_model, "document_artifacts"):
                from huf.ai.document_artifact_instructions import (
                    DOCUMENT_ARTIFACT_INSTRUCTIONS,
                    DOCUMENT_EXPORT_TOOL_INSTRUCTIONS,
                    agent_has_document_tools,
                )

                instructions += DOCUMENT_ARTIFACT_INSTRUCTIONS
                if agent_has_document_tools(self.agent_doc):
                    instructions += DOCUMENT_EXPORT_TOOL_INSTRUCTIONS

        # Inject Project-level instructions, if the conversation is scoped to a
        # HUF Project. This layer sits between the Agent's own instructions
        # (plus all hardcoded scaffolding above) and the conversation-level /
        # per-turn context assembled later in run_agent_sync / run_agent_stream.
        # No project set -> no-op, instructions stay byte-for-byte unchanged.
        if conversation_id:
            try:
                project = frappe.db.get_value("Agent Conversation", conversation_id, "project")
                if project:
                    project_instructions = frappe.db.get_value("HUF Project", project, "instructions")
                    if project_instructions:
                        instructions += "\n\n" + project_instructions
            except Exception as e:
                frappe.log_error(
                    f"Error injecting project instructions: {str(e)}",
                    "Project Instruction Error",
                )

        model_settings = ModelSettings(
            temperature=self.agent_doc.temperature,
            top_p=self.agent_doc.top_p
        )

        model = self.provider.get_model(self.effective_model)

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

def _is_user_allowed(agent_doc, user: str) -> bool:
    """Check if user is allowed to run this agent.

    Thin wrapper kept for backward compatibility with existing callers
    (e.g. huf/ai/handlers/agent_runner.py); delegates to the shared
    huf.ai.agent_access helper, which is now the single source of truth.
    """
    return _check_agent_access(agent_doc, user)

# Canonical lifecycle status values. These must match the Agent Run doctype
# Select options (Queued/Started/Success/Failed), the HTTP acknowledgement
# returned by run_agent_sync, and the frontend AgentRunStatusEvent union in
# frontend/src/hooks/useChatSocket.tsx. Callers may pass lowercase; the wire
# contract is always canonical.
_RUN_STATUS_CANONICAL = {
    "queued": "Queued",
    "started": "Started",
    "success": "Success",
    "failed": "Failed",
}


def _canonical_run_status(status):
    """Map a lifecycle status to its canonical (doctype) spelling."""
    if isinstance(status, str):
        return _RUN_STATUS_CANONICAL.get(status.strip().lower(), status)
    return status


def _emit_run_lifecycle_event(run_doc, conversation, status, extra=None):
    """Emit a realtime lifecycle event for an Agent Run (Queued/Started/Success/Failed)."""
    try:
        message = {
            "type": "agent_run_status",
            "status": _canonical_run_status(status),
            "agent_run_id": run_doc.name,
            "conversation_id": conversation.name,
            "agent": run_doc.agent,
            "sequence": getattr(run_doc, "sequence", None),
        }
        if extra:
            message.update(extra)
        frappe.publish_realtime(
            event=f"conversation:{conversation.name}",
            message=message,
            user=frappe.session.user,
        )
    except (RuntimeError, TypeError, ValueError, KeyError, AttributeError,
            frappe.DoesNotExistError, frappe.ValidationError, frappe.PermissionError) as exc:
        # Non-critical UI notification; do not fail the run.
        frappe.logger("huf").debug(f"Realtime publish failed: {exc!s}")


def _emit_conversation_title_updated(conversation_name, title):
    """Emit a realtime event when a conversation title is auto-named."""
    try:
        owner = frappe.db.get_value("Agent Conversation", conversation_name, "owner")
        if not owner:
            return
        frappe.publish_realtime(
            event=f"conversation:{conversation_name}",
            message={
                "type": "conversation_title_updated",
                "conversation_id": conversation_name,
                "title": title,
            },
            user=owner,
        )
    except (RuntimeError, TypeError, ValueError, KeyError, AttributeError,
            frappe.DoesNotExistError, frappe.ValidationError, frappe.PermissionError) as exc:
        # Non-critical UI notification; do not fail the title update.
        frappe.logger("huf").debug(f"Realtime title update publish failed: {exc!s}")


def _parse_prompt_cache_options(prompt_cache_options):
    """Parse prompt caching options passed via API/runtime and return a dict."""
    if not prompt_cache_options:
        return {}

    if isinstance(prompt_cache_options, dict):
        return prompt_cache_options

    if isinstance(prompt_cache_options, str):
        try:
            parsed = json.loads(prompt_cache_options)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}

    return {}


def _resolve_prompt_cache_options(channel_id: str, prompt_cache_options=None) -> dict:
    """
    Resolve prompt-cache controls from runtime overrides + site config defaults.

    Site config (non-UI) format:
    {
      "default": {"openai_prompt_cache_retention": "24h"},
      "channels": {
        "api": {"openai_prompt_cache_retention": "6h"},
        "doc_event": {"openai_prompt_cache_retention": "24h"},
        "sse_stream": {"openai_prompt_cache_retention": "24h"}
      }
    }
    """
    resolved = {}
    site_defaults = frappe.conf.get("huf_prompt_cache_defaults")

    if isinstance(site_defaults, str):
        try:
            site_defaults = json.loads(site_defaults)
        except json.JSONDecodeError:
            site_defaults = {}

    if isinstance(site_defaults, dict):
        default_opts = site_defaults.get("default")
        if isinstance(default_opts, dict):
            resolved.update(default_opts)

        channel_opts = (site_defaults.get("channels") or {}).get((channel_id or "").lower())
        if isinstance(channel_opts, dict):
            resolved.update(channel_opts)

    runtime_opts = _parse_prompt_cache_options(prompt_cache_options)
    if runtime_opts:
        resolved.update(runtime_opts)

    return resolved

def process_tool_call(agent_run, conversation, name=None, args=None, result=None, error=None, is_output=False, tool_call_id=None):
    """Process tool call - handle requests (insert) and outputs (update) separately"""
    try:
        if is_output:
            filters = {
                "agent_run": agent_run,
                "status": "Queued"
            }
            if tool_call_id:
                filters["call_id"] = tool_call_id

            existing_queued = frappe.get_all(
                "Agent Tool Call",
                filters=filters,
                pluck="name",
                limit=1,
                order_by="creation asc"
            )

            if existing_queued:
                doc_id = existing_queued[0]
                doc = frappe.get_doc("Agent Tool Call", doc_id)

                update_data = {}

                if result is not None:
                    # JSON field: store valid JSON-serializable value
                    if isinstance(result, (dict, list)):
                        update_data["tool_result"] = result
                    else:
                        val = str(result)
                        if len(val) > 140000:
                            val = val[:140000]
                        update_data["tool_result"] = {"output": val}

                if error:
                    update_data["status"] = "Failed"
                    update_data["error_message"] = error
                else:
                    update_data["status"] = "Completed"

                doc.update(update_data)
                if not frappe.has_permission("Agent Tool Call", "write", doc=doc):
                    frappe.throw(
                        _("Not permitted to update Agent Tool Call records."),
                        frappe.PermissionError,
                    )
                doc.save()
                return doc.name
            else:
                return None

        else:
            is_mcp_tool = 0
            mcp_server = None

            if name:
                mcp_tool_entry = frappe.db.get_value("MCP Server Tool", {"tool_name": name, "enabled": 1}, "parent")
                if mcp_tool_entry:
                    is_mcp_tool = 1
                    mcp_server = mcp_tool_entry

            result_val = result
            if result_val is not None:
                # JSON field: store valid JSON-serializable value
                if not isinstance(result_val, (dict, list)):
                    val = str(result_val)
                    if len(val) > 140000:
                        val = val[:140000]
                    result_val = {"output": val}

            # Idempotency: a client-side tool call (see client_side_tool.py's
            # ``_get_or_create_call``) already inserted an ``Agent Tool Call``
            # row for this (call_id, agent_run) DURING execution, before this
            # function ever runs. Without this lookup we'd insert a second,
            # unpolled row here and point ``tool_call_ref`` at it instead of
            # the row the frontend/poller are actually using. call_id alone
            # is not unique across runs, so scope the lookup by agent_run too.
            existing_name = (
                frappe.db.get_value(
                    "Agent Tool Call",
                    {"call_id": tool_call_id, "agent_run": agent_run},
                    "name",
                )
                if tool_call_id
                else None
            )

            if existing_name:
                doc = frappe.get_doc("Agent Tool Call", existing_name)

                update_data = {}
                if name and not doc.tool:
                    update_data["tool"] = name
                if not doc.is_mcp_tool:
                    update_data["is_mcp_tool"] = is_mcp_tool
                if mcp_server and not doc.mcp_server:
                    update_data["mcp_server"] = mcp_server
                if args and not doc.tool_args:
                    update_data["tool_args"] = json.dumps(args)
                if result_val is not None and not doc.tool_result:
                    update_data["tool_result"] = result_val
                if error and not doc.error_message:
                    update_data["error_message"] = error
                if conversation and not doc.conversation:
                    update_data["conversation"] = conversation

                if update_data:
                    doc.update(update_data)
                    if not frappe.has_permission("Agent Tool Call", "write", doc=doc):
                        frappe.throw(
                            _("Not permitted to update Agent Tool Call records."),
                            frappe.PermissionError,
                        )
                    doc.save()
                return doc.name

            doc = frappe.get_doc({
                "doctype": "Agent Tool Call",
                "agent_run": agent_run,
                "conversation": conversation,
                "tool": name,
                "is_mcp_tool": is_mcp_tool,
                "mcp_server": mcp_server,
                "tool_args": json.dumps(args) if args else None,
                "tool_result": result_val,
                "error_message": error,
                "status": "Queued",
                "call_id": tool_call_id
            })
            if not frappe.has_permission("Agent Tool Call", "create"):
                frappe.throw(
                    _("Not permitted to create Agent Tool Call records."),
                    frappe.PermissionError,
                )
            doc.insert()
            return doc.name

    except frappe.PermissionError:
        raise
    except Exception as e:
        # Tool-call persistence boundary: any failure here corrupts run audit state.
        frappe.log_error(
            f"Error processing tool call: {str(e)}\n{frappe.get_traceback()}",
            "Agent Tool Call Error"
        )
        return None

def log_tool_call(run_doc, conversation, raw_call, tool_result=None, error=None, is_output=False):
    name = raw_call.get("name") if isinstance(raw_call, dict) else getattr(raw_call, "name", None)
    args = raw_call.get("arguments") if isinstance(raw_call, dict) and not is_output else (getattr(raw_call, "arguments", None) if not is_output else None)
    call_id = raw_call.get("id") if isinstance(raw_call, dict) else getattr(raw_call, "id", None)
    return process_tool_call(
        agent_run=run_doc.name,
        conversation=conversation.name,
        name=name,
        args=args,
        result=tool_result,
        error=error,
        is_output=is_output,
        tool_call_id=call_id
    )

def _run_async_safely(coro):
    """
    Safely execute an asyncio coroutine in a synchronous Frappe context.
    If an event loop is already running (e.g. nested inside a tool call),
    run the coroutine in a new thread, preserving Frappe's database context.
    """
    import asyncio
    import concurrent.futures
    import frappe

    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None

    if current_loop and current_loop.is_running():
        site = frappe.local.site
        user = getattr(frappe.session, "user", None)

        def _thread_worker():
            frappe.init(site)
            frappe.connect()
            if user:
                frappe.set_user(user)
            try:
                return asyncio.run(coro)
            finally:
                frappe.destroy()

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            return executor.submit(_thread_worker).result()
    else:
        return asyncio.run(coro)


@frappe.whitelist()
def run_background_summarization(conversation_name, agent_name):
    """
    Background job to summarize conversation history.
    """
    try:
        from huf.ai.prompt_resolver import resolve_summary_prompt

        agent_doc = frappe.get_doc("Agent", agent_name)
        conv_manager = ConversationManager(agent_name=agent_name)

        history_limit = agent_doc.history_limit or 20
        # Fetch slightly more than limit to check for overflow
        history = conv_manager.get_conversation_history(conversation_name, limit=history_limit + 20)

        if len(history) <= history_limit:
            return

        stored_summary = conv_manager.get_stored_summary(conversation_name)

        # Calculate overflow, ensuring we don't split tool-call pairs
        overflow_count = len(history) - history_limit
        to_summarize, _remaining = safe_history_split(history, overflow_count)

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

        summary_prompt_template = resolve_summary_prompt(agent_doc)
        summary_prompt = summary_prompt_template.replace(
            "{summary_data}", json.dumps(summary_input_data, indent=2)
        )

        messages = [{"role": "user", "content": summary_prompt}]

        # Run completion (sync in this background job context or safely in thread if nested)
        new_summary_text = _run_async_safely(
            get_simple_completion(summary_model, messages, summary_provider)
        )
        if new_summary_text:
            conv_manager.update_stored_summary(conversation_name, new_summary_text)
            frappe.db.commit()  # nosemgrep: justified background-job commit

    except Exception as e:
        # Background job entry point: log full traceback for observability.
        logger.warning(f"Background summarization failed: {e!s}")
        frappe.log_error(
            f"Background summarization failed: {e!s}\n{frappe.get_traceback()}",
            "Agent Background Summarization Error"
        )

@frappe.whitelist()
def generate_conversation_title(conversation_name, agent_name):
    """
    Background job to auto-name conversation based on context.
    """
    try:
        # Check if title is still default to avoid overwriting user changes
        current_title = frappe.db.get_value("Agent Conversation", conversation_name, "title")
        if current_title and not (current_title.startswith("Chat with") or current_title.startswith("Conversation with") or current_title.startswith("Streaming chat with")):
             return

        conv_manager = ConversationManager(agent_name=agent_name)
        history = conv_manager.get_conversation_history(conversation_name, limit=5)

        if not history:
            return

        prompt = f"""
        Analyze the following conversation start and generate a short, concise title (max 6 words).
        The title should summarize the user's intent or the main topic.
        Do not use quotes.
        Conversation:
        {json.dumps(history)}
        """

        agent_doc = frappe.get_doc("Agent", agent_name)
        provider = agent_doc.provider
        model = agent_doc.model

        from huf.ai.providers.litellm import get_simple_completion

        messages = [{"role": "user", "content": prompt}]

        title = _run_async_safely(
            get_simple_completion(model, messages, provider)
        )
        if title:
            title = title.strip().strip('"').strip("'")
            frappe.db.set_value("Agent Conversation", conversation_name, "title", title)
            frappe.db.commit()  # nosemgrep: justified background-job commit
            _emit_conversation_title_updated(conversation_name, title)
    except Exception as e:
        # Background job entry point: log full traceback for observability.
        logger.warning(f"Conversation title generation failed: {e!s}")
        frappe.log_error(
            f"Conversation title generation failed: {e!s}\n{frappe.get_traceback()}",
            "Agent Conversation Title Error"
        )

def _history_without_pending_user_turn(history, skip_user_message: bool):
	"""When the user message was already persisted (e.g. file prepare), drop it from history.

	The current ``prompt`` carries the full agent turn (including OCR context).
	"""
	if skip_user_message and history and history[-1].get("role") == "user":
		return history[:-1]
	return history


def _link_preexisting_user_message(conversation_name: str, run_name: str):
	"""Link an existing unlinked user message in a conversation to the newly created Agent Run."""
	if not conversation_name or not run_name:
		return
	msg_name = frappe.db.get_value(
		"Agent Message",
		{"conversation": conversation_name, "role": "user", "agent_run": ("is", "not set")},
		"name",
		order_by="conversation_index desc",
	)
	if not msg_name:
		unlinked = frappe.get_all(
			"Agent Message",
			filters={"conversation": conversation_name, "role": "user"},
			fields=["name", "agent_run"],
			order_by="conversation_index desc",
			limit=5,
		)
		for m in unlinked:
			if not m.get("agent_run"):
				msg_name = m.name
				break
	if msg_name:
		frappe.db.set_value("Agent Message", msg_name, "agent_run", run_name, update_modified=False)


@frappe.whitelist(allow_guest=True)
def run_agent_sync(
    agent_name: str,
    prompt: str = None,
    provider : str = None,
    model : str = None,
    channel_id: str = None,
    external_id: str = None,
    conversation_id: str = None,
    parent_run_id: str = None,
    orchestration_id: str = None,
    response_format = None,
    flow_run_id: str = None,
    flow_node_id: str = None,
    run_kind: str = None,
    prompt_template: str = None,
    prompt_version = None,
    parent_conversation_id: str = None,
    invoked_by_agent: str = None,
    prompt_cache_options=None,
    files=None,
    skip_user_message: bool = False,
    now=None,
    project: str = None,
):

    if not agent_name:
        frappe.throw(_("Agent Name is required"))
    if not channel_id:
        channel_id = "api"

    # A missing agent and a Guest-not-allowed agent must look identical to a
    # Guest caller — otherwise the exception type (DoesNotExistError vs
    # PermissionError) is an oracle for enumerating agent names.
    try:
        agent_doc = frappe.get_doc("Agent", agent_name)
    except frappe.DoesNotExistError:
        agent_doc = None
    if agent_doc is None or (frappe.session.user == "Guest" and not agent_doc.allow_guest):
        frappe.throw(_("Agent not found or access denied."), frappe.PermissionError)

    if agent_doc.disabled:
        frappe.throw(
            _("Agent '{0}' is disabled.").format(agent_name),
            frappe.ValidationError,
        )

    assert_agent_access(agent_doc, user=frappe.session.user)

    if frappe.session.user != "Guest" and not has_capability(frappe.session.user, "agent.use"):
        frappe.throw(
            _("You are not authorized to use this agent."),
            frappe.PermissionError
        )

    if frappe.session.user == "Guest":
        # Guests may not redirect execution to a caller-chosen provider/model.
        provider = None
        model = None

    resolved_provider, resolved_model, resolved_model_name = _resolve_effective_model(
        agent_doc,
        model=model,
        provider=provider,
    )

    conv_manager = ConversationManager(
        agent_name=agent_name,
        channel=channel_id,
        external_id=external_id
    )
    if agent_doc.persist_conversation:
        conversation = conv_manager.get_or_create_conversation(
            title=f"Chat with {agent_name}",
            conversation_id=conversation_id,
            project=project
        )

    else:
        conversation = conv_manager.create_new_conversation(
            title=f"Chat with {agent_name}",
            project=project
        )

    # if conversation.model:
    #     if conversation.model != model:
    #          frappe.throw(
    #              _("Agent model has changed from {0} to {1}. Please start a new conversation.").format(conversation.model, model),
    #              frappe.ValidationError
    #          )
    # else:

    frappe.db.set_value("Agent Conversation", conversation.name, "model", resolved_model)


    resolved_prompt_template = prompt_template
    if not resolved_prompt_template:
        if agent_doc.prompt_mode == "Local":
            resolved_prompt_template = None
        else:
            resolved_prompt_template = getattr(agent_doc, "agent_prompt", None)

    if resolved_prompt_template and prompt_version:
        prompt_data = frappe.db.get_value("Agent Prompt", resolved_prompt_template, ["prompt_group", "version"], as_dict=True)
        if prompt_data and prompt_data.prompt_group and prompt_data.version != int(prompt_version):
            exact_match = frappe.db.get_value("Agent Prompt", {"prompt_group": prompt_data.prompt_group, "version": int(prompt_version)}, "name")
            if exact_match:
                resolved_prompt_template = exact_match

    sequence = _next_run_sequence(conversation.name)

    runtime_context = {
        "channel_id": channel_id,
        "external_id": external_id,
        "response_format": response_format,
        "prompt_template": prompt_template,
        "prompt_version": prompt_version,
        "resolved_prompt_template": resolved_prompt_template,
        "parent_conversation_id": parent_conversation_id,
        "invoked_by_agent": invoked_by_agent,
        "prompt_cache_options": prompt_cache_options,
        "files": files,
        "skip_user_message": skip_user_message,
    }

    run_doc_data = {
        "doctype": "Agent Run",
        "agent": agent_name,
        "status": "Queued",
        "conversation": conversation.name,
        "prompt": prompt,
        "prompt_template": resolved_prompt_template,
        "model": resolved_model,
        "provider": resolved_provider,
        "parent_run": parent_run_id,
        "is_child": 1 if parent_run_id else 0,
        "agent_orchestration": orchestration_id,
        "sequence": sequence,
        "runtime_context": frappe.as_json(runtime_context),
    }
    # Add flow linkage fields if provided
    if flow_run_id:
        run_doc_data["flow_run"] = flow_run_id
    if flow_node_id:
        run_doc_data["flow_node_id"] = flow_node_id
    if run_kind:
        run_doc_data["run_kind"] = run_kind
    if flow_run_id:
        flow_id = frappe.db.get_value("Flow Run", flow_run_id, "flow_id")
        if flow_id:
            run_doc_data["flow_id"] = flow_id

    if not frappe.has_permission("Agent Run", "create"):
        frappe.throw(
            _("You do not have permission to create an Agent Run."),
            frappe.PermissionError
        )

    run_doc = frappe.get_doc(run_doc_data)
    run_doc.insert()

    execution_kwargs = {
        "agent_name": agent_name,
        "run_id": run_doc.name,
        "conversation_id": conversation.name,
        "prompt": prompt,
        "provider": resolved_provider,
        "model": resolved_model,
        "channel_id": channel_id,
        "external_id": external_id,
        "response_format": response_format,
        "prompt_template": prompt_template,
        "prompt_version": prompt_version,
        "resolved_prompt_template": resolved_prompt_template,
        "parent_conversation_id": parent_conversation_id,
        "invoked_by_agent": invoked_by_agent,
        "prompt_cache_options": prompt_cache_options,
        "files": files,
        "skip_user_message": skip_user_message,
    }

    is_queued = not getattr(agent_doc, "run_immediately", 0) and not _is_truthy(now)

    if is_queued:
        # Queue-first path: persist the Agent Run only. The user message is
        # created later by the worker while holding the conversation lock, so
        # two accepted requests for the same conversation cannot interleave
        # into each other's history. The prompt travels on the run itself.
        safe_commit()
        frappe.enqueue(
            "huf.ai.agent_integration._run_queued_agent",
            queue="default",
            timeout=600,
            is_async=True,
            enqueue_after_commit=True,
            conversation_id=conversation.name,
        )
        _emit_run_lifecycle_event(run_doc, conversation, "queued")
        safe_commit()
        return {
            "success": True,
            "queued": True,
            "status": "Queued",
            "response": None,
            "provider": resolved_provider,
            "agent_run_id": run_doc.name,
            "conversation_id": conversation.name,
            "session_id": conv_manager.session_id,
            "sequence": sequence,
        }

    # Direct path (``now`` override or Agent.run_immediately): preserve the
    # existing immediate behavior — persist the user message up front and
    # execute inline. To keep the ordering guarantee, it must not jump ahead
    # of queued runs for the same conversation and must hold the same lock.
    if _has_queued_runs(conversation.name, exclude_run_id=run_doc.name):
        frappe.throw(
            _(
                "This conversation has queued runs pending. Wait for them to complete before using the direct-execution override."
            ),
            frappe.ValidationError,
        )

    lock_key = _conversation_lock_key(conversation.name)
    lock_acquired = False
    for attempt in range(_DIRECT_LOCK_ATTEMPTS):
        if frappe.cache().set(lock_key, 1, ex=_QUEUE_LOCK_TTL, nx=True):
            lock_acquired = True
            break
        if attempt < _DIRECT_LOCK_ATTEMPTS - 1:
            # Exponential backoff with jitter so concurrent direct-execution
            # waiters on the same conversation don't all retry in lockstep.
            backoff = _DIRECT_LOCK_RETRY_DELAY * (2 ** attempt)
            time.sleep(backoff + random.uniform(0, _DIRECT_LOCK_RETRY_DELAY))

    if not lock_acquired:
        frappe.throw(
            _(
                "This conversation is currently executing another run. Please try the direct-execution override again shortly."
            ),
            frappe.ValidationError,
        )

    # Close the check-then-lock race: a queued run may have been submitted
    # between the _has_queued_runs() check above and the lock acquisition.
    # Re-check while holding the lock; queued runs must not be jumped.
    if _has_queued_runs(conversation.name, exclude_run_id=run_doc.name):
        try:
            frappe.cache().delete(lock_key)
        except Exception as exc:
            # Defensive cleanup: must not mask the queued-runs validation error.
            frappe.logger("huf").debug(f"Cache lock delete failed: {exc!s}")
        frappe.throw(
            _(
                "This conversation has queued runs pending. Wait for them to complete before using the direct-execution override."
            ),
            frappe.ValidationError,
        )

    # Keep the lock alive for long direct runs (same heartbeat as the queued
    # drainer) so it cannot expire mid-run and let a drainer run concurrently.
    heartbeat = _RunHeartbeat(lock_key)
    heartbeat.start()
    try:
        if prompt and not str(prompt).startswith("[SILENT_TRIGGER]") and not skip_user_message:
            conv_manager.add_message(conversation, "user", prompt, resolved_provider, resolved_model, agent_name, run_doc.name)
        else:
            _link_preexisting_user_message(conversation.name, run_doc.name)
        safe_commit()

        return _execute_agent_run(**execution_kwargs)
    finally:
        heartbeat.stop()
        try:
            frappe.cache().delete(lock_key)
        except Exception as exc:
            # Defensive finally cleanup: must not suppress the original exception.
            frappe.logger("huf").debug(f"Cache lock delete failed: {exc!s}")
        # A queued run may have arrived while we held the lock; wake a drainer.
        try:
            if _has_queued_runs(conversation.name):
                _enqueue_drain(conversation.name)
        except Exception as exc:
            # Defensive finally cleanup: must not suppress the original exception.
            frappe.logger("huf").warning(f"Drain enqueue failed: {exc!s}")


def _is_truthy(value):
    """Interpret API/runtime boolean-ish values (e.g. ``now``)."""
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes")
    return bool(value)


@frappe.whitelist(allow_guest=True)
def get_agent_run_status(agent_run_id: str):
    """Return the status/result of an Agent Run for queue-first clients.

    Polling fallback for clients that cannot receive the ``agent_run_status``
    realtime events (guests, external API consumers). Permissions mirror
    ``run_agent_sync``: guests need an agent that allows guest access;
    logged-in users must be allowed to use the agent.
    """
    if not agent_run_id:
        frappe.throw(_("Agent Run ID is required"))

    run = frappe.db.get_value(
        "Agent Run",
        agent_run_id,
        ["name", "agent", "status", "response", "error_message", "conversation"],
        as_dict=True,
    )
    if not run:
        frappe.throw(_("Agent Run not found: {0}").format(agent_run_id), frappe.DoesNotExistError)

    agent_doc = frappe.get_doc("Agent", run.agent)
    assert_agent_access(agent_doc, user=frappe.session.user)

    agent_message_id = None
    if run.status in ("Success", "Failed"):
        agent_message_id = frappe.db.get_value(
            "Agent Message",
            {"agent_run": run.name, "role": "agent"},
            "name",
            order_by="creation desc",
        )

    return {
        "success": True,
        "queued": run.status in ("Queued", "Started"),
        "status": run.status,
        "response": run.response if run.status == "Success" else None,
        "error": run.error_message if run.status == "Failed" else None,
        "agent_run_id": run.name,
        "conversation_id": run.conversation,
        "agent": run.agent,
        "agent_message_id": agent_message_id,
    }


def _update_agent_run_stats(agent_name):
    """Update the denormalized run stats on the Agent doc.

    Uses a single atomic UPDATE that does not bump ``modified`` and performs
    no optimistic-lock read, so parallel runs on the same agent cannot trip
    the ``tabAgent`` TimestampMismatchError race. A stats failure must never
    fail a user run.
    """
    try:
        total_runs = frappe.db.count("Agent Run", filters={"agent": agent_name})
        last_run_time = frappe.db.get_value("Agent Run", {"agent": agent_name}, "start_time", order_by="start_time DESC")
        frappe.db.sql(
            "UPDATE `tabAgent` SET `total_run`=%s, `last_run`=%s WHERE `name`=%s",
            (total_runs, last_run_time, agent_name),
        )
    except frappe.TimestampMismatchError:
        pass
    except Exception as e:
        frappe.logger("huf").warning(
            f"Failed to update run stats for agent '{agent_name}': {e}"
        )


def _notify_sub_agent_failure(agent_name, error_msg, parent_conversation_id, invoked_by_agent, channel_id=None, external_id=None):
    """Sub-Agent Failure Lifecycle Hook: silent auto-awaken trigger + realtime notice."""
    # 1. Silent Auto-Awaken Trigger
    try:
        silent_trigger = f"[SILENT_TRIGGER] The sub-agent '{agent_name}' encountered an error during its background task.\nError:\n{error_msg}"
        # NOTE: no ``now=1`` — the direct path can deadlock against the
        # parent conversation lock.
        frappe.enqueue(
            "huf.ai.agent_integration.run_agent_sync",
            queue="default",
            timeout=300,
            is_async=True,
            agent_name=invoked_by_agent,
            prompt=silent_trigger,
            parent_conversation_id=None,
            conversation_id=parent_conversation_id,
            channel_id=channel_id,
            external_id=external_id,
        )
    except Exception as hook_err:
        frappe.log_error(f"Error in Sub-Agent Failure Hook: {str(hook_err)}", "Agent Integration Error")

    # 2. Real-Time UI Notification
    frappe.publish_realtime(
        event=f"conversation:{parent_conversation_id}",
        message={
            "type": "sub_agent_failed",
            "agent_name": agent_name,
            "status": "Failed",
            "result": error_msg
        },
        user=frappe.session.user
    )


def _execute_agent_run(
    agent_name,
    run_id,
    conversation_id,
    prompt=None,
    provider=None,
    model=None,
    channel_id=None,
    external_id=None,
    response_format=None,
    prompt_template=None,
    prompt_version=None,
    resolved_prompt_template=None,
    parent_conversation_id=None,
    invoked_by_agent=None,
    prompt_cache_options=None,
    files=None,
    skip_user_message=False,
):
    """Execute an agent against an existing Agent Run and conversation.

    Shared execution logic for direct (``now`` / ``run_immediately``) and
    queued runs. The Agent Run is created by the caller; the user message is
    persisted by the caller (direct path) or by the queued worker while
    holding the conversation lock. This function never creates another run
    or user message.
    """
    agent_doc = frappe.get_doc("Agent", agent_name)
    resolved_provider, resolved_model, resolved_model_name = _resolve_effective_model(
        agent_doc,
        model=model,
        provider=provider,
    )

    conv_manager = ConversationManager(
        agent_name=agent_name,
        channel=channel_id,
        external_id=external_id
    )
    conversation = frappe.get_doc("Agent Conversation", conversation_id)
    run_doc = frappe.get_doc("Agent Run", run_id)
    run_doc.db_set("start_time", now_datetime())

    # Optimized history fetching with dynamic limit + buffer.
    # This turn's user message was persisted just before execution: inline
    # (direct path) or by the queued worker under the conversation lock.
    # The lock serializes queued runs per conversation, so the trailing
    # user message is always this run's own turn — drop it from history
    # because ``prompt`` carries the full turn.
    user_message_persisted = skip_user_message or bool(
        prompt and not str(prompt).startswith("[SILENT_TRIGGER]")
    )
    fetch_limit = (agent_doc.history_limit or 20) + 10
    history = conv_manager.get_conversation_history(conversation.name, limit=fetch_limit)
    history = _history_without_pending_user_turn(history, user_message_persisted)

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
        transaction_checkpoint(reason="agent_streaming_progress")
        return {
            "success": True,
            "response": f"Orchestration started: {orch_name}",
            "orchestration_id": orch_name,
            "mode": "multi_run",
            "agent_run_id": run_doc.name
        }


    try:
        frappe.db.set_value("Agent Run", run_doc.name, "status", "Started", update_modified=True)
        _emit_run_lifecycle_event(run_doc, conversation, "started")
        safe_commit()
        transaction_checkpoint(reason="agent_streaming_progress")

        _update_agent_run_stats(agent_name)
        transaction_checkpoint(reason="agent_streaming_progress")

        manager = AgentManager(
            agent_name,
            provider_override=resolved_provider,
            model_override=resolved_model,
            conversation_id=conversation_id,
        )

        if (prompt_template or prompt_version) and resolved_prompt_template:
            manager.agent_doc.prompt_mode = "Template"
            manager.agent_doc.agent_prompt = resolved_prompt_template
            manager.agent_doc.prompt_version_locked = 0

        agent = manager.create_agent(memory_query=prompt, conversation_id=conversation_id)

        # Build knowledge context for mandatory sources
        knowledge_context = None
        try:
            from huf.ai.knowledge.context_builder import build_knowledge_context, inject_knowledge_context

            knowledge_context = build_knowledge_context(
                agent_name=agent_name,
                user_query=prompt,
                max_tokens=agent_doc.max_knowledge_tokens or 4000
            )
        except (ImportError, ValueError, TypeError, KeyError, AttributeError, RuntimeError,
                frappe.DoesNotExistError, frappe.ValidationError, frappe.PermissionError):
            # Abort the run instead of continuing with partial state.
            # Mandatory knowledge context is required for this agent; failing here
            # prevents inconsistent tool-call messages from being committed later.
            error_msg = _("Failed to build knowledge context for this agent run.")
            frappe.log_error(
                frappe.get_traceback(),
                "Knowledge context build failed — aborting agent run"
            )
            run_doc.db_set("status", "Failed", update_modified=True)
            run_doc.db_set("error_message", error_msg)
            return {
                "success": False,
                "error": error_msg,
                "agent_run_id": run_doc.name,
                "conversation_id": conversation.name,
                "session_id": conv_manager.session_id,
            }

        # Parse response_format if string
        if response_format and isinstance(response_format, str):
            try:
                response_format = json.loads(response_format)
            except json.JSONDecodeError:
                pass

        resolved_prompt_cache = _resolve_prompt_cache_options(channel_id, prompt_cache_options)

        context = {
            "channel": channel_id,
            "external_id": external_id,
            "conversation_history": history,
            "agent_name": agent_name,
            "response_format": response_format,
            "conversation_id": conversation.name,
            "agent_run_id": run_doc.name,
            "prompt_cache_options": resolved_prompt_cache,
            "files": files,
        }

        context_strategy = agent_doc.context_strategy or "Summarize"
        history_limit = agent_doc.history_limit or 20
        stored_summary = conv_manager.get_stored_summary(conversation.name)

        if context_strategy == "Summarize":
            # Just inject the stored summary. Actual summarization happens in background.
            if stored_summary:
                history = [{"role": "system", "content": f"Context Summary: {stored_summary}"}] + history
        elif context_strategy == "FIFO":
            if len(history) > history_limit:
                history = safe_history_slice(history, history_limit)

        # Inject Conversation Data Snapshot if enabled and auto-injection is not disabled (defaults to 1 if not specified)
        if agent_doc.enable_conversation_data and getattr(agent_doc, "inject_conversation_data", 1) and conversation.conversation_data:
             try:
                data_snapshot = json.loads(conversation.conversation_data)
                # Filter to only show name/value to save tokens, excluding hidden/non-injected variables
                simplified_items = {}
                for item in data_snapshot.get("items", []):
                    if item.get("auto_inject") is False or item.get("inject_mode") == "hidden":
                        continue
                    simplified_items[item["name"]] = item["value"]

                if simplified_items:
                    data_msg = f"CURRENT MEMORY STATE (Conversation Data): {json.dumps(simplified_items, ensure_ascii=False)}"
                    # Insert right after summary but before user messages
                    insert_idx = 1 if stored_summary else 0
                    history.insert(insert_idx, {"role": "system", "content": data_msg})
             except (json.JSONDecodeError, TypeError, KeyError) as e:
                 frappe.logger("huf").warning(
                     f"Skipped conversation_data memory snapshot for conversation "
                     f"{conversation.name}: {e}"
                 )

        # Inject User-usage skill prompts before the current user message.
        try:
            from huf.ai.skills.loader import get_skill_prompts

            skill_prompts = get_skill_prompts(agent_name)
            user_prompts = [p["body"] for p in skill_prompts if p["usage"] == "User"]
            if user_prompts:
                prompt = "\n\n".join(user_prompts) + "\n\n" + (prompt or "")
        except Exception as e:
            frappe.log_error(
                f"Error injecting user skill prompts: {str(e)}",
                "Skill Prompt Error",
            )

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

        from huf.ai.context_segments import compute_segment_tokens, compute_prefix_breakpoints
        segment_tokens = compute_segment_tokens(
            agent_doc, agent, resolved_model_name, resolved_provider, history, knowledge_context, prompt
        )
        prefix_breakpoints = compute_prefix_breakpoints(
            agent_doc, agent, resolved_model_name, resolved_provider, history
        )

        context = {
            "channel": channel_id,
            "external_id": external_id,
            "conversation_history": history,
            "agent_name": agent_name,
            "response_format": response_format,
            "conversation_id": conversation.name,
            "agent_run_id": run_doc.name,
            "prompt_cache_options": resolved_prompt_cache,
            "files": files,
        }
        async def _run_with_mcp_pool():
            from huf.ai.mcp_client import mcp_session_pool
            async with mcp_session_pool():
                return await RunProvider.run(agent, enhanced_prompt, resolved_provider, resolved_model_name, context)

        result = _run_async_safely(_run_with_mcp_pool())

        new_items = getattr(result, "new_items", []) or []

        client_side_tool_calls = []
        tool_call_message_map = {}  # call_id -> Agent Message name

        for item in new_items:
            if item.type == "tool_call_item":
                raw = item.raw_item
                tool_call_id = log_tool_call(run_doc, conversation, raw, is_output=False)

                tool_name = getattr(raw, "name", "Unknown Tool")
                tool_args = getattr(raw, "arguments", "{}")
                call_id = getattr(raw, "id", None)

                tool_type = frappe.db.get_value("Agent Tool Function", {"tool_name": tool_name}, "types")
                if tool_type == "Client Side Tool":
                    client_side_tool_calls.append({
                         "id": call_id,
                         "type": "function",
                         "function": {
                             "name": tool_name,
                             "arguments": tool_args
                        },
                        # Agent Tool Call docname — the unambiguous key the frontend
                        # sends back to huf.ai.client_side_tool.submit_client_tool_result.
                        # ``call_id`` (above) is kept for backward compatibility.
                        "tool_call_ref": tool_call_id
                    })

                msg_content = f"Requesting Tool: {tool_name}\nArguments: {tool_args}"

                message_doc = conv_manager.add_message(
                    conversation,
                    role="agent",
                    content=msg_content,
                    provider=resolved_provider,
                    model=resolved_model,
                    agent=agent_name,
                    run_name=run_doc.name,
                    kind="Tool Call",
                    tool_call=tool_call_id,
                    tool_call_id=call_id,
                    tool_calls=[{
                        "id": call_id,
                        "type": "function",
                        "function": {"name": tool_name, "arguments": tool_args}
                    }]
                )
                if call_id:
                    tool_call_message_map[call_id] = message_doc.name
                transaction_checkpoint(reason="agent_streaming_progress")

            elif item.type == "tool_call_output_item":
                raw = item.raw_item
                try:
                    tool_result = json.loads(raw.get("output")) if raw and raw.get("output") else None
                except (json.JSONDecodeError, TypeError):
                    frappe.log_error(
                        frappe.get_traceback(),
                        "Tool result JSON parse failed — using raw output"
                    )
                    tool_result = raw.get("output")

                updated_tool_call_id = log_tool_call(run_doc, conversation, raw, tool_result=tool_result, is_output=True)

                if updated_tool_call_id:
                    # Get tool call doc to check status
                    tool_call_doc = frappe.get_doc("Agent Tool Call", updated_tool_call_id)
                    tool_status = tool_call_doc.status or "Completed"
                    tool_name = tool_call_doc.tool or "Unknown Tool"
                    call_id = tool_call_doc.call_id

                    # Update the original Tool Call message in place so request + result
                    # are stored in a single Agent Message row.
                    message_name = tool_call_message_map.get(call_id)
                    if not message_name:
                        message_name = frappe.db.get_value("Agent Message", {"tool_call": updated_tool_call_id}, "name")

                    tool_call_dict = {
                        "id": call_id,
                        "type": "function",
                        "function": {"name": tool_name, "arguments": tool_call_doc.tool_args or "{}"}
                    }

                    from huf.ai.conversation_manager import update_tool_call_message
                    updated = update_tool_call_message(
                        message_name=message_name,
                        tool_call_id=call_id,
                        tool_call=[tool_call_dict],
                        result_content=tool_result,
                        agent_doc=agent_doc,
                    )

                    if not updated:
                        # Fallback: create a separate Tool Result message if the
                        # original Tool Call message could not be updated.
                        tool_result_str = str(tool_result) if tool_result is not None else ""
                        tool_result_summary = (tool_result_str[:200] + "...") if len(tool_result_str) > 200 else tool_result_str
                        max_context_chars = int(getattr(agent_doc, "max_context_chars", 2000))
                        use_reference = len(tool_result_str) > max_context_chars

                        result_message = conv_manager.add_message(
                            conversation,
                            role="tool",
                            content=tool_result_str,
                            provider=resolved_provider,
                            model=resolved_model,
                            agent=agent_name,
                            run_name=run_doc.name,
                            kind="Tool Result",
                            tool_call=updated_tool_call_id,
                            tool_call_id=call_id,
                            record_kind="tool_result",
                            context_policy="include_reference" if use_reference else "include_full",
                            context_summary=tool_result_summary,
                            reference_doctype="Agent Tool Call",
                            reference_name=updated_tool_call_id
                        )
                        message_name = result_message.name

                    # Emit socket event for tool call completed/failed
                    # Always emit, even if message not found (e.g., for image generation which creates its own message)
                    # For image generation, try to find the Image message created by the tool
                    if not message_name and tool_name == "generate_image":
                        # Look for Image message created by this tool call
                        image_message = frappe.db.get_value(
                            "Agent Message",
                            {
                                "conversation": conversation.name,
                                "agent_run": run_doc.name,
                                "kind": "Image"
                            },
                            "name",
                            order_by="creation desc",
                            limit=1
                        )
                        if image_message:
                            message_name = image_message

                    event_type = "tool_call_completed" if tool_status == "Completed" else "tool_call_failed"
                    frappe.publish_realtime(
                        event=f'conversation:{conversation.name}',
                        message={
                            "type": event_type,
                            "conversation_id": conversation.name,
                            "agent_run_id": run_doc.name,
                            "tool_call_id": updated_tool_call_id,
                            "message_id": message_name or None,
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
        cache_creation_tokens = 0
        cache_skipped_unsupported_model = False

        if usage:

            if isinstance(usage, dict):
                input_tokens = (getattr(usage, "prompt_tokens", usage.get("input_tokens", 0)) if isinstance(usage, dict) else 0) or 0
                output_tokens = (getattr(usage, "completion_tokens", usage.get("output_tokens", 0)) if isinstance(usage, dict) else 0) or 0

                details = getattr(usage, "prompt_tokens_details", None)
                if not details and isinstance(usage, dict):
                    details = usage.get("prompt_tokens_details")

                if details:
                    if isinstance(details, dict):
                        cached_tokens = details.get("cached_tokens") or details.get("cache_hit_tokens") or 0
                        cache_creation_tokens = (
                            details.get("cache_creation_input_tokens")
                            or details.get("cache_write_tokens")
                            or details.get("cache_creation_tokens")
                            or 0
                        )
                    else:
                        cached_tokens = getattr(details, "cached_tokens", None) or getattr(details, "cache_hit_tokens", None) or 0
                        cache_creation_tokens = (
                            getattr(details, "cache_creation_input_tokens", None)
                            or getattr(details, "cache_write_tokens", None)
                            or getattr(details, "cache_creation_tokens", None)
                            or 0
                        )
                elif isinstance(usage, dict):
                    cached_tokens = usage.get("cached_tokens") or usage.get("cache_hit_tokens") or 0
                    cache_creation_tokens = (
                        usage.get("cache_creation_tokens")
                        or usage.get("cache_creation_input_tokens")
                        or usage.get("cache_write_input_tokens")
                        or usage.get("cache_miss_tokens")
                        or 0
                    )

                if not cache_creation_tokens and isinstance(usage, dict):
                    cache_creation_tokens = (
                        usage.get("cache_creation_tokens")
                        or usage.get("cache_creation_input_tokens")
                        or usage.get("cache_write_input_tokens")
                        or usage.get("cache_miss_tokens")
                        or 0
                    )

                if isinstance(usage, dict):
                    cache_skipped_unsupported_model = bool(usage.get("cache_skipped_unsupported_model", False))

            else:
                input_tokens = (getattr(usage, "input_tokens", getattr(usage, "prompt_tokens", 0))) or 0
                output_tokens = (getattr(usage, "output_tokens", getattr(usage, "completion_tokens", 0))) or 0
                cached_tokens = getattr(usage, "cached_tokens", None) or 0
                cache_creation_tokens = (
                    getattr(usage, "cache_creation_tokens", None)
                    or getattr(usage, "cache_creation_input_tokens", None)
                    or getattr(usage, "cache_write_input_tokens", None)
                    or getattr(usage, "cache_miss_tokens", None)
                    or 0
                )
                cache_skipped_unsupported_model = bool(getattr(usage, "cache_skipped_unsupported_model", False))

            cached_tokens = cached_tokens or 0
            cache_creation_tokens = cache_creation_tokens or 0

            try:
                # Prefer cost directly from the result
                cost = getattr(result, "cost", 0)
                if not cost:
                    from huf.ai.cost_calculator import calculate_cost

                    pricing_model = _normalize_model_name(resolved_model_name, resolved_provider)

                    mock_response = {
                        "usage": {
                            "prompt_tokens": input_tokens,
                            "completion_tokens": output_tokens,
                            "total_tokens": input_tokens + output_tokens
                        },
                        # Use the normalized model name (e.g. openai/gpt-4o) so LiteLLM's
                        # built-in price table can resolve it.
                        "model": pricing_model
                    }

                    if cached_tokens > 0:
                        mock_response["usage"]["prompt_tokens_details"] = {"cached_tokens": cached_tokens}

                    cost, _source = calculate_cost(
                        model_name=resolved_model_name,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        cached_tokens=cached_tokens,
                        litellm_response=mock_response
                    )
            except (ImportError, AttributeError, TypeError, ValueError, KeyError, RuntimeError) as e:
                frappe.logger("huf").warning(
                    f"Cost calculation failed for {resolved_model_name} in sync: {e}"
                )
                cost = 0.0

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
            except (RuntimeError, TypeError, ValueError,
                    frappe.ValidationError, frappe.PermissionError) as e:
                frappe.logger("huf").warning(
                    f"Failed to update conversation metrics: {str(e)}"
                )

            frappe.db.set_value("Agent Run", run_doc.name, {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cached_tokens": cached_tokens,
                "cost": cost,
                "usage_snapshot": json.dumps({
                    "schema_version": 1,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "cache_read_tokens": cached_tokens if usage else None,
                    "cache_creation_tokens": cache_creation_tokens if usage else None,
                    "cache_miss_tokens": cache_creation_tokens if usage else None,
                    "cache_skipped_unsupported_model": cache_skipped_unsupported_model,
                    "total_tokens": total_tokens,
                    "completeness": "provider_reported" if usage else "estimated",
                    "segment_tokens": segment_tokens,
                    "prefix_breakpoints": prefix_breakpoints,
                }),
                "cost_source": "provider_reported" if getattr(result, "cost", None) is not None else "unknown",
                "cost_calculation_status": "calculated" if cost is not None else "unavailable",
            })

        agent_message = conv_manager.add_message(conversation, "agent", final_output, resolved_provider, resolved_model, agent_name, run_doc.name)

        r_res = context.get("reasoning_resolution") if context else None
        r_snap = json.dumps(r_res.to_dict()) if r_res else None

        run_update = {
            "status": "Success",
            "response": final_output,
            "prompt": prompt,
            "model": resolved_model,
            "provider": resolved_provider,
            "end_time": now_datetime()
        }
        if r_snap:
            run_update["reasoning_snapshot"] = r_snap

        frappe.db.set_value("Agent Run", run_doc.name, run_update, update_modified=True)
        try:
            frappe.enqueue(
                "huf.ai.memory_tools.extract_memory_from_run",
                queue="default",
                timeout=300,
                is_async=True,
                enqueue_after_commit=True,
                run_id=run_doc.name,
            )
        except (RuntimeError, TypeError, ValueError, KeyError, AttributeError,
                frappe.DoesNotExistError, frappe.ValidationError, frappe.PermissionError) as e:
            frappe.logger("huf").warning(f"Memory extraction enqueue failed: {e!s}")
        _emit_run_lifecycle_event(
            run_doc,
            conversation,
            "success",
            {
                "response": final_output,
                "agent_message_id": getattr(agent_message, "name", None),
            },
        )
        safe_commit()
        transaction_checkpoint(reason="agent_streaming_progress")

        # Handle Sub-Agent Success Lifecycle Hook
        if parent_conversation_id and invoked_by_agent:
            # 1. Silent Auto-Awaken Trigger
            # We bypass Agent Message insertion and use a silent trigger to hide the intermediate execution from the UI
            try:
                silent_trigger = f"[SILENT_TRIGGER] The sub-agent '{agent_name}' has responded. IMPORTANT: DO NOT assume this means the task was successful. Read the result carefully and appropriately relay it to the user.\nResult:\n{final_output}"
                # NOTE: no ``now=1`` here. The parent conversation may still be
                # locked by the worker that just finished this sub-agent; the
                # direct path would fail to acquire the lock and the awaken
                # would be lost (deadlock). Going through the queue-first
                # drainer lets the post-release sweep pick it up.
                frappe.enqueue(
                    "huf.ai.agent_integration.run_agent_sync",
                    queue="default",
                    timeout=300,
                    is_async=True,
                    agent_name=invoked_by_agent,
                    prompt=silent_trigger,
                    parent_conversation_id=None,
                    conversation_id=parent_conversation_id,
                    channel_id=channel_id,
                    external_id=external_id,
                )
            except (ValueError, KeyError, TypeError, AttributeError,
                    frappe.DoesNotExistError, frappe.ValidationError,
                    frappe.PermissionError, frappe.TimestampMismatchError) as hook_err:
                frappe.logger("huf").warning(f"Agent hook dispatch failure: {hook_err!s}")

            except Exception as hook_err:  # boundary exception handler: agent hook dispatcher
                frappe.log_error(
                    f"Error in Sub-Agent Success Hook: {str(hook_err)}\n{frappe.get_traceback()}",
                    "Agent Integration Error"
                )

            # 3. Real-Time UI Notification
            frappe.publish_realtime(
                event=f"conversation:{parent_conversation_id}",
                message={
                    "type": "sub_agent_completed",
                    "agent_name": agent_name,
                    "status": "Success",
                    "result": final_output
                },
                user=frappe.session.user
            )

        # Auto-naming check
        if agent_doc.autonaming_of_conversation_title:
            conv_title = conversation.title
            if conv_title and (
                conv_title.startswith("Chat with")
                or conv_title.startswith("Conversation with")
                or conv_title.startswith("Streaming chat with")
            ):
                frappe.enqueue(
                    "huf.ai.agent_integration.generate_conversation_title",
                    queue="default",
                    conversation_name=conversation.name,
                    agent_name=agent_name
                )

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
            "provider": resolved_provider,
            "agent_run_id": run_doc.name,
            "conversation_id": conversation.name,
            "session_id": conv_manager.session_id
        }

    except ProviderUnavailableError as e:
        # Provider-level failure (connection refused, model not pulled, bad
        # model prefix, empty response). Surface it as a failed run — never
        # as assistant message content.
        error_msg = str(e)
        log_error_msg = getattr(e, "log_message", error_msg)
        run_doc.db_set("status", "Failed", update_modified=True)
        run_doc.db_set("error_message", error_msg)
        frappe.log_error(f"Provider unavailable for agent '{agent_name}': {log_error_msg}", "Huf Provider")
        _emit_run_lifecycle_event(run_doc, conversation, "failed", {"error": error_msg})

        # Handle Sub-Agent Failure Lifecycle Hook
        if parent_conversation_id and invoked_by_agent:
            _notify_sub_agent_failure(agent_name, error_msg, parent_conversation_id, invoked_by_agent, channel_id, external_id)

        return {
            "success": False,
            "error": error_msg,
            "agent_run_id": run_doc.name,
            "conversation_id": conversation.name,
            "session_id": conv_manager.session_id
        }

    except Exception as e:
        error_msg = str(e)

        if "ContextWindowExceededError" in error_msg:
            try:
                frappe.db.set_value("Agent Conversation", conversation.name, "is_active", 0)
                transaction_checkpoint(reason="agent_streaming_progress")

                error_msg = _("This conversation has exceeded the maximum token limit. Please start a new conversation to continue.")

                conv_manager.add_message(
                    conversation=conversation,
                    role="agent",
                    content=error_msg,
                    provider=resolved_provider,
                    model=resolved_model,
                    agent=agent_name,
                    run_name=run_doc.name,
                    kind="Error"
                )
                transaction_checkpoint(reason="agent_streaming_progress")
            except (RuntimeError, TypeError, ValueError, KeyError, AttributeError,
                    frappe.DoesNotExistError, frappe.ValidationError, frappe.PermissionError) as inner_e:
                frappe.logger("huf").warning(
                    f"Failed to handle context window error in sync: {str(inner_e)}"
                )

        elif "RateLimitError" in error_msg:
            try:
                error_msg = _("You have reached the API rate limit (requests/tokens per minute). Please wait a moment and try again.")

                conv_manager.add_message(
                    conversation=conversation,
                    role="agent",
                    content=error_msg,
                    provider=resolved_provider,
                    model=resolved_model,
                    agent=agent_name,
                    run_name=run_doc.name,
                    kind="Error"
                )
                transaction_checkpoint(reason="agent_streaming_progress")
            except (RuntimeError, TypeError, ValueError, KeyError, AttributeError,
                    frappe.DoesNotExistError, frappe.ValidationError, frappe.PermissionError) as inner_e:
                frappe.logger("huf").warning(
                    f"Failed to handle rate limit error in sync: {str(inner_e)}"
                )

        run_doc.db_set("status", "Failed", update_modified=True)
        run_doc.db_set("error_message", error_msg)
        frappe.log_error(f"Agent Run Error: {frappe.get_traceback()}", "Huf")
        _emit_run_lifecycle_event(run_doc, conversation, "failed", {"error": error_msg})

        # Handle Sub-Agent Failure Lifecycle Hook
        if parent_conversation_id and invoked_by_agent:
            # 1. Silent Auto-Awaken Trigger
            try:
                silent_trigger = f"[SILENT_TRIGGER] The sub-agent '{agent_name}' encountered an error during its background task.\nError:\n{error_msg}"
                # NOTE: no ``now=1`` — see the success hook above; the direct
                # path can deadlock against the parent conversation lock.
                frappe.enqueue(
                    "huf.ai.agent_integration.run_agent_sync",
                    queue="default",
                    timeout=300,
                    is_async=True,
                    agent_name=invoked_by_agent,
                    prompt=silent_trigger,
                    parent_conversation_id=None,
                    conversation_id=parent_conversation_id,
                    channel_id=channel_id,
                    external_id=external_id,
                )
            except (ValueError, KeyError, TypeError, AttributeError,
                    frappe.DoesNotExistError, frappe.ValidationError,
                    frappe.PermissionError, frappe.TimestampMismatchError) as hook_err:
                frappe.logger("huf").warning(f"Agent hook dispatch failure: {hook_err!s}")

            except Exception as hook_err:  # boundary exception handler: agent hook dispatcher
                frappe.log_error(
                    f"Error in Sub-Agent Failure Hook: {str(hook_err)}\n{frappe.get_traceback()}",
                    "Agent Integration Error"
                )

            # 3. Real-Time UI Notification
            frappe.publish_realtime(
                event=f"conversation:{parent_conversation_id}",
                message={
                    "type": "sub_agent_failed",
                    "agent_name": agent_name,
                    "status": "Failed",
                    "result": error_msg
                },
                user=frappe.session.user
            )

        return {
            "success": False,
            "error": error_msg,
            "agent_run_id": run_doc.name,
            "conversation_id": conversation.name,
            "session_id": conv_manager.session_id
        }


# Conversation-scoped execution lock for queued runs. Serializes workers of
# the same conversation (so a history snapshot never observes a later turn)
# without blocking runs of other conversations. Uses the same cache set
# nx/ex convention as huf/ai/knowledge/indexer.py.
_QUEUE_LOCK_TTL = 600
_QUEUE_HEARTBEAT_INTERVAL = 180  # refresh lock every 3 minutes
_QUEUE_ORPHANED_QUEUED_AGE = 60  # seconds before a Queued run is considered orphaned
_DIRECT_LOCK_ATTEMPTS = 3
_DIRECT_LOCK_RETRY_DELAY = 1


def _conversation_lock_key(conversation_id: str) -> str:
    return f"agent_run_conv_{conversation_id}"


def _next_run_sequence(conversation_id: str) -> int:
    """Return the next per-conversation sequence number (atomic via Redis INCR)."""
    seq_key = f"agent_run_seq:{conversation_id}"
    try:
        return int(frappe.cache().incr(seq_key))
    except (RuntimeError, TypeError, ValueError, AttributeError):
        # Redis/cache unavailable: gaps are acceptable; 0 lets the drain loop fall
        # back to creation-time ordering.
        return 0


def _next_queued_run(conversation_id: str):
    """Return the oldest Queued Agent Run name for a conversation, or None."""
    return frappe.db.get_value(
        "Agent Run",
        filters={"conversation": conversation_id, "status": "Queued"},
        fieldname="name",
        order_by="sequence asc, creation asc",
    )


def _has_queued_runs(conversation_id: str, exclude_run_id: str = None) -> bool:
    filters = {"conversation": conversation_id, "status": "Queued"}
    if exclude_run_id:
        filters["name"] = ("!=", exclude_run_id)
    return bool(frappe.db.exists("Agent Run", filters))


def _enqueue_drain(conversation_id: str):
    """Wake a drainer for this conversation. Safe to call repeatedly."""
    frappe.enqueue(
        "huf.ai.agent_integration._run_queued_agent",
        queue="default",
        timeout=_QUEUE_LOCK_TTL,
        is_async=True,
        conversation_id=conversation_id,
    )


def _reset_run_to_queued(run_id: str, error_message: str = None):
    """Recover a run that was lost by a dead worker."""
    try:
        values = {"status": "Queued"}
        if error_message:
            values["error_message"] = error_message
        frappe.db.set_value("Agent Run", run_id, values, update_modified=True)
        frappe.db.commit()
    except Exception as exc:  # top-level recovery helper
        frappe.logger("huf").debug(f"Failed to reset run {run_id} to queued: {exc!s}")


class _RunHeartbeat:
    """Keep the conversation lock alive while a run executes."""

    def __init__(self, lock_key: str, interval: int = _QUEUE_HEARTBEAT_INTERVAL):
        self.lock_key = lock_key
        self.interval = interval
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)

    def _loop(self):
        while not self._stop.wait(self.interval):
            try:
                frappe.cache().expire(self.lock_key, _QUEUE_LOCK_TTL)
            except Exception as exc:  # worker-thread heartbeat: must never kill the heartbeat thread
                frappe.logger("huf").debug(f"Lock heartbeat renewal failed for {self.lock_key}: {exc!s}")


def _run_queued_agent(lock_attempt=0, **kwargs):
    """Background drainer for a single conversation.

    Acquires the conversation-scoped execution lock and processes every queued
    run for this conversation in strict sequence order. If another drainer
    already holds the lock, this job exits immediately — the holder will drain
    everything. After releasing the lock, a final re-check enqueues a sweeper
    in case a run was submitted during the final SELECT.
    """
    conversation_id = kwargs.get("conversation_id")
    if not conversation_id:
        return

    lock_key = _conversation_lock_key(conversation_id)

    if not frappe.cache().set(lock_key, 1, ex=_QUEUE_LOCK_TTL, nx=True):
        # Another worker is draining this conversation; it will pick up all
        # queued runs including any submitted while this job was waiting.
        return

    last_result = None
    try:
        while True:
            run_id = _next_queued_run(conversation_id)
            if not run_id:
                break
            run_doc = frappe.get_doc("Agent Run", run_id)
            if run_doc.status != "Queued":
                continue
            last_result = _drain_run(run_doc, lock_key)
        return last_result
    except Exception:
        # Background queue drainer boundary: log full traceback.
        frappe.log_error(f"Conversation drainer failed: {frappe.get_traceback()}", "Huf")
    finally:
        try:
            frappe.cache().delete(lock_key)
        except Exception as exc:
            # Defensive finally cleanup: must not suppress the original exception.
            frappe.logger("huf").debug(f"Cache lock delete failed: {exc!s}")
        # Re-check after releasing lock. If a submit happened between our last
        # SELECT and the delete, enqueue a sweeper so the run is not orphaned.
        try:
            if _has_queued_runs(conversation_id):
                _enqueue_drain(conversation_id)
        except Exception as exc:
            # Defensive finally cleanup: must not suppress the original exception.
            frappe.logger("huf").warning(f"Post-release drain enqueue failed for {conversation_id}: {exc!s}")


def _drain_run(run_doc, lock_key: str):
    """Execute a single queued run while keeping the conversation lock alive."""
    heartbeat = _RunHeartbeat(lock_key)
    heartbeat.start()
    try:
        context = frappe.parse_json(run_doc.runtime_context or "{}")
        execution_kwargs = _build_execution_kwargs(run_doc, context)

        prompt = execution_kwargs.get("prompt")
        if (
            prompt
            and not str(prompt).startswith("[SILENT_TRIGGER]")
            and not execution_kwargs.get("skip_user_message")
        ):
            if not frappe.db.exists("Agent Message", {"agent_run": run_doc.name, "role": "user"}):
                conv_manager = ConversationManager(
                    agent_name=execution_kwargs.get("agent_name"),
                    channel=execution_kwargs.get("channel_id"),
                    external_id=execution_kwargs.get("external_id"),
                )
                conversation = frappe.get_doc("Agent Conversation", run_doc.conversation)
                conv_manager.add_message(
                    conversation,
                    "user",
                    prompt,
                    execution_kwargs.get("provider"),
                    execution_kwargs.get("model"),
                    execution_kwargs.get("agent_name"),
                    run_doc.name,
                )
                safe_commit()
        else:
            _link_preexisting_user_message(run_doc.conversation, run_doc.name)
            safe_commit()

        result = _execute_agent_run(**execution_kwargs)
        return result
    except Exception as e:
        # Worker thread boundary: ensure the queued run is marked failed and logged.
        _fail_queued_run(run_doc.name, str(e))
        try:
            _emit_run_lifecycle_event(
                run_doc,
                SimpleNamespace(name=run_doc.conversation),
                "failed",
                {"error": str(e)},
            )
        except (RuntimeError, TypeError, ValueError, KeyError, AttributeError,
                frappe.DoesNotExistError, frappe.ValidationError, frappe.PermissionError) as exc:
            # Non-critical lifecycle event notification.
            frappe.logger("huf").debug(f"Failed-run lifecycle event emission failed for {run_doc.name}: {exc!s}")
        frappe.log_error(f"Queued agent run failed: {frappe.get_traceback()}", "Huf")
    finally:
        heartbeat.stop()


def _build_execution_kwargs(run_doc, context: dict):
    """Reconstruct execution kwargs from the persisted run doc + runtime context."""
    return {
        "agent_name": run_doc.agent,
        "run_id": run_doc.name,
        "conversation_id": run_doc.conversation,
        "prompt": run_doc.prompt,
        "provider": run_doc.provider,
        "model": run_doc.model,
        "channel_id": context.get("channel_id"),
        "external_id": context.get("external_id"),
        "response_format": context.get("response_format"),
        "prompt_template": context.get("prompt_template"),
        "prompt_version": context.get("prompt_version"),
        "resolved_prompt_template": context.get("resolved_prompt_template"),
        "parent_conversation_id": context.get("parent_conversation_id"),
        "invoked_by_agent": context.get("invoked_by_agent"),
        "prompt_cache_options": context.get("prompt_cache_options"),
        "files": context.get("files"),
        "skip_user_message": context.get("skip_user_message", False),
    }


def _fail_queued_run(run_id, error_message):
    """Mark a queued Agent Run as failed without losing the error."""
    try:
        if run_id:
            frappe.db.set_value("Agent Run", run_id, {
                "status": "Failed",
                "error_message": error_message,
            }, update_modified=True)
            frappe.db.commit()
    except Exception as exc:  # top-level recovery helper
        frappe.logger("huf").warning(f"Failed to mark run {run_id} as Failed: {exc!s}")


def recover_stalled_agent_runs():
    """Scheduler entry point: recover runs left behind by crashed workers.

    Runs marked ``Started`` whose lock has disappeared are reset to ``Queued``
    and re-drained. ``Queued`` runs that have been pending without an active
    lock are also re-drained. Live runs are protected by the heartbeat, which
    keeps the Redis lock alive.
    """
    try:
        # Stale Started runs: if the worker is alive, it still holds the lock.
        # Group in Python rather than in the query so EVERY stale Started run
        # in a conversation is reset — grouping in SQL would recover only one
        # run per conversation per tick and leave the rest stuck.
        started_cutoff = add_to_date(now_datetime(), seconds=-_QUEUE_LOCK_TTL)
        stale_started = frappe.db.get_all(
            "Agent Run",
            filters={"status": "Started", "modified": ("<", started_cutoff)},
            fields=["name", "conversation"],
        )
        stale_by_conversation = {}
        for run in stale_started:
            stale_by_conversation.setdefault(run.conversation, []).append(run)

        drained_conversations = set()
        for conversation, conversation_runs in stale_by_conversation.items():
            lock_key = _conversation_lock_key(conversation)
            try:
                ttl = frappe.cache().ttl(lock_key)
            except (RuntimeError, TypeError, ValueError, AttributeError):
                ttl = None
            if ttl and ttl > 0:
                continue
            for run in conversation_runs:
                _reset_run_to_queued(run.name, _("Worker heartbeat lost; run recovered to queue."))
            _enqueue_drain(conversation)
            drained_conversations.add(conversation)

        # Orphaned Queued runs: a run that has been Queued for longer than the
        # sweep interval without an active lock probably lost its wake-up job.
        # One drain per conversation is enough (the drain is idempotent), so
        # no grouping needed here — drained_conversations dedupes repeats.
        queued_cutoff = add_to_date(now_datetime(), seconds=-_QUEUE_ORPHANED_QUEUED_AGE)
        orphaned = frappe.db.get_all(
            "Agent Run",
            filters={"status": "Queued", "modified": ("<", queued_cutoff)},
            fields=["name", "conversation"],
        )
        for run in orphaned:
            if run.conversation in drained_conversations:
                continue
            lock_key = _conversation_lock_key(run.conversation)
            try:
                ttl = frappe.cache().ttl(lock_key)
            except (RuntimeError, TypeError, ValueError, AttributeError):
                ttl = None
            if ttl and ttl > 0:
                continue
            _enqueue_drain(run.conversation)
            drained_conversations.add(run.conversation)
    except Exception:
        # Scheduler entry point / top-level recovery helper: log full traceback.
        frappe.log_error(f"Agent run recovery failed: {frappe.get_traceback()}", "Huf")


async def run_agent_stream(
    agent_name: str,
    prompt: str,
    provider: str = None,
    model: str = None,
    channel_id: str = None,
    external_id: str = None,
    conversation_id: str = None,
    create_new: bool = False,
    prompt_template: str = None,
    prompt_version = None,
    parent_conversation_id: str = None,
    invoked_by_agent: str = None,
    prompt_cache_options=None,
    skip_user_message: bool = False,
    files=None,
    project: str = None,
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
        # 0. Load the agent, keeping "doesn't exist" and "exists but Guest
        # isn't allowed" indistinguishable to a Guest caller (same generic
        # error) so agent names can't be enumerated by exception type.
        try:
            agent_doc = frappe.get_doc("Agent", agent_name)
        except frappe.DoesNotExistError:
            agent_doc = None
        if agent_doc is None or (frappe.session.user == "Guest" and not agent_doc.allow_guest):
            yield {
                "type": "error",
                "error": "Agent not found or access denied."
            }
            return

        # 0b. Disabled agents cannot run
        if agent_doc.disabled:
            yield {
                "type": "error",
                "error": f"Agent '{agent_name}' is disabled."
            }
            return

        # 1. Guest + Permission Check (User/Role binding)
        try:
            assert_agent_access(agent_doc, user=frappe.session.user)
        except frappe.PermissionError as e:
            yield {
                "type": "error",
                "error": str(e) or "You are not authorized to use this agent."
            }
            return

        # 1b. Capability check for logged-in users
        if frappe.session.user != "Guest" and not has_capability(frappe.session.user, "agent.use"):
            yield {
                "type": "error",
                "error": "You are not authorized to use this agent."
            }
            return

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

        if create_new or not agent_doc.persist_conversation:
            conversation = conv_manager.create_new_conversation(
                title=f"Streaming chat with {agent_name}",
                project=project
            )
        else:
            conversation = conv_manager.get_or_create_conversation(
                title=f"Streaming chat with {agent_name}",
                conversation_id=conversation_id,
                project=project
            )

        # Model Validation
        # if conversation.model:
        #     if conversation.model != model:
        #          yield {
        #              "type": "error",
        #              "error": f"Agent model has changed from {conversation.model} to {model}. Please start a new conversation."
        #          }
        #          return
        # else:
        # Resolve prompt template
        resolved_prompt_template = prompt_template
        if not resolved_prompt_template:
            if agent_doc.get("prompt_mode", "Local") == "Local":
                resolved_prompt_template = None
            else:
                resolved_prompt_template = getattr(agent_doc, "agent_prompt", None)

        if resolved_prompt_template and prompt_version:
            prompt_data = frappe.db.get_value("Agent Prompt", resolved_prompt_template, ["prompt_group", "version"], as_dict=True)
            if prompt_data and prompt_data.prompt_group and prompt_data.version != int(prompt_version):
                exact_match = frappe.db.get_value("Agent Prompt", {"prompt_group": prompt_data.prompt_group, "version": int(prompt_version)}, "name")
                if exact_match:
                    resolved_prompt_template = exact_match

        # Guests may not override the agent's configured provider/model
        if frappe.session.user == "Guest":
            provider = None
            model = None

        resolved_provider, resolved_model, resolved_model_name = _resolve_effective_model(
            agent_doc,
            model=model,
            provider=provider,
        )

        # Persist the effective model override on the conversation so subsequent
        # turns in the same chat continue using it unless explicitly changed again.
        frappe.db.set_value("Agent Conversation", conversation.name, "model", resolved_model)

        context_strategy = agent_doc.context_strategy or "Summarize"
        history_limit = agent_doc.history_limit or 20
        fetch_limit = history_limit + 10

        history = conv_manager.get_conversation_history(conversation.name, limit=fetch_limit)
        history = _history_without_pending_user_turn(history, skip_user_message)

        # Create Agent Run document
        if not frappe.has_permission("Agent Run", "create"):
            yield {
                "type": "error",
                "error": "You do not have permission to create an Agent Run."
            }
            return

        run_doc = frappe.get_doc({
            "doctype": "Agent Run",
            "agent": agent_name,
            "status": "Started",
            "conversation": conversation.name,
            "prompt": prompt,
            "prompt_template": resolved_prompt_template,
            "model": resolved_model,
            "provider": resolved_provider
        })
        run_doc.insert()
        if not skip_user_message:
            conv_manager.add_message(conversation, "user", prompt, resolved_provider, resolved_model, agent_name, run_doc.name)
        else:
            _link_preexisting_user_message(conversation.name, run_doc.name)
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

        manager = AgentManager(
            agent_name,
            provider_override=resolved_provider,
            model_override=resolved_model,
            conversation_id=conversation.name,
        )

        if (prompt_template or prompt_version) and resolved_prompt_template:
            manager.agent_doc.update({
                "prompt_mode": "Template",
                "agent_prompt": resolved_prompt_template,
                "prompt_version_locked": 0
            })

        agent = manager.create_agent(memory_query=prompt, conversation_id=conversation.name)

        resolved_prompt_cache = _resolve_prompt_cache_options(channel_id, prompt_cache_options)

        tool_call_message_map = {}  # call_id -> Agent Message name (used by streaming provider)

        context = {
            "channel": channel_id,
            "external_id": external_id,
            "conversation_history": history,
            "agent_name": agent_name,
            "conversation_id": conversation.name,
            "agent_run_id": run_doc.name,
            "prompt_cache_options": resolved_prompt_cache,
            "_tool_call_message_map": tool_call_message_map,
            "files": files,
        }

        stored_summary = conv_manager.get_stored_summary(conversation.name)

        if context_strategy == "Summarize":
            if stored_summary:
                history = [{"role": "system", "content": f"Context Summary: {stored_summary}"}] + history
        elif context_strategy == "FIFO":
            if len(history) > history_limit:
                history = safe_history_slice(history, history_limit)


        if agent_doc.enable_conversation_data and getattr(agent_doc, "inject_conversation_data", 1) and conversation.conversation_data:
             try:
                data_snapshot = json.loads(conversation.conversation_data)
                # Filter to only show name/value to save tokens, excluding hidden/non-injected variables
                simplified_items = {}
                for item in data_snapshot.get("items", []):
                    if item.get("auto_inject") is False or item.get("inject_mode") == "hidden":
                        continue
                    simplified_items[item["name"]] = item["value"]

                if simplified_items:
                    data_msg = f"CURRENT MEMORY STATE (Conversation Data): {json.dumps(simplified_items, ensure_ascii=False)}"
                    insert_idx = 0
                    for i, m in enumerate(history):
                        if m.get("role") != "system":
                            insert_idx = i
                            break
                    if insert_idx == 0 and history and history[0].get("role") == "system":
                         insert_idx = 1

                    history.insert(insert_idx, {"role": "system", "content": data_msg})
             except (json.JSONDecodeError, TypeError, KeyError) as e:
                 frappe.logger("huf").warning(
                     f"Skipped conversation_data memory snapshot for conversation "
                     f"{conversation.name}: {e}"
                 )

        knowledge_context = None
        try:
            knowledge_context = build_knowledge_context(
                agent_name=agent_name,
                user_query=prompt,
                max_tokens=agent_doc.max_knowledge_tokens or 4000
            )
        except (ImportError, ValueError, TypeError, KeyError, AttributeError, RuntimeError,
                frappe.DoesNotExistError, frappe.ValidationError, frappe.PermissionError):
            # Abort the stream instead of continuing with partial state.
            # Mandatory knowledge context is required for this agent; failing here
            # prevents inconsistent tool-call messages from being committed later.
            error_msg = _("Failed to build knowledge context for this agent run.")
            frappe.log_error(
                frappe.get_traceback(),
                "Knowledge context build failed — aborting agent stream"
            )
            frappe.db.set_value("Agent Run", run_doc.name, {
                "status": "Failed",
                "error_message": error_msg,
                "end_time": now_datetime(),
            }, update_modified=True)
            transaction_checkpoint(reason="agent_streaming_progress")
            yield {
                "type": "error",
                "error": error_msg,
            }
            return

        base_prompt = f"""
            Current user message:
            {prompt}
        """

        if knowledge_context and knowledge_context.get("context_text"):
            enhanced_prompt = inject_knowledge_context(base_prompt, knowledge_context)

            if knowledge_context.get("sources_used"):
                run_doc.db_set({
                    "knowledge_sources_used": json.dumps(knowledge_context["sources_used"]),
                    "chunks_injected": len(knowledge_context.get("chunks_used", []))
                })
        else:
            enhanced_prompt = base_prompt

        from huf.ai.context_segments import compute_segment_tokens, compute_prefix_breakpoints
        segment_tokens = compute_segment_tokens(
            agent_doc, agent, resolved_model_name, resolved_provider, history, knowledge_context, prompt
        )
        prefix_breakpoints = compute_prefix_breakpoints(
            agent_doc, agent, resolved_model_name, resolved_provider, history
        )

        context["conversation_history"] = history

        # Stream from provider
        full_response = ""
        try:
            stream = RunProvider.run_stream(agent, enhanced_prompt, resolved_provider, resolved_model_name, context)

            async for chunk in stream:
                chunk_type = chunk.get("type")

                if chunk_type == "delta":
                    full_response = chunk.get("full_response", full_response)
                    yield chunk

                elif chunk_type == "reasoning":
                    yield chunk

                elif chunk_type == "tool_call":
                    # Log tool call
                    tool_call = chunk.get("tool_call", {})
                    if tool_call:
                        raw_item = SimpleNamespace(
                            name=tool_call.get("function", {}).get("name", ""),
                            arguments=tool_call.get("function", {}).get("arguments", "{}"),
                            id=tool_call.get("id")
                        )
                        tool_call_id = log_tool_call(run_doc, conversation, raw_item, is_output=False)

                        tool_name = getattr(raw_item, "name", "Unknown Tool")
                        tool_args = getattr(raw_item, "arguments", "{}")
                        call_id = tool_call.get("id")

                        msg_content = f"Requesting Tool: {tool_name}\nArguments: {tool_args}"

                        message_doc = conv_manager.add_message(
                            conversation,
                            role="agent",
                            content=msg_content,
                            provider=resolved_provider,
                            model=resolved_model,
                            agent=agent_name,
                            run_name=run_doc.name,
                            kind="Tool Call",
                            tool_call=tool_call_id,
                            tool_call_id=call_id,
                            tool_calls=[{
                                "id": call_id,
                                "type": "function",
                                "function": {"name": tool_name, "arguments": tool_args}
                            }]
                        )
                        if call_id:
                            tool_call_message_map[call_id] = message_doc.name
                        safe_commit()

                    yield chunk

                elif chunk_type == "complete":
                    full_response = chunk.get("full_response", full_response)

                    if not (full_response or "").strip() and not tool_call_message_map:
                        # Empty completion with no tool calls — the provider
                        # failed to generate content (known with reasoning
                        # models on the 'ollama/' endpoint). Never store an
                        # empty assistant message; fail the run and emit an
                        # error frame instead of a success-looking complete.
                        error_msg = _(
                            "The provider returned an empty response. For reasoning models on Ollama, use the 'ollama_chat/' model prefix."
                        )
                        frappe.log_error(f"Empty provider response for agent '{agent_name}' (model '{resolved_model_name}')", "Huf Provider")
                        frappe.db.set_value("Agent Run", run_doc.name, {
                            "status": "Failed",
                            "error_message": error_msg,
                            "end_time": now_datetime()
                        }, update_modified=True)
                        safe_commit()
                        yield {
                            "type": "error",
                            "error": error_msg,
                            "success": False,
                            "agent_run_id": run_doc.name,
                            "conversation_id": conversation.name
                        }
                        return

                    usage = chunk.get("usage", {})

                    # Calculate metrics
                    cost = 0.0
                    input_tokens = 0
                    output_tokens = 0
                    cached_tokens = 0
                    cache_creation_tokens = 0
                    cache_skipped_unsupported_model = False
                    total_tokens = 0

                    if usage:

                        if isinstance(usage, dict):
                            input_tokens = (getattr(usage, "prompt_tokens", usage.get("prompt_tokens", 0)) if isinstance(usage, dict) else 0) or 0
                            output_tokens = (getattr(usage, "completion_tokens", usage.get("completion_tokens", 0)) if isinstance(usage, dict) else 0) or 0

                            details = getattr(usage, "prompt_tokens_details", None)
                            if not details and isinstance(usage, dict):
                                details = usage.get("prompt_tokens_details")

                            if details:
                                if isinstance(details, dict):
                                    cached_tokens = details.get("cached_tokens") or details.get("cache_hit_tokens") or 0
                                    cache_creation_tokens = (
                                        details.get("cache_creation_input_tokens")
                                        or details.get("cache_write_tokens")
                                        or details.get("cache_creation_tokens")
                                        or 0
                                    )
                                else:
                                    cached_tokens = getattr(details, "cached_tokens", None) or getattr(details, "cache_hit_tokens", None) or 0
                                    cache_creation_tokens = (
                                        getattr(details, "cache_creation_input_tokens", None)
                                        or getattr(details, "cache_write_tokens", None)
                                        or getattr(details, "cache_creation_tokens", None)
                                        or 0
                                    )
                            elif isinstance(usage, dict):
                                cached_tokens = usage.get("cached_tokens") or usage.get("cache_hit_tokens") or 0
                                cache_creation_tokens = (
                                    usage.get("cache_creation_tokens")
                                    or usage.get("cache_creation_input_tokens")
                                    or usage.get("cache_write_input_tokens")
                                    or usage.get("cache_miss_tokens")
                                    or 0
                                )

                            if not cache_creation_tokens and isinstance(usage, dict):
                                cache_creation_tokens = (
                                    usage.get("cache_creation_tokens")
                                    or usage.get("cache_creation_input_tokens")
                                    or usage.get("cache_write_input_tokens")
                                    or usage.get("cache_miss_tokens")
                                    or 0
                                )

                            if isinstance(usage, dict):
                                cache_skipped_unsupported_model = bool(usage.get("cache_skipped_unsupported_model", False))

                            total_tokens = getattr(usage, "total_tokens", (input_tokens + output_tokens))
                        else:
                            input_tokens = (getattr(usage, "prompt_tokens", getattr(usage, "input_tokens", 0))) or 0
                            output_tokens = (getattr(usage, "completion_tokens", getattr(usage, "output_tokens", 0))) or 0
                            cached_tokens = getattr(usage, "cached_tokens", None) or 0
                            cache_creation_tokens = (
                                getattr(usage, "cache_creation_tokens", None)
                                or getattr(usage, "cache_creation_input_tokens", None)
                                or getattr(usage, "cache_write_input_tokens", None)
                                or getattr(usage, "cache_miss_tokens", None)
                                or 0
                            )
                            cache_skipped_unsupported_model = bool(getattr(usage, "cache_skipped_unsupported_model", False))
                            total_tokens = getattr(usage, "total_tokens", (input_tokens + output_tokens)) or (input_tokens + output_tokens)

                    cached_tokens = cached_tokens or 0
                    cache_creation_tokens = cache_creation_tokens or 0

                    if input_tokens == 0 or output_tokens == 0:
                        try:
                            pricing_model = _normalize_model_name(resolved_model_name, resolved_provider)

                            msgs_for_count = history + [{"role": "user", "content": prompt}]
                            input_tokens = token_counter(model=pricing_model, messages=msgs_for_count)
                            output_tokens = token_counter(model=pricing_model, text=full_response)
                            total_tokens = input_tokens + output_tokens
                        except (ImportError, AttributeError, TypeError, ValueError, KeyError, RuntimeError) as e:
                            frappe.logger("huf").warning(
                                f"Fallback token counting failed: {e}"
                            )

                    try:
                        # Prefer cost directly from the chunk (calculated by provider)
                        cost = chunk.get("cost")
                        if not cost:
                            from huf.ai.cost_calculator import calculate_cost

                            pricing_model = _normalize_model_name(resolved_model_name, resolved_provider)

                            mock_response = {
                                "usage": {
                                    "prompt_tokens": input_tokens,
                                    "completion_tokens": output_tokens,
                                    "total_tokens": input_tokens + output_tokens
                                },
                                "model": pricing_model
                            }

                            if cached_tokens > 0:
                                mock_response["usage"]["prompt_tokens_details"] = {"cached_tokens": cached_tokens}

                            cost, _source = calculate_cost(
                                model_name=resolved_model_name,
                                input_tokens=input_tokens,
                                output_tokens=output_tokens,
                                cached_tokens=cached_tokens,
                                litellm_response=mock_response
                            )

                    except (ImportError, AttributeError, TypeError, ValueError, KeyError, RuntimeError) as e:
                        frappe.logger("huf").warning(
                            f"Cost calculation failed for {resolved_model_name}: {e}"
                        )
                        cost = 0.0

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
                    except (RuntimeError, TypeError, ValueError,
                            frappe.ValidationError, frappe.PermissionError) as e:
                        frappe.logger("huf").warning(
                            f"Failed to update conv metrics stream: {str(e)}"
                        )

                    # Save final response
                    final_message = conv_manager.add_message(
                        conversation, "agent", full_response, resolved_provider, resolved_model, agent_name, run_doc.name
                    )

                    r_res_stream = context.get("reasoning_resolution") if context else None
                    r_snap_stream = json.dumps(r_res_stream.to_dict()) if r_res_stream else None

                    stream_run_update = {
                        "status": "Success",
                        "response": full_response,
                        "prompt": prompt,
                        "model": resolved_model,
                        "provider": resolved_provider,
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                        "cached_tokens": cached_tokens,
                        "cost": cost,
                        "usage_snapshot": json.dumps({
                            "schema_version": 1,
                            "input_tokens": input_tokens,
                            "output_tokens": output_tokens,
                            "cache_read_tokens": cached_tokens if usage else None,
                            "cache_creation_tokens": cache_creation_tokens if usage else None,
                            "cache_miss_tokens": cache_creation_tokens if usage else None,
                            "cache_skipped_unsupported_model": cache_skipped_unsupported_model,
                            "total_tokens": total_tokens,
                            "completeness": "provider_reported" if usage else "estimated",
                            "segment_tokens": segment_tokens,
                            "prefix_breakpoints": prefix_breakpoints,
                        }),
                        "cost_source": "provider_reported" if chunk.get("cost") is not None else "unknown",
                        "cost_calculation_status": "calculated" if cost is not None else "unavailable",
                        "end_time": now_datetime()
                    }
                    if r_snap_stream:
                        stream_run_update["reasoning_snapshot"] = r_snap_stream

                    frappe.db.set_value("Agent Run", run_doc.name, stream_run_update, update_modified=True)
                    safe_commit()

                    # Handle Sub-Agent Success Lifecycle Hook
                    if parent_conversation_id and invoked_by_agent:
                        # Silent Auto-Awaken Trigger
                        try:
                            silent_trigger = f"[SILENT_TRIGGER] The sub-agent '{agent_name}' has responded. IMPORTANT: DO NOT assume this means the task was successful. Read the result carefully and appropriately relay it to the user.\nResult:\n{full_response}"
                            frappe.enqueue(
                                "huf.ai.agent_integration.run_agent_sync",
                                queue="default",
                                timeout=300,
                                is_async=True,
                                agent_name=invoked_by_agent,
                                prompt=silent_trigger,
                                parent_conversation_id=None,
                                conversation_id=parent_conversation_id,
                                channel_id=channel_id,
                                external_id=external_id
                            )
                        except (ValueError, KeyError, TypeError, AttributeError,
                                frappe.DoesNotExistError, frappe.ValidationError,
                                frappe.PermissionError, frappe.TimestampMismatchError) as hook_err:
                            frappe.logger("huf").warning(f"Agent hook dispatch failure: {hook_err!s}")

                        except Exception as hook_err:  # boundary exception handler: agent hook dispatcher
                            frappe.log_error(
                                f"Error in Sub-Agent Success Hook: {str(hook_err)}\n{frappe.get_traceback()}",
                                "Agent Integration Error"
                            )

                        frappe.publish_realtime(
                            event=f"conversation:{parent_conversation_id}",
                            message={
                                "type": "sub_agent_completed",
                                "agent_name": agent_name,
                                "status": "Success",
                                "result": full_response
                            },
                            user=frappe.session.user
                        )

                    # Auto-naming check for stream
                    try:
                        if agent_doc.autonaming_of_conversation_title:
                            conv_title = frappe.db.get_value("Agent Conversation", conversation.name, "title")
                            if conv_title and (conv_title.startswith("Chat with") or conv_title.startswith("Conversation with") or conv_title.startswith("Streaming chat with")):
                                frappe.enqueue(
                                    "huf.ai.agent_integration.generate_conversation_title",
                                    queue="default",
                                    conversation_name=conversation.name,
                                    agent_name=agent_name
                                )
                    except (RuntimeError, TypeError, ValueError, AttributeError,
                            frappe.ValidationError, frappe.PermissionError):
                        # Best-effort auto-naming enqueue; ignore failures.
                        pass

                    if context_strategy == "Summarize":
                        if len(history) >= history_limit:
                            frappe.enqueue(
                                "huf.ai.agent_integration.run_background_summarization",
                                queue="default",
                                conversation_name=conversation.name,
                                agent_name=agent_name
                            )

                    # Force commit to ensure messages, Agent Run, and background jobs are persisted to MariaDB
                    # This is necessary because streaming generators bypass the standard Frappe auto-commit lifecycle.
                    safe_commit()

                    # Normalize complete event to match REST run_agent_sync response shape
                    chunk["conversation_id"] = conversation.name
                    chunk["response"] = full_response
                    chunk["success"] = True
                    chunk["agent_run_id"] = run_doc.name
                    chunk["agent_message_id"] = final_message.name
                    chunk["session_id"] = conv_manager.session_id
                    chunk["provider"] = resolved_provider
                    yield chunk
                    return

                elif chunk_type == "error":
                    error_msg = chunk.get("error", "Unknown error")

                    if "ContextWindowExceededError" in error_msg:
                        try:
                            frappe.db.set_value("Agent Conversation", conversation.name, "is_active", 0)
                            transaction_checkpoint(reason="agent_streaming_progress")

                            user_error_msg = _("This conversation has exceeded the maximum token limit. Please start a new conversation to continue.")

                            conv_manager.add_message(
                                conversation=conversation,
                                role="agent",
                                content=user_error_msg,
                                provider=resolved_provider,
                                model=resolved_model,
                                agent=agent_name,
                                run_name=run_doc.name,
                                kind="Error"
                            )
                            transaction_checkpoint(reason="agent_streaming_progress")
                            chunk["error"] = user_error_msg # override so the client sees the same message
                            error_msg = user_error_msg
                        except (RuntimeError, TypeError, ValueError, KeyError, AttributeError,
                                frappe.DoesNotExistError, frappe.ValidationError, frappe.PermissionError) as inner_e:
                            frappe.logger("huf").warning(
                                f"Failed to handle context window error in stream inner block: {str(inner_e)}"
                            )

                    elif "RateLimitError" in error_msg:
                        try:
                            user_error_msg = _("You have reached the API rate limit (requests/tokens per minute). Please wait a moment and try again.")

                            conv_manager.add_message(
                                conversation=conversation,
                                role="agent",
                                content=user_error_msg,
                                provider=resolved_provider,
                                model=resolved_model,
                                agent=agent_name,
                                run_name=run_doc.name,
                                kind="Error"
                            )
                            transaction_checkpoint(reason="agent_streaming_progress")
                            chunk["error"] = user_error_msg # override so the client sees the same message
                            error_msg = user_error_msg
                        except (RuntimeError, TypeError, ValueError, KeyError, AttributeError,
                                frappe.DoesNotExistError, frappe.ValidationError, frappe.PermissionError) as inner_e:
                            frappe.logger("huf").warning(
                                f"Failed to handle rate limit in stream inner block: {str(inner_e)}"
                            )

                    frappe.db.set_value("Agent Run", run_doc.name, {
                        "status": "Failed",
                        "error_message": error_msg,
                        "end_time": now_datetime()
                    }, update_modified=True)
                    safe_commit()

                    # Handle Sub-Agent Failure Lifecycle Hook
                    if parent_conversation_id and invoked_by_agent:
                        # Silent Auto-Awaken Trigger
                        try:
                            silent_trigger = f"[SILENT_TRIGGER] The sub-agent '{agent_name}' encountered an error during its background task.\nError:\n{error_msg}"
                            frappe.enqueue(
                                "huf.ai.agent_integration.run_agent_sync",
                                queue="default",
                                timeout=300,
                                is_async=True,
                                agent_name=invoked_by_agent,
                                prompt=silent_trigger,
                                parent_conversation_id=None,
                                conversation_id=parent_conversation_id,
                                channel_id=channel_id,
                                external_id=external_id
                            )
                        except (ValueError, KeyError, TypeError, AttributeError,
                                frappe.DoesNotExistError, frappe.ValidationError,
                                frappe.PermissionError, frappe.TimestampMismatchError) as hook_err:
                            frappe.logger("huf").warning(f"Agent hook dispatch failure: {hook_err!s}")

                        except Exception as hook_err:  # boundary exception handler: agent hook dispatcher
                            frappe.log_error(
                                f"Error in Sub-Agent Failure Hook: {str(hook_err)}\n{frappe.get_traceback()}",
                                "Agent Integration Error"
                            )

                        frappe.publish_realtime(
                            event=f"conversation:{parent_conversation_id}",
                            message={
                                "type": "sub_agent_failed",
                                "agent_name": agent_name,
                                "status": "Failed",
                                "result": error_msg
                            },
                            user=frappe.session.user
                        )

                    chunk["success"] = False
                    chunk["agent_run_id"] = run_doc.name
                    chunk["conversation_id"] = conversation.name
                    yield chunk
                    return

        except Exception as e:
            error_msg = str(e)
            if isinstance(e, ProviderUnavailableError):
                # Expected operational failure (connection refused, model not
                # pulled, bad model prefix) — message is self-explanatory, no
                # traceback needed. The run is still marked Failed below.
                log_error_msg = getattr(e, "log_message", error_msg)
                frappe.log_error(f"Provider unavailable for agent '{agent_name}': {log_error_msg}", "Huf Provider")
            else:
                frappe.log_error(f"Agent Stream Error: {frappe.get_traceback()}", "Huf Streaming")
            if "ContextWindowExceededError" in error_msg:
                try:
                    frappe.db.set_value("Agent Conversation", conversation.name, "is_active", 0)
                    transaction_checkpoint(reason="agent_streaming_progress")

                    error_msg = _("This conversation has exceeded the maximum token limit. Please start a new conversation to continue.")

                    conv_manager.add_message(
                        conversation=conversation,
                        role="agent",
                        content=error_msg,
                        provider=resolved_provider,
                        model=resolved_model,
                        agent=agent_name,
                        run_name=run_doc.name,
                        kind="Error"
                    )
                    transaction_checkpoint(reason="agent_streaming_progress")
                except (RuntimeError, TypeError, ValueError, KeyError, AttributeError,
                        frappe.DoesNotExistError, frappe.ValidationError, frappe.PermissionError) as inner_e:
                    frappe.logger("huf").warning(
                        f"Failed to handle context window error in stream inner block: {str(inner_e)}"
                    )

            elif "RateLimitError" in error_msg:
                try:
                    error_msg = _("You have reached the API rate limit (requests/tokens per minute). Please wait a moment and try again.")

                    conv_manager.add_message(
                        conversation=conversation,
                        role="agent",
                        content=error_msg,
                        provider=resolved_provider,
                        model=resolved_model,
                        agent=agent_name,
                        run_name=run_doc.name,
                        kind="Error"
                    )
                    transaction_checkpoint(reason="agent_streaming_progress")
                except (RuntimeError, TypeError, ValueError, KeyError, AttributeError,
                        frappe.DoesNotExistError, frappe.ValidationError, frappe.PermissionError) as inner_e:
                    frappe.logger("huf").warning(
                        f"Failed to handle rate limit in stream inner block: {str(inner_e)}"
                    )

            frappe.db.set_value("Agent Run", run_doc.name, {
                "status": "Failed",
                "error_message": error_msg,
                "end_time": now_datetime()
            }, update_modified=True)
            safe_commit()

            # Handle Sub-Agent Failure Lifecycle Hook
            if parent_conversation_id and invoked_by_agent:
                # Silent Auto-Awaken Trigger
                try:
                    silent_trigger = f"[SILENT_TRIGGER] The sub-agent '{agent_name}' encountered an error during its background task.\nError:\n{error_msg}"
                    frappe.enqueue(
                        "huf.ai.agent_integration.run_agent_sync",
                        queue="default",
                        timeout=300,
                        is_async=True,
                        agent_name=invoked_by_agent,
                        prompt=silent_trigger,
                        parent_conversation_id=None,
                        conversation_id=parent_conversation_id,
                        channel_id=channel_id,
                        external_id=external_id
                    )
                except (ValueError, KeyError, TypeError, AttributeError,
                        frappe.DoesNotExistError, frappe.ValidationError,
                        frappe.PermissionError, frappe.TimestampMismatchError) as hook_err:
                    frappe.logger("huf").warning(f"Agent hook dispatch failure: {hook_err!s}")

                except Exception as hook_err:  # boundary exception handler: agent hook dispatcher
                    frappe.log_error(
                        f"Error in Sub-Agent Failure Hook: {str(hook_err)}\n{frappe.get_traceback()}",
                        "Agent Integration Error"
                    )

                frappe.publish_realtime(
                    event=f"conversation:{parent_conversation_id}",
                    message={
                        "type": "sub_agent_failed",
                        "agent_name": agent_name,
                        "status": "Failed",
                        "result": error_msg
                    },
                    user=frappe.session.user
                )

            yield {
                "type": "error",
                "error": error_msg,
                "success": False,
                "agent_run_id": run_doc.name,
                "conversation_id": conversation.name
            }

    except Exception as e:
        error_msg = str(e)
        frappe.log_error(f"Agent Stream Setup Error: {frappe.get_traceback()}", "Huf Streaming")
        yield {
            "type": "error",
            "error": error_msg
        }
    finally:
        if 'run_doc' in locals() and run_doc:
            try:
                current_status = frappe.db.get_value("Agent Run", run_doc.name, "status")
                if current_status == "Started":
                    response_text = locals().get("full_response", "")
                    if response_text and str(response_text).strip():
                        # Save generated text so user sees the response upon reload (ChatGPT pattern)
                        if 'conv_manager' in locals() and 'conversation' in locals():
                            conv_manager.add_message(
                                conversation,
                                "agent",
                                response_text,
                                locals().get("resolved_provider"),
                                locals().get("resolved_model"),
                                agent_name,
                                run_doc.name
                            )
                        frappe.db.set_value("Agent Run", run_doc.name, {
                            "status": "Success",
                            "response": response_text,
                            "end_time": now_datetime()
                        }, update_modified=True)
                    else:
                        frappe.db.set_value("Agent Run", run_doc.name, {
                            "status": "Failed",
                            "error_message": "Stream disconnected before response was generated",
                            "end_time": now_datetime()
                        }, update_modified=True)
                    safe_commit()
            except Exception as clean_err:
                # Defensive finally cleanup: must not suppress the original exception.
                frappe.logger("huf").warning(
                    f"Error in stream disconnect response recovery: {clean_err}\n{frappe.get_traceback()}"
                )

# ---------------------------------------------------------------------------
# Permission query conditions — used by hooks.py permission_query_conditions
# These return SQL WHERE fragments so Frappe's list view only shows rows
# the current user is allowed to see.
# ---------------------------------------------------------------------------


def get_conversation_permission_conditions(user):
	"""
	Restrict Agent Conversation list to conversations the user owns,
	unless the user has chat.view_all capability.
	"""
	if not user:
		user = frappe.session.user

	from huf.permissions import has_capability, SYSTEM_MANAGER
	if SYSTEM_MANAGER in frappe.get_roles(user):
		return None

	if has_capability(user, "chat.view_all"):
		return None

	# Only own conversations
	return f"`tabAgent Conversation`.owner = {frappe.db.escape(user)}"


def get_message_permission_conditions(user):
	"""
	Restrict Agent Message list to messages from conversations the user owns,
	unless the user has chat.view_all capability.
	"""
	if not user:
		user = frappe.session.user

	from huf.permissions import has_capability, SYSTEM_MANAGER
	if SYSTEM_MANAGER in frappe.get_roles(user):
		return None

	if has_capability(user, "chat.view_all"):
		return None

	# Filter by conversation ownership
	return f"(`tabAgent Message`.conversation IN (SELECT name FROM `tabAgent Conversation` WHERE owner = {frappe.db.escape(user)}))"


def get_run_permission_conditions(user):
	"""
	Restrict Agent Run list to runs the user owns,
	unless the user has agent.view_all capability.
	"""
	if not user:
		user = frappe.session.user

	from huf.permissions import has_capability, SYSTEM_MANAGER
	if SYSTEM_MANAGER in frappe.get_roles(user):
		return None

	if has_capability(user, "agent.view_all"):
		return None

	return f"`tabAgent Run`.owner = {frappe.db.escape(user)}"
