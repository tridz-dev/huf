# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Security-focused tests for the Subscription CLI provider feature
(Track-Item: T-T6, plan §75.6). Pure addition -- no existing test file is
modified.

Covers five areas, each its own ``TestCase``:

1. ``TestNoCredentialLeakage`` -- each adapter's error-classification/parsing
   path is fed a synthetic stderr string containing a fake secret token, and
   the resulting ``SubscriptionTurnResult``'s user/log-facing error text
   (``final_text`` / ``events[]`` / raised exception message) must not
   contain that exact token substring.
2. ``TestAuthChallengeAccessScoping`` -- unit tests for
   ``SubscriptionAuthChallenge.has_permission()``.
3. ``TestTenancyBeforeLoginAndInference`` -- re-verifies (framed as a
   security assertion) that ``executor.py`` checks tenancy before any
   adapter/CLI invocation.
4. ``TestNoPasswordFieldAccepted`` -- greps the subscription package (and
   ``subscription_api.py`` if it has landed) for a parameter/field literally
   named like a password/secret.
5. ``TestFailClosedOnUnrecognizedTenancyPolicy`` -- an unknown/corrupted
   ``tenancy_policy`` value must deny access, framed as a security assertion
   (already covered functionally by test_runtime_doctype_tenancy.py's
   ``test_unknown_policy_fails_closed``; this test exists so the security
   suite carries its own standalone proof of fail-closed behavior).

Layer A (no bench / no live Frappe site): relies on the repo-root
``conftest.py`` to stub ``frappe``/``litellm``/``agents`` before anything
under the ``huf`` package is imported, exactly as
``test_runtime_doctype_tenancy.py`` and ``test_executor_passthrough.py``
already do.
"""

from __future__ import annotations

import asyncio
import re
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import frappe

# See test_runtime_doctype_tenancy.py's docstring for why this shim is
# needed in a standalone (frappe-less) run: `subscription_runtime.py` and
# `subscription_auth_challenge.py` both do
# `from frappe.model.document import Document` at import time, which needs a
# real `frappe.model.document` submodule in `sys.modules`, not just an
# attribute on a MagicMock.
if not hasattr(frappe, "__file__"):
	_frappe_model = sys.modules.setdefault("frappe.model", types.ModuleType("frappe.model"))
	_frappe_model_document = sys.modules.setdefault(
		"frappe.model.document", types.ModuleType("frappe.model.document")
	)
	if not hasattr(_frappe_model_document, "Document"):
		class Document:  # noqa: D401 - minimal stand-in, real class lives in frappe
			pass

		_frappe_model_document.Document = Document

from huf.ai.subscription.adapters.claude import ClaudeAdapter
from huf.ai.subscription.adapters.codex import CodexAdapter
from huf.ai.subscription.adapters.gemini import GeminiAdapter
from huf.ai.subscription.errors import SubscriptionCLIError, SubscriptionError
from huf.ai.subscription.transports.base import ExecutionTransport, ProcessResult, StagedFile, TransportProbe
from huf.ai.subscription.types import SubscriptionTurnRequest
from huf.huf.doctype.subscription_auth_challenge.subscription_auth_challenge import SubscriptionAuthChallenge

# Fake, obviously-synthetic secret values -- shaped like real credential
# formats but never a real key. Used as "the thing that must never leak."
FAKE_BEARER_TOKEN = "Bearer sk-ant-FAKE1234567890abcdefFAKE"  # noqa: S105
FAKE_OPENAI_KEY = "sk-FAKE1234567890abcdefFAKESECRETVALUE"  # noqa: S105
FAKE_GOOGLE_TOKEN = "ya29.FAKE_a0AbCdEfGhIjKlMnOpQrStUvWxYzFAKE1234567890"  # noqa: S105


def _run(coro):
	return asyncio.run(coro)


class _RecordingTransport(ExecutionTransport):
	"""Minimal transport stub returning a pre-scripted ProcessResult."""

	def __init__(self, result: ProcessResult):
		self.result = result
		self.calls: list[dict] = []

	async def probe(self) -> TransportProbe:
		return TransportProbe(reachable=True)

	async def run(self, argv, *, cwd=None, env=None, stdin=None, timeout=None) -> ProcessResult:
		self.calls.append({"argv": argv, "cwd": cwd, "env": env, "stdin": stdin, "timeout": timeout})
		return self.result

	async def stage_file(self, source_path: str, *, target_name: str | None = None) -> StagedFile:
		raise NotImplementedError

	async def remove_staged_file(self, staged_file: StagedFile) -> None:
		pass


def _make_request(**overrides) -> SubscriptionTurnRequest:
	defaults = dict(
		runtime_name="sec-test-runtime",
		provider_session_id=None,
		text="hello",
		files=[],
		model_override=None,
		run_id="run-1",
		conversation_id=None,
		timeout_seconds=30,
	)
	defaults.update(overrides)
	return SubscriptionTurnRequest(**defaults)


class _FakeRuntime:
	def __init__(self, **overrides):
		defaults = dict(
			name="sec-test-runtime",
			transport_type="local",
			executable="cli",
			working_directory="/work/proj",
			docker_container=None,
			ssh_connection=None,
		)
		defaults.update(overrides)
		for key, value in defaults.items():
			setattr(self, key, value)


def _result_text_blob(result) -> str:
	"""Flatten every user/log-facing text field of a SubscriptionTurnResult
	into one string, for a single "does the secret appear anywhere" check."""
	parts = [result.final_text or "", result.auth_reason or ""]
	for event in result.events or []:
		parts.append(str(event.get("message") or ""))
		parts.append(str(event.get("code") or ""))
	return "\n".join(parts)


class TestNoCredentialLeakage(unittest.TestCase):
	"""Point 1: no adapter's error path ever echoes a raw secret token into
	the SubscriptionTurnResult's user/log-facing error text."""

	# --- Claude: plain-text stderr (non-JSON stdout) parsing path ---------

	def test_claude_parse_turn_output_sanitizes_bearer_token_in_stderr(self):
		adapter = ClaudeAdapter(_RecordingTransport(ProcessResult(stdout="", stderr="", exit_code=1)))
		fake_result = SimpleNamespace(
			stdout="",
			stderr=f"Error: authentication failed. Authorization: {FAKE_BEARER_TOKEN}",
			exit_code=1,
		)
		turn_result = adapter._parse_turn_output(["claude"], fake_result)

		self.assertEqual(turn_result.status, "error")
		blob = _result_text_blob(turn_result)
		self.assertNotIn(FAKE_BEARER_TOKEN, blob)
		# The bare token value (without the "Bearer " prefix) must not survive either.
		self.assertNotIn(FAKE_BEARER_TOKEN.split()[-1], blob)

	def test_claude_parse_turn_output_sanitizes_raw_api_key_in_stderr(self):
		adapter = ClaudeAdapter(_RecordingTransport(ProcessResult(stdout="", stderr="", exit_code=1)))
		# A CLI/HTTP-client style error line embedding a raw sk- secret with
		# no other trigger keyword nearby.
		fake_result = SimpleNamespace(
			stdout="",
			stderr=f"upstream request failed: token {FAKE_OPENAI_KEY} rejected",
			exit_code=1,
		)
		turn_result = adapter._parse_turn_output(["claude"], fake_result)

		blob = _result_text_blob(turn_result)
		self.assertNotIn(FAKE_OPENAI_KEY, blob)

	# --- Codex: exit!=0 / no-stdout plain-CLI-failure path -----------------

	def test_codex_run_turn_sanitizes_secret_in_stderr_exception_message(self):
		transport = _RecordingTransport(
			ProcessResult(stdout="", stderr=f"fatal: login failed ({FAKE_GOOGLE_TOKEN})", exit_code=1)
		)
		adapter = CodexAdapter(transport)
		runtime = _FakeRuntime()
		request = _make_request()

		with self.assertRaises(SubscriptionCLIError) as ctx:
			_run(adapter.run_turn(runtime, request))

		self.assertNotIn(FAKE_GOOGLE_TOKEN, str(ctx.exception))

	def test_codex_resume_not_found_path_keeps_final_text_and_events_clean(self):
		# Finding-1 path (malformed/nonexistent resume target): this returns a
		# SubscriptionTurnResult directly rather than raising. Its `raw_debug_ref`
		# is an internal debug field never wired into telemetry/executor output
		# (verified: huf/ai/subscription/telemetry.py never reads it) -- the
		# fields that actually reach a user/log surface (`final_text`, `events`)
		# must still be clean regardless.
		stderr = (
			f"Error: thread/resume: thread/resume failed: no rollout found for "
			f"thread id {FAKE_BEARER_TOKEN} (code -32600)"
		)
		transport = _RecordingTransport(ProcessResult(stdout="", stderr=stderr, exit_code=1))
		adapter = CodexAdapter(transport)
		runtime = _FakeRuntime()
		request = _make_request(provider_session_id="00000000-0000-0000-0000-000000000000")

		turn_result = _run(adapter.run_turn(runtime, request))

		blob = _result_text_blob(turn_result)
		self.assertNotIn(FAKE_BEARER_TOKEN, blob)

	# --- Gemini: exit!=0 verbatim-stderr path -------------------------------

	def test_gemini_run_turn_error_path_never_puts_secret_in_final_text(self):
		# Gemini's adapter (per its own module docstring) has no confirmed
		# error-output shape, so on a non-zero exit it surfaces the raw stderr
		# only via `raw_debug_ref` (an internal-only field, not read by
		# telemetry.py or the executor) and leaves `final_text`/`events` empty.
		# This test locks in that `final_text`/`events` -- the fields an
		# unrelated caller might reasonably treat as "the error text" -- never
		# carry the secret, regardless of what raw_debug_ref holds.
		transport = _RecordingTransport(
			ProcessResult(stdout="", stderr=f"login required: {FAKE_OPENAI_KEY}", exit_code=1)
		)
		adapter = GeminiAdapter(transport)
		runtime = _FakeRuntime()
		request = _make_request()

		turn_result = _run(adapter.run_turn(runtime, request))

		self.assertIsNone(turn_result.final_text)
		blob = _result_text_blob(turn_result)
		self.assertNotIn(FAKE_OPENAI_KEY, blob)


def _make_challenge(**overrides):
	defaults = dict(created_by=None, runtime=None)
	defaults.update(overrides)
	challenge = object.__new__(SubscriptionAuthChallenge)
	for key, value in defaults.items():
		setattr(challenge, key, value)
	return challenge


class TestAuthChallengeAccessScoping(unittest.TestCase):
	"""Point 2: SubscriptionAuthChallenge.has_permission() scoping.

	Style matches test_runtime_doctype_tenancy.py: a real (never-`__init__`-ed)
	`SubscriptionAuthChallenge` instance built via `object.__new__`, with only
	the fields `has_permission` reads set directly, plus `frappe.session`/
	`frappe.get_roles`/`frappe.db.get_value` monkeypatched for the branches
	that touch them.
	"""

	def test_challenge_creator_can_read_own_challenge(self):
		challenge = _make_challenge(created_by="alice@example.com", runtime="RUNTIME-1")
		with mock.patch.object(frappe, "session", types.SimpleNamespace(user="alice@example.com")), \
			mock.patch.object(frappe, "get_roles", return_value=["Huf User"]), \
			mock.patch("huf.permissions.has_capability", return_value=False), \
			mock.patch.object(frappe.db, "get_value", return_value="bob@example.com"):
			self.assertTrue(challenge.has_permission("read"))

	def test_runtime_owner_can_read_challenge_they_did_not_create(self):
		challenge = _make_challenge(created_by="alice@example.com", runtime="RUNTIME-1")
		with mock.patch.object(frappe, "session", types.SimpleNamespace(user="owner@example.com")), \
			mock.patch.object(frappe, "get_roles", return_value=["Huf User"]), \
			mock.patch("huf.permissions.has_capability", return_value=False), \
			mock.patch.object(frappe.db, "get_value", return_value="owner@example.com"):
			self.assertTrue(challenge.has_permission("read"))

	def test_user_with_manage_capability_can_read_challenge(self):
		challenge = _make_challenge(created_by="alice@example.com", runtime="RUNTIME-1")
		with mock.patch.object(frappe, "session", types.SimpleNamespace(user="manager@example.com")), \
			mock.patch.object(frappe, "get_roles", return_value=["Huf Manager"]), \
			mock.patch("huf.permissions.has_capability", return_value=True) as mock_cap, \
			mock.patch.object(frappe.db, "get_value", return_value="bob@example.com"):
			self.assertTrue(challenge.has_permission("read"))
		mock_cap.assert_called_once_with("manager@example.com", "subscription_runtime.manage")

	def test_unrelated_random_user_cannot_read_challenge(self):
		challenge = _make_challenge(created_by="alice@example.com", runtime="RUNTIME-1")
		with mock.patch.object(frappe, "session", types.SimpleNamespace(user="random@example.com")), \
			mock.patch.object(frappe, "get_roles", return_value=["Huf User"]), \
			mock.patch("huf.permissions.has_capability", return_value=False), \
			mock.patch.object(frappe.db, "get_value", return_value="bob@example.com"):
			self.assertFalse(challenge.has_permission("read"))

	def test_system_manager_can_always_read_challenge(self):
		challenge = _make_challenge(created_by="alice@example.com", runtime="RUNTIME-1")
		with mock.patch.object(frappe, "session", types.SimpleNamespace(user="admin@example.com")), \
			mock.patch.object(frappe, "get_roles", return_value=["System Manager"]), \
			mock.patch("huf.permissions.has_capability", return_value=False), \
			mock.patch.object(frappe.db, "get_value", return_value="bob@example.com"):
			self.assertTrue(challenge.has_permission("read"))


class TestTenancyBeforeLoginAndInference(unittest.TestCase):
	"""Point 3: tenancy must be checked before any adapter/CLI invocation.

	This is a security-framed re-verification of T-06-C, already exercised
	functionally by
	`test_executor_passthrough.py::TestTenancyBeforeAnyCLIInvocation`. Rather
	than re-implementing (and risking drifting from) that test's fixtures,
	this imports and re-runs it directly plus adds one direct source-level
	assertion: `check_tenancy` must appear, and be called, before
	`_build_adapter` in `SubscriptionPassthroughExecutor.execute`'s source.
	"""

	def test_check_tenancy_precedes_build_adapter_in_source(self):
		import huf.ai.subscription.executor as executor_module

		source = Path(executor_module.__file__).read_text()
		# Slice to the body of SubscriptionPassthroughExecutor.execute only,
		# so this doesn't accidentally match an unrelated later definition.
		start = source.index("class SubscriptionPassthroughExecutor")
		tenancy_idx = source.index("check_tenancy(", start)
		adapter_idx = source.index("_build_adapter(", start)
		self.assertLess(
			tenancy_idx,
			adapter_idx,
			"check_tenancy() must be called before _build_adapter() in "
			"SubscriptionPassthroughExecutor.execute -- tenancy must be "
			"enforced before any login/inference attempt (plan sec 75.6).",
		)

	def test_existing_tenancy_before_cli_invocation_suite_passes(self):
		# Re-run the existing T-06-C suite from here too, so a regression in
		# "tenancy before CLI invocation" fails this security suite directly
		# rather than only a separate test file someone might not think to run.
		from huf.ai.tests.subscription.test_executor_passthrough import (
			TestTenancyBeforeAnyCLIInvocation,
		)

		suite = unittest.TestLoader().loadTestsFromTestCase(TestTenancyBeforeAnyCLIInvocation)
		result = unittest.TestResult()
		suite.run(result)
		self.assertTrue(
			result.wasSuccessful(),
			f"errors={result.errors} failures={result.failures}",
		)


# Parameter/field name shapes that would let a real password be submitted
# through this feature. Deliberately narrow (word-boundary-ish) so it doesn't
# false-positive on legitimate identifiers like "password" appearing only in
# prose/comments about *not* accepting one, or on SSH's own redaction list
# (huf/ai/subscription/transports/ssh.py's `_REDACT_KEYS`-style constant,
# which exists to redact, not accept, secrets).
_FORBIDDEN_FIELD_NAME_RE = re.compile(
	r"^\s*(?:async\s+def\s+\w+\s*\(|@dataclass|def\s+\w+\s*\()"
)
_FORBIDDEN_PARAM_RE = re.compile(r"\b(password|passwd|pwd)\s*[:=]", re.IGNORECASE)
_FORBIDDEN_DATACLASS_FIELD_RE = re.compile(r"^\s*(password|passwd|pwd)\s*:", re.IGNORECASE)


class TestNoPasswordFieldAccepted(unittest.TestCase):
	"""Point 4: no function parameter or dataclass field literally named
	like a password is accepted anywhere in the subscription package."""

	def _iter_subscription_py_files(self):
		subscription_pkg = Path(__file__).resolve().parents[2] / "subscription"
		self.assertTrue(subscription_pkg.is_dir(), f"expected package dir at {subscription_pkg}")
		yield from subscription_pkg.rglob("*.py")

	def test_no_password_shaped_parameter_in_subscription_package(self):
		offenders = []
		for path in self._iter_subscription_py_files():
			text = path.read_text()
			for lineno, line in enumerate(text.splitlines(), start=1):
				stripped = line.strip()
				if stripped.startswith("#"):
					continue
				if _FORBIDDEN_PARAM_RE.search(line) or _FORBIDDEN_DATACLASS_FIELD_RE.search(line):
					offenders.append(f"{path}:{lineno}: {stripped}")
		self.assertEqual(
			offenders,
			[],
			"Found a password/passwd/pwd-shaped parameter or field in "
			f"huf/ai/subscription/: {offenders}",
		)

	def test_subscription_api_checked_if_landed_else_noted(self):
		api_path = Path(__file__).resolve().parents[2] / "subscription_api.py"
		if not api_path.exists():
			self.skipTest(
				"huf/ai/subscription_api.py has not landed yet (T-10-api still in "
				"progress) -- recommend re-running this test file once it lands."
			)
		text = api_path.read_text()
		offenders = [
			f"{lineno}: {line.strip()}"
			for lineno, line in enumerate(text.splitlines(), start=1)
			if not line.strip().startswith("#")
			and (_FORBIDDEN_PARAM_RE.search(line) or _FORBIDDEN_DATACLASS_FIELD_RE.search(line))
		]
		self.assertEqual(offenders, [], f"Found a password-shaped parameter in {api_path}: {offenders}")


def _make_runtime_for_tenancy(**overrides):
	from huf.huf.doctype.subscription_runtime.subscription_runtime import SubscriptionRuntime

	defaults = dict(
		tenancy_policy="owner_only",
		owner_user=None,
		allowed_users_json=None,
		allowed_roles_json=None,
	)
	defaults.update(overrides)
	runtime = object.__new__(SubscriptionRuntime)
	for key, value in defaults.items():
		setattr(runtime, key, value)
	return runtime


class TestFailClosedOnUnrecognizedTenancyPolicy(unittest.TestCase):
	"""Point 5: an unknown/corrupted tenancy_policy value must DENY access.

	Functionally identical to
	test_runtime_doctype_tenancy.py::test_unknown_policy_fails_closed;
	restated here, framed explicitly as a security assertion (fail-closed,
	not fail-open, on an unrecognized authorization policy), so the security
	suite carries its own standalone proof independent of that file.
	"""

	def test_unknown_tenancy_policy_denies_rather_than_allows(self):
		runtime = _make_runtime_for_tenancy(tenancy_policy="some_future_policy_this_version_does_not_know")
		self.assertFalse(runtime.check_tenancy("alice@example.com"))

	def test_corrupted_empty_tenancy_policy_denies_rather_than_allows(self):
		runtime = _make_runtime_for_tenancy(tenancy_policy="")
		self.assertFalse(runtime.check_tenancy("alice@example.com"))

	def test_none_tenancy_policy_denies_rather_than_allows(self):
		runtime = _make_runtime_for_tenancy(tenancy_policy=None)
		self.assertFalse(runtime.check_tenancy("alice@example.com"))


if __name__ == "__main__":
	unittest.main()
