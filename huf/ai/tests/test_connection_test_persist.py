"""Security round 2 (DECISIONS 13): Test connection only writes an integration's health for someone who may edit it."""

from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.tools.connection_test import test_connection


def _ok_slack():
	resp = MagicMock()
	resp.status_code = 200
	resp.json.return_value = {"ok": True, "team": "Tridz", "user": "huf_live"}
	resp.raise_for_status.return_value = None
	return resp


class TestConnectionHealthIsPersistedOnlyByEditors(IntegrationTestCase):
	def _permission(self, allowed):
		def check(doctype, ptype="read", doc=None, **kw):
			return ptype in allowed

		return patch("frappe.has_permission", side_effect=check)

	def _run(self, allowed):
		with patch("frappe.only_for"), patch("huf.ai.tools.connection_test._resolve_credentials", return_value={"token": "xoxb-fake"}), \
			patch("httpx.post", return_value=_ok_slack()), self._permission(allowed), \
			patch("huf.ai.tools.connection_test._remember_check") as remember:
			return test_connection(service="slack", setting="any-setting"), remember

	def test_a_read_only_caller_gets_the_answer_but_nothing_is_stored(self):
		out, remember = self._run({"read"})
		self.assertEqual(out["status"], "Connected")
		remember.assert_not_called()
		self.assertNotIn("checked_at", out)

	def test_an_editor_also_stores_the_check(self):
		out, remember = self._run({"read", "write"})
		self.assertEqual(out["status"], "Connected")
		remember.assert_called_once()
		self.assertIn("checked_at", out)

	def test_typed_values_are_never_stored_for_anyone(self):
		with patch("frappe.only_for"), patch("httpx.post", return_value=_ok_slack()), self._permission({"read", "write"}), \
			patch("huf.ai.tools.connection_test._remember_check") as remember:
			out = test_connection(service="slack", setting="any-setting", credentials={"token": "xoxb-typed"})
		self.assertEqual(out["status"], "Connected")
		remember.assert_not_called()

	def test_the_stored_record_is_untouched_for_a_read_only_caller(self):
		name = frappe.get_all("Integration Settings", filters={"service": "slack"}, pluck="name", limit=1)
		if not name:
			self.skipTest("needs a saved Slack integration")
		before = frappe.db.get_value("Integration Settings", name[0], ["last_test_status", "last_test_at", "last_test_message", "account_label"], as_dict=True)
		with patch("frappe.only_for"), patch("huf.ai.tools.connection_test._resolve_credentials", return_value={"token": "xoxb-fake"}), \
			patch("httpx.post", return_value=_ok_slack()), self._permission({"read"}):
			test_connection(service="slack", setting=name[0])
		after = frappe.db.get_value("Integration Settings", name[0], ["last_test_status", "last_test_at", "last_test_message", "account_label"], as_dict=True)
		self.assertEqual(before, after)
