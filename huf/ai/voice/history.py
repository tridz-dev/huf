"""Voice session nonces: who owns a saved voice conversation.

``start_session`` / ``start_public_session`` are the only points where the real
caller is known. For engines that save through a provider webhook, they mint a
single-use nonce here. Only its sha256 hash is stored (``Huf Voice Session``);
the raw value goes to the browser once and comes back inside the signed
post-call payload. The webhook uses it purely as a lookup key: identity and
authorisation come from the server-side row, never from a client-echoed value.

See the ``Huf Voice Session`` doctype for the stored fields.
"""

from __future__ import annotations

import hashlib
import secrets
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import timedelta

import frappe
from frappe.utils import add_to_date, now_datetime

DOCTYPE = "Huf Voice Session"
NONCE_VARIABLE = "huf_voice_nonce"
SESSION_TTL = timedelta(hours=24)
CLAIM_RETENTION_DAYS = 7
ANONYMOUS_WRITER = "Administrator"
PURGE_FLAG = "huf:voice:session:purge"
PURGE_INTERVAL_SEC = 3600


class DuplicateCall(Exception):
	"""The provider conversation was already saved (redelivery or race)."""


@dataclass(frozen=True)
class VoiceAttribution:
	writer: str  # identity the writes run as (frappe.set_user)
	owner_user: str | None  # None means anonymous
	conversation: str | None  # server-recorded conversation to join, or None
	session_row: str  # Huf Voice Session name


def hash_nonce(nonce: str) -> str:
	return hashlib.sha256(nonce.encode()).hexdigest()


def mint_voice_session(agent: str, engine: str, *, user: str | None, conversation: str | None) -> str:
	"""Store a session row and return the raw nonce (never stored, never logged)."""
	nonce = secrets.token_urlsafe(32)
	frappe.get_doc(
		{
			"doctype": DOCTYPE,
			"agent": agent,
			"engine_key": engine,
			"user": user or "",
			"conversation": conversation or "",
			"nonce_hash": hash_nonce(nonce),
			"claim_kind": "Nonce",
			"expires_at": add_to_date(now_datetime(), hours=24),
		}
	).insert(ignore_permissions=True)
	_maybe_purge()
	return nonce


def find_nonce_agent(nonce) -> str | None:
	"""Agent of a live, unconsumed row. Only used to pick among candidate agents."""
	if not nonce or not isinstance(nonce, str):
		return None
	row = frappe.db.get_value(
		DOCTYPE,
		{"nonce_hash": hash_nonce(nonce), "claim_kind": "Nonce", "consumed_at": ["is", "not set"]},
		["agent", "expires_at"],
		as_dict=True,
	)
	if row and row.expires_at and row.expires_at > now_datetime():
		return row.agent
	return None


def is_duplicate(provider_conversation_id: str) -> bool:
	return bool(frappe.db.exists(DOCTYPE, {"provider_conversation_id": provider_conversation_id}))


def resolve_writer(agent_doc, user: str | None) -> str | None:
	"""Re-check access at save time. Returns the identity to write as, or None."""
	from huf.ai.agent.access import check_agent_access

	if user:
		if not frappe.db.get_value("User", user, "enabled"):
			return None
		if not check_agent_access(agent_doc, user):
			return None
		if not frappe.has_permission("Agent Conversation", "create", user=user):
			return None
		return user
	if check_agent_access(agent_doc, "Guest") and agent_doc.embed_enabled:
		return ANONYMOUS_WRITER
	return None


@contextmanager
def acting_as(user: str):
	"""Run writes as ``user``; always restore the previous identity."""
	previous = frappe.session.user
	frappe.set_user(user)
	try:
		yield
	finally:
		frappe.set_user(previous)


def _claim_row(agent: str, nonce_hash: str, pcid: str) -> bool:
	now = now_datetime()
	try:
		frappe.db.sql(
			"""UPDATE `tabHuf Voice Session`
			SET consumed_at = %(now)s, provider_conversation_id = %(pcid)s
			WHERE nonce_hash = %(h)s AND agent = %(agent)s AND claim_kind = 'Nonce'
			AND consumed_at IS NULL AND expires_at > %(now)s""",
			{"now": now, "pcid": pcid, "h": nonce_hash, "agent": agent},
		)
	except Exception as e:
		if frappe.db.is_duplicate_entry(e):
			raise DuplicateCall from e
		raise
	return bool(frappe.db._cursor.rowcount)


def claim_nonce(agent_doc, nonce, provider_conversation_id: str) -> VoiceAttribution | None:
	"""Atomically consume a matching nonce for this agent. None means no usable nonce."""
	if not nonce or not isinstance(nonce, str):
		return None
	nonce_hash = hash_nonce(nonce)
	if not _claim_row(agent_doc.name, nonce_hash, provider_conversation_id):
		return None
	row = frappe.db.get_value(
		DOCTYPE, {"nonce_hash": nonce_hash}, ["name", "user", "conversation"], as_dict=True
	)
	writer = resolve_writer(agent_doc, row.user or None)
	if writer is None:
		mark_outcome(row.name, outcome="Rejected")
		return None
	return VoiceAttribution(writer, row.user or None, row.conversation or None, row.name)


def claim_guest(agent_doc, provider_conversation_id: str) -> VoiceAttribution | None:
	"""Existing guest-access check; records a claim row so redeliveries dedupe."""
	from huf.ai.agent.access import check_agent_access

	if not check_agent_access(agent_doc, "Guest"):
		return None
	# A nonce claimed a moment ago but rejected at re-check already holds this call's key;
	# reuse its row instead of colliding on the unique provider_conversation_id.
	rejected = frappe.db.get_value(
		DOCTYPE, {"provider_conversation_id": provider_conversation_id, "outcome": "Rejected"}, "name"
	)
	if rejected:
		return VoiceAttribution(ANONYMOUS_WRITER, None, None, rejected)
	now = now_datetime()
	try:
		doc = frappe.get_doc(
			{
				"doctype": DOCTYPE,
				"agent": agent_doc.name,
				"engine_key": "elevenlabs_convai",
				"claim_kind": "Guest",
				"expires_at": add_to_date(now, hours=24),
				"consumed_at": now,
				"provider_conversation_id": provider_conversation_id,
			}
		).insert(ignore_permissions=True)
	except (frappe.UniqueValidationError, frappe.DuplicateEntryError) as e:
		raise DuplicateCall from e
	return VoiceAttribution(ANONYMOUS_WRITER, None, None, doc.name)


def mark_outcome(session_row: str, *, outcome: str, agent_run: str | None = None) -> None:
	values = {"outcome": outcome}
	if agent_run:
		values["agent_run"] = agent_run
	frappe.db.set_value(DOCTYPE, session_row, values, update_modified=False)


def _maybe_purge() -> None:
	cache = frappe.cache()
	if cache.get_value(PURGE_FLAG):
		return
	cache.set_value(PURGE_FLAG, 1, expires_in_sec=PURGE_INTERVAL_SEC)
	purge_expired()


def purge_expired(limit: int = 500) -> int:
	"""Delete unused expired nonces and old claims (no permission check)."""
	now = now_datetime()
	cutoff = add_to_date(now, days=-CLAIM_RETENTION_DAYS)
	names = frappe.get_all(
		DOCTYPE,
		filters={"consumed_at": ["is", "not set"], "expires_at": ["<", now]},
		pluck="name",
		limit=limit,
		ignore_permissions=True,
	)
	if len(names) < limit:
		names += frappe.get_all(
			DOCTYPE,
			filters={"consumed_at": ["<", cutoff]},
			pluck="name",
			limit=limit - len(names),
			ignore_permissions=True,
		)
	if names:
		frappe.db.delete(DOCTYPE, {"name": ["in", names]})
	return len(names)
