# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Pure-Python unit tests for the batch provider modules.

These do NOT need a live Frappe site or DB: `frappe`, `litellm`, and
`anthropic` are stubbed out in `sys.modules` before the modules under test are
imported, and the frappe-calling functions are exercised via
`unittest.mock.patch` on the stubbed `frappe` attributes. No existing test in
this repo stubs frappe at import time this way (the other test files under
`huf/` all rely on `frappe.tests.IntegrationTestCase` against a live site), so
this file establishes its own minimal convention rather than following one.

Runnable standalone (no bench/site needed) via:

	python3 -m unittest huf.ai.providers.batch.test_batch_providers

...PROVIDED `frappe`, `litellm`, and `anthropic` are not already importable
for real in the environment in a way that conflicts with the stubs below (the
stubs are only installed if those modules aren't already present real
packages -- see the `sys.modules.setdefault` guards). In this worktree's
plain `python3`, none of `frappe`/`litellm`/`anthropic` are installed, so the
stubs are always used and the tests run against pure logic only.
"""

from __future__ import annotations

import sys
import types
import unittest
from unittest.mock import MagicMock


def _install_stub_module(name: str, **attrs) -> types.ModuleType:
	"""Install a bare stub module under `name` in sys.modules if not already present."""
	module = sys.modules.get(name)
	if module is None:
		module = types.ModuleType(name)
		sys.modules[name] = module
	for key, value in attrs.items():
		setattr(module, key, value)
	return module


class _FrappeThrow(Exception):
	"""Stand-in for frappe.throw raising, so tests can assertRaises on it."""


def _fake_frappe_throw(msg, *args, **kwargs):
	raise _FrappeThrow(msg)


# Every stub below MUTATES whatever is already in sys.modules -- it setattr's
# onto the existing module object rather than only creating missing ones. Under
# `bench run-tests` those existing objects are the REAL frappe, litellm and huf
# packages, so installing the stubs replaces frappe.throw, frappe.db (with a
# bare module that has no .commit), and huf.ai.providers.litellm's helpers for
# the rest of the process. That aborted the whole backend suite:
# `AttributeError: module 'frappe.db' has no attribute 'commit'` in frappe's own
# _cleanup_after_tests. Detect a live site and, when there is one, install
# nothing and skip the module -- these are standalone pure-logic tests.
try:
	import frappe as _maybe_real_frappe

	_HAS_REAL_FRAPPE = bool(getattr(getattr(_maybe_real_frappe, "local", None), "site", None))
except Exception:
	_HAS_REAL_FRAPPE = False

_SKIP_REASON = (
	"standalone mocked tests -- run outside bench: "
	"python3 -m unittest huf.ai.providers.batch.test_batch_providers"
)


class ProviderUnavailableError(Exception):
	def __init__(self, message, log_message=None):
		super().__init__(message)
		self.log_message = log_message


if not _HAS_REAL_FRAPPE:
	# Install minimal stub packages BEFORE importing the modules under test, since
	# openai_batch.py / anthropic_batch.py import `frappe`, `litellm`, and
	# `anthropic` at module scope.
	_install_stub_module(
		"frappe",
		throw=_fake_frappe_throw,
		get_doc=MagicMock(),
		log_error=MagicMock(),
		get_traceback=MagicMock(return_value=""),
	)
	_install_stub_module("frappe.db", get_value=MagicMock())
	sys.modules["frappe"].db = sys.modules["frappe.db"]  # type: ignore[attr-defined]

	_install_stub_module(
		"litellm",
		acreate_file=MagicMock(),
		acreate_batch=MagicMock(),
		aretrieve_batch=MagicMock(),
		afile_content=MagicMock(),
	)

	_anthropic_stub = _install_stub_module("anthropic", AsyncAnthropic=MagicMock())

	# huf.ai.providers.litellm is a real repo module but importing it drags in the
	# `frappe`/`litellm` deps above (now stubbed) plus repo-internal helpers we
	# don't want to fight with; stub the two symbols openai_batch/anthropic_batch
	# actually import from it instead of importing the real module.
	_huf_ai_providers_litellm_stub = _install_stub_module(
		"huf.ai.providers.litellm",
		_resolve_api_key=MagicMock(return_value="test-api-key"),
		_resolve_api_base=MagicMock(return_value=None),
	)


	_huf_ai_providers_litellm_stub.ProviderUnavailableError = ProviderUnavailableError

	# Make sure the parent packages resolve for `from huf.ai.providers.litellm import ...`
	# WITHOUT executing the real huf/__init__.py (which hard-imports frappe at
	# module scope and would blow up before this stub-installation code even
	# runs, if the real package were imported normally). We stub `huf`, `huf.ai`,
	# and `huf.ai.providers` as bare packages, but point their `__path__` at the
	# real on-disk directories so that the real `huf.ai.providers.batch`
	# subpackage (and its real openai_batch.py/anthropic_batch.py modules) still
	# get found and imported normally below -- only the *parent* __init__.py
	# files are skipped, since a module already present in sys.modules is never
	# re-imported/re-executed.
	import pathlib

	_THIS_DIR = pathlib.Path(__file__).resolve().parent  # .../huf/ai/providers/batch
	_PROVIDERS_DIR = _THIS_DIR.parent  # .../huf/ai/providers
	_AI_DIR = _PROVIDERS_DIR.parent  # .../huf/ai
	_HUF_PKG_DIR = _AI_DIR.parent  # .../huf (the inner "huf" Python package dir)

	_huf_pkg_stub = _install_stub_module("huf")
	_huf_pkg_stub.__path__ = [str(_HUF_PKG_DIR)]  # type: ignore[attr-defined]

	_huf_ai_stub = _install_stub_module("huf.ai")
	_huf_ai_stub.__path__ = [str(_AI_DIR)]  # type: ignore[attr-defined]

	_huf_ai_providers_stub = _install_stub_module("huf.ai.providers")
	_huf_ai_providers_stub.__path__ = [str(_PROVIDERS_DIR)]  # type: ignore[attr-defined]

	sys.modules["huf.ai"].providers = sys.modules["huf.ai.providers"]  # type: ignore[attr-defined]
	sys.modules["huf.ai.providers"].litellm = _huf_ai_providers_litellm_stub  # type: ignore[attr-defined]

	from huf.ai.providers.batch import anthropic_batch, openai_batch
else:  # pragma: no cover - bench run; module is skipped wholesale below
	anthropic_batch = openai_batch = None


@unittest.skipIf(_HAS_REAL_FRAPPE, _SKIP_REASON)
class TestOpenAIBuildJsonl(unittest.TestCase):
	def test_build_jsonl_shapes_each_line_by_custom_id(self):
		requests = [
			{"custom_id": "job-1", "model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hi"}]},
			{"custom_id": "job-2", "model": "gpt-4o-mini", "messages": [{"role": "user", "content": "bye"}]},
		]

		jsonl_bytes = openai_batch._build_jsonl(requests)
		lines = jsonl_bytes.decode("utf-8").splitlines()

		self.assertEqual(len(lines), 2)

		import json

		parsed = [json.loads(line) for line in lines]
		by_custom_id = {p["custom_id"]: p for p in parsed}

		self.assertEqual(set(by_custom_id), {"job-1", "job-2"})
		for record in by_custom_id.values():
			self.assertEqual(record["method"], "POST")
			self.assertEqual(record["url"], openai_batch._BATCH_ENDPOINT)
			self.assertNotIn("custom_id", record["body"])
			self.assertEqual(record["body"]["model"], "gpt-4o-mini")

	def test_build_jsonl_ends_with_trailing_newline(self):
		requests = [{"custom_id": "job-1", "model": "gpt-4o-mini", "messages": []}]
		jsonl_bytes = openai_batch._build_jsonl(requests)
		self.assertTrue(jsonl_bytes.endswith(b"\n"))

	def test_build_jsonl_requires_custom_id(self):
		with self.assertRaises(_FrappeThrow):
			openai_batch._build_jsonl([{"model": "gpt-4o-mini"}])


@unittest.skipIf(_HAS_REAL_FRAPPE, _SKIP_REASON)
class TestOpenAIStatusMap(unittest.TestCase):
	def test_covers_all_documented_openai_statuses(self):
		documented_statuses = {
			"validating",
			"in_progress",
			"finalizing",
			"completed",
			"failed",
			"expired",
			"cancelling",
			"cancelled",
		}
		self.assertEqual(set(openai_batch._OPENAI_STATUS_TO_BATCH_JOB_STATUS), documented_statuses)

	def test_maps_onto_valid_batch_job_statuses_only(self):
		valid_batch_job_statuses = {
			"Pending",
			"Submitted",
			"In Progress",
			"Completed",
			"Failed",
			"Cancelled",
			"Expired",
		}
		mapped_values = set(openai_batch._OPENAI_STATUS_TO_BATCH_JOB_STATUS.values())
		self.assertTrue(mapped_values.issubset(valid_batch_job_statuses))


@unittest.skipIf(_HAS_REAL_FRAPPE, _SKIP_REASON)
class TestAnthropicBuildBatchRequests(unittest.TestCase):
	def test_build_batch_requests_shapes_by_custom_id_and_strips_stream(self):
		requests = [
			{
				"custom_id": "job-1",
				"model": "claude-3-5-sonnet-latest",
				"messages": [{"role": "user", "content": "hi"}],
				"stream": True,
			},
			{
				"custom_id": "job-2",
				"model": "claude-3-5-sonnet-latest",
				"messages": [{"role": "user", "content": "bye"}],
			},
		]

		batch_requests = anthropic_batch._build_batch_requests(requests)
		by_custom_id = {r["custom_id"]: r for r in batch_requests}

		self.assertEqual(set(by_custom_id), {"job-1", "job-2"})
		self.assertNotIn("stream", by_custom_id["job-1"]["params"])
		self.assertEqual(by_custom_id["job-2"]["params"]["model"], "claude-3-5-sonnet-latest")

	def test_build_batch_requests_requires_custom_id(self):
		with self.assertRaises(_FrappeThrow):
			anthropic_batch._build_batch_requests([{"model": "claude-3-5-sonnet-latest"}])


@unittest.skipIf(_HAS_REAL_FRAPPE, _SKIP_REASON)
class TestAnthropicStatusMap(unittest.TestCase):
	def test_covers_all_documented_anthropic_statuses(self):
		documented_statuses = {"in_progress", "canceling", "ended"}
		self.assertEqual(set(anthropic_batch._ANTHROPIC_STATUS_TO_BATCH_JOB_STATUS), documented_statuses)

	def test_maps_onto_valid_batch_job_statuses_only(self):
		valid_batch_job_statuses = {
			"Pending",
			"Submitted",
			"In Progress",
			"Completed",
			"Failed",
			"Cancelled",
			"Expired",
		}
		mapped_values = set(anthropic_batch._ANTHROPIC_STATUS_TO_BATCH_JOB_STATUS.values())
		self.assertTrue(mapped_values.issubset(valid_batch_job_statuses))


@unittest.skipIf(_HAS_REAL_FRAPPE, _SKIP_REASON)
class TestOpenAIFetchResultsParsing(unittest.IsolatedAsyncioTestCase):
	"""Exercises fetch_results()'s JSONL-parsing/custom_id-keying logic via a
	mocked litellm.aretrieve_batch/afile_content, without any real network or
	Frappe dependency.
	"""

	async def test_keys_results_by_custom_id_regardless_of_order(self):
		batch_obj = MagicMock(output_file_id="output-file", error_file_id=None)
		openai_batch.litellm.aretrieve_batch = MagicMock(
			return_value=_async_return(batch_obj),
		)

		# Deliberately out of submission order (job-2 before job-1).
		output_text = (
			'{"custom_id": "job-2", "response": {"body": {"answer": "b"}}, "error": null}\n'
			'{"custom_id": "job-1", "response": {"body": {"answer": "a"}}, "error": null}\n'
		)
		file_content = MagicMock(text=output_text)
		openai_batch.litellm.afile_content = MagicMock(return_value=_async_return(file_content))

		results = await openai_batch.fetch_results("batch-123", batch_job=None)
		by_custom_id = {r["custom_id"]: r for r in results}

		self.assertEqual(by_custom_id["job-1"]["response"], {"answer": "a"})
		self.assertEqual(by_custom_id["job-2"]["response"], {"answer": "b"})

	async def test_merges_error_file_onto_existing_custom_id(self):
		batch_obj = MagicMock(output_file_id="output-file", error_file_id="error-file")
		openai_batch.litellm.aretrieve_batch = MagicMock(return_value=_async_return(batch_obj))

		output_text = '{"custom_id": "job-1", "response": {"body": {"answer": "a"}}, "error": null}\n'
		error_text = '{"custom_id": "job-2", "error": {"message": "boom"}}\n'

		async def _fake_afile_content(file_id, **kwargs):
			if file_id == "output-file":
				return MagicMock(text=output_text)
			return MagicMock(text=error_text)

		openai_batch.litellm.afile_content = _fake_afile_content

		results = await openai_batch.fetch_results("batch-123", batch_job=None)
		by_custom_id = {r["custom_id"]: r for r in results}

		self.assertIsNone(by_custom_id["job-1"]["error"])
		self.assertEqual(by_custom_id["job-2"]["error"], {"message": "boom"})
		self.assertIsNone(by_custom_id["job-2"]["response"])


async def _async_return(value):
	return value


if __name__ == "__main__":
	unittest.main()
