"""Tests for the ACP command registry runtime loader.

These tests do not require the ``ACP Command Registry`` DocType to exist in the
 database; they mock ``frappe.get_doc`` with a stand-in object.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import patch

import pytest

from huf.ai.acp.exceptions import AcpLaunchError, AcpSecurityError
from huf.ai.acp.registry import build_launch_context


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


class TestBuildLaunchContext:
	@pytest.fixture
	def registry(self):
		with tempfile.TemporaryDirectory() as tmp:
			registry = _FakeRegistry(
				name="echo-local",
				registry_name="echo-local",
				binary_path="/bin/echo",
				argv_shape=["hello"],
				working_directory=tmp,
				auth_required=1,
				auth_env_key="HUF_ACP_TARGET_TOKEN",
				env_allow_list=[
					_FakeRegistryEnvVar("PATH", "/usr/bin:/bin"),
				],
			)
			yield registry

	def test_builds_scrubbed_context(self, registry: _FakeRegistry) -> None:
		with patch("frappe.get_doc", return_value=registry):
			ctx = build_launch_context("echo-local", auth_secret="secret123")

		assert ctx["cmd"] == ["/bin/echo", "hello"]
		assert ctx["cwd"] == registry.working_directory
		assert ctx["env"]["HUF_ACP_TARGET_TOKEN"] == "secret123"
		assert ctx["env"]["PATH"] == "/usr/bin:/bin"
		assert ctx["auth_env_key"] == "HUF_ACP_TARGET_TOKEN"
		assert ctx["max_wall_time_seconds"] == 120
		# Thread limits pinned.
		assert ctx["env"]["OMP_NUM_THREADS"] == "1"

	def test_rejects_disabled_registry(self, registry: _FakeRegistry) -> None:
		registry.enabled = 0
		with patch("frappe.get_doc", return_value=registry), pytest.raises(AcpLaunchError, match="disabled"):
			build_launch_context("echo-local")

	def test_rejects_missing_registry(self) -> None:
		class _DoesNotExistError(Exception):
			pass

		import frappe

		frappe.DoesNotExistError = _DoesNotExistError
		with patch("frappe.get_doc", side_effect=_DoesNotExistError("not found")), pytest.raises(
			AcpLaunchError, match="not found"
		):
			build_launch_context("missing")

	def test_rejects_relative_binary_path(self, registry: _FakeRegistry) -> None:
		registry.binary_path = "echo"
		with patch("frappe.get_doc", return_value=registry), pytest.raises(
			AcpSecurityError, match="absolute"
		):
			build_launch_context("echo-local")

	def test_rejects_non_executable_binary(self, registry: _FakeRegistry) -> None:
		registry.binary_path = "/etc/passwd"
		with patch("frappe.get_doc", return_value=registry), pytest.raises(
			AcpSecurityError, match="executable"
		):
			build_launch_context("echo-local")

	def test_rejects_invalid_argv_shape(self, registry: _FakeRegistry) -> None:
		registry.argv_shape = ["ok", 123]
		with patch("frappe.get_doc", return_value=registry), pytest.raises(
			AcpSecurityError, match="string"
		):
			build_launch_context("echo-local")

	def test_rejects_missing_auth_secret_when_required(self, registry: _FakeRegistry) -> None:
		registry.auth_required = 1
		registry.auth_env_key = "HUF_ACP_TARGET_TOKEN"
		with patch("frappe.get_doc", return_value=registry), pytest.raises(
			AcpSecurityError, match="requires auth_secret"
		):
			build_launch_context("echo-local")

	def test_rejects_deny_listed_auth_env_key(self, registry: _FakeRegistry) -> None:
		registry.auth_required = 1
		registry.auth_env_key = "LD_PRELOAD"
		with patch("frappe.get_doc", return_value=registry), pytest.raises(
			AcpSecurityError, match="deny-list"
		):
			build_launch_context("echo-local", auth_secret="x")

	def test_env_scrubbing_removes_worker_secrets(self, registry: _FakeRegistry) -> None:
		registry.auth_required = 0
		registry.auth_env_key = ""
		registry.env_allow_list = [
			_FakeRegistryEnvVar("PATH", "/usr/bin"),
			_FakeRegistryEnvVar("LD_PRELOAD", "evil.so"),
			_FakeRegistryEnvVar("NODE_OPTIONS", "--require evil"),
		]
		with patch("frappe.get_doc", return_value=registry):
			ctx = build_launch_context("echo-local")

		assert ctx["env"].get("PATH") == "/usr/bin"
		assert "LD_PRELOAD" not in ctx["env"]
		assert "NODE_OPTIONS" not in ctx["env"]
