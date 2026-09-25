"""Pure logic for binding an Agent Conversation to a subscription CLI provider session.

This module contains NO Frappe doc access. Every function accepts plain data in
and returns plain data out (a dataclass or a dict of field updates). The caller
(a later dispatch task) is responsible for reading the actual Agent Conversation
doc, calling these functions, and applying the returned updates via `frappe.db`/
`doc.save()`.

Field names referenced here match `agent_conversation.json`:
    subscription_runtime
    subscription_provider_session_id
    subscription_provider_session_status  (Uninitialized/Active/Unavailable/Expired/Closed/Error)
    subscription_provider_session_created_at
    subscription_provider_session_last_verified_at
    runtime_mode
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


ACTION_CREATE_NEW = "create_new"
ACTION_RESUME_EXISTING = "resume_existing"
ACTION_REFUSE_MISMATCH = "refuse_mismatch"


@dataclass(frozen=True, slots=True)
class BindingDecision:
	"""Outcome of evaluating an existing conversation's provider session binding."""

	action: str
	reason: str | None = None
	provider_session_id: str | None = None


def _iso_now() -> str:
	# LIVE-VERIFIED bug fix: `datetime.isoformat()` with a tz-aware datetime
	# produces "...+00:00", which MariaDB (in Frappe's default strict SQL
	# mode) rejects for a Datetime column with
	# `OperationalError: (1292, "Incorrect datetime value ...")` -- confirmed
	# by an actual live run against a real Frappe site. Frappe's own
	# `frappe.utils.now_datetime()`/DB layer expects a naive
	# "YYYY-MM-DD HH:MM:SS.ffffff" string (no "T", no offset). This module
	# deliberately has no Frappe import (see module docstring), so format it
	# by hand rather than depending on `frappe.utils.get_datetime_str`.
	return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")


def resolve_binding_for_turn(
	conversation_state: dict,
	runtime_name: str,
	model_name: str,
) -> BindingDecision:
	"""Decide what to do about the provider session binding for the current turn.

	`conversation_state` is a plain dict snapshot of the relevant Agent Conversation
	fields (not the doc itself):
		subscription_provider_session_id
		subscription_provider_session_status
		subscription_runtime
		runtime_mode (or an equivalent "expected mode" key, treated leniently)
		model / effective_model (whatever key the caller uses; we look at
			"model_name" if present, falling back to no model check)
	"""
	status = conversation_state.get("subscription_provider_session_status")

	# Uninitialized (or missing/None, e.g. a brand-new conversation dict that never
	# set the field) means no provider session exists yet.
	if status is None or status == "Uninitialized":
		return BindingDecision(action=ACTION_CREATE_NEW)

	if status == "Active":
		bound_runtime = conversation_state.get("subscription_runtime")
		bound_model = conversation_state.get("model_name")
		runtime_matches = bound_runtime == runtime_name
		# Only enforce the model check if the stored state actually recorded one;
		# a conversation bound before model tracking existed should not be forced
		# to refuse solely because of a missing historical value.
		model_matches = bound_model is None or bound_model == model_name

		if runtime_matches and model_matches:
			return BindingDecision(
				action=ACTION_RESUME_EXISTING,
				provider_session_id=conversation_state.get("subscription_provider_session_id"),
			)

		return BindingDecision(
			action=ACTION_REFUSE_MISMATCH,
			reason=(
				"This conversation was created with a different subscription "
				"runtime/model. Start a new conversation."
			),
		)

	if status in ("Unavailable", "Expired", "Error"):
		return BindingDecision(
			action=ACTION_REFUSE_MISMATCH,
			reason=(
				"The subscription provider session for this conversation is no "
				"longer usable (status: "
				f"{status}). Start a new conversation rather than replaying HUF "
				"history into a fresh provider session."
			),
		)

	if status == "Closed":
		# Judgment call: "Closed" is only ever set by an explicit close action on an
		# EXISTING provider session (see plan §11.2/§26). It is not the initial state
		# of a new conversation object, so a Closed status on a conversation we're
		# asked to bind for a turn always means "this specific conversation already
		# had a session that was deliberately ended" — never "conversation is new".
		# Treating Closed like Uninitialized here would let a turn silently reopen
		# a logically-finished conversation under a brand-new provider session,
		# which conflicts with the immutability rule in §11.2 (the binding for a
		# given HUF conversation is fixed once created). If a genuinely new
		# conversation is desired, the caller creates a new Agent Conversation
		# (which starts Uninitialized) rather than reusing a Closed one — so this
		# function refuses instead of silently creating a new session in place.
		return BindingDecision(
			action=ACTION_REFUSE_MISMATCH,
			reason=(
				"This conversation's subscription provider session has been "
				"closed. Start a new conversation."
			),
		)

	# Unknown/unexpected status value: fail safe by refusing rather than guessing.
	return BindingDecision(
		action=ACTION_REFUSE_MISMATCH,
		reason=(
			f"Unrecognized subscription provider session status: {status!r}. "
			"Start a new conversation."
		),
	)


def binding_for_new_session(provider_session_id: str, runtime_name: str) -> dict:
	"""Field updates to apply once a new provider session is successfully created."""
	now = _iso_now()
	return {
		"subscription_provider_session_id": provider_session_id,
		"subscription_provider_session_status": "Active",
		"subscription_runtime": runtime_name,
		"subscription_provider_session_created_at": now,
		"subscription_provider_session_last_verified_at": now,
		"runtime_mode": "subscription_passthrough",
	}


def binding_for_fork() -> dict:
	"""Field updates to apply to a forked conversation (plan §11.3).

	A fork must NEVER inherit the source conversation's provider_session_id -
	regardless of what state the source was in, the fork always starts clean.
	"""
	return {
		"subscription_provider_session_id": None,
		"subscription_provider_session_status": "Uninitialized",
		"subscription_provider_session_created_at": None,
		"subscription_provider_session_last_verified_at": None,
	}


def binding_for_missing_session() -> dict:
	"""Field updates when a resume attempt discovers the native session is gone (plan §26.4).

	The session_id itself is intentionally left untouched (for future diagnostics);
	only the status is marked. The caller must then fail the current Agent Run with
	an actionable error rather than silently replaying HUF history - that dispatch
	logic lives outside this pure module.
	"""
	return {
		"subscription_provider_session_status": "Unavailable",
	}


def pending_binding_for_uncertain_creation(candidate_session_id: str) -> dict:
	"""Field updates for a session creation whose outcome is uncertain (plan §16.2/§26.3).

	HUF may generate the provider session UUID upfront (e.g. Claude's `--session-id`)
	before knowing whether the CLI actually accepted/created it. If the transport
	fails mid-request, we don't know if the provider-side session exists.

	We deliberately do NOT mark this "Active" (it might not exist) and do NOT mark
	it "Uninitialized" (that would lose the candidate ID and, on a naive retry,
	risk generating a second candidate ID and creating a duplicate provider-side
	session). Instead we retain the candidate ID with status "Error" so a later
	reconciliation step can check whether that session actually exists before
	deciding whether to reuse it or start over.
	"""
	return {
		"subscription_provider_session_id": candidate_session_id,
		"subscription_provider_session_status": "Error",
	}
