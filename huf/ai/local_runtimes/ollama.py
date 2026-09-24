# Copyright (c) 2025, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Ollama local LLM server adapter.

Implements LocalRuntimeAdapter Protocol for Ollama, providing server probing,
model listing, and per-model capability queries via HTTP.
"""

import requests

_PROBE_TIMEOUT = 5


class OllamaAdapter:
	"""Adapter for Ollama local LLM server.

	Probes Ollama's HTTP API to discover available models and their capabilities.
	"""

	def flavor(self) -> str:
		"""Return the adapter flavor identifier.

		Returns:
			str: "ollama"
		"""
		return "ollama"

	def probe_server(self, api_base: str) -> dict:
		"""Ping an Ollama server and list its pulled models.

		Returns {"ok": bool, "models": [...], "error": str|None}. Never raises.

		Args:
			api_base: Server URL (e.g. "http://localhost:11434").

		Returns:
			dict: {"ok": bool, "models": list[str], "error": str | None}.
				- ok: True if server is reachable and responded.
				- models: List of model names available on the server (empty if ok is False).
				- error: None on success; error message on failure.
		"""
		try:
			resp = requests.get(
				f"{api_base.rstrip('/')}/api/tags", timeout=_PROBE_TIMEOUT
			)
			resp.raise_for_status()
			data = resp.json()
			models = [
				m.get("name")
				for m in data.get("models", [])
				if m.get("name")
			]
			return {"ok": True, "models": models, "error": None}
		except Exception as e:
			return {"ok": False, "models": [], "error": str(e)}

	def probe_model(self, api_base: str, model: str) -> dict:
		"""Query Ollama for a single model's metadata and capabilities.

		Returns {"ok": bool, "capabilities": [...], "error": str|None}.
		When the model is not pulled, returns ok=False with the server error message.
		Never raises.

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
		name = model or ""
		for prefix in ("ollama_chat/", "ollama/"):
			if name.startswith(prefix):
				name = name[len(prefix):]
				break

		try:
			resp = requests.post(
				f"{api_base.rstrip('/')}/api/show",
				json={"name": name},
				timeout=_PROBE_TIMEOUT,
			)
			if resp.status_code != 200:
				try:
					error = resp.json().get("error") or resp.text
				except Exception:
					error = resp.text or f"HTTP {resp.status_code}"
				return {"ok": False, "capabilities": [], "error": str(error)}

			data = resp.json()
			capabilities = data.get("capabilities") or []
			return {"ok": True, "capabilities": capabilities, "error": None}
		except Exception as e:
			return {"ok": False, "capabilities": [], "error": str(e)}

	def capability_overrides(self, probe: dict) -> dict:
		"""Map a probe_model() result to Huf configuration overrides.

		Mirrors huf/ai/local_runtime.py:181-185 exactly: the capability flags are
		read only when the probe succeeded, so an unprobed model stays unknown
		(``supports_tools`` is None) while a successfully probed model that does
		not advertise "tools" is a definite False.

		Args:
			probe: A probe_model() result -- {"ok", "capabilities", "error"}.

		Returns:
			dict: {"supports_tools": bool | None, "is_reasoning_model": bool}.
		"""
		if not probe.get("ok"):
			return {"supports_tools": None, "is_reasoning_model": False}

		capabilities = probe.get("capabilities") or []
		return {
			"supports_tools": "tools" in capabilities,
			"is_reasoning_model": "thinking" in capabilities,
		}
