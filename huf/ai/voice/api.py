"""Whitelisted API endpoints for voice sessions.

These endpoints are the session-authenticated entry points into the voice
engine registry (``huf.ai.voice``). Publishable-key and server-secret callers
will be added later as additional thin wrappers over ``_mint_session`` -
see the comment on that function.
"""

from __future__ import annotations

import json
from typing import Any

import frappe
from frappe import _

from huf.ai.voice import get_engine, supported_engines
from huf.ai.voice.engines.base import VoiceEngine


def _get_agent_voice_config(agent_doc) -> tuple[str, dict[str, Any]]:
	"""Resolve the ``(engine_key, config)`` pair configured on an Agent.

	Tolerates both ``voice_engine`` and ``voice_config`` being unset, raising a
	clear user-facing error in that case rather than failing deeper in an
	engine.
	"""
	engine_key = getattr(agent_doc, "voice_engine", None)
	if not engine_key:
		frappe.throw(_("Agent '{0}' does not have a voice engine configured.").format(agent_doc.name))

	raw_config = getattr(agent_doc, "voice_config", None)
	if not raw_config:
		config: dict[str, Any] = {}
	else:
		try:
			config = json.loads(raw_config)
		except (TypeError, ValueError):
			frappe.throw(_("Agent '{0}' has an invalid voice configuration.").format(agent_doc.name))

	return engine_key, config


def _check_agent_access(agent_doc) -> None:
	"""Raise a PermissionError unless the current user may read ``agent_doc``.

	Shared by every whitelisted endpoint that acts on an Agent's voice session
	(``start_session``, ``end_session``, ``send_to_session``, ``list_voices``)
	so the access rule stays defined in exactly one place.
	"""
	if not frappe.has_permission("Agent", "read", doc=agent_doc):
		frappe.throw(_("Not permitted to read Agent '{0}'").format(agent_doc.name), frappe.PermissionError)


def _mint_session(agent_doc, config: dict[str, Any], user_ref: Any) -> dict[str, Any]:
	"""Resolve the agent's voice engine and start a session.

	Plain module-level function (NOT whitelisted). It intentionally does not
	reference ``frappe.session.user`` - callers are responsible for resolving
	and permission-checking ``agent_doc`` and for supplying an appropriate
	``user_ref`` before calling this. This lets session-authenticated,
	publishable-key, and server-secret callers all share this one
	session-minting path; those other callers will be added later as thin
	wrappers that resolve the Agent/permissions their own way and then call
	this same function.
	"""
	engine_key = getattr(agent_doc, "voice_engine", None)
	if not engine_key:
		frappe.throw(_("Agent '{0}' does not have a voice engine configured.").format(agent_doc.name))

	engine: VoiceEngine = get_engine(engine_key)
	return engine.start_session(agent_doc, config, user_ref)


@frappe.whitelist()
def list_engines() -> list[dict[str, Any]]:
	"""Return ``{key, label, kind}`` for every discovered voice engine."""
	engines = []
	for engine_key in supported_engines():
		engine_class = type(get_engine(engine_key))
		engines.append(
			{
				"key": engine_class.key,
				"label": engine_class.label,
				"kind": engine_class.kind,
			}
		)
	return engines


@frappe.whitelist()
def get_config_schema(engine: str) -> list[dict[str, Any]]:
	"""Return the config schema for a given voice engine key."""
	engine_class = get_engine(engine)
	return engine_class.get_config_schema()


@frappe.whitelist()
def list_voices(agent: str) -> list[dict[str, Any]]:
	"""Return the voices available for an Agent's configured voice engine."""
	agent_doc = frappe.get_doc("Agent", agent)
	_check_agent_access(agent_doc)

	engine_key, config = _get_agent_voice_config(agent_doc)
	engine = get_engine(engine_key)
	return engine.list_voices(agent_doc, config)


@frappe.whitelist()
def start_session(agent: str) -> dict[str, Any]:
	"""Start a voice session for an Agent on behalf of the current user."""
	agent_doc = frappe.get_doc("Agent", agent)
	_check_agent_access(agent_doc)

	engine_key, config = _get_agent_voice_config(agent_doc)
	return _mint_session(agent_doc, config, frappe.session.user)


@frappe.whitelist()
def end_session(agent: str, session_id: str) -> None:
	"""End an active voice session belonging to ``agent``.

	The caller must have read access to ``agent`` - the same check
	``start_session`` performs - since ``session_id`` alone is not proof of
	ownership. The engine to delegate to is resolved from the Agent's own
	configured ``voice_engine`` rather than guessed from the registry, so this
	works correctly regardless of how many voice engines are configured.
	"""
	agent_doc = frappe.get_doc("Agent", agent)
	_check_agent_access(agent_doc)

	engine_key, _config = _get_agent_voice_config(agent_doc)
	engine = get_engine(engine_key)
	engine.end_session(session_id)


@frappe.whitelist()
def send_to_session(agent: str, session_id: str, kind: str, text: str) -> None:
	"""Push out-of-band content into an active voice session belonging to ``agent``.

	The caller must have read access to ``agent`` - the same check
	``start_session`` performs - since ``session_id`` alone is not proof of
	ownership, and this endpoint can make an agent speak arbitrary text.
	The engine to delegate to is resolved from the Agent's own configured
	``voice_engine`` rather than guessed from the registry.

	``kind`` distinguishes how the content should be delivered:
	- "context": background information injected without interrupting the
	  agent mid-sentence.
	- "user_message": deliberately takes a conversational turn, as if the
	  user said it.
	- "activity": a side-channel event, delivered like "context".
	The distinction matters because "context" must never interrupt the agent
	mid-sentence, whereas "user_message" deliberately takes a conversational
	turn.
	"""
	valid_kinds = ("context", "user_message", "activity")
	if kind not in valid_kinds:
		frappe.throw(_("Invalid kind '{0}'. Must be one of: {1}").format(kind, ", ".join(valid_kinds)))

	agent_doc = frappe.get_doc("Agent", agent)
	_check_agent_access(agent_doc)

	engine_key, _config = _get_agent_voice_config(agent_doc)
	engine = get_engine(engine_key)
	engine.send_to_session(session_id, kind=kind, text=text)
