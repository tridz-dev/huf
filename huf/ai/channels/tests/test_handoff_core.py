"""BE-ADAPT-CORE: ecosystem detection, handoff_to_human, handed-off inbound skip, reply API, Communication hook."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_to_date, now_datetime

from huf.ai.channels import adapters, conversation as conv, ecosystem, handoff, handoff_hooks, reply_api
from huf.ai.channels.pipeline import run_pre_route

NO_PERM_USER = "chan-reply-none@example.com"
REPLY_USER = "chan-reply-ok@example.com"


class _MockAdapter(adapters.ChannelAdapter):
	name = "mock"
	appended: list = []
	replied = False

	def handoff(self, conversation, summary="", priority="normal"):
		return "ToDo", "TODO-MOCK-1"

	def append_inbound(self, conversation, text, event=None):
		_MockAdapter.appended.append(text)


class TestHandoffCore(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.addCleanup(frappe.db.rollback)
		self.addCleanup(frappe.set_user, "Administrator")
		_MockAdapter.appended = []
		sfx = frappe.generate_hash(length=6)
		phone = "555" + str(int(frappe.generate_hash(length=7), 16) % 10**8).zfill(8)
		settings = frappe.get_doc(
			{
				"doctype": "Integration Settings",
				"service": "whatsapp",
				"credentials": [
					{"key": "phone_number_id", "value": phone},
					{"key": "access_token", "value": "tok"},
					{"key": "webhook_verify_token", "value": "verify"},
					{"key": "app_secret", "value": "sec"},
				],
			}
		).insert(ignore_permissions=True)
		self.gw = frappe.get_doc(
			{
				"doctype": "Gateway",
				"gateway_name": f"Hand {sfx}",
				"provider": "WhatsApp",
				"is_enabled": 1,
				"integration_settings": settings.name,
				"execution_user": "Administrator",
				"direct_policy": "Allow list",
				"handoff_message": "A person will reply shortly.",
			}
		).insert(ignore_permissions=True)
		self.conv = conv.get_or_create_conversation(self.gw.name, "15550003333")

	def _users(self):
		for email in (NO_PERM_USER, REPLY_USER):
			if not frappe.db.exists("User", email):
				frappe.get_doc(
					{"doctype": "User", "email": email, "first_name": "T", "send_welcome_email": 0, "roles": [{"role": "System User"}]}
				).insert(ignore_permissions=True)

	# --- ecosystem ---
	def test_ecosystem_detection(self):
		with patch("frappe.get_installed_apps", return_value=["frappe", "helpdesk", "erpnext"]), patch.object(
			ecosystem, "_app_version", return_value="1.2.3"
		), patch.dict(adapters.ADAPTER_MODULES, {"helpdesk": "huf.ai.channels.tests.test_handoff_core"}, clear=True):
			with patch.object(adapters, "_load", return_value=_MockAdapter()):
				apps = ecosystem.get_ecosystem_apps()
		self.assertEqual(set(apps), {"crm", "erpnext", "helpdesk", "lms", "ravan"})
		self.assertEqual(apps["helpdesk"], {"installed": True, "version": "1.2.3", "enabled_for_whatsapp": True})
		self.assertEqual(apps["erpnext"]["enabled_for_whatsapp"], False)
		self.assertEqual(apps["crm"], {"installed": False, "version": None, "enabled_for_whatsapp": False})

	def test_missing_adapter_falls_back_to_none(self):
		with patch("frappe.get_installed_apps", return_value=["frappe"]):
			self.assertEqual(adapters.get_adapter("helpdesk").name, "none")
		with patch("frappe.get_installed_apps", return_value=["frappe", "helpdesk"]), patch.dict(adapters.ADAPTER_MODULES, {}, clear=True):
			self.assertEqual(adapters.get_adapter("helpdesk").name, "none")
		self.assertEqual(adapters.get_adapter("none").name, "none")

	# --- handoff ---
	def test_handoff_none_target_sets_status_and_sends_once(self):
		with patch.object(handoff, "send_free_text", return_value="wamid.1") as send:
			res = handoff.handoff_conversation(self.conv, summary="needs help")
			again = handoff.handoff_conversation(self.conv.name, summary="again")
		self.assertTrue(res["success"])
		self.assertTrue(again["already"])
		send.assert_called_once_with(self.gw.name, "15550003333", "A person will reply shortly.")
		self.conv.reload()
		self.assertEqual(self.conv.status, "handed_off")
		self.assertFalse(self.conv.handoff_name)

	def test_handoff_uses_adapter_doc(self):
		with patch.object(adapters, "get_adapter", return_value=_MockAdapter()), patch.object(handoff, "send_free_text"):
			handoff.handoff_conversation(self.conv, target="helpdesk", summary="s", priority="high")
		self.conv.reload()
		self.assertEqual((self.conv.handoff_doctype, self.conv.handoff_name), ("ToDo", "TODO-MOCK-1"))

	def test_tool_handler(self):
		from huf.ai.tools import handoff as tool

		with patch.object(tool, "_run_chat", return_value=(self.gw.name, "15550003333")), patch.object(
			handoff, "send_free_text"
		):
			out = json.loads(tool.handle_handoff_to_human(summary="x", priority="urgent"))
		self.assertTrue(out["success"])
		self.assertEqual(out["conversation"], self.conv.name)
		self.assertEqual(frappe.db.get_value("Channel Conversation", self.conv.name, "status"), "handed_off")
		with patch.object(tool, "_run_chat", return_value=("", "")):
			self.assertFalse(json.loads(tool.handle_handoff_to_human(summary="x"))["success"])

	def test_handed_off_inbound_skips_ai_and_appends(self):
		self.conv.db_set({"status": "handed_off", "handoff_doctype": "ToDo", "handoff_name": "TODO-MOCK-1"})
		ctx = {"gateway": self.gw.name, "event": None, "context": {"sender_id": "15550003333", "message_text": "hello?"}}
		with patch.object(adapters, "adapter_for_conversation", return_value=_MockAdapter()):
			decision = run_pre_route(ctx)
		self.assertEqual(decision.action, "drop")
		self.assertEqual(_MockAdapter.appended, ["hello?"])
		self.conv.db_set("status", "ai")
		self.assertIsNone(handoff_hooks.handed_off_hook(ctx))

	def test_hook_is_first(self):
		from huf.ai.channels.pipeline import PRE_ROUTE_HOOKS

		self.assertEqual(PRE_ROUTE_HOOKS[0], "huf.ai.channels.handoff_hooks.handed_off_hook")

	# --- reply api ---
	def test_send_reply_inside_window(self):
		self.conv.db_set("last_inbound_at", now_datetime())
		with patch.object(reply_api, "send_free_text", return_value="wamid.2") as send:
			res = reply_api.send_reply(self.conv.name, text="hi")
		send.assert_called_once()
		self.assertEqual((res["status"], res["message_id"]), ("sent", "wamid.2"))

	def test_send_reply_outside_window_needs_template(self):
		self.conv.db_set("last_inbound_at", add_to_date(now_datetime(), hours=-30))
		with patch.object(reply_api, "send_free_text") as send:
			res = reply_api.send_reply(self.conv.name, text="hi")
		send.assert_not_called()
		self.assertEqual(res, {"status": "needs_template", "needs_template": True})
		with patch.object(reply_api, "_send_template", return_value="wamid.3") as tpl:
			res = reply_api.send_reply(self.conv.name, template="hello_tpl", params=["Ann"])
		tpl.assert_called_once_with(self.gw.name, "15550003333", "hello_tpl", ["Ann"])
		self.assertEqual(res["status"], "sent")

	def test_send_reply_refused_by_outbound_policy(self):
		self.conv.db_set("last_inbound_at", now_datetime())
		with patch.dict(frappe.conf, {"wa_outbound_allowlist": ["19998887777"]}):
			with patch("huf.ai.gateway_webhook.get_gateway_adapter") as get_adapter:
				from huf.ai.whatsapp import outbound_policy as policy

				get_adapter.return_value.send_reply.side_effect = policy.OutboundRefused("no", "recipient_not_allowlisted")
				res = reply_api.send_reply(self.conv.name, text="hi")
		self.assertEqual((res["status"], res["error"]), ("refused", "recipient_not_allowlisted"))

	def test_permissions(self):
		self._users()
		frappe.set_user(NO_PERM_USER)
		with self.assertRaises(frappe.PermissionError):
			reply_api.close(self.conv.name)
		with self.assertRaises(frappe.PermissionError):
			reply_api.list_templates(self.gw.name)
		frappe.set_user("Administrator")
		with patch("huf.permissions.has_capability", side_effect=lambda u, c: u == REPLY_USER and c == "channels.reply"):
			frappe.set_user(REPLY_USER)
			self.assertEqual(reply_api.close(self.conv.name)["status"], "ok")
		frappe.set_user("Administrator")
		self.assertIn("channels.reply", __import__("huf.permissions", fromlist=["x"]).CAPABILITIES)

	def test_return_to_ai_and_close(self):
		self.assertEqual(reply_api.return_to_ai(self.conv.name)["error"], "not_handed_off")
		self.conv.db_set("status", "handed_off")
		self.assertEqual(reply_api.return_to_ai(self.conv.name)["conversation_status"], "ai")
		self.assertEqual(reply_api.close(self.conv.name)["conversation_status"], "closed")
		self.assertEqual(frappe.db.get_value("Channel Conversation", self.conv.name, "status"), "closed")

	# --- Communication hook ---
	def test_communication_hook_calls_reply(self):
		self.conv.db_set({"status": "handed_off", "handoff_doctype": "ToDo", "handoff_name": "TODO-X"})
		comm = frappe._dict(
			sent_or_received="Sent", reference_doctype="ToDo", reference_name="TODO-X", content="<p>On it</p>"
		)
		with patch.object(reply_api, "deliver_reply", return_value={"status": "sent"}) as send:
			handoff_hooks.communication_after_insert(comm)
		self.assertEqual(send.call_args.kwargs["text"], "On it")
		with patch.object(reply_api, "deliver_reply", return_value={"status": "needs_template", "needs_template": True}), patch.object(
			handoff_hooks, "_comment"
		) as note:
			handoff_hooks.communication_after_insert(comm)
		note.assert_called_once()
		received = frappe._dict(sent_or_received="Received", reference_doctype="ToDo", reference_name="TODO-X")
		with patch.object(reply_api, "deliver_reply") as send:
			handoff_hooks.communication_after_insert(received)
		send.assert_not_called()
