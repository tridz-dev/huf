"""ElevenLabs Conversational AI voice engine.

Implemented natively over raw HTTP (``requests``) against the ElevenLabs
Conversational AI REST API - no ``@elevenlabs/*`` SDK or
``frappe_ElevenLabs`` app dependency.
"""

from __future__ import annotations

import json
from typing import Any

import frappe
import requests
from frappe.rate_limiter import rate_limit

from huf.ai.tool_registry import PermissionAwareToolRegistry
from huf.ai.voice.engines.base import VoiceEngine

SETTINGS_DOCTYPE = "Elevenlabs Settings"
API_BASE = "https://api.elevenlabs.io/v1"


class ElevenLabsConvaiEngine(VoiceEngine):
	key = "elevenlabs_convai"
	label = "ElevenLabs Conversational AI"
	kind = "realtime"

	@classmethod
	def get_config_schema(cls) -> list[dict[str, Any]]:
		return [
			{
				"key": "agent_id",
				"label": "ElevenLabs Agent ID",
				"type": "text",
				"default": "",
				"help_text": (
					"The ElevenLabs Conversational AI agent id to use for this HUF "
					"Agent. Set here by an admin only - never taken from a caller "
					"or request."
				),
			},
		]

	def _get_api_key(self) -> str | None:
		if not frappe.db.exists("DocType", SETTINGS_DOCTYPE):
			return None
		settings = frappe.get_single(SETTINGS_DOCTYPE)
		if not settings.provider:
			return None
		provider = frappe.get_doc("AI Provider", settings.provider)
		return provider.get_password("api_key")

	def health(self, agent_doc, config: dict[str, Any]) -> dict[str, Any]:
		agent_id = (config or {}).get("agent_id")
		if not agent_id:
			return {"ok": False, "message": "Missing agent_id in voice config."}

		api_key = self._get_api_key()
		if not api_key:
			return {"ok": False, "message": "Missing ElevenLabs API key in Elevenlabs Settings."}

		try:
			response = requests.get(
				f"{API_BASE}/convai/agents/{agent_id}",
				headers={"xi-api-key": api_key},
				timeout=15,
			)
		except Exception as e:
			return {"ok": False, "message": f"Failed to reach ElevenLabs: {e!s}"}

		if not response.ok:
			return {"ok": False, "message": f"ElevenLabs API error ({response.status_code})"}

		return {"ok": True, "message": "ElevenLabs Conversational AI agent is reachable."}

	def list_voices(self, agent_doc, config: dict[str, Any]) -> list[dict[str, Any]]:
		api_key = self._get_api_key()
		if not api_key:
			return []

		response = requests.get(
			f"{API_BASE}/voices",
			headers={"xi-api-key": api_key},
			timeout=15,
		)
		if not response.ok:
			return []

		data = response.json()
		return [
			{"id": voice.get("voice_id"), "name": voice.get("name")}
			for voice in data.get("voices", [])
		]

	@rate_limit(limit=10, seconds=60)
	def start_session(self, agent_doc, config: dict[str, Any], user_ref: Any) -> dict[str, Any]:
		# agent_id comes only from the per-Agent voice_config resolved upstream in
		# huf.ai.voice.api - never from user_ref or any browser-supplied value.
		agent_id = (config or {}).get("agent_id")
		if not agent_id:
			frappe.throw("Missing agent_id in ElevenLabs voice config.", frappe.ValidationError)

		api_key = self._get_api_key()
		if not api_key:
			frappe.throw("Missing ElevenLabs API key in Elevenlabs Settings.", frappe.ValidationError)

		url = f"{API_BASE}/convai/conversation/get-signed-url?agent_id={agent_id}"
		response = requests.get(
			url, headers={"xi-api-key": api_key}, timeout=30
		)

		if not response.ok:
			try:
				error_json = response.json()
				if error_json.get("detail", {}).get("status") == "missing_permissions":
					frappe.throw(
						"ElevenLabs API key is missing convai_write permission",
						frappe.PermissionError,
					)
			except Exception:
				pass
			frappe.throw(f"ElevenLabs API error ({response.status_code})", frappe.ValidationError)

		data = response.json()
		return {
			"engine": "elevenlabs_convai",
			"signed_url": data.get("signed_url"),
			"agent_id": agent_id,
		}

	# No documented ElevenLabs REST endpoint exists to explicitly end an active
	# Conversational AI conversation; the browser closing the WebSocket ends it.
	# Leaving end_session as the base class no-op.

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
					"expects_response": True,
				}
			)

		return declarations
