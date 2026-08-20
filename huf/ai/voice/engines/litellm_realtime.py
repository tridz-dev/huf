"""LiteLLM Realtime voice engine (OpenAI Realtime API, via an ASGI sidecar).

This engine does not hold the duplex WebSocket to the realtime provider
itself - that is owned by a separate ASGI sidecar process
(``huf.ai.voice.sidecar.app``). This engine's job is only to validate
configuration, mint a session id, and stash the session details the sidecar
needs into ``frappe.cache()`` under a well-known key so the sidecar can pick
them up when the browser connects to it directly.
"""

from __future__ import annotations

import json
from typing import Any

import frappe
from frappe.rate_limiter import rate_limit

from huf.ai.tool_registry import PermissionAwareToolRegistry
from huf.ai.voice.engines.base import VoiceEngine

SESSION_CACHE_KEY_PREFIX = "huf:voice:realtime:session:"
SESSION_CACHE_EXPIRY_SEC = 300
REQUIRED_MODALITY = "Speech-to-Speech"


class LitellmRealtimeEngine(VoiceEngine):
	key = "litellm_realtime"
	label = "Realtime Voice (OpenAI)"
	kind = "realtime"

	@classmethod
	def get_config_schema(cls) -> list[dict[str, Any]]:
		# Options are AI Model docnames, not wire model ids - health()/
		# start_session() below resolve `config["model"]` via
		# frappe.db.exists("AI Model", model_name), so the schema must offer
		# the same identifier space the Voice tab UI will write back
		# verbatim, or every session minted through the default UI path
		# fails validation.
		model_names = [
			row.name
			for row in frappe.get_all(
				"AI Model",
				filters=[["modalities", "like", f"%{REQUIRED_MODALITY}%"]],
				fields=["name"],
				order_by="name",
			)
		]
		options = [{"label": name, "value": name} for name in model_names]
		return [
			{
				"key": "model",
				"label": "Realtime Model",
				"type": "select",
				"default": "",
				"help_text": (
					"The AI Model to use for this realtime voice session - must "
					"have Speech-to-Speech modality."
				),
				"options": options,
			},
		]

	@classmethod
	def capabilities(cls) -> dict[str, bool]:
		return {
			"instructions": False,  # the sidecar relays raw provider frames; it does not send Agent.instructions - see sidecar/app.py
			"tools": True,  # via declare_client_tools below (client-side tools only)
			"memory": False,
			"persistence": True,  # best-effort transcript capture in the sidecar - see sidecar/app.py
			"barge_in": True,  # OpenAI Realtime supports server-side VAD interruption by default
		}

	def health(self, agent_doc, config: dict[str, Any]) -> dict[str, Any]:
		model_name = (config or {}).get("model")
		if not model_name:
			return {"ok": False, "message": "Missing model in voice config."}

		if not frappe.db.exists("AI Model", model_name):
			return {"ok": False, "message": f"AI Model '{model_name}' does not exist."}

		modalities = frappe.db.get_value("AI Model", model_name, "modalities") or ""
		modality_list = [m.strip() for m in modalities.split(",") if m.strip()]
		if REQUIRED_MODALITY not in modality_list:
			return {
				"ok": False,
				"message": f"AI Model '{model_name}' does not support {REQUIRED_MODALITY} modality.",
			}

		provider_name = frappe.db.get_value("AI Model", model_name, "provider")
		if not provider_name:
			return {"ok": False, "message": f"AI Model '{model_name}' has no linked AI Provider."}

		provider = frappe.get_doc("AI Provider", provider_name)
		if not provider.get_password("api_key"):
			return {"ok": False, "message": f"AI Provider '{provider_name}' has no API key set."}

		return {"ok": True, "message": "LiteLLM realtime model is configured."}

	@rate_limit(limit=10, seconds=60)
	def start_session(
		self, agent_doc, config: dict[str, Any], user_ref: Any, *, conversation_id: str | None = None
	) -> dict[str, Any]:
		# model comes only from the per-Agent voice_config resolved upstream in
		# huf.ai.voice.api - never from user_ref or any browser-supplied value.
		# This method MUST NOT read frappe.session.user (see base.VoiceEngine
		# docstring) - it is shared by publishable-key/server-secret callers.
		model_name = (config or {}).get("model")
		if not model_name:
			frappe.throw("Missing model in LiteLLM realtime voice config.", frappe.ValidationError)

		if not frappe.db.exists("AI Model", model_name):
			frappe.throw(f"AI Model '{model_name}' does not exist.", frappe.ValidationError)

		provider_name = frappe.db.get_value("AI Model", model_name, "provider")
		if not provider_name:
			frappe.throw(
				f"AI Model '{model_name}' has no linked AI Provider.", frappe.ValidationError
			)

		session_id = frappe.generate_hash(length=32)
		cache_key = f"{SESSION_CACHE_KEY_PREFIX}{session_id}"
		payload = {
			"agent": agent_doc.name,
			"model": model_name,
			"api_key_provider": provider_name,
			"conversation_id": conversation_id,
		}
		frappe.cache().set_value(cache_key, payload, expires_in_sec=SESSION_CACHE_EXPIRY_SEC)

		result = {
			"engine": "litellm_realtime",
			"session_id": session_id,
			"sidecar_ws_path": f"/voice/realtime/{session_id}",
		}
		if conversation_id:
			result["conversation_id"] = conversation_id
		return result

	def end_session(self, session_id: str) -> None:
		# Deletes the stashed cache key so a browser reconnect after an
		# explicit hangup cannot reuse a stale session.
		frappe.cache().delete_value(f"{SESSION_CACHE_KEY_PREFIX}{session_id}")

	def declare_client_tools(self, agent_doc, user_ref: Any = None) -> list[dict[str, Any]]:
		tool_docs = PermissionAwareToolRegistry.get_allowed_tools(agent_doc, user_ref or frappe.session.user)

		declarations = []
		for tool_doc in tool_docs:
			if tool_doc.types != "Client Side Tool" or not tool_doc.function_name:
				continue

			parameters = {}
			if tool_doc.params:
				try:
					parameters = json.loads(tool_doc.params)
				except json.JSONDecodeError:
					parameters = {}

			declarations.append(
				{
					"name": tool_doc.tool_name,
					"description": tool_doc.description or "",
					"parameters": parameters,
				}
			)

		return declarations
