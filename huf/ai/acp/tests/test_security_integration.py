"""Integration-style tests for the full ACP security layer.

These tests exercise the DocType/security layers end-to-end without spawning
real subprocesses. They rely on the same frappe stub used by the rest of the
ACP test suite.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import patch

import frappe
import pytest

from huf.ai.acp.exceptions import AcpCapacityError, AcpLaunchError, AcpSecurityError
from huf.ai.acp.registry import build_launch_context
from huf.ai.acp.subprocess_guard import (
	_MEMORY_COUNTER_BACKEND,
	AcpSubprocessCounter,
	scrub_environment,
)
from huf.ai.acp.subprocess_launcher import AcpSubprocessLauncher
from huf.ai.remote_agents.exceptions import RemoteAgentPolicyError
from huf.ai.remote_agents.policy import POLICY_DOCTYPE, resolve_policy


@dataclass
class _FakeRegistryEnvVar:
	variable_name: str
	fixed_value: str | None = None


@dataclass
class _FakeRegistry:
	name: str
	registry_name: str
	enabled: int = 1
	binary_path: str = "/bin/echo"
	argv_shape: list[str] | None = field(default_factory=list)
	working_directory: str | None = None
	auth_required: int = 0
	auth_env_key: str = ""
	max_wall_time_seconds: int = 120
	env_allow_list: list[_FakeRegistryEnvVar] = field(default_factory=list)


@pytest.fixture(autouse=True)
def _reset_frappe_stubs():
	frappe.get_all = lambda *args, **kwargs: []
	frappe.get_doc = lambda *args, **kwargs: None
	frappe.get_roles = lambda user=None: ["System Manager"]


class TestPolicyEnforcement:
	def test_resolve_policy_rejects_unauthorized_agent(self, monkeypatch):
		policy_rows = [
			{
				"name": "policy-1",
				"default_agent": "agent-alpha",
				"scope_type": "single_agent",
				"capability_scope": "{}",
				"max_run_duration_seconds": 300,
			}
		]

		monkeypatch.setattr(
			frappe,
			"get_all",
			lambda doctype, filters=None, fields=None, order_by=None: list(policy_rows)
			if doctype == POLICY_DOCTYPE
			else [],
		)

		with pytest.raises(RemoteAgentPolicyError, match="not allowed"):
			resolve_policy("api_key", "key-1", requested_agent="agent-beta")

	def test_resolve_policy_rejects_unknown_caller(self, monkeypatch):
		monkeypatch.setattr(frappe, "get_all", lambda *args, **kwargs: [])

		with pytest.raises(RemoteAgentPolicyError, match="No Remote Agent Policy"):
			resolve_policy("api_key", "unknown-key")


class TestRegistryValidation:
	@pytest.fixture
	def registry(self):
		with tempfile.TemporaryDirectory() as tmp:
			yield _FakeRegistry(
				name="echo-local",
				registry_name="echo-local",
				binary_path="/bin/echo",
				argv_shape=["hello"],
				working_directory=tmp,
				auth_required=1,
				auth_env_key="HUF_ACP_TARGET_TOKEN",
				env_allow_list=[_FakeRegistryEnvVar("PATH", "/usr/bin:/bin")],
			)

	def test_rejects_relative_binary_path(self, registry):
		registry.binary_path = "echo"
		with patch("frappe.get_doc", return_value=registry), pytest.raises(
			AcpSecurityError, match="absolute"
		):
			build_launch_context("echo-local")

	def test_rejects_bad_argv_shape(self, registry):
		registry.argv_shape = ["ok", 123]
		with patch("frappe.get_doc", return_value=registry), pytest.raises(
			AcpSecurityError, match="string"
		):
			build_launch_context("echo-local", auth_secret="x")

	def test_rejects_missing_auth_secret(self, registry):
		with patch("frappe.get_doc", return_value=registry), pytest.raises(
			AcpSecurityError, match="requires auth_secret"
		):
			build_launch_context("echo-local")

	def test_rejects_deny_listed_auth_env_key(self, registry):
		registry.auth_env_key = "LD_PRELOAD"
		with patch("frappe.get_doc", return_value=registry), pytest.raises(
			AcpSecurityError, match="deny-list"
		):
			build_launch_context("echo-local", auth_secret="x")


class TestSubprocessSecurity:
	def test_scrubbing_removes_dangerous_env_vars(self):
		env = {
			"PATH": "/usr/bin",
			"LD_PRELOAD": "evil.so",
			"NODE_OPTIONS": "--require evil",
			"PYTHONPATH": "/tmp",
			"FRAPPE_SITE": "test",
			"DB_PASSWORD": "hunter2",
			"REDIS_QUEUE": "redis://localhost",
			"MY_SECRET_KEY": "hidden",
			"HUF_ACP_TARGET_TOKEN": "allowed-secret",
		}
		scrubbed = scrub_environment(env)
		assert scrubbed["PATH"] == "/usr/bin"
		assert scrubbed["HUF_ACP_TARGET_TOKEN"] == "allowed-secret"
		for key in ("LD_PRELOAD", "NODE_OPTIONS", "PYTHONPATH", "FRAPPE_SITE", "DB_PASSWORD", "REDIS_QUEUE", "MY_SECRET_KEY"):
			assert key not in scrubbed
		assert scrubbed["OMP_NUM_THREADS"] == "1"

	def test_site_wide_ceiling_blocks_spawns(self):
		counter = AcpSubprocessCounter(
			max_subprocesses=1,
			backend=_MEMORY_COUNTER_BACKEND(),
		)
		launcher = AcpSubprocessLauncher(counter=counter, timeout=10.0)

		async def _run() -> None:
			proc = await launcher.launch(["/bin/echo", "ok"])
			assert counter.current() == 1
			with pytest.raises((AcpLaunchError, AcpCapacityError), match="ceiling"):
				await launcher.launch(["/bin/echo", "blocked"])
			await launcher.reap(proc)

		import asyncio

		asyncio.run(_run())

	def test_failed_launch_releases_ceiling_slot(self):
		counter = AcpSubprocessCounter(
			max_subprocesses=1,
			backend=_MEMORY_COUNTER_BACKEND(),
		)
		launcher = AcpSubprocessLauncher(counter=counter, timeout=10.0)

		with pytest.raises(AcpSecurityError):
			import asyncio

			asyncio.run(launcher.launch(["/nonexistent"]))

		assert counter.current() == 0
