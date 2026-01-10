"""Knowledge search tool for agent use."""

import frappe
from typing import Optional

from .retriever import knowledge_search


def create_knowledge_search_tool(agent_name: str) -> Optional[dict]:
	"""
	Create a knowledge_search tool definition for an agent.
	
	This tool allows agents to optionally search knowledge sources.
	"""
	# Get optional knowledge sources for this agent
	try:
		agent = frappe.get_doc("Agent", agent_name)
	except Exception:
		return None
		
	optional_sources = []
	
	for ak in agent.get("agent_knowledge", []):
		if ak.mode == "Optional":
			optional_sources.append(ak.knowledge_source)
	
	if not optional_sources:
		return None
	
	# Build tool definition
	return {
		"tool_name": "knowledge_search",
		"description": f"""Search the agent's knowledge base for relevant information.
		
Available knowledge sources: {', '.join(optional_sources)}

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
				"description": f"Specific knowledge source to search. Options: {', '.join(optional_sources)}",
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
	# Validate that agent has access to this source
	if knowledge_source:
		agent = frappe.get_doc("Agent", agent_name)
		allowed_sources = [
			ak.knowledge_source 
			for ak in agent.get("agent_knowledge", [])
			if ak.mode == "Optional"
		]
		
		if knowledge_source not in allowed_sources:
			return f"Error: Knowledge source '{knowledge_source}' is not available."
	else:
		# Search all optional sources
		agent = frappe.get_doc("Agent", agent_name)
		sources = [
			ak.knowledge_source 
			for ak in agent.get("agent_knowledge", [])
			if ak.mode == "Optional"
		]
		knowledge_source = sources[0] if len(sources) == 1 else None
	
	# Perform search
	try:
		results = knowledge_search(
			query=query,
			knowledge_source=knowledge_source,
			top_k=top_k,
		)
		
		if not results:
			return "No relevant results found for your query."
		
		# Format results
		output = []
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
