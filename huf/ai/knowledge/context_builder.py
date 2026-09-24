"""Build knowledge context for agent prompts with RAG Filter decision integration.

PLAN.md §3.8: Query-time filtering runs on already-authorized results from retriever.py.
The RAG Filter binding narrows retrieved passages (Enforce) or annotates them with scores (Advise).
"""

from typing import List, Dict, Any, Optional, Sequence
import frappe

from .retriever import knowledge_search, get_mandatory_knowledge, get_optional_knowledge


def _apply_rag_filter_decision(
	agent_doc: Any,
	chunks: List[Dict[str, Any]],
	user_query: str,
) -> tuple[List[Dict[str, Any]], Optional[str]]:
	"""Apply RAG Filter decision binding to authorized retrieval results.

	PLAN.md §3.8: Runs after retrieval but before injection. Enforce mode narrows
	the chunk set; Advise mode returns all chunks with a hint. No decision or Off
	mode returns all chunks unchanged.

	Args:
		agent_doc: The Agent document with decision_bindings.
		chunks: List of retrieved chunks (dicts with 'chunk_id', 'text', 'score', etc.).
		user_query: The user's search query (for decision policy context).

	Returns:
		Tuple of (filtered_chunks, hint_or_none).
	"""
	try:
		from huf.ai.decision.agent_surfaces import decide_for_surface
		from huf.ai.decision.types import DecisionOrigin, CandidateSource, Option
		from huf.ai.decision.rag import apply_rag_filter_decision
	except ImportError:
		# Decision runtime not available; proceed without filtering
		return chunks, None

	if not agent_doc or not chunks:
		return chunks, None

	try:
		# Build candidate Option objects from chunks (passage ids + titles)
		candidates = tuple(
			Option(chunk["chunk_id"], chunk.get("title", chunk["chunk_id"]))
			for chunk in chunks
		)

		# Get current agent run context for origin
		run_id = getattr(frappe.flags, "huf_current_agent_run_id", None) if hasattr(frappe, "flags") else None
		origin = DecisionOrigin(
			origin_type="Agent Run",
			agent=getattr(agent_doc, "name", None),
			agent_run=run_id,
		)

		# State for the decision policy: passage scores and metadata
		state = {
			"query": user_query,
			"passage_count": len(chunks),
			"scores": [chunk.get("score", 0) for chunk in chunks],
		}

		# Call the decision system
		decision = decide_for_surface(
			agent_doc,
			"RAG Filter",
			candidates,
			state,
			origin,
			candidate_source=CandidateSource.AUTHORIZED_KNOWLEDGE_CHUNKS,
			hint_kind="passages",
		)

		# Apply the decision result
		if decision is None:
			# Off mode or no binding
			return chunks, None

		# Filter or keep based on mode
		if decision.selected_ids is not None:
			# Enforce mode: narrow to selected ids
			selected_set = set(decision.selected_ids)
			filtered_chunks = [c for c in chunks if c["chunk_id"] in selected_set]
			return filtered_chunks, None

		# Advise mode: keep all chunks but return hint
		return chunks, decision.hint

	except Exception as e:
		# Log but do not fail; knowledge context is not critical
		frappe.log_error(
			title="RAG Filter decision error",
			message=str(e)
		)
		return chunks, None


def build_knowledge_context(
	agent_name: str,
	user_query: str,
	max_tokens: int = 4000,
	agent_doc: Optional[Any] = None,
) -> Dict[str, Any]:
	"""
	Build knowledge context to inject into agent prompt.

	This is called for mandatory knowledge sources before agent execution.
	Integrates RAG Filter decision binding to optionally narrow retrieved passages.

	Args:
		agent_name: Name of the agent
		user_query: The user's query (used for search)
		max_tokens: Maximum tokens for knowledge context
		agent_doc: Optional Agent document (loaded if not provided). Used for RAG Filter
			decision binding.

	Returns:
		Dict with 'context_text', 'sources_used', 'chunks_used', 'rag_filter_hint' (if Advise mode)
	"""
	if agent_doc is None:
		try:
			agent_doc = frappe.get_cached_doc("Agent", agent_name)
		except (frappe.DoesNotExistError, frappe.ValidationError):
			agent_doc = None

	mandatory_sources = get_mandatory_knowledge(agent_name)

	try:
		from huf.ai.skills.loader import get_mandatory_skill_knowledge
		mandatory_sources += get_mandatory_skill_knowledge(agent_name)
	except Exception:
		pass

	if not mandatory_sources:
		return {
			"context_text": "",
			"sources_used": [],
			"chunks_used": [],
			"rag_filter_hint": None,
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
				ignore_permissions=True,  # Agent has explicit knowledge linkage
			)

			if results:
				all_chunks.extend(results)
				sources_used.append(source_name)

		except Exception as e:
			frappe.log_error(title=frappe.get_traceback(), message=f"Knowledge context error for {source_name}")

	if not all_chunks:
		return {
			"context_text": "",
			"sources_used": [],
			"chunks_used": [],
			"rag_filter_hint": None,
		}

	# Apply RAG Filter decision (T8.02)
	filtered_chunks, rag_filter_hint = _apply_rag_filter_decision(agent_doc, all_chunks, user_query)

	# Build context text with source attribution
	context_parts = ["## Relevant Knowledge\n"]
	chunks_used = []
	estimated_tokens = 0

	for chunk in filtered_chunks:
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
		"rag_filter_hint": rag_filter_hint,
	}


def inject_knowledge_context(
	prompt: str,
	knowledge_context: Dict[str, Any],
) -> str:
	"""
	Inject knowledge context into the agent prompt.

	Places knowledge before the user's message. If RAG Filter Advise mode produced
	a hint, it is included after the knowledge sections but before the user prompt.
	"""
	if not knowledge_context.get("context_text"):
		context_text = ""
	else:
		context_text = knowledge_context["context_text"]

	# Collect all pieces to inject
	parts = []
	if context_text:
		parts.append(context_text)

	# Add RAG Filter hint if present (Advise mode)
	if knowledge_context.get("rag_filter_hint"):
		parts.append(f"## {knowledge_context['rag_filter_hint']}")

	if not parts:
		return prompt

	# Insert all context before the prompt
	parts.append(prompt)
	return "\n---\n\n".join(parts)
