# Copyright (c) 2025, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Local LLM server adapter Protocol.

Defines a runtime adapter interface that abstracts "a local LLM server we can
probe" (e.g. Ollama, MLX Server). Implementations of this Protocol handle
server reachability checks, model listing, per-model capability queries, and
capability-to-override mapping.
"""

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
	pass


class LocalRuntimeAdapter(Protocol):
	"""Protocol for a local LLM server adapter.

	Implementations provide methods to probe a local server's status, list its
	models, query model capabilities, and map those capabilities to Huf
	configuration overrides (e.g. whether the model supports tool calls).
	"""

	def flavor(self) -> str:
		"""Return a stable identifier for this local-server flavor.

		Examples: "ollama", "mlx_server", "vllm".

		Returns:
			str: A lowercase, underscore-separated flavor name.
		"""
		...

	def probe_server(self, api_base: str) -> dict:
		"""Ping a local server and list its available models.

		Reachability + model listing. Returns a dict with fixed keys.
		On connection failure, ok is False and models is an empty list.

		Args:
			api_base: Server URL (e.g. "http://localhost:11434").

		Returns:
			dict: {"ok": bool, "models": list[str], "error": str | None}.
				- ok: True if server is reachable and responded.
				- models: List of model names available on the server (empty if ok is False).
				- error: None on success; error message on failure.
		"""
		...

	def probe_model(self, api_base: str, model: str) -> dict:
		"""Query a local server for a single model's capabilities.

		Per-model capability discovery (e.g. does this model support tool calls?
		does it support thinking/reasoning?). Returns a dict with fixed keys.
		On query failure, ok is False and capabilities is an empty list.

		Args:
			api_base: Server URL (e.g. "http://localhost:11434").
			model: Model name or identifier.

		Returns:
			dict: {"ok": bool, "capabilities": list[str], "error": str | None}.
				- ok: True if the model was probed successfully.
				- capabilities: List of capability strings (e.g. ["tools", "thinking"]).
					Empty if ok is False.
				- error: None on success; error message on failure.
		"""
		...

	def capability_overrides(self, capabilities: list[str]) -> dict:
		"""Map probed capabilities to Huf configuration overrides.

		Converts a capability list from probe_model() into structured overrides
		for model configuration (e.g. whether Huf should assume the model can
		handle tool calls, whether it is a reasoning model).

		Args:
			capabilities: List of capability strings from probe_model().

		Returns:
			dict: {"supports_tools": bool | None, "is_reasoning_model": bool}.
				- supports_tools: True if the model supports tool/function calling.
					None if the capability is unknown (not probed or not reported).
					Never assume False for unknown — preserve the "unknown" state so
					Huf does not degrade behavior when capability cannot be determined.
				- is_reasoning_model: True if the model supports reasoning/thinking.
					False if reasoning is not supported or unknown.
		"""
		...
