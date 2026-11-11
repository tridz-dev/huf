"""A failed audit mirror must be logged (Error Log) and must never fail the send (mock-based, no network)."""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe

from huf.ai.gateway_adapters import whatsapp_bridge as wb
from huf.ai.whatsapp import account_events

ACCT = {
	"name": "ACC",
	"phone_id": "111",
	"business_id": "BIZ",
	"app_id": "APP",
	"token": "tok",
	"url": "https://graph.facebook.com",
	"version": "v25.0",
	"webhook_verify_token": "v",
	"status": "Active",
}
TITLE = "WhatsApp mirror failed"


class FailingDoc(SimpleNamespace):
	def get(self, key, default=None):
		return getattr(self, key, default)

	def insert(self, **kwargs):
		raise RuntimeError("forced insert failure")


class FakeResp:
	def __init__(self, json_data):
		self._j = json_data
		self.status_code = 200

	def json(self):
		return self._j


_REAL_GET_DOC = frappe.get_doc


def _failing_message_doc(*args, **kwargs):
	"""Only the WhatsApp Message insert fails; frappe.log_error still builds its Error Log normally."""
	values = args[0] if args else kwargs
	if isinstance(values, dict) and values.get("doctype") == "WhatsApp Message":
		return FailingDoc()
	return _REAL_GET_DOC(*args, **kwargs)


def _error_log_count():
	return len(frappe.get_all("Error Log", filters={"method": TITLE}, pluck="name"))


class TestMirrorFailureLogging(unittest.TestCase):
	def test_template_mirror_failure_logs_and_send_still_succeeds(self):
		before = _error_log_count()
		with patch.object(wb, "resolve_account", return_value=ACCT), patch.object(
			wb, "_template_docname", return_value="hello_tpl-en_US"
		), patch.object(wb, "_graph_post_message", return_value="wamid.G1") as post, patch.object(
			frappe, "get_doc", side_effect=_failing_message_doc
		), patch.object(frappe, "has_permission", return_value=True), patch.object(
			frappe.db, "commit"
		) as commit:
			res = wb.send_template("ACC", "+1 415", "hello_tpl", ["a", "b"], ["h"])
		self.assertEqual(res["success"], True)
		self.assertEqual(res["message_id"], "wamid.G1")
		self.assertIs(res["mirrored"], False)
		self.assertEqual(post.call_count, 1)  # the delivery happened once; the failed row is never resent
		commit.assert_not_called()
		self.assertEqual(_error_log_count(), before + 1)

	def test_direct_send_mirror_failure_logs_and_send_still_succeeds(self):
		payload = {"messaging_product": "whatsapp", "to": "14155552671", "type": "text", "text": {"body": "x"}}
		http_post = MagicMock(return_value=FakeResp({"messages": [{"id": "wamid.D1"}]}))
		before = _error_log_count()
		with patch.object(wb, "resolve_account", return_value=ACCT), patch.object(
			wb, "_account_or_error", return_value=ACCT
		), patch.object(account_events, "send_refusal", return_value=None), patch.object(
			frappe, "get_doc", side_effect=_failing_message_doc
		), patch.object(frappe, "has_permission", return_value=True):
			res = wb._send_payload("ACC", payload, False, http_post)
		self.assertEqual(res["message_id"], "wamid.D1")
		self.assertIs(res["mirrored"], False)
		self.assertEqual(http_post.call_count, 1)
		self.assertEqual(_error_log_count(), before + 1)

	def test_mirror_failure_log_has_traceback_and_no_message_body(self):
		with patch.object(wb, "resolve_account", return_value=ACCT), patch.object(
			wb, "_template_docname", return_value="hello_tpl-en_US"
		), patch.object(wb, "_graph_post_message", return_value="wamid.G2"), patch.object(
			frappe, "get_doc", side_effect=_failing_message_doc
		), patch.object(frappe, "has_permission", return_value=True), patch.object(
			frappe, "log_error"
		) as log_error:
			wb.send_template("ACC", "+1 415", "hello_tpl", ["secret-body-text"], ["h"])
		log_error.assert_called_once()
		self.assertEqual(log_error.call_args.kwargs["title"], TITLE)
		self.assertNotIn("secret-body-text", str(log_error.call_args))
		self.assertNotIn("tok", str(log_error.call_args.kwargs.get("message", "")).split())
