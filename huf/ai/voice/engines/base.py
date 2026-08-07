"""The provider contract implemented by each voice engine."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class VoiceEngine(ABC):
	"""Abstract base class for voice engines.

	A voice engine mints and manages voice sessions for an Agent, either by
	composing HUF's existing text pipeline with speech-to-text/text-to-speech
	("composed") or by delegating the whole conversation to a realtime speech
	provider ("realtime"). Concrete engines live under ``huf.ai.voice.engines``
	and are registered in ``huf.ai.voice`` (built-in or via the
	``huf_voice_engines`` hook).
	"""

	key: str
	label: str
	kind: str  # "composed" or "realtime"

	@classmethod
	def get_config_schema(cls) -> list[dict[str, Any]]:
		"""Return schema for this engine's configuration fields.

		Each entry is shaped::

			{key, label, type, default, help_text, options?, visible_when?}

		``type`` is one of ``"text"``, ``"number"``, ``"boolean"``, ``"select"``,
		``"secret"``. ``options`` is only present for ``"select"``.
		``visible_when`` is an optional ``{field: value}`` dict used by the
		client to conditionally show/hide the field.

		Fields of type ``"secret"`` are stored server-side in a Frappe
		``Password`` field and MUST NEVER be returned to a client in plaintext.
		When reporting the current value of a secret field back to a client,
		the API must return ``{"has_value": True}`` (or ``{"has_value": False}``
		if unset) instead of the actual secret.
		"""
		return []

	@abstractmethod
	def health(self, agent_doc, config: dict[str, Any]) -> dict[str, Any]:
		"""Check whether this engine is reachable/configured for the given agent."""

	def list_voices(self, agent_doc, config: dict[str, Any]) -> list[dict[str, Any]]:
		"""Return the voices available for this engine/agent, if applicable."""
		return []

	@abstractmethod
	def start_session(self, agent_doc, config: dict[str, Any], user_ref: Any) -> dict[str, Any]:
		"""Mint a new voice session for ``agent_doc`` and return session details.

		``agent_doc`` is an already-resolved Agent document; ``user_ref`` is an
		opaque reference to the caller (it may be a Frappe user id, a
		publishable-key identity, or a server-secret caller identity - the
		engine must treat it as opaque and MUST NOT interpret it).

		This method MUST NOT read ``frappe.session.user``. Authentication and
		authorization are the caller's concern (see ``huf.ai.voice.api``), so
		that session-authenticated, publishable-key, and server-secret callers
		can all share this one session-minting path without the engine caring
		which kind of caller it is.
		"""

	def end_session(self, session_id: str) -> None:
		"""End an active voice session. Default is a no-op."""
		return None

	def handle_event(self, payload: dict[str, Any], agent_doc) -> None:
		"""Handle an inbound provider webhook/event payload. Default is a no-op."""
		return None

	def send_to_session(self, session_id: str, *, kind: str, text: str) -> None:
		"""Push out-of-band content into an active session.

		``kind`` is one of:

		- ``"context"``: non-interrupting background info. The agent keeps
		  talking/listening uninterrupted; the content is folded in silently.
		- ``"user_message"``: takes a conversational turn and prompts a
		  response, as if the user had said it.
		- ``"activity"``: a brief pause signal (e.g. "user is typing"), not a
		  turn and not spoken content.

		This distinction MUST NOT be collapsed: injecting background context
		must never interrupt the agent mid-sentence the way a user message
		would. Engines that do not support out-of-band injection should leave
		this method raising ``NotImplementedError``.
		"""
		raise NotImplementedError

	def declare_client_tools(self, agent_doc, user_ref: Any = None) -> list[dict[str, Any]]:
		"""Return client-side tool declarations this engine wants exposed.

		``user_ref`` mirrors ``start_session``'s contract: implementations
		resolving the allowed tool set per-caller (e.g. via a permission-aware
		registry) should use ``user_ref`` rather than reading
		``frappe.session.user`` directly, so this also works for
		publishable-key/server-secret sessions where there is no session user.
		Defaulting to ``None`` keeps this backward compatible; callers that
		don't yet have a caller identity to pass may omit it.
		"""
		return []
