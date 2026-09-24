# Copyright (c) 2025, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Local LLM server adapter Protocol.

Defines a runtime adapter interface that abstracts "a local LLM server we can
probe" (e.g. Ollama, MLX Server). Implementations of this Protocol handle
server reachability checks, model listing, per-model capability queries, and
capability-to-override mapping.
"""

from typing import Protocol


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

	def capability_overrides(self, probe: dict) -> dict:
		"""Map a probe_model() result to Huf configuration overrides.

		Takes the whole probe result, not just its capability list, because the
		``None`` vs ``False`` distinction for ``supports_tools`` depends on whether
		the probe SUCCEEDED, not on whether the list happens to be empty. A model
		that was probed successfully and did not report "tools" definitively does
		not support them (``False``); a model that could not be probed at all is
		unknown (``None``). A list-only signature cannot express that difference,
		which is why this takes the dict.

		Args:
			probe: A probe_model() result -- {"ok", "capabilities", "error"}.

		Returns:
			dict: {"supports_tools": bool | None, "is_reasoning_model": bool}.
				- supports_tools: True if the probe succeeded and reported tool
					support; False if the probe succeeded and did not; None if the
					model could not be probed. Never assume False for an unprobed
					model -- preserve the "unknown" state so Huf does not silently
					degrade behaviour on a probe failure.
				- is_reasoning_model: True if the probe succeeded and reported
					reasoning/thinking support; False otherwise (including unprobed).
		"""
		...
