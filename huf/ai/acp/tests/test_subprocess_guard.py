"""Tests for the ACP subprocess security guard."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from huf.ai.acp.exceptions import AcpCapacityError, AcpSecurityError
from huf.ai.acp.subprocess_guard import (
	_MEMORY_COUNTER_BACKEND,
	DEFAULT_MAX_SUBPROCESSES,
	AcpSubprocessCounter,
	scrub_environment,
	validate_env_key,
	validate_working_directory,
)


class TestScrubEnvironment:
	def test_removes_deny_listed_fragments(self) -> None:
		env = {
			"PATH": "/usr/bin",
			"LD_PRELOAD": "evil.so",
			"NODE_OPTIONS": "--require evil",
			"PYTHONPATH": "/tmp",
			"HUF_ACP_TARGET_TOKEN": "secret",
			"FRAPPE_SITE": "test",
			"DB_PASSWORD": "hunter2",
			"REDIS_QUEUE": "redis://localhost",
			"MY_SECRET_KEY": "hidden",
			"API_KEY_VALUE": "hidden",
			"OPENBLAS_NUM_THREADS": "4",
		}
		scrubbed = scrub_environment(env)
		assert scrubbed.get("PATH") == "/usr/bin"
		assert scrubbed.get("HUF_ACP_TARGET_TOKEN") == "secret"
		assert "LD_PRELOAD" not in scrubbed
		assert "NODE_OPTIONS" not in scrubbed
		assert "PYTHONPATH" not in scrubbed
		assert "FRAPPE_SITE" not in scrubbed
		assert "DB_PASSWORD" not in scrubbed
		assert "REDIS_QUEUE" not in scrubbed
		assert "MY_SECRET_KEY" not in scrubbed
		assert "API_KEY_VALUE" not in scrubbed
		# Math-library limits are pinned if not already safe.
		assert scrubbed.get("OPENBLAS_NUM_THREADS") == "4"
		assert scrubbed.get("OMP_NUM_THREADS") == "1"

	def test_empty_env_returns_only_thread_limits(self) -> None:
		scrubbed = scrub_environment({})
		assert set(scrubbed.keys()) == {
			"OPENBLAS_NUM_THREADS",
			"OMP_NUM_THREADS",
			"MKL_NUM_THREADS",
			"VECLIB_MAXIMUM_THREADS",
			"NUMEXPR_NUM_THREADS",
		}

	def test_none_env_returns_only_thread_limits(self) -> None:
		scrubbed = scrub_environment(None)
		assert scrubbed["OMP_NUM_THREADS"] == "1"


class TestValidateWorkingDirectory:
	def test_accepts_valid_absolute_directory(self) -> None:
		with tempfile.TemporaryDirectory() as tmp:
			validate_working_directory(tmp)

	def test_rejects_relative_path(self) -> None:
		with pytest.raises(AcpSecurityError, match="must be absolute"):
			validate_working_directory("relative/path")

	def test_rejects_nonexistent_directory(self) -> None:
		with pytest.raises(AcpSecurityError, match="does not exist"):
			validate_working_directory("/tmp/this_should_not_exist_12345")

	def test_rejects_file(self) -> None:
		with tempfile.NamedTemporaryFile() as tmp:
			with pytest.raises(AcpSecurityError, match="does not exist or is not a directory"):
				validate_working_directory(tmp.name)

	def test_rejects_frappe_site_directory(self) -> None:
		with tempfile.TemporaryDirectory() as tmp:
			Path(tmp, "site_config.json").write_text("{}", encoding="utf-8")
			with pytest.raises(AcpSecurityError, match="Frappe"):
				validate_working_directory(tmp)


class TestValidateEnvKey:
	def test_accepts_safe_key(self) -> None:
		validate_env_key("HUF_ACP_TARGET_TOKEN")

	def test_rejects_lowercase(self) -> None:
		with pytest.raises(AcpSecurityError, match="invalid"):
			validate_env_key("lower_case")

	def test_rejects_deny_listed(self) -> None:
		with pytest.raises(AcpSecurityError, match="deny-listed"):
			validate_env_key("LD_PRELOAD")

	def test_rejects_leading_digit(self) -> None:
		with pytest.raises(AcpSecurityError, match="invalid"):
			validate_env_key("1VAR")


class TestAcpSubprocessCounter:
	@pytest.fixture
	def counter(self):
		return AcpSubprocessCounter(
			max_subprocesses=3,
			ttl_seconds=60,
			backend=_MEMORY_COUNTER_BACKEND(),
		)

	def test_acquire_increments_and_release_decrements(self, counter: AcpSubprocessCounter) -> None:
		counter.acquire()
		assert counter.current() == 1
		counter.acquire()
		assert counter.current() == 2
		counter.release()
		assert counter.current() == 1
		counter.release()
		assert counter.current() == 0

	def test_ceiling_blocks_additional_acquires(self, counter: AcpSubprocessCounter) -> None:
		counter.acquire()
		counter.acquire()
		counter.acquire()
		with pytest.raises(AcpCapacityError, match="ceiling reached"):
			counter.acquire()

	def test_release_is_idempotent(self, counter: AcpSubprocessCounter) -> None:
		counter.acquire()
		counter.release()
		counter.release()
		assert counter.current() == 0

	def test_release_deletes_key_at_zero(self, counter: AcpSubprocessCounter) -> None:
		counter.acquire()
		counter.release()
		assert counter.backend.get(counter._make_key()) in (0, None)
