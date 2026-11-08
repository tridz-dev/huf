# ruff: noqa: S101
from __future__ import annotations

import pytest

from huf.ai.external.identity import IDENTITY_KEYS, pin_external_identity


def _pin(args, **overrides):
	kwargs = {
		"conversation_id": "CONV-1",
		"agent_run_id": "RUN-1",
		"agent_name": "agent-a",
	}
	kwargs.update(overrides)
	return pin_external_identity(args, **kwargs)


def test_model_supplied_identity_is_replaced():
	args = {
		"agent_run_id": "RUN-EVIL",
		"conversation_id": "CONV-EVIL",
		"call_id": "CALL-EVIL",
		"user": "attacker@example.com",
		"ignore_permissions": True,
	}

	pinned = _pin(args, call_id="CALL-1")

	assert pinned["agent_run_id"] == "RUN-1"
	assert pinned["conversation_id"] == "CONV-1"
	assert pinned["agent_name"] == "agent-a"
	assert pinned["call_id"] == "CALL-1"
	assert "user" not in pinned
	assert "ignore_permissions" not in pinned


def test_blank_model_identity_values_are_removed():
	args = {
		"user": "",
		"session_id": "",
		"ignore_permissions": "",
		"_dx_pin": "",
		"agent_name": "",
	}

	pinned = _pin(args)

	for key in ("user", "session_id", "ignore_permissions", "_dx_pin"):
		assert key not in pinned
	assert pinned["agent_name"] == "agent-a"


def test_every_identity_key_is_removed_when_no_trusted_value_is_given():
	args = {key: "model-value" for key in IDENTITY_KEYS}
	args["query"] = "keep me"

	pinned = pin_external_identity(args, conversation_id=None, agent_run_id=None, agent_name=None)

	assert pinned == {"query": "keep me"}


@pytest.mark.parametrize(
	"key",
	["User", "Agent_Run_Id", "agent-name", "SESSION-ID", "Conversation_Id", "Ignore-Permissions", "_DX_PIN", "dxpin"],
)
def test_identity_keys_match_case_and_separator_variants(key):
	pinned = _pin({key: "model-value", "query": "keep me"})

	assert key not in pinned
	assert pinned["query"] == "keep me"
	assert "model-value" not in pinned.values()


def test_variant_keys_are_stripped_even_when_no_trusted_value_is_given():
	args = {"User": "attacker", "Agent_Run_Id": "RUN-EVIL", "agent-name": "evil", "query": "x"}

	pinned = pin_external_identity(args, conversation_id=None, agent_run_id=None, agent_name=None)

	assert pinned == {"query": "x"}


def test_variant_identity_key_is_replaced_by_canonical_trusted_value():
	pinned = _pin({"Agent_Run_Id": "RUN-EVIL", "Agent-Name": "evil"})

	assert pinned["agent_run_id"] == "RUN-1"
	assert pinned["agent_name"] == "agent-a"
	assert "Agent_Run_Id" not in pinned
	assert "Agent-Name" not in pinned


def test_non_identity_keys_with_similar_text_are_kept():
	pinned = _pin({"users": ["a"], "run_id": "R-2", "name": "widget"})

	assert pinned["users"] == ["a"]
	assert pinned["run_id"] == "R-2"
	assert pinned["name"] == "widget"


def test_unrelated_keys_are_kept():
	args = {"query": "hello", "limit": 5, "filters": {"status": "Open"}}

	pinned = _pin(args)

	assert pinned["query"] == "hello"
	assert pinned["limit"] == 5
	assert pinned["filters"] == {"status": "Open"}


def test_input_is_not_mutated():
	args = {"agent_run_id": "RUN-EVIL", "user": "attacker", "query": "x"}
	snapshot = dict(args)

	pinned = _pin(args, call_id="CALL-1")

	assert args == snapshot
	assert pinned is not args


def test_call_id_omitted_when_none():
	pinned = _pin({"call_id": "CALL-EVIL"}, call_id=None)

	assert "call_id" not in pinned


def test_none_args_yield_only_trusted_fields():
	pinned = _pin(None)

	assert pinned == {
		"conversation_id": "CONV-1",
		"agent_run_id": "RUN-1",
		"agent_name": "agent-a",
	}
