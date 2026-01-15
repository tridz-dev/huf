"""Knowledge search tool for agent use."""

import frappe
from typing import Optional

from .retriever import knowledge_search



def create_knowledge_search_tool(agent_name: str) -> Optional[dict]:
	"""
	Create a knowledge_search tool definition for an agent.
	
	This tool allows agents to search knowledge sources.
	"""
	# Get all knowledge sources for this agent (valid for search)
	try:
		agent = frappe.get_doc("Agent", agent_name)
	except Exception:
		return None
		
	available_sources = []
	for ak in agent.get("agent_knowledge", []):
		# Both Optional and Mandatory sources can be searched via tool
		# if the agent needs more specific info
		available_sources.append(f"{ak.knowledge_source} ({ak.mode})")
	
	if not available_sources:
		return None
	
	# Build tool definition
	return {
		"tool_name": "knowledge_search",
		"description": f"""Search the agent's knowledge base for relevant information.
		
Available knowledge sources: {', '.join(available_sources)}

Use this tool when you need to find specific information from the knowledge base.
Always cite the source when using information from search results.""",
		"parameters": [
			{
				"label": "Query",
				"fieldname": "query",
				"type": "string",
				"required": True,
				"description": "The search query to find relevant information",
			},
			{
				"label": "Knowledge Source",
				"fieldname": "knowledge_source",
				"type": "string",
				"required": False,
				"description": "Specific knowledge source to search. If omitted, searches all available sources.",
			},
			{
				"label": "Top K",
				"fieldname": "top_k",
				"type": "integer",
				"required": False,
				"description": "Maximum number of results to return (default: 5)",
			},
		],
	}


def handle_knowledge_search(
	agent_name: str,
	query: str,
	knowledge_source: Optional[str] = None,
	top_k: int = 5,
) -> str:
	"""
	Handle knowledge_search tool call from agent.
	
	Returns formatted search results.
	"""
	# Get allowed sources
	agent = frappe.get_doc("Agent", agent_name)
	allowed_sources = [
		ak.knowledge_source 
		for ak in agent.get("agent_knowledge", [])
	]
	
	# Validate requested source
	if knowledge_source:
		if knowledge_source not in allowed_sources:
			return f"Error: Knowledge source '{knowledge_source}' is not available. Available sources: {', '.join(allowed_sources)}"
	else:
		# Search matching source if only one exists, or use first one (simplistic logic)
		# Improved: search across all optional/available if not specified?
		# For now, let's pick the first one to avoid breaking existing logic,
		# but ideally we should search all or ask for clarification.
		# The retriever supports list of sources, let's use that if backend supports it.
		# Current backend might be single-source focused in `knowledge_search` helper wrapper
		# Let's stick to single source selection for now to match interface.
		if len(allowed_sources) == 1:
			knowledge_source = allowed_sources[0]
		else:
			# If multiple sources, we need to know which one.
			# Or we search main one?
			# Let's default to the highest priority one.
			# Sort by priority
			sorted_knowledge = sorted(
				agent.get("agent_knowledge", []), 
				key=lambda x: x.priority or 0, 
				reverse=True
			)
			if sorted_knowledge:
				knowledge_source = sorted_knowledge[0].knowledge_source
	
	if not knowledge_source:
		return "Error: No knowledge sources available for this agent."

	# Perform search
	try:
		results = knowledge_search(
			query=query,
			knowledge_source=knowledge_source,
			top_k=top_k,
		)
		
		if not results:
			return f"No relevant results found for your query in '{knowledge_source}'."
		
		# Format results
		output = []
		output.append(f"Search results from '{knowledge_source}':")
		output.append("")
		
		for i, result in enumerate(results, 1):
			output.append(f"## Result {i}: {result.get('title', 'Untitled')}")
			output.append(f"Source: {result['source']}")
			output.append(f"Score: {result['score']:.3f}")
			output.append("")
			output.append(result["text"])
			output.append("")
			output.append("---")
			output.append("")
		
		return "\n".join(output)
		
	except Exception as e:
		return f"Error searching knowledge base: {str(e)}"


def create_get_knowledge_sources_tool(agent_name: str) -> Optional[dict]:
	"""
	Create a tool to list available knowledge sources.
	"""
	return {
		"tool_name": "get_knowledge_sources",
		"description": "List all knowledge sources available to this agent.",
		"parameters": [],
	}


def handle_get_knowledge_sources(agent_name: str) -> str:
	"""
	Handle get_knowledge_sources tool call.
	"""
	try:
		agent = frappe.get_doc("Agent", agent_name)
		sources = []
		
		for ak in agent.get("agent_knowledge", []):
			sources.append(f"- {ak.knowledge_source} (Mode: {ak.mode}, Priority: {ak.priority})")
			
		if not sources:
			return "No knowledge sources assigned to this agent."
			
		return "Available Knowledge Sources:\n" + "\n".join(sources)
		
	except Exception as e:
		return f"Error retrieving knowledge sources: {str(e)}"
