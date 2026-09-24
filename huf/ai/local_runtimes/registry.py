# Copyright (c) 2025, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Local runtime adapter registry.

Maps AI Provider.provider_brand values to the appropriate LocalRuntimeAdapter
implementation. Provides a single entry point for selecting the right adapter
based on the provider brand.
"""

from .generic_openai import GenericOpenAIAdapter
from .ollama import OllamaAdapter


def get_adapter(provider_brand: str | None):
	"""Get the appropriate LocalRuntimeAdapter for a provider brand.

	Routes a provider brand string to its corresponding adapter implementation.
	Matching is case-insensitive.

	Args:
		provider_brand: The provider brand string (e.g. "ollama", "lmstudio").
			Can be None, empty string, or unrecognized.

	Returns:
		LocalRuntimeAdapter: An adapter instance.
			- "ollama" → OllamaAdapter
			- "lmstudio" → GenericOpenAIAdapter
			- "vllm" → GenericOpenAIAdapter
			- None, empty, unrecognized → OllamaAdapter (default, preserves today's behaviour)

	Note:
		MLX is registered by a separate task (T2.04) and must not collide with
		this file. Leave a short comment noting MLX is registered by that task.
	"""
	if not provider_brand:
		# Unset, None, or empty string → default to Ollama
		return OllamaAdapter()

	brand_lower = provider_brand.lower()

	if brand_lower == "ollama":
		return OllamaAdapter()
	elif brand_lower in ("lmstudio", "vllm"):
		return GenericOpenAIAdapter()
	else:
		# Unrecognized brand → default to Ollama
		return OllamaAdapter()

	# MLX adapter is wired in by task T2.04 (in that task's own file/registry update)
