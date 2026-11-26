# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Who may read, and who may change or export, a conversation's artifacts.

Reading and the HTML preview follow the Agent Conversation document permission
(what the chat view uses); everything else stays with the owner and System Manager.

Runs without a bench (frappe is mocked) and under:
	bench --site <site> run-tests --app huf --module huf.ai.tests.test_artifact_api_access
"""

import importlib.util
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import frappe

_SOURCE = Path(__file__).resolve().parents[1] / "artifact_api.py"
_EXPORT_SOURCE = _SOURCE.with_name("artifact_export_api.py")


class _Denied(Exception):
	pass


def _load_artifact_api(source=_SOURCE):
	"""A private copy of the module with ``whitelist`` as a pass-through, so endpoints stay callable."""
	spec = importlib.util.spec_from_file_location(f"_{source.stem}_under_test", source)
	module = importlib.util.module_from_spec(spec)
	with mock.patch.object(frappe, "whitelist", lambda *a, **kw: lambda fn: fn):
		spec.loader.exec_module(module)
	return module


def _throw(message, exc=None):
	raise (exc or Exception)(message)


class TestArtifactConversationAccess(unittest.TestCase):
	def setUp(self):
		self.api = _load_artifact_api()
		self.conversation = SimpleNamespace(owner="owner@example.com")
		self.artifact = mock.MagicMock(conversation="CONV-1")
		self.fake = mock.MagicMock()
		self.fake.PermissionError = _Denied
		self.fake.throw.side_effect = _throw
		self.fake.get_doc.side_effect = lambda doctype, name: (
			self.conversation if doctype == "Agent Conversation" else self.artifact
		)
		self.fake.get_all.return_value = [{"name": "ART-1"}]
		self.api.frappe = self.fake
		self.api._ = lambda text: text

	def _as(self, user, roles=("Huf User",), can_read=False):
		self.fake.session.user = user
		self.fake.get_roles.return_value = list(roles)
		self.fake.has_permission.return_value = can_read

	def test_user_who_can_open_the_conversation_can_list_and_read(self):
		self._as("manager@example.com", roles=("Huf Manager",), can_read=True)

		self.assertEqual(self.api.list_conversation_artifacts("CONV-1"), [{"name": "ART-1"}])
		self.assertEqual(self.api.get_artifact("ART-1")["conversation"], "CONV-1")
		self.fake.has_permission.assert_called_with("Agent Conversation", "read", doc=self.conversation)

	def test_user_who_cannot_open_the_conversation_is_refused(self):
		self._as("other@example.com")

		with self.assertRaises(_Denied):
			self.api.list_conversation_artifacts("CONV-1")
		with self.assertRaises(_Denied):
			self.api.get_artifact("ART-1")
		self.fake.get_all.assert_not_called()

	def test_owner_and_system_manager_keep_access(self):
		for user, roles in (("owner@example.com", ("Huf User",)), ("sm@example.com", ("System Manager",))):
			self._as(user, roles=roles)
			self.assertEqual(self.api.list_conversation_artifacts("CONV-1"), [{"name": "ART-1"}])
			self.api._check_conversation_access("CONV-1")

	def test_read_permission_does_not_grant_the_strict_check(self):
		self._as("manager@example.com", roles=("Huf Manager",), can_read=True)

		with self.assertRaises(_Denied):
			self.api._check_conversation_access("CONV-1")

	def _export_api(self):
		# The renderers need PDF/DOCX libraries; only the permission checks are under test.
		renderers = {f"huf.ai.artifacts.render.{kind}": mock.MagicMock() for kind in ("docx", "html", "pdf")}
		with mock.patch.dict("sys.modules", {"huf.ai.artifact_api": self.api, **renderers}):
			export_api = _load_artifact_api(_EXPORT_SOURCE)
		export_api.frappe = self.fake
		export_api._ = lambda text: text
		self.artifact.artifact_type = "document"
		return export_api

	def test_reader_gets_the_html_preview_but_cannot_export(self):
		export_api = self._export_api()
		self._as("manager@example.com", roles=("Huf Manager",), can_read=True)

		with mock.patch.object(export_api, "_render_artifact_html", return_value="<html></html>"):
			self.assertEqual(export_api.get_artifact_html("ART-1"), "<html></html>")
		for fmt in ("pdf", "docx"):
			with self.assertRaises(_Denied):
				export_api.export_artifact("ART-1", fmt)
			with self.assertRaises(_Denied):
				export_api.preview_artifact_file("ART-1", fmt)

	def test_non_reader_gets_no_html_preview(self):
		export_api = self._export_api()
		self._as("other@example.com")

		with mock.patch.object(export_api, "_render_artifact_html") as render:
			with self.assertRaises(_Denied):
				export_api.get_artifact_html("ART-1")
		render.assert_not_called()

	def test_agent_list_tool_stays_owner_only(self):
		from huf.ai.tools import document_artifact

		self._as("manager@example.com", roles=("Huf Manager",), can_read=True)
		with (
			mock.patch.dict("sys.modules", {"huf.ai.artifact_api": self.api}),
			mock.patch.object(document_artifact.frappe, "PermissionError", _Denied),
		):
			result = json.loads(document_artifact.handle_list_document_artifacts(conversation_id="CONV-1"))

		self.assertFalse(result["success"])
		self.fake.get_all.assert_not_called()


if __name__ == "__main__":
	unittest.main()
