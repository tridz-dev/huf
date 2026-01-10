"""Build knowledge context for agent prompts."""

from typing import List, Dict, Any
import frappe

from .retriever import knowledge_search, get_mandatory_knowledge


def build_knowledge_context(
	agent_name: str,
	user_query: str,
	max_tokens: int = 4000,
) -> Dict[str, Any]:
	"""
	Build knowledge context to inject into agent prompt.
	
	This is called for mandatory knowledge sources before agent execution.
	
	Args:
		agent_name: Name of the agent
		user_query: The user's query (used for search)
		max_tokens: Maximum tokens for knowledge context
	
	Returns:
		Dict with 'context_text', 'sources_used', 'chunks_used'
	"""
	mandatory_sources = get_mandatory_knowledge(agent_name)
	
	if not mandatory_sources:
		return {
			"context_text": "",
			"sources_used": [],
			"chunks_used": [],
		}
	
	all_chunks = []
	sources_used = []
	
	for source_config in mandatory_sources:
		source_name = source_config["knowledge_source"]
		max_chunks = source_config["max_chunks"]
		
		try:
			results = knowledge_search(
				query=user_query,
				knowledge_source=source_name,
				top_k=max_chunks,
			)
			
			if results:
				all_chunks.extend(results)
				sources_used.append(source_name)
				
		except Exception as e:
			frappe.log_error(
				f"Knowledge context error for {source_name}",
				frappe.get_traceback()
			)
	
	if not all_chunks:
		return {
			"context_text": "",
			"sources_used": [],
			"chunks_used": [],
		}
	
	# Build context text with source attribution
	context_parts = ["## Relevant Knowledge\n"]
	chunks_used = []
	estimated_tokens = 0
	
	for chunk in all_chunks:
		# Rough token estimation (4 chars per token)
		chunk_tokens = len(chunk["text"]) // 4
		
		if estimated_tokens + chunk_tokens > max_tokens:
			break
		
		context_parts.append(f"### {chunk.get('title', 'Source')}\n")
		context_parts.append(chunk["text"])
		context_parts.append("\n\n")
		
		chunks_used.append({
			"chunk_id": chunk["chunk_id"],
			"source": chunk["source"],
			"title": chunk.get("title"),
		})
		
		estimated_tokens += chunk_tokens
	
	return {
		"context_text": "".join(context_parts),
		"sources_used": sources_used,
		"chunks_used": chunks_used,
	}


def inject_knowledge_context(
	prompt: str,
	knowledge_context: Dict[str, Any],
) -> str:
	"""
	Inject knowledge context into the agent prompt.
	
	Places knowledge before the user's message.
	"""
	if not knowledge_context.get("context_text"):
		return prompt
	
	context_text = knowledge_context["context_text"]
	
	# Insert context before the prompt
	return f"{context_text}\n---\n\n{prompt}"
