"""Unit tests for Remote Agent Policy resolution."""

from __future__ import annotations

from typing import Any

import frappe
import pytest

from huf.ai.remote_agents.exceptions import RemoteAgentPolicyError
from huf.ai.remote_agents.policy import (
	POLICY_AGENT_CHILD_DOCTYPE,
	POLICY_DOCTYPE,
	resolve_policy,
)


class FakeDoc:
	"""Minimal stand-in for a Frappe document returned by frappe.get_doc."""

	def __init__(self, **fields: Any):
		for key, value in fields.items():
			setattr(self, key, value)


@pytest.fixture(autouse=True)
def _reset_frappe_stubs():
	"""Ensure a clean stub state for every test."""
	frappe.get_all = lambda *args, **kwargs: []
	frappe.get_doc = lambda *args, **kwargs: None
	frappe.get_roles = lambda user=None: ["System Manager"]


class TestResolvePolicy:
	def test_exact_match_returns_default_agent(self, monkeypatch):
		policy_rows = [
			{
				"name": "api-key-exact",
				"default_agent": "agent-default",
				"scope_type": "single_agent",
				"capability_scope": '{"tool_allow_list": ["t1"]}',
				"max_run_duration_seconds": 120,
			}
		]

		def _fake_get_all(doctype, filters=None, fields=None, order_by=None):
			if doctype == POLICY_DOCTYPE:
				return list(policy_rows)
			return []

		monkeypatch.setattr(frappe, "get_all", _fake_get_all)

		result = resolve_policy("api_key", "key-1")
		assert result["default_agent"] == "agent-default"
		assert result["resolved_agent"] == "agent-default"
		assert result["policy"] == "api-key-exact"

	def test_requested_agent_must_be_allowed(self, monkeypatch):
		policy_rows = [
			{
				"name": "api-key-exact",
				"default_agent": "agent-default",
				"scope_type": "agent_list",
				"capability_scope": "{}",
				"max_run_duration_seconds": 300,
			}
		]
		child_rows = [{"agent": "agent-default"}, {"agent": "agent-beta"}]

		def _fake_get_all(doctype, filters=None, fields=None, order_by=None):
			if doctype == POLICY_DOCTYPE:
				return list(policy_rows)
			if doctype == POLICY_AGENT_CHILD_DOCTYPE:
				return list(child_rows)
			return []

		monkeypatch.setattr(frappe, "get_all", _fake_get_all)

		with pytest.raises(RemoteAgentPolicyError, match="not allowed by policy"):
			resolve_policy("api_key", "key-1", requested_agent="agent-unknown")

	def test_catch_all_policy_used_when_no_reference(self, monkeypatch):
		def _fake_get_all(doctype, filters=None, fields=None, order_by=None):
			if doctype != POLICY_DOCTYPE:
				return []
			if filters and filters.get("caller_reference") == "":
				return [
					{
						"name": "catch-all",
						"default_agent": "agent-catch",
						"scope_type": "single_agent",
						"capability_scope": "{}",
						"max_run_duration_seconds": 300,
					}
				]
			return []

		monkeypatch.setattr(frappe, "get_all", _fake_get_all)

		result = resolve_policy("api_key", None)
		assert result["default_agent"] == "agent-catch"

	def test_no_policy_raises(self, monkeypatch):
		monkeypatch.setattr(frappe, "get_all", lambda *args, **kwargs: [])

		with pytest.raises(RemoteAgentPolicyError, match="No Remote Agent Policy admits"):
			resolve_policy("api_key", "key-1")

	def test_missing_caller_type_raises(self):
		with pytest.raises(RemoteAgentPolicyError, match="caller_type is required"):
			resolve_policy("", "key-1")


	def test_user_caller_defaults_to_session_user(self, monkeypatch):
		frappe.session.user = "tester@example.com"
		policy_rows = [
			{
				"name": "user-policy",
				"default_agent": "agent-user",
				"scope_type": "single_agent",
				"capability_scope": "{}",
				"max_run_duration_seconds": 300,
			}
		]

		def _fake_get_all(doctype, filters=None, fields=None, order_by=None):
			if doctype == POLICY_DOCTYPE:
				# Confirm the resolved caller_reference is the session user.
				if filters and filters.get("caller_reference") == "tester@example.com":
					return list(policy_rows)
			return []

		monkeypatch.setattr(frappe, "get_all", _fake_get_all)

		result = resolve_policy("user", None)
		assert result["default_agent"] == "agent-user"
		assert result["resolved_agent"] == "agent-user"
	def test_capability_scope_is_normalized(self, monkeypatch):
		policy_rows = [
			{
				"name": "api-key-exact",
				"default_agent": "agent-default",
				"scope_type": "single_agent",
				"capability_scope": '{"tool_allow_list": ["t1"]}',
				"max_run_duration_seconds": 120,
			}
		]

		def _fake_get_all(doctype, filters=None, fields=None, order_by=None):
			if doctype == POLICY_DOCTYPE:
				return list(policy_rows)
			return []

		monkeypatch.setattr(frappe, "get_all", _fake_get_all)

		result = resolve_policy("api_key", "key-1")
		scope = result["capability_scope"]
		assert scope["tool_allow_list"] == ["t1"]
		assert scope["max_run_duration_seconds"] == 120
		assert "max_concurrent_runs" in scope
