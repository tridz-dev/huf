"""Knowledge search tool for agent use."""

import frappe
from typing import Optional

from .retriever import knowledge_search, get_search_diagnostics



def _get_allowed_knowledge_sources(agent_name: str) -> list[str]:
	"""
	Return all knowledge sources the agent is allowed to search.

	Includes agent-level sources and sources attached via skills.
	"""
	allowed_sources = []
	seen = set()

	try:
		agent = frappe.get_doc("Agent", agent_name)
		for ak in agent.get("agent_knowledge", []):
			name = ak.knowledge_source
			if name and name not in seen:
				seen.add(name)
				allowed_sources.append(name)
	except Exception:
		pass

	try:
		from huf.ai.skills.loader import get_agent_skills
		for skill in get_agent_skills(agent_name):
			for sk in skill.get("skill_knowledge", []):
				name = getattr(sk, "knowledge_source", None)
				if name and name not in seen:
					seen.add(name)
					allowed_sources.append(name)
	except Exception:
		pass

	return allowed_sources


def create_knowledge_search_tool(agent_name: str) -> Optional[dict]:
	"""
	Create a knowledge_search tool definition for an agent.
	
	This tool allows agents to search knowledge sources.
	"""
	# Get all knowledge sources for this agent (valid for search)
	allowed_sources = _get_allowed_knowledge_sources(agent_name)
	
	if not allowed_sources:
		return None
	
	# Build human-readable source list including skill context.
	available_sources = []
	try:
		agent = frappe.get_doc("Agent", agent_name)
		for ak in agent.get("agent_knowledge", []):
			available_sources.append(f"{ak.knowledge_source} ({ak.mode})")
	except Exception:
		pass

	try:
		from huf.ai.skills.loader import get_agent_skills
		for skill in get_agent_skills(agent_name):
			for sk in skill.get("skill_knowledge", []):
				available_sources.append(
					f"{sk.knowledge_source} (Skill: {skill.skill_name}, {getattr(sk, 'mode', 'Mandatory')})"
				)
	except Exception:
		pass
	
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
	# Get allowed sources (agent-level + skill-attached)
	allowed_sources = _get_allowed_knowledge_sources(agent_name)

	if not allowed_sources:
		return "Error: No knowledge sources available for this agent."

	# Validate requested source
	if knowledge_source:
		if knowledge_source not in allowed_sources:
			return f"Error: Knowledge source '{knowledge_source}' is not available. Available sources: {', '.join(allowed_sources)}"
		target_sources = [knowledge_source]
	else:
		# Search across all allowed sources using the retriever's list support.
		target_sources = allowed_sources

	# Perform search (ignore_permissions=True: agent has explicit knowledge linkage)
	try:
		results = knowledge_search(
			query=query,
			knowledge_sources=target_sources,
			top_k=top_k,
			ignore_permissions=True,
		)

		if not results:
			if knowledge_source:
				msg = f"No relevant results found for your query in '{knowledge_source}'."
			else:
				msg = f"No relevant results found for your query across sources: {', '.join(target_sources)}."
			diagnostics = get_search_diagnostics(target_sources)
			if diagnostics:
				diag = diagnostics[0]
				if diag.get("reason"):
					msg += f"\n\nDiagnostic: {diag['reason']}"
					if diag.get("status"):
						msg += f" (current status: {diag['status']})"
			return msg

		# Format results
		output = []
		if knowledge_source:
			output.append(f"Search results from '{knowledge_source}':")
		else:
			output.append(f"Search results across sources: {', '.join(target_sources)}")
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
		frappe.log_error(
			f"Knowledge search tool error for sources {target_sources}: {e}",
			"Knowledge Search Tool Error",
		)
		return f"Error searching knowledge base: {str(e)}"


def create_get_knowledge_sources_tool(agent_name: str) -> Optional[dict]:
	"""
	Create a tool to list available knowledge sources.
	Returns None if the agent has no knowledge sources (tool should not be added).
	"""
	allowed_sources = _get_allowed_knowledge_sources(agent_name)
	if not allowed_sources:
		return None
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
		sources = []
		
		agent = frappe.get_doc("Agent", agent_name)
		for ak in agent.get("agent_knowledge", []):
			sources.append(f"- {ak.knowledge_source} (Mode: {ak.mode}, Priority: {ak.priority})")

		from huf.ai.skills.loader import get_agent_skills
		for skill in get_agent_skills(agent_name):
			for sk in skill.get("skill_knowledge", []):
				sources.append(
					f"- {sk.knowledge_source} (Skill: {skill.skill_name}, "
					f"Mode: {getattr(sk, 'mode', 'Mandatory')}, "
					f"Priority: {getattr(sk, 'priority', 0)})"
				)
			
		if not sources:
			return "No knowledge sources assigned to this agent."
			
		return "Available Knowledge Sources:\n" + "\n".join(sources)
		
	except Exception as e:
		return f"Error retrieving knowledge sources: {str(e)}"
