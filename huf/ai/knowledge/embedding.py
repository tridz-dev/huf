"""
Embedding Infrastructure for Knowledge System.

Provides model-agnostic embedding functions using LiteLLM's unified API.
Supports OpenAI, Gemini, Cohere, HuggingFace, and any LiteLLM-compatible provider.
"""

import frappe
from typing import List, Dict, Any, Optional


# Maximum texts per batch request (most APIs cap at 2048, we use conservative default)
DEFAULT_BATCH_SIZE = 100


def get_embedding(
	text: str,
	model: str,
	api_key: Optional[str] = None,
	api_base: Optional[str] = None,
) -> List[float]:
	"""
	Get embedding vector for a single text string.

	Args:
		text: The text to embed.
		model: LiteLLM model identifier (e.g. 'openai/text-embedding-3-small').
		api_key: Optional API key. If None, resolved from environment or provider config.
		api_base: Optional API base URL for custom endpoints.

	Returns:
		List of floats representing the embedding vector.
	"""
	import litellm

	kwargs = {"model": model, "input": [text]}
	if api_key:
		kwargs["api_key"] = api_key
	if api_base:
		kwargs["api_base"] = api_base

	response = litellm.embedding(**kwargs)
	return response.data[0]["embedding"]


def get_embeddings(
	texts: List[str],
	model: str,
	api_key: Optional[str] = None,
	api_base: Optional[str] = None,
	batch_size: int = DEFAULT_BATCH_SIZE,
) -> List[List[float]]:
	"""
	Get embedding vectors for multiple texts with batched requests.

	Processes texts in batches to respect API rate limits and payload size constraints.

	Args:
		texts: List of texts to embed.
		model: LiteLLM model identifier.
		api_key: Optional API key.
		api_base: Optional API base URL.
		batch_size: Number of texts per API call. Default: 100.

	Returns:
		List of embedding vectors, one per input text (preserves order).
	"""
	import litellm

	if not texts:
		return []

	all_embeddings = []

	for i in range(0, len(texts), batch_size):
		batch = texts[i : i + batch_size]

		kwargs = {"model": model, "input": batch}
		if api_key:
			kwargs["api_key"] = api_key
		if api_base:
			kwargs["api_base"] = api_base

		response = litellm.embedding(**kwargs)

		# Sort by index to guarantee order matches input
		sorted_data = sorted(response.data, key=lambda x: x["index"])
		batch_embeddings = [item["embedding"] for item in sorted_data]
		all_embeddings.extend(batch_embeddings)

	return all_embeddings


def resolve_embedding_config(knowledge_source: str) -> Dict[str, Any]:
	"""
	Resolve embedding configuration from a Knowledge Source document.

	Reads the embedding_model, vector_dimension, and embedding_provider fields
	from the Knowledge Source DocType and resolves the API key from the linked
	AI Provider.

	Args:
		knowledge_source: Name of the Knowledge Source document.

	Returns:
		Dict with keys: model, dimension, api_key, api_base
	"""
	source = frappe.get_doc("Knowledge Source", knowledge_source)

	model = source.embedding_model
	dimension = source.vector_dimension or 1536

	api_key = None
	api_base = None

	if source.embedding_provider:
		provider = frappe.get_doc("AI Provider", source.embedding_provider)
		api_key = provider.get_password("api_key") if provider.api_key else None
		api_base = getattr(provider, "api_base", None) or None

	return {
		"model": model,
		"dimension": dimension,
		"api_key": api_key,
		"api_base": api_base,
	}
