"""Unit tests for huf.ai.subscription.session_binding (pure logic, no Frappe)."""

from __future__ import annotations

from huf.ai.subscription.session_binding import (
	ACTION_CREATE_NEW,
	ACTION_REFUSE_MISMATCH,
	ACTION_RESUME_EXISTING,
	BindingDecision,
	binding_for_fork,
	binding_for_missing_session,
	binding_for_new_session,
	pending_binding_for_uncertain_creation,
	resolve_binding_for_turn,
)


# --------------------------------------------------------------------------
# resolve_binding_for_turn
# --------------------------------------------------------------------------


def test_uninitialized_status_creates_new():
	state = {"subscription_provider_session_status": "Uninitialized"}
	decision = resolve_binding_for_turn(state, "claude-code", "sonnet")
	assert decision == BindingDecision(action=ACTION_CREATE_NEW)


def test_missing_status_key_creates_new():
	state = {}
	decision = resolve_binding_for_turn(state, "claude-code", "sonnet")
	assert decision.action == ACTION_CREATE_NEW


def test_none_status_creates_new():
	state = {"subscription_provider_session_status": None}
	decision = resolve_binding_for_turn(state, "claude-code", "sonnet")
	assert decision.action == ACTION_CREATE_NEW


def test_active_matching_runtime_and_model_resumes():
	state = {
		"subscription_provider_session_status": "Active",
		"subscription_runtime": "claude-code",
		"model_name": "sonnet",
		"subscription_provider_session_id": "sess-123",
	}
	decision = resolve_binding_for_turn(state, "claude-code", "sonnet")
	assert decision.action == ACTION_RESUME_EXISTING
	assert decision.provider_session_id == "sess-123"
	assert decision.reason is None


def test_active_matching_runtime_no_stored_model_resumes():
	# Backwards-compat: a conversation bound before model tracking existed
	# should not be forced to refuse just because model_name is absent.
	state = {
		"subscription_provider_session_status": "Active",
		"subscription_runtime": "claude-code",
		"subscription_provider_session_id": "sess-123",
	}
	decision = resolve_binding_for_turn(state, "claude-code", "sonnet")
	assert decision.action == ACTION_RESUME_EXISTING


def test_active_runtime_mismatch_refuses():
	state = {
		"subscription_provider_session_status": "Active",
		"subscription_runtime": "codex-cli",
		"model_name": "sonnet",
		"subscription_provider_session_id": "sess-123",
	}
	decision = resolve_binding_for_turn(state, "claude-code", "sonnet")
	assert decision.action == ACTION_REFUSE_MISMATCH
	assert decision.reason == (
		"This conversation was created with a different subscription "
		"runtime/model. Start a new conversation."
	)
	assert decision.provider_session_id is None


def test_active_model_mismatch_refuses():
	state = {
		"subscription_provider_session_status": "Active",
		"subscription_runtime": "claude-code",
		"model_name": "opus",
		"subscription_provider_session_id": "sess-123",
	}
	decision = resolve_binding_for_turn(state, "claude-code", "sonnet")
	assert decision.action == ACTION_REFUSE_MISMATCH
	assert "different subscription runtime/model" in decision.reason


def test_unavailable_status_refuses():
	state = {"subscription_provider_session_status": "Unavailable"}
	decision = resolve_binding_for_turn(state, "claude-code", "sonnet")
	assert decision.action == ACTION_REFUSE_MISMATCH
	assert "Unavailable" in decision.reason
	assert "Start a new conversation" in decision.reason


def test_expired_status_refuses():
	state = {"subscription_provider_session_status": "Expired"}
	decision = resolve_binding_for_turn(state, "claude-code", "sonnet")
	assert decision.action == ACTION_REFUSE_MISMATCH
	assert "Expired" in decision.reason


def test_error_status_refuses():
	state = {"subscription_provider_session_status": "Error"}
	decision = resolve_binding_for_turn(state, "claude-code", "sonnet")
	assert decision.action == ACTION_REFUSE_MISMATCH
	assert "Error" in decision.reason


def test_closed_status_refuses_documented_judgment_call():
	# Judgment call: Closed means a session existed and was deliberately ended,
	# so we refuse rather than silently treating it like Uninitialized -
	# consistent with the immutable-binding rule in plan §11.2.
	state = {"subscription_provider_session_status": "Closed"}
	decision = resolve_binding_for_turn(state, "claude-code", "sonnet")
	assert decision.action == ACTION_REFUSE_MISMATCH
	assert "closed" in decision.reason.lower()


def test_unknown_status_refuses_fail_safe():
	state = {"subscription_provider_session_status": "SomethingWeird"}
	decision = resolve_binding_for_turn(state, "claude-code", "sonnet")
	assert decision.action == ACTION_REFUSE_MISMATCH
	assert "SomethingWeird" in decision.reason


# --------------------------------------------------------------------------
# binding_for_new_session
# --------------------------------------------------------------------------


def test_binding_for_new_session_shape():
	result = binding_for_new_session("sess-abc", "claude-code")
	assert result["subscription_provider_session_id"] == "sess-abc"
	assert result["subscription_provider_session_status"] == "Active"
	assert result["subscription_runtime"] == "claude-code"
	assert isinstance(result["subscription_provider_session_created_at"], str)
	assert isinstance(result["subscription_provider_session_last_verified_at"], str)
	assert set(result.keys()) == {
		"subscription_provider_session_id",
		"subscription_provider_session_status",
		"subscription_runtime",
		"subscription_provider_session_created_at",
		"subscription_provider_session_last_verified_at",
	}


# --------------------------------------------------------------------------
# binding_for_fork
# --------------------------------------------------------------------------


def test_binding_for_fork_shape():
	result = binding_for_fork()
	assert result == {
		"subscription_provider_session_id": None,
		"subscription_provider_session_status": "Uninitialized",
		"subscription_provider_session_created_at": None,
		"subscription_provider_session_last_verified_at": None,
	}


# --------------------------------------------------------------------------
# binding_for_missing_session
# --------------------------------------------------------------------------


def test_binding_for_missing_session_shape():
	result = binding_for_missing_session()
	assert result == {"subscription_provider_session_status": "Unavailable"}


# --------------------------------------------------------------------------
# pending_binding_for_uncertain_creation
# --------------------------------------------------------------------------


def test_pending_binding_for_uncertain_creation_shape():
	result = pending_binding_for_uncertain_creation("candidate-uuid-1")
	assert result == {
		"subscription_provider_session_id": "candidate-uuid-1",
		"subscription_provider_session_status": "Error",
	}
