# Copyright (c) 2025, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Generic OpenAI-compatible local LLM server adapter.

Implements LocalRuntimeAdapter Protocol for OpenAI-compatible servers
(e.g. LMStudio, vLLM), providing server probing and model listing via the
/v1/models endpoint. Does not expose per-model capability metadata.
"""

import requests

_PROBE_TIMEOUT = 5


class GenericOpenAIAdapter:
	"""Adapter for OpenAI-compatible local LLM servers.

	Probes OpenAI-style HTTP API endpoints to discover available models.
	Does not query per-model capabilities because OpenAI-compatible servers
	do not expose tool-support metadata in their model listings.
	"""

	def flavor(self) -> str:
		"""Return the adapter flavor identifier.

		Returns:
			str: "generic_openai"
		"""
		return "generic_openai"

	def probe_server(self, api_base: str) -> dict:
		"""Ping an OpenAI-compatible server and list its available models.

		Queries the /v1/models endpoint. Returns {"ok": bool, "models": [...], "error": str|None}.
		Never raises.

		Args:
			api_base: Server URL (e.g. "http://localhost:8000").

		Returns:
			dict: {"ok": bool, "models": list[str], "error": str | None}.
				- ok: True if server is reachable and responded.
				- models: List of model names available on the server (empty if ok is False).
				- error: None on success; error message on failure.
		"""
		try:
			resp = requests.get(
				f"{api_base.rstrip('/')}/v1/models", timeout=_PROBE_TIMEOUT
			)
			resp.raise_for_status()
			data = resp.json()
			models = [
				m.get("id")
				for m in data.get("data", [])
				if m.get("id")
			]
			return {"ok": True, "models": models, "error": None}
		except Exception as e:
			return {"ok": False, "models": [], "error": str(e)}

	def probe_model(self, api_base: str, model: str) -> dict:
		"""Query an OpenAI-compatible server for a single model's presence.

		Checks whether the model appears in the /v1/models listing.
		Returns {"ok": bool, "capabilities": [], "error": str|None}.
		Capabilities list is always empty because OpenAI-compatible endpoints
		do not expose per-model tool-capability metadata.
		Never raises.

		Args:
			api_base: Server URL (e.g. "http://localhost:8000").
			model: Model name or identifier.

		Returns:
			dict: {"ok": bool, "capabilities": [], "error": str | None}.
				- ok: True if the model was found in the /v1/models listing.
				- capabilities: Always empty list (this server type cannot tell us).
				- error: None on success; error message on failure.
		"""
		try:
			resp = requests.get(
				f"{api_base.rstrip('/')}/v1/models", timeout=_PROBE_TIMEOUT
			)
			resp.raise_for_status()
			data = resp.json()
			models = [
				m.get("id")
				for m in data.get("data", [])
				if m.get("id")
			]
			if model in models:
				return {"ok": True, "capabilities": [], "error": None}
			else:
				return {"ok": False, "capabilities": [], "error": f"model '{model}' not found"}
		except Exception as e:
			return {"ok": False, "capabilities": [], "error": str(e)}

	def capability_overrides(self, probe: dict) -> dict:
		"""Map a probe_model() result to Huf configuration overrides.

		For OpenAI-compatible servers, supports_tools is ALWAYS None because
		these endpoints do not expose per-model tool-capability metadata.
		This is the one legitimate exception to the "successful probe gives a
		definite bool" rule that OllamaAdapter follows: an OpenAI-compatible
		endpoint cannot tell us whether a model supports tools, even if it
		responds successfully. The honest answer is "unknown", never False and
		never an assumed True.

		Args:
			probe: A probe_model() result -- {"ok", "capabilities", "error"}.

		Returns:
			dict: {"supports_tools": None, "is_reasoning_model": False}.
				- supports_tools: Always None for generic OpenAI (server cannot tell us).
				- is_reasoning_model: Always False (no metadata available).
		"""
		return {"supports_tools": None, "is_reasoning_model": False}
