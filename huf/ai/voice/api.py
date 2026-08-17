"""Whitelisted API endpoints for voice sessions.

These endpoints are the session-authenticated entry points into the voice
engine registry (``huf.ai.voice``). Publishable-key and server-secret callers
will be added later as additional thin wrappers over ``_mint_session`` -
see the comment on that function.
"""

from __future__ import annotations

import hmac
import json
from typing import Any
from urllib.parse import urlsplit

import frappe
from frappe import _

from huf.ai.voice import get_engine, get_engine_class, supported_engines
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
		# Class-level metadata only — never instantiate just to read it, since an
		# engine is free to require constructor arguments.
		engine_class = get_engine_class(engine_key)
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
	# get_config_schema is a classmethod — resolve the class rather than
	# constructing an engine we would immediately discard.
	return get_engine_class(engine).get_config_schema()


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


def _origin_allowed(origin: str, allowed_origins: str | None) -> bool:
	"""Check ``origin`` against newline-separated ``allowed_origins``.

	Compares parsed ``(scheme, netloc)`` tuples exactly - never a substring
	check, which would let e.g. "evil-example.com" pass an allowlist entry of
	"example.com".
	"""
	if not origin or not allowed_origins:
		return False

	origin_parts = urlsplit(origin)
	origin_key = (origin_parts.scheme.lower(), origin_parts.netloc.lower())

	for line in allowed_origins.splitlines():
		candidate = line.strip()
		if not candidate:
			continue
		candidate_parts = urlsplit(candidate)
		candidate_key = (candidate_parts.scheme.lower(), candidate_parts.netloc.lower())
		if candidate_key == origin_key:
			return True

	return False


def ensure_publishable_key(doc, method=None) -> None:
	"""``doc_events`` fallback for auto-generating ``publishable_key``.

	Not currently wired into ``hooks.py`` - the Agent controller's own
	``validate()`` handles this directly (see ``Agent._ensure_publishable_key``
	in ``huf/huf/doctype/agent/agent.py``). Kept here, unused, only in case a
	future controller-less doctype needs the same behavior via ``doc_events``.
	"""
	if getattr(doc, "embed_enabled", None) and not getattr(doc, "publishable_key", None):
		doc.publishable_key = f"pk_{frappe.generate_hash(length=32)}"


@frappe.whitelist(allow_guest=True, methods=["POST"])
def start_public_session(publishable_key, agent) -> dict[str, Any]:
	"""Mint a voice session for an unauthenticated embedded caller.

	Scoped by publishable_key (per-Agent, never site-wide) + Origin header
	allowlist, NOT by frappe.session.user (which is Guest here). This is
	the Mode A (publishable-key) counterpart to start_session()'s
	session-user-authenticated Mode.

	Deliberately takes NO ``config`` parameter: a publishable key is public
	by design (it ships in third-party page source), so accepting a
	caller-supplied engine config here would let anyone holding it point a
	session at an arbitrary AI Model/ElevenLabs agent_id of their choosing,
	riding on this Agent's own provider credentials. The engine config is
	always the Agent's own ``voice_config``, exactly as ``start_session``
	uses it - never something the browser supplies.

	NOTE - cross-origin preflight: Frappe answers a bare OPTIONS request at
	the WSGI dispatch layer, before whitelisted-method routing, using the
	site-wide ``allow_cors`` config rather than this function's own Origin
	allowlist. A site that wants to actually serve embedded callers from
	browsers must additionally configure ``allow_cors`` (see site_config.json)
	to include the same origins configured in this Agent's
	``allowed_origins`` - the check in this function is a second, per-Agent
	gate on top of that, not a replacement for it. Documented in TESTING.md.
	"""
	try:
		agent_doc = frappe.get_doc("Agent", agent)
	except frappe.DoesNotExistError:
		# Same PermissionError as every other rejection in this function, so an
		# unauthenticated caller can't use the response to enumerate valid
		# Agent docnames.
		frappe.throw(_("Not permitted to start a session for Agent '{0}'").format(agent), frappe.PermissionError)

	stored_key = getattr(agent_doc, "publishable_key", None) or ""
	key_matches = bool(stored_key) and hmac.compare_digest(stored_key, publishable_key or "")

	if not agent_doc.embed_enabled or not key_matches:
		frappe.throw(_("Not permitted to start a session for Agent '{0}'").format(agent), frappe.PermissionError)

	origin = frappe.get_request_header("Origin")
	if not _origin_allowed(origin, getattr(agent_doc, "allowed_origins", None)):
		frappe.throw(_("Origin not permitted for Agent '{0}'").format(agent), frappe.PermissionError)

	# No per-request header injection here: this Frappe version builds a
	# fresh werkzeug Response from frappe.local.response (the JSON payload
	# dict) in build_response(), well after this function returns, and
	# there is no frappe.local.response_headers object to write into (an
	# earlier version of this function tried that and crashed every call
	# with AttributeError - do not reintroduce it). The actual
	# Access-Control-Allow-Origin reflection happens centrally in
	# frappe/app.py's set_cors_headers(), driven by the site's own
	# `allow_cors` config - see the NOTE above and TESTING.md for why that
	# site-wide config is required for this endpoint to be browser-callable
	# at all, independent of the allowed_origins check above.
	_, config = _get_agent_voice_config(agent_doc)

	# Identifies the source as an embed session without propagating the
	# publishable key itself into engine-layer session records or logs.
	return _mint_session(agent_doc, config, user_ref=f"embed:{agent_doc.name}")
