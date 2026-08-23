# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Unit tests for T-11b: Agent Context Artifact lifecycle and quotas (F-16/F-17).

Exercises ``huf.ai.context_artifacts._check_artifact_quotas``,
``purge_expired_context_artifacts``, ``delete_conversation_artifacts``, and
the ``AgentConversation.on_trash`` cascade against a hand-written fake
``frappe`` -- no MagicMock-only affordances (``.side_effect`` etc.), per the
house convention in ``huf.ai.tests.test_graph_permissions``.

Run with:
  bench --site <site> run-tests --app huf --module huf.ai.tests.test_context_artifact_lifecycle
"""

import sys
import types
import unittest


def _install_standalone_frappe_stub():
	"""Install a narrow, hand-written fake ``frappe`` before importing anything
	under ``huf`` -- ``huf/__init__.py`` does ``import frappe`` unconditionally
	at module-load time, before ``conftest.py``'s own MagicMock stub has a
	chance to run (see ``test_graph_permissions._install_standalone_frappe_stub``,
	which this mirrors).

	On a real bench 'frappe' is already the genuine package (has a
	``__file__``); never touch that.
	"""
	existing = sys.modules.get("frappe")
	if existing is not None and hasattr(existing, "__file__"):
		return

	fake = _make_frappe_double()
	sys.modules["frappe"] = fake
	sys.modules["frappe.utils"] = fake.utils
	sys.modules["frappe.utils.file_manager"] = fake.utils.file_manager
	sys.modules["frappe.model"] = fake.model
	sys.modules["frappe.model.document"] = fake.model.document


def _make_frappe_double():
	"""Build a self-contained ``frappe`` stand-in.

	Tests patch this ONTO the module under test; they must never assign to attributes of the
	real ``frappe`` module. Doing so replaces them for the entire test session -- an earlier
	version of this file set ``frappe.conf = {}`` in setUp, which on a bench turned the real
	``frappe.conf`` into a plain dict and killed roughly 80 unrelated tests later in the run,
	all of them dying inside ``log_query`` on ``frappe.conf.allow_tests``.
	"""

	fake = types.ModuleType("frappe")

	class _DB:
		def __init__(self):
			self.counts = {}
			self.sql_results = {}
			self.values = {}
			self.deleted = []

		def count(self, doctype, filters=None):
			return self.counts.get(doctype, 0)

		def sql(self, query, params=None, as_dict=0):
			key = (query.strip().split("\n")[0].strip(), params)
			return self.sql_results.get(key, [[0]])

		def get_value(self, doctype, filters, fieldname=None):
			return self.values.get((doctype, str(filters), fieldname))

		def set_value(self, *a, **k):
			pass

	class _Log:
		def __init__(self):
			self.calls = []

		def __call__(self, message=None, title=None):
			self.calls.append((message, title))

	fake.db = _DB()
	fake.conf = {}
	fake.log_error = _Log()
	fake.flags = types.SimpleNamespace(currently_saving=[])

	fake.get_all_results = []

	def _get_all(doctype, filters=None, fields=None):
		return fake.get_all_results

	fake.get_all = _get_all

	fake.deleted_docs = []

	def _delete_doc(doctype, name, ignore_permissions=False, delete_permanently=False):
		fake.deleted_docs.append((doctype, name))

	fake.delete_doc = _delete_doc

	def _get_doc(spec_or_doctype, name=None):
		raise NotImplementedError("get_doc is not exercised by this test module")

	fake.get_doc = _get_doc

	fake_utils = types.ModuleType("frappe.utils")
	fake_utils.now_datetime = lambda: "2026-08-24 00:00:00"
	fake_utils.add_to_date = lambda dt, days=0: f"{dt}+{days}d"
	fake.utils = fake_utils

	import tempfile

	fake_file_manager = types.ModuleType("frappe.utils.file_manager")
	fake_file_manager.save_file = lambda *a, **k: None
	_fake_files_path = tempfile.mkdtemp(prefix="huf-test-files-")
	fake_file_manager.get_files_path = lambda is_private=False: _fake_files_path
	fake.utils.file_manager = fake_file_manager

	fake.PermissionError = PermissionError
	fake.ValidationError = ValueError
	fake._ = lambda msg, *a, **k: msg
	fake.whitelist = lambda *a, **k: (lambda f: f)
	fake.get_traceback = lambda: "<fake traceback>"

	fake_model = types.ModuleType("frappe.model")
	fake_document = types.ModuleType("frappe.model.document")

	class _Document:
		pass

	fake_document.Document = _Document
	fake_model.document = fake_document
	fake.model = fake_model

	return fake


_install_standalone_frappe_stub()

import frappe

from huf.ai import context_artifacts


class ArtifactQuotaTests(unittest.TestCase):
	"""F-17: per-artifact, per-conversation-count and per-conversation-bytes caps."""

	def setUp(self):
		# Patch the module under test, never the real frappe module. Assigning
		# frappe.db / frappe.conf directly replaces them for the WHOLE test session: on a
		# bench that turned frappe.conf into a plain dict, and every later test doing SQL
		# then died in log_query on frappe.conf.allow_tests. Roughly 80 unrelated tests
		# failed from this one line.
		double = _make_frappe_double()
		patcher = patch.object(context_artifacts, "frappe", double)
		patcher.start()
		self.addCleanup(patcher.stop)
		self.frappe = double

	def test_allows_a_small_artifact_under_all_caps(self):
		# no exception
		context_artifacts._check_artifact_quotas("CONV-1", incoming_bytes=100)

	def test_rejects_a_payload_over_the_per_artifact_cap(self):
		with self.assertRaises(context_artifacts.ArtifactQuotaExceeded):
			context_artifacts._check_artifact_quotas(
				"CONV-1", incoming_bytes=context_artifacts.DEFAULT_MAX_ARTIFACT_BYTES + 1
			)

	def test_rejects_when_conversation_is_already_at_the_count_cap(self):
		self.frappe.db.counts["Agent Context Artifact"] = context_artifacts.DEFAULT_MAX_ARTIFACTS_PER_CONVERSATION
		with self.assertRaises(context_artifacts.ArtifactQuotaExceeded):
			context_artifacts._check_artifact_quotas("CONV-1", incoming_bytes=10)

	def test_rejects_when_conversation_bytes_would_exceed_the_total_cap(self):
		query_key = (
			"SELECT COALESCE(SUM(payload_bytes), 0) FROM `tabAgent Context Artifact` WHERE conversation=%s",
			("CONV-1",),
		)
		self.frappe.db.sql_results[query_key] = [[context_artifacts.DEFAULT_MAX_CONVERSATION_BYTES - 10]]
		with self.assertRaises(context_artifacts.ArtifactQuotaExceeded):
			context_artifacts._check_artifact_quotas("CONV-1", incoming_bytes=20)

	def test_conf_overrides_are_honoured(self):
		self.frappe.conf["huf_context_artifact_max_bytes"] = 50
		with self.assertRaises(context_artifacts.ArtifactQuotaExceeded):
			context_artifacts._check_artifact_quotas("CONV-1", incoming_bytes=100)


class PurgeExpiredArtifactsTests(unittest.TestCase):
	"""F-16: the daily scheduler entry deletes expired artifacts and their Files."""

	def setUp(self):
		# Patch the module under test; never assign to the real frappe module (see
		# _make_frappe_double's docstring for what that cost us).
		double = _make_frappe_double()
		patcher = patch.object(context_artifacts, "frappe", double)
		patcher.start()
		self.addCleanup(patcher.stop)
		self.frappe = double

	def test_deletes_artifact_and_its_file(self):
		self.frappe.get_all_results = [{"name": "ART-0001", "payload_file": "/files/foo.json"}]
		self.frappe.db.values[("File", "{'file_url': '/files/foo.json'}", "name")] = "FILE-0001"

		purged = context_artifacts.purge_expired_context_artifacts()

		self.assertEqual(purged, 1)
		self.assertIn(("File", "FILE-0001"), self.frappe.deleted_docs)
		self.assertIn(("Agent Context Artifact", "ART-0001"), self.frappe.deleted_docs)

	def test_artifact_with_no_payload_file_is_still_deleted(self):
		self.frappe.get_all_results = [{"name": "ART-0002", "payload_file": None}]

		purged = context_artifacts.purge_expired_context_artifacts()

		self.assertEqual(purged, 1)
		self.assertNotIn(("File", None), self.frappe.deleted_docs)
		self.assertIn(("Agent Context Artifact", "ART-0002"), self.frappe.deleted_docs)

	def test_one_failure_does_not_stop_the_rest(self):
		def _flaky_delete(doctype, name, ignore_permissions=False, delete_permanently=False):
			if name == "ART-BAD":
				raise RuntimeError("boom")
			self.frappe.deleted_docs.append((doctype, name))

		self.frappe.delete_doc = _flaky_delete
		self.frappe.get_all_results = [
			{"name": "ART-BAD", "payload_file": None},
			{"name": "ART-OK", "payload_file": None},
		]

		purged = context_artifacts.purge_expired_context_artifacts()

		self.assertEqual(purged, 1)
		self.assertIn(("Agent Context Artifact", "ART-OK"), self.frappe.deleted_docs)
		self.assertTrue(self.frappe.log_error.calls)


class DeleteConversationArtifactsTests(unittest.TestCase):
	"""F-16: the on_trash cascade deletes every artifact/File for a conversation."""

	def setUp(self):
		# Patch the module under test; never assign to the real frappe module (see
		# _make_frappe_double's docstring for what that cost us).
		double = _make_frappe_double()
		patcher = patch.object(context_artifacts, "frappe", double)
		patcher.start()
		self.addCleanup(patcher.stop)
		self.frappe = double

	def test_deletes_every_artifact_for_the_conversation(self):
		self.frappe.get_all_results = [
			{"name": "ART-0001", "payload_file": None},
			{"name": "ART-0002", "payload_file": None},
		]

		from unittest.mock import patch

		with patch.object(context_artifacts, "_remove_shared_dir") as remove_dir:
			deleted = context_artifacts.delete_conversation_artifacts("CONV-1")

		self.assertEqual(deleted, 2)
		self.assertIn(("Agent Context Artifact", "ART-0001"), self.frappe.deleted_docs)
		self.assertIn(("Agent Context Artifact", "ART-0002"), self.frappe.deleted_docs)
		remove_dir.assert_called_once_with("CONV-1")


class AgentConversationOnTrashTests(unittest.TestCase):
	"""The DocType controller delegates to the cascade helper -- nothing more."""

	def test_on_trash_calls_delete_conversation_artifacts(self):
		from unittest.mock import patch

		from huf.huf.doctype.agent_conversation.agent_conversation import AgentConversation

		conv = AgentConversation.__new__(AgentConversation)
		conv.name = "CONV-42"

		with patch("huf.ai.context_artifacts.delete_conversation_artifacts") as cascade:
			conv.on_trash()

		cascade.assert_called_once_with("CONV-42")


if __name__ == "__main__":
	unittest.main()
