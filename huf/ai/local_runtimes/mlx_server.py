# Copyright (c) 2025, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
MLX local LLM server adapter.

Implements LocalRuntimeAdapter Protocol for MLX's OpenAI-compatible HTTP server
(mlx_lm.server), providing server probing and model listing via the /v1/models
endpoint. Surfaces host-level MLX device state (not installed, installed-but-
degraded, or working with Metal) via mlx_probe.
"""

import requests

from . import mlx_probe

_PROBE_TIMEOUT = 5


class MlxServerAdapter:
	"""Adapter for MLX OpenAI-compatible local LLM server.

	Probes MLX's HTTP API to discover available models. Does not query per-model
	capabilities because MLX's server does not expose tool-support metadata in
	its model listings. Surfaces host-level MLX device state via mlx_probe.
	"""

	def flavor(self) -> str:
		"""Return the adapter flavor identifier.

		Returns:
			str: "mlx_server"
		"""
		return "mlx_server"

	def probe_server(self, api_base: str) -> dict:
		"""Ping an MLX server and list its available models.

		Queries the /v1/models endpoint (OpenAI-compatible). Returns
		{"ok": bool, "models": [...], "error": str|None}.
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
		"""Query an MLX server for a single model's presence.

		Checks whether the model appears in the /v1/models listing.
		Returns {"ok": bool, "capabilities": [], "error": str|None}.
		Capabilities list is always empty because MLX's server does not expose
		per-model tool-capability metadata.
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

		For MLX's server, supports_tools is ALWAYS None because MLX's HTTP
		endpoint does not expose per-model tool-capability metadata. This is
		the one legitimate exception to the "successful probe gives a definite
		bool" rule that OllamaAdapter follows: an MLX endpoint cannot tell us
		whether a model supports tools, even if it responds successfully. The
		honest answer is "unknown" (None), never False and never an assumed True.

		Args:
			probe: A probe_model() result -- {"ok", "capabilities", "error"}.

		Returns:
			dict: {"supports_tools": None, "is_reasoning_model": False}.
				- supports_tools: Always None for MLX server (server cannot tell us).
				- is_reasoning_model: Always False (no metadata available).
		"""
		return {"supports_tools": None, "is_reasoning_model": False}

	def get_device_info(self) -> dict:
		"""Retrieve host-level MLX device information.

		Surfaces the state of MLX on this host: whether the package is installed,
		whether a Metal device is available, and the installed version.

		Returns:
			dict: Result from mlx_probe.probe_device() with keys:
				- import_ok (bool): whether `import mlx` succeeded.
				- device (str | None): str(mx.default_device()) if available, else None.
				- metal_available (bool): whether Metal is available.
				- mlx_version (str | None): installed MLX distribution version.
		"""
		return mlx_probe.probe_device()

	def describe_device(self) -> str:
		"""Get a human-readable description of the host MLX device state.

		Distinguishes "MLX not installed" from "MLX installed but no Metal
		(degraded)" so that callers can surface a typed reason without
		re-deriving the wording.

		Returns:
			str: A human-readable reason describing MLX availability.
		"""
		probe_result = self.get_device_info()
		return mlx_probe.describe_probe_result(probe_result)
