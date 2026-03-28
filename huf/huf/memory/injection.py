"""Memory prompt injection for HUF Memory System.

Builds memory context blocks and injects them into agent prompts.
Integrates with retrieval modes to provide seamless memory context.

Based on:
- PRD Section 15: Retrieval Model (prompt injection)
- CAPTURE_RETRIEVAL.md Section 3.2 (Inject Mode context format)
- knowledge/context_builder.py patterns for consistency
"""

from typing import List, Dict, Any, Optional
import frappe
from frappe import _

from .retrieval import (
	RetrievalMode,
	MemoryRetrievalConfig,
	get_retrieval_mode,
	InjectRetrievalMode,
	HybridRetrievalMode,
)
from .search import MemorySearcher, MemoryFilterBuilder


class MemoryContextBuilder:
	"""Build memory context blocks for prompt injection.
	
	Mirrors knowledge/context_builder.py::build_knowledge_context()
	
	Context Format (from CAPTURE_RETRIEVAL.md):
	```markdown
	## Relevant Memory

	### Profile: User Preferences
	- Language: English
	- Timezone: America/New_York

	### Session: Travel Planning
	- Destination: Tokyo
	- Dates: 2024-05-01 to 2024-05-10
	```
	"""
	
	def __init__(self, max_tokens: int = 2000):
		self.max_tokens = max_tokens
		self.searcher = MemorySearcher()
	
	def build_memory_context(
		self,
		agent_name: Optional[str] = None,
		conversation_id: Optional[str] = None,
		user_id: Optional[str] = None,
		query: Optional[str] = None,
		filters: Optional[Dict[str, Any]] = None,
		max_items: int = 5,
		format_style: str = "markdown",  # markdown, json, xml
	) -> Dict[str, Any]:
		"""Build memory context for prompt injection.
		
		Args:
			agent_name: Agent to scope memory for
			conversation_id: Conversation to scope memory for
			user_id: User to scope memory for
			query: Optional query for relevance ranking
			filters: Additional filters
			max_items: Maximum memory items to include
			format_style: Output format style
		
		Returns:
			Dict with 'context_text', 'memories_used', 'estimated_tokens'
		"""
		# Build base filters
		builder = MemoryFilterBuilder()
		builder.add_scope_filter(
			agent_name=agent_name,
			conversation_id=conversation_id,
			user_id=user_id,
		)
		builder.add_status_filter(status="active")
		
		if filters:
			builder.filters.update(filters)
		
		# Search for memories
		memories = self.searcher.search(
			query=query,
			filters=builder.build(),
			limit=max_items * 2,  # Get extra for token budget filtering
			ignore_permissions=True,  # Agent context
		)
		
		if not memories:
			return {
				"context_text": "",
				"memories_used": [],
				"estimated_tokens": 0,
				"memory_count": 0,
			}
		
		# Apply token budget and format
		if format_style == "markdown":
			return self._build_markdown_context(memories)
		elif format_style == "json":
			return self._build_json_context(memories)
		elif format_style == "xml":
			return self._build_xml_context(memories)
		else:
			return self._build_markdown_context(memories)
	
	def _build_markdown_context(
		self,
		memories: List[Dict[str, Any]],
	) -> Dict[str, Any]:
		"""Build markdown-formatted memory context."""
		context_parts = []
		memories_used = []
		estimated_tokens = 0
		total_tokens = 0
		
		# Group memories by type for better organization
		grouped = self._group_by_type(memories)
		
		for memory_type, type_memories in grouped.items():
			for memory in type_memories:
				memory_text = self._format_memory_markdown(memory)
				memory_tokens = len(memory_text) // 4
				
				if total_tokens + memory_tokens > self.max_tokens:
					break
				
				if not context_parts:
					context_parts.append("## Relevant Memory\n")
				
				context_parts.append(memory_text)
				memories_used.append({
					"name": memory.get("name"),
					"title": memory.get("title"),
					"memory_type": memory.get("memory_type"),
					"relevance_score": memory.get("relevance_score"),
				})
				total_tokens += memory_tokens
			
			if total_tokens >= self.max_tokens:
				break
		
		return {
			"context_text": "\n".join(context_parts) if context_parts else "",
			"memories_used": memories_used,
			"estimated_tokens": total_tokens,
			"memory_count": len(memories_used),
		}
	
	def _build_json_context(
		self,
		memories: List[Dict[str, Any]],
	) -> Dict[str, Any]:
		"""Build JSON-formatted memory context."""
		memories_data = []
		total_tokens = 0
		max_tokens_reached = False
		
		for memory in memories:
			memory_json = self._format_memory_json(memory)
			memory_tokens = len(str(memory_json)) // 4
			
			if total_tokens + memory_tokens > self.max_tokens:
				max_tokens_reached = True
				break
			
			memories_data.append(memory_json)
			total_tokens += memory_tokens
		
		context_text = frappe.as_json({
			"relevant_memory": memories_data
		}, indent=2) if memories_data else ""
		
		return {
			"context_text": context_text,
			"memories_used": [{"name": m.get("name"), "title": m.get("title")} for m in memories_data],
			"estimated_tokens": total_tokens,
			"memory_count": len(memories_data),
			"truncated": max_tokens_reached,
		}
	
	def _build_xml_context(
		self,
		memories: List[Dict[str, Any]],
	) -> Dict[str, Any]:
		"""Build XML-formatted memory context."""
		lines = ["<memories>"]
		memories_used = []
		total_tokens = 0
		max_tokens_reached = False
		
		for memory in memories:
			memory_xml = self._format_memory_xml(memory)
			memory_tokens = len(memory_xml) // 4
			
			if total_tokens + memory_tokens > self.max_tokens:
				max_tokens_reached = True
				break
			
			lines.append(memory_xml)
			memories_used.append({
				"name": memory.get("name"),
				"title": memory.get("title"),
			})
			total_tokens += memory_tokens
		
		if memories_used:
			lines.append("</memories>")
			context_text = "\n".join(lines)
		else:
			context_text = ""
		
		return {
			"context_text": context_text,
			"memories_used": memories_used,
			"estimated_tokens": total_tokens,
			"memory_count": len(memories_used),
			"truncated": max_tokens_reached,
		}
	
	def _group_by_type(self, memories: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
		"""Group memories by type for organized display."""
		grouped = {}
		# Define priority order for memory types
		type_order = [
			"profile",
			"preference",
			"session_state",
			"plan",
			"fact",
			"insight",
			"observation",
			"domain_object",
			"custom",
		]
		
		for memory_type in type_order:
			type_memories = [m for m in memories if m.get("memory_type") == memory_type]
			if type_memories:
				grouped[memory_type] = type_memories
		
		# Add any remaining types not in priority list
		for memory in memories:
			mtype = memory.get("memory_type", "custom")
			if mtype not in grouped:
				grouped[mtype] = []
			if memory not in grouped[mtype]:
				grouped[mtype].append(memory)
		
		return grouped
	
	def _format_memory_markdown(self, memory: Dict[str, Any]) -> str:
		"""Format a single memory as markdown."""
		lines = []
		
		# Header with title and type
		title = memory.get("title", "Untitled Memory")
		memory_type = memory.get("memory_type", "memory").replace("_", " ").title()
		lines.append(f"### {memory_type}: {title}")
		
		# Summary text if available
		summary = memory.get("summary_text", "").strip()
		if summary:
			lines.append(summary)
		
		# Structured data
		data = memory.get("data_json", {})
		if data and isinstance(data, dict):
			for key, value in data.items():
				if value is not None and value != "":
					lines.append(f"- **{key.replace('_', ' ').title()}:** {value}")
		
		# Metadata
		meta_parts = []
		if memory.get("confidence"):
			meta_parts.append(f"confidence: {memory['confidence']:.2f}")
		if memory.get("relevance_score"):
			meta_parts.append(f"relevance: {memory['relevance_score']:.2f}")
		
		if meta_parts:
			lines.append(f"_({', '.join(meta_parts)})_")
		
		lines.append("")
		return "\n".join(lines)
	
	def _format_memory_json(self, memory: Dict[str, Any]) -> Dict[str, Any]:
		"""Format a single memory as JSON object."""
		return {
			"id": memory.get("name"),
			"title": memory.get("title"),
			"type": memory.get("memory_type"),
			"summary": memory.get("summary_text"),
			"data": memory.get("data_json"),
			"confidence": memory.get("confidence"),
			"importance": memory.get("importance_score"),
			"relevance_score": memory.get("relevance_score"),
			"created": str(memory.get("creation")),
		}
	
	def _format_memory_xml(self, memory: Dict[str, Any]) -> str:
		"""Format a single memory as XML."""
		lines = [f'  <memory id="{memory.get("name")}" type="{memory.get("memory_type")}"\u003e']
		lines.append(f'    <title>{self._xml_escape(memory.get("title", ""))}</title>')
		
		if memory.get("summary_text"):
			lines.append(f'    <summary>{self._xml_escape(memory["summary_text"])}</summary>')
		
		data = memory.get("data_json", {})
		if data:
			lines.append("    <data>")
			for key, value in data.items():
				lines.append(f'      <{key}>{self._xml_escape(str(value))}</{key}>')
			lines.append("    </data>")
		
		lines.append("  </memory>")
		return "\n".join(lines)
	
	def _xml_escape(self, text: str) -> str:
		"""Escape special XML characters."""
		if not text:
			return ""
		return (text
			.replace("&", "&amp;")
			.replace("<", "&lt;")
			.replace(">", "&gt;")
			.replace('"', "&quot;")
			.replace("'", "&apos;"))


class MemoryPromptInjector:
	"""Inject memory context into agent prompts.
	
	Follows knowledge/context_builder.py::inject_knowledge_context() pattern.
	
	Placement: Memory context is inserted before the main prompt,
	after core instructions but before the user's message.
	"""
	
	def __init__(self):
		self.builder = MemoryContextBuilder()
	
	def inject_memory_context(
		self,
		prompt: str,
		agent_name: Optional[str] = None,
		conversation_id: Optional[str] = None,
		user_id: Optional[str] = None,
		query: Optional[str] = None,
		retrieval_mode: RetrievalMode = RetrievalMode.HYBRID,
		max_items: int = 5,
		max_tokens: int = 2000,
		position: str = "before",  # before, after, replace
	) -> str:
		"""Inject memory context into the agent prompt.
		
		Args:
			prompt: Original agent prompt
			agent_name: Agent for scoping
			conversation_id: Conversation for scoping
			user_id: User for scoping
			query: Optional query for relevance
			retrieval_mode: How to retrieve memories
			max_items: Max memories to inject
			max_tokens: Token budget for memories
			position: Where to insert context
		
		Returns:
			Prompt with injected memory context
		"""
		# Build context based on retrieval mode
		if retrieval_mode == RetrievalMode.TOOL_ONLY:
			# No injection in tool-only mode
			return prompt
		
		# Use retrieval mode to get memories
		config = MemoryRetrievalConfig(
			mode=retrieval_mode,
			inject_max_items=max_items,
			inject_max_tokens=max_tokens,
		)
		
		retrieval = get_retrieval_mode(retrieval_mode, config)
		
		if retrieval_mode == RetrievalMode.HYBRID:
			# Use hybrid mode but only take injected portion
			hybrid_results = retrieval.retrieve(
				query=query,
				agent_name=agent_name,
				conversation_id=conversation_id,
				user_id=user_id,
			)
			memories = hybrid_results.get("injected", [])
		else:
			# Inject mode
			results = retrieval.retrieve(
				query=query,
				agent_name=agent_name,
				conversation_id=conversation_id,
				user_id=user_id,
			)
			memories = results.get("results", [])
		
		if not memories:
			return prompt
		
		# Build context text
		self.builder.max_tokens = max_tokens
		context_result = self.builder._build_markdown_context(memories)
		
		if not context_result["context_text"]:
			return prompt
		
		context_text = context_result["context_text"]
		
		# Insert based on position
		if position == "before":
			return f"{context_text}\n---\n\n{prompt}"
		elif position == "after":
			return f"{prompt}\n---\n\n{context_text}"
		elif position == "replace":
			return context_text
		else:
			return f"{context_text}\n---\n\n{prompt}"
	
	def get_injection_metadata(
		self,
		agent_name: Optional[str] = None,
		conversation_id: Optional[str] = None,
	) -> Dict[str, Any]:
		"""Get metadata about what would be injected.
		
		Useful for debugging and UI preview.
		"""
		context_result = self.builder.build_memory_context(
			agent_name=agent_name,
			conversation_id=conversation_id,
		)
		
		return {
			"memory_count": context_result["memory_count"],
			"estimated_tokens": context_result["estimated_tokens"],
			"memories": [
				{
					"name": m["name"],
					"title": m["title"],
					"type": m["memory_type"],
					"score": m.get("relevance_score"),
				}
				for m in context_result["memories_used"]
			],
		}


# Convenience functions for integration with agent system

def build_memory_context_for_agent(
	agent_name: str,
	user_query: str,
	conversation_id: Optional[str] = None,
	user_id: Optional[str] = None,
	max_tokens: int = 2000,
) -> Dict[str, Any]:
	"""Build memory context for an agent (similar to knowledge context builder).
	
	This is the main entry point for agent integration.
	Called before agent execution to prepare memory context.
	
	Args:
		agent_name: Name of the agent
		user_query: The user's query (used for relevance search)
		conversation_id: Conversation context
		user_id: User context
		max_tokens: Maximum tokens for memory context
		
	Returns:
		Dict with 'context_text', 'memories_used', 'estimated_tokens'
	"""
	# Check if agent has memory enabled
	try:
		agent = frappe.get_doc("Agent", agent_name)
		if not agent.get("enable_memory", False):
			return {
				"context_text": "",
				"memories_used": [],
				"estimated_tokens": 0,
			}
		
		# Get agent's memory configuration
		retrieval_mode_str = agent.get("memory_retrieval_mode", "hybrid")
		max_items = agent.get("memory_max_items", 5) or 5
		inject_budget = agent.get("memory_in_prompt_budget", max_tokens) or max_tokens
		
	except Exception:
		# Agent doesn't exist or error, return empty
		return {
			"context_text": "",
			"memories_used": [],
			"estimated_tokens": 0,
		}
	
	# Build context
	builder = MemoryContextBuilder(max_tokens=inject_budget)
	return builder.build_memory_context(
		agent_name=agent_name,
		conversation_id=conversation_id,
		user_id=user_id,
		query=user_query,
		max_items=max_items,
	)


def inject_memory_into_prompt(
	prompt: str,
	agent_name: str,
	conversation_id: Optional[str] = None,
	user_id: Optional[str] = None,
	query: Optional[str] = None,
) -> str:
	"""Inject memory context into agent prompt.
	
	Main integration point for agent execution pipeline.
	Called similarly to knowledge context injection.
	"""
	try:
		agent = frappe.get_doc("Agent", agent_name)
		if not agent.get("enable_memory", False):
			return prompt
		
		retrieval_mode_str = agent.get("memory_retrieval_mode", "hybrid")
		retrieval_mode = RetrievalMode(retrieval_mode_str)
		
		injector = MemoryPromptInjector()
		return injector.inject_memory_context(
			prompt=prompt,
			agent_name=agent_name,
			conversation_id=conversation_id,
			user_id=user_id,
			query=query,
			retrieval_mode=retrieval_mode,
			max_items=agent.get("memory_max_items", 5) or 5,
			max_tokens=agent.get("memory_in_prompt_budget", 2000) or 2000,
		)
	except Exception as e:
		frappe.log_error(
			f"Memory injection error for agent {agent_name}: {str(e)}",
			"Memory Injection Error"
		)
		return prompt


# Whitelist API functions

@frappe.whitelist()
def preview_memory_context(
	agent_name: str,
	conversation_id: Optional[str] = None,
	query: Optional[str] = None,
	format_style: str = "markdown",
) -> Dict[str, Any]:
	"""Preview what memory context would be injected for an agent.
	
	Useful for debugging and UI preview.
	"""
	builder = MemoryContextBuilder()
	return builder.build_memory_context(
		agent_name=agent_name,
		conversation_id=conversation_id,
		query=query,
		format_style=format_style,
	)


@frappe.whitelist()
def test_memory_injection(
	prompt: str,
	agent_name: str,
	conversation_id: Optional[str] = None,
	query: Optional[str] = None,
) -> Dict[str, Any]:
	"""Test memory injection with a sample prompt.
	
	Returns the full prompt with injected memory context.
	"""
	try:
		result = inject_memory_into_prompt(
			prompt=prompt,
			agent_name=agent_name,
			conversation_id=conversation_id,
			query=query,
		)
		
		# Get metadata about what was injected
		injector = MemoryPromptInjector()
		metadata = injector.get_injection_metadata(
			agent_name=agent_name,
			conversation_id=conversation_id,
		)
		
		return {
			"success": True,
			"original_prompt": prompt,
			"injected_prompt": result,
			"injection_metadata": metadata,
		}
	except Exception as e:
		return {
			"success": False,
			"error": str(e),
		}
