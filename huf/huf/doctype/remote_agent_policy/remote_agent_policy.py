# Copyright (c) 2025, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

from __future__ import annotations

import json
from typing import Any

import frappe
from frappe import _
from frappe.model.document import Document


class RemoteAgentPolicy(Document):
	def validate(self):
		self._validate_caller_reference()
		self._validate_scope()
		self._validate_capability_scope()

	def _validate_caller_reference(self) -> None:
		if not self.caller_reference:
			# Blank caller_reference means a catch-all/default policy.
			return
		if self.caller_type == "api_key":
			# Caller reference should point to an API Key record.
			if not frappe.db.exists("API Key", self.caller_reference):
				frappe.throw(_("Caller Reference must be a valid API Key"))
		elif self.caller_type == "remote_connection":
			if not frappe.db.exists("Remote Agent Connection", self.caller_reference):
				frappe.throw(_("Caller Reference must be a valid Remote Agent Connection"))

	def _validate_scope(self) -> None:
		if self.scope_type == "single_agent":
			if not self.default_agent:
				frappe.throw(_("Default Agent is required for single-agent scope"))
			self.set("allowed_agents", [])
		elif self.scope_type == "agent_list":
			if not self.allowed_agents:
				frappe.throw(_("At least one allowed agent is required for agent-list scope"))
			self.default_agent = None

	def _validate_capability_scope(self) -> None:
		raw = self.capability_scope
		if not raw:
			self.capability_scope = json.dumps(self._default_capability_scope())
			return
		if isinstance(raw, str):
			try:
				parsed = json.loads(raw)
			except json.JSONDecodeError as exc:
				frappe.throw(_("Capability Scope must be valid JSON: {0}").format(str(exc)))
			if not isinstance(parsed, dict):
				frappe.throw(_("Capability Scope must be a JSON object"))
			self.capability_scope = json.dumps(parsed)
		elif isinstance(raw, dict):
			self.capability_scope = json.dumps(raw)
		else:
			frappe.throw(_("Capability Scope must be a JSON object"))

	def get_capability_scope(self) -> dict[str, Any]:
		return json.loads(self.capability_scope or "{}") or self._default_capability_scope()

	@staticmethod
	def _default_capability_scope() -> dict[str, Any]:
		return {
			"tool_allow_list": [],
			"tool_deny_list": [],
			"allow_file_tools": False,
			"allow_shell_tools": False,
			"max_run_duration_seconds": 300,
			"max_concurrent_runs": 1,
		}

	def get_allowed_agent_names(self) -> list[str]:
		if self.scope_type == "single_agent":
			return [self.default_agent] if self.default_agent else []
		return [row.agent for row in (self.allowed_agents or []) if row.agent]

	def resolves_to(self, requested_agent: str | None) -> tuple[str | None, dict[str, Any]]:
		allowed = self.get_allowed_agent_names()
		if requested_agent and requested_agent not in allowed:
			return None, {}
		resolved = requested_agent or (self.default_agent if self.scope_type == "single_agent" else None)
		return resolved, self.get_capability_scope()
