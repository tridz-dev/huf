# Copyright (c) 2025, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Local runtime adapter registry.

Maps AI Provider.provider_brand values to the appropriate LocalRuntimeAdapter
implementation. Provides a single entry point for selecting the right adapter
based on the provider brand.
"""

from .generic_openai import GenericOpenAIAdapter
from .mlx_server import MlxServerAdapter
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
			- "mlx" → MlxServerAdapter
			- None, empty, unrecognized → OllamaAdapter (default, preserves today's behaviour)

	Note:
		"laya" is not mapped here. Laya is a decision-runtime provider served over
		HTTP by a PyTorch sidecar (laya-serve), not a local generation runtime, and
		has no LocalRuntimeAdapter implementation.
	"""
	if not provider_brand:
		# Unset, None, or empty string → default to Ollama
		return OllamaAdapter()

	brand_lower = provider_brand.lower()

	if brand_lower == "ollama":
		return OllamaAdapter()
	elif brand_lower in ("lmstudio", "vllm"):
		return GenericOpenAIAdapter()
	elif brand_lower == "mlx":
		return MlxServerAdapter()
	else:
		# Unrecognized brand → default to Ollama
		return OllamaAdapter()
