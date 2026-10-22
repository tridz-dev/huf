# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Unit tests for the WhatsApp management API (mock-based, no bench required)."""

import json
import unittest
from unittest.mock import MagicMock, patch

import frappe

if isinstance(frappe, MagicMock):
	# Keep decorated functions callable when frappe is the test stub.
	frappe.whitelist = lambda *args, **kwargs: (lambda fn: fn)
	frappe.PermissionError = PermissionError

from huf.ai.whatsapp import management as mgmt  # noqa: E402
from huf.ai.gateway_adapters import whatsapp_bridge as bridge  # noqa: E402
from huf.ai.gateway_adapters.whatsapp_bridge import BridgeError  # noqa: E402

TOKEN_SECRET = "EAAG-very-secret-token"


def _cred(key: str, value: str) -> MagicMock:
	row = MagicMock(key=key)
	row.get_password.return_value = value
	return row


class TestWhatsAppManagement(unittest.TestCase):
	def setUp(self):
		frappe_patcher = patch("huf.ai.whatsapp.management.frappe")
		self.frappe = frappe_patcher.start()
		self.addCleanup(frappe_patcher.stop)
		self.frappe.PermissionError = PermissionError
		self.frappe.db.exists.return_value = True
		self.frappe.db.get_value.return_value = "ACC-1"
		self.frappe.has_permission.return_value = True
		self.frappe.get_roles.return_value = ["System Manager"]
		self.opted_out = patch.object(mgmt, "_opted_out", return_value=False).start()
		self.addCleanup(patch.stopall)

		available = patch.object(bridge, "is_available", return_value=True)
		available.start()
		self.addCleanup(available.stop)

		self.resolve = patch.object(
			bridge,
			"resolve_account",
			return_value={"name": "ACC-1", "phone_id": "111", "status": "Active"},
		)
		self.resolve.start()
		self.addCleanup(self.resolve.stop)

	# --- window policy -------------------------------------------------

	def test_send_text_refused_when_window_closed(self):
		with (
			patch.object(bridge, "window_state", return_value={"open": False, "expires_at": None}) as window,
			patch.object(bridge, "send_text") as send_text,
		):
			result = mgmt.send_text_message(gateway_name="GW-1", to="+44 7700 900123", text="hello")

		self.assertFalse(result["success"])
		self.assertEqual(result["error"], "window_closed")
		self.assertIn("send_template_message", result["hint"])
		window.assert_called_once_with("GW-1", "447700900123")
		send_text.assert_not_called()

	def test_send_text_sends_when_window_open(self):
		with (
			patch.object(bridge, "window_state", return_value={"open": True}),
			patch.object(bridge, "send_text", return_value={"success": True, "name": "WM-1"}) as send_text,
		):
			result = mgmt.send_text_message(gateway_name="GW-1", to="+44 7700 900123", text="hello")

		self.assertTrue(result["success"])
		send_text.assert_called_once_with("ACC-1", "447700900123", "hello")

	def test_send_text_rejects_empty_recipient_before_bridge(self):
		with patch.object(bridge, "window_state") as window:
			result = mgmt.send_text_message(gateway_name="GW-1", to="  ", text="hello")

		self.assertEqual(result["error"], "invalid_recipient")
		window.assert_not_called()

	# --- bridge passthrough --------------------------------------------

	def test_bridge_unavailable_passthrough_for_messages(self):
		with patch.object(bridge, "is_available", return_value=False):
			self.assertEqual(mgmt.list_messages(), {"success": False, "error": "bridge_unavailable"})
			self.assertEqual(mgmt.list_conversations(), {"success": False, "error": "bridge_unavailable"})
			self.assertEqual(
				mgmt.send_template_message(gateway_name="GW-1", to="447700900123", template_name="welcome"),
				{"success": False, "error": "bridge_unavailable"},
			)

	def test_bridge_error_is_converted_to_error_dict(self):
		with patch.object(bridge, "send_template", side_effect=BridgeError({"error": "send_failed", "message": "boom"})):
			result = mgmt.send_template_message(gateway_name="GW-1", to="447700900123", template_name="welcome")

		self.assertFalse(result["success"])
		self.assertEqual(result["error"], "send_failed")
		self.assertEqual(result["message"], "boom")

	def test_send_template_validates_template_name(self):
		with patch.object(bridge, "send_template") as send_template:
			result = mgmt.send_template_message(gateway_name="GW-1", to="447700900123", template_name="Bad Name!")

		self.assertEqual(result["error"], "invalid_name")
		send_template.assert_not_called()

	def test_send_template_accepts_record_name_and_bare_name(self):
		for name in ("invalid_wash_day-en", "huf_wait_test_x-en_US", "welcome"):
			with patch.object(bridge, "send_template", return_value={"success": True}) as send_template:
				result = mgmt.send_template_message(gateway_name="GW-1", to="447700900123", template_name=name)
			self.assertNotEqual(result.get("error"), "invalid_name", name)
			self.assertEqual(send_template.call_args.args[2], name)

	def test_send_template_surfaces_language_required(self):
		err = BridgeError({"success": False, "error": "language_required", "languages": ["en", "hi"]})
		with patch.object(bridge, "send_template", side_effect=err):
			result = mgmt.send_template_message(gateway_name="GW-1", to="447700900123", template_name="wash")
		self.assertEqual(result["error"], "language_required")
		self.assertEqual(result["languages"], ["en", "hi"])

	def test_create_template_rejects_bad_name_without_bridge_call(self):
		with patch.object(bridge, "create_template") as create:
			result = mgmt.create_template(payload={"template_name": "Hello-World", "category": "UTILITY"})

		self.assertEqual(result["error"], "invalid_name")
		create.assert_not_called()

	def test_delete_template_requires_name(self):
		with patch.object(bridge, "delete_template") as delete:
			result = mgmt.delete_template(name="")

		self.assertEqual(result["error"], "invalid_name")
		delete.assert_not_called()

	# --- setup status ----------------------------------------------------

	def test_setup_status_flags_missing_app_secret_without_leaking_values(self):
		self.frappe.utils.get_url.return_value = "https://huf.example.com"
		self.frappe.get_all.side_effect = lambda doctype, **kwargs: (
			[{"name": "GW-1", "is_enabled": 1, "integration_settings": "IS-1"}]
			if doctype == "Gateway"
			else [{"name": "ACC-1", "phone_id": "111", "status": "Active"}]
		)
		settings = MagicMock(
			credentials=[
				_cred("app_secret", ""),
				_cred("webhook_verify_token", "verify-me"),
			]
		)
		self.frappe.get_doc.return_value = settings

		result = mgmt.get_setup_status("GW-1")

		self.assertTrue(result["success"])
		self.assertTrue(result["connector_available"])
		self.assertEqual(result["accounts"], [{"name": "ACC-1", "phone_id": "111", "status": "Active"}])
		gateway = result["gateway"]
		self.assertFalse(gateway["app_secret_present"])
		self.assertIn("app_secret_missing", [r["code"] for r in gateway["reasons"]])
		self.assertTrue(gateway["verify_token_present"])
		self.assertEqual(
			gateway["webhook_url"],
			"https://huf.example.com/api/method/huf.ai.gateway_webhook.handle_gateway_webhook?gateway_name=GW-1",
		)
		self.assertNotIn("verify-me", json.dumps(result))

	def _status_with_phones(self, account_phone, credential_phone, linked=True):
		self.frappe.utils.get_url.return_value = "https://huf.example.com"
		self.frappe.get_all.side_effect = lambda doctype, **kwargs: (
			[{"name": "GW-1", "is_enabled": 1, "integration_settings": "IS-1"}] if doctype == "Gateway" else []
		)
		self.frappe.db.get_value.side_effect = lambda doctype, name, field=None, *a, **k: (
			("ACC-1" if linked else None) if doctype == "Gateway" else account_phone
		)
		self.frappe.get_doc.return_value = MagicMock(
			credentials=[
				_cred("app_secret", "x"),
				_cred("webhook_verify_token", "y"),
				_cred("phone_number_id", credential_phone),
			]
		)
		return mgmt.get_setup_status("GW-1")["gateway"]

	def test_setup_status_flags_account_phone_mismatch(self):
		gateway = self._status_with_phones("111", "222")
		self.assertTrue(gateway["account_phone_mismatch"])
		self.assertIn("account_phone_mismatch", [r["code"] for r in gateway["reasons"]])

	def test_setup_status_no_mismatch_when_phones_match_or_unlinked(self):
		for gateway in (self._status_with_phones("111", "111"), self._status_with_phones("111", "222", linked=False)):
			self.assertFalse(gateway["account_phone_mismatch"])
			self.assertNotIn("account_phone_mismatch", [r["code"] for r in gateway["reasons"]])

	def test_setup_status_requires_admin_role(self):
		self.frappe.get_roles.return_value = ["Guest"]

		with self.assertRaises(PermissionError):
			mgmt.get_setup_status()

	def test_setup_status_without_bridge_reports_no_accounts(self):
		self.frappe.get_all.side_effect = lambda doctype, **kwargs: (
			[{"name": "GW-1", "is_enabled": 1, "integration_settings": "IS-1"}]
			if doctype == "Gateway"
			else [{"name": "ACC-1", "phone_id": "111", "status": "Active"}]
		)
		with patch.object(bridge, "is_available", return_value=False):
			result = mgmt.get_setup_status("GW-1")

		self.assertFalse(result["connector_available"])
		self.assertEqual(result["accounts"], [])

	def test_mutating_calls_never_use_ignore_permissions(self):
		with (
			patch.object(bridge, "window_state", return_value={"open": True}),
			patch.object(bridge, "send_text", return_value={"success": True}),
		):
			mgmt.send_text_message(gateway_name="GW-1", to="447700900123", text="hi")
		for call in self.frappe.mock_calls:
			self.assertNotIn("ignore_permissions", call.kwargs)
		self.frappe.set_user.assert_not_called()

	def test_permission_denied_propagates_not_converted(self):
		self.frappe.has_permission.return_value = False

		with self.assertRaises(PermissionError):
			mgmt.list_messages(gateway_name="GW-1")


class TestWhatsAppManagementAuthority(unittest.TestCase):
	"""Roles, Gateway authority and account isolation of the management API (mock-based)."""

	def setUp(self):
		patcher = patch("huf.ai.whatsapp.management.frappe")
		self.frappe = patcher.start()
		self.addCleanup(patcher.stop)
		self.frappe.PermissionError = PermissionError
		self.frappe.db.exists.return_value = True
		self.accounts = {"GW-A": "ACC-A", "GW-B": "ACC-B", "GW-NONE": ""}
		self.frappe.db.get_value.side_effect = lambda doctype, name, field=None, *a, **k: (
			self.accounts.get(name) if doctype == "Gateway" else None
		)
		self.roles = ["Desk User"]
		self.frappe.get_roles.side_effect = lambda: list(self.roles)
		self.frappe.session.user = "plain@example.com"
		self.opted_out = patch.object(mgmt, "_opted_out", return_value=False).start()
		self.addCleanup(patch.stopall)
		self.gateway_perms = {"read": True, "write": False}
		self.doctype_perms = {"WhatsApp Message": True, "WhatsApp Templates": True}
		self.draft_create = False

		def has_permission(doctype, ptype="read", doc=None, **kwargs):
			if doctype == "Gateway":
				return self.gateway_perms.get(ptype, False)
			if doctype == bridge.DRAFT_DOCTYPE:
				return ptype == "read" or self.draft_create
			return self.doctype_perms.get(doctype, False)

		self.frappe.has_permission.side_effect = has_permission
		self.frappe.get_list.return_value = ["GW-A"]
		for target, kwargs in (
			(bridge, {"name": "is_available", "return_value": True}),
			(bridge, {"name": "resolve_account", "side_effect": lambda n=None: {"name": n, "phone_id": "1"} if n else {"error": "no_account"}}),
		):
			name = kwargs.pop("name")
			p = patch.object(target, name, **kwargs)
			p.start()
			self.addCleanup(p.stop)
		caps = patch("huf.permissions.has_capability", return_value=False)
		self.has_capability = caps.start()
		self.addCleanup(caps.stop)

	# --- template management is admin-only -------------------------------

	def test_plain_desk_user_cannot_manage_templates(self):
		payload = json.dumps({"template_name": "hello", "category": "UTILITY", "language_code": "en_US", "body": "x"})
		calls = (
			lambda: mgmt.create_template(account="ACC-A", payload=payload),
			lambda: mgmt.edit_template(name="hello-en_US", payload=payload),
			lambda: mgmt.delete_template(name="hello-en_US"),
			lambda: mgmt.sync_templates(account="ACC-A"),
			lambda: mgmt.approve_template_draft(name="DRAFT-1"),
			lambda: mgmt.reject_template_draft(name="DRAFT-1"),
		)
		with (
			patch.object(bridge, "create_template") as create,
			patch.object(bridge, "edit_template") as edit,
			patch.object(bridge, "delete_template") as delete,
			patch.object(bridge, "sync_templates") as sync,
			patch.object(bridge, "approve_draft") as approve,
			patch.object(bridge, "reject_draft") as reject,
		):
			for call in calls:
				with self.assertRaises(PermissionError):
					call()
			for mock in (create, edit, delete, sync, approve, reject):
				mock.assert_not_called()

	def test_admin_roles_may_manage_templates(self):
		payload = json.dumps({"template_name": "hello", "category": "UTILITY", "language_code": "en_US", "body": "x"})
		for role in ("System Manager", "Huf Admin"):
			self.roles = [role]
			with patch.object(bridge, "create_template", return_value={"success": True}) as create:
				self.assertTrue(mgmt.create_template(account="ACC-A", payload=payload)["success"])
			create.assert_called_once()
			self.assertEqual(create.call_args.args[0], "ACC-A")
			with patch.object(bridge, "sync_templates", return_value={"success": True}) as sync:
				self.assertTrue(mgmt.sync_templates(gateway_name="GW-A")["success"])
			sync.assert_called_once_with("ACC-A")

	def test_template_management_has_no_default_account(self):
		self.roles = ["System Manager"]
		payload = json.dumps({"template_name": "hello", "category": "UTILITY", "language_code": "en_US", "body": "x"})
		with patch.object(bridge, "create_template") as create, patch.object(bridge, "sync_templates") as sync:
			self.assertEqual(mgmt.create_template(payload=payload)["error"], "gateway_required")
			self.assertEqual(mgmt.sync_templates()["error"], "gateway_required")
		create.assert_not_called()
		sync.assert_not_called()

	def test_draft_request_path_needs_create_permission_or_admin(self):
		payload = json.dumps({"template_name": "hello", "category": "UTILITY", "language_code": "en_US", "body": "x"})
		with patch.object(bridge, "create_draft", return_value={"success": True, "name": "D-1"}) as create:
			with self.assertRaises(PermissionError):
				mgmt.create_template_draft(account="ACC-A", payload=payload)
			create.assert_not_called()
			self.draft_create = True  # the non-admin request path
			self.assertTrue(mgmt.create_template_draft(gateway_name="GW-A", payload=payload)["success"])
			self.assertEqual(create.call_args.kwargs["account"], "ACC-A")
			self.assertNotIn("trusted", create.call_args.kwargs)  # never ignore_permissions on a user path
			self.draft_create = False
			self.roles = ["Huf Admin"]
			self.assertTrue(mgmt.create_template_draft(account="ACC-A", payload=payload)["success"])

	def test_draft_request_without_account_is_refused(self):
		self.draft_create = True
		payload = json.dumps({"template_name": "hello", "category": "UTILITY", "language_code": "en_US", "body": "x"})
		with patch.object(bridge, "create_draft") as create:
			self.assertEqual(mgmt.create_template_draft(payload=payload)["error"], "gateway_required")
		create.assert_not_called()

	# --- sending needs WRITE authority on the gateway ---------------------

	def test_sends_require_gateway_name(self):
		self.gateway_perms["write"] = True
		with patch.object(bridge, "send_template") as send_template:
			result = mgmt.send_template_message(to="447700900123", template_name="welcome")
		self.assertEqual(result["error"], "invalid_gateway")
		send_template.assert_not_called()
		self.assertEqual(mgmt.send_text_message(to="447700900123", text="x")["error"], "invalid_gateway")
		self.assertEqual(mgmt.send_media_message(to="447700900123", kind="image", link="https://a/b.png")["error"], "invalid_gateway")

	def test_read_only_gateway_access_cannot_send(self):
		self.gateway_perms.update(read=True, write=False)
		with (
			patch.object(bridge, "window_state", return_value={"open": True}),
			patch.object(bridge, "send_text") as send_text,
			patch.object(bridge, "send_media") as send_media,
			patch.object(bridge, "send_template") as send_template,
		):
			with self.assertRaises(PermissionError):
				mgmt.send_text_message(gateway_name="GW-A", to="447700900123", text="hi")
			with self.assertRaises(PermissionError):
				mgmt.send_media_message(gateway_name="GW-A", to="447700900123", kind="image", link="https://a/b.png")
			with self.assertRaises(PermissionError):
				mgmt.send_template_message(gateway_name="GW-A", to="447700900123", template_name="welcome")
		for mock in (send_text, send_media, send_template):
			mock.assert_not_called()

	def test_gateway_writer_sends_from_the_gateways_own_account(self):
		self.gateway_perms["write"] = True
		with (
			patch.object(bridge, "window_state", return_value={"open": True}),
			patch.object(bridge, "send_text", return_value={"success": True}) as send_text,
			patch.object(bridge, "send_media", return_value={"success": True}) as send_media,
			patch.object(bridge, "send_template", return_value={"success": True}) as send_template,
		):
			mgmt.send_text_message(gateway_name="GW-B", to="447700900123", text="hi")
			mgmt.send_media_message(gateway_name="GW-B", to="447700900123", kind="image", link="https://a/b.png")
			mgmt.send_template_message(gateway_name="GW-B", to="447700900123", template_name="welcome")
		self.assertEqual(send_text.call_args.args[0], "ACC-B")
		self.assertEqual(send_media.call_args.args[0], "ACC-B")
		self.assertEqual(send_template.call_args.args[0], "ACC-B")

	def test_integrations_capability_grants_send_without_gateway_doc_write(self):
		self.has_capability.return_value = True
		with patch.object(bridge, "send_template", return_value={"success": True}) as send_template:
			self.assertTrue(
				mgmt.send_template_message(gateway_name="GW-A", to="447700900123", template_name="welcome")["success"]
			)
		self.assertEqual(send_template.call_args.args[0], "ACC-A")

	def test_text_and_media_enforce_the_24h_window_but_templates_do_not(self):
		self.gateway_perms["write"] = True
		with (
			patch.object(bridge, "window_state", return_value={"open": False, "expires_at": None}),
			patch.object(bridge, "send_text") as send_text,
			patch.object(bridge, "send_media") as send_media,
			patch.object(bridge, "send_template", return_value={"success": True}) as send_template,
		):
			self.assertEqual(mgmt.send_text_message(gateway_name="GW-A", to="447700900123", text="x")["error"], "window_closed")
			self.assertEqual(
				mgmt.send_media_message(gateway_name="GW-A", to="447700900123", kind="image", link="https://a/b.png")["error"],
				"window_closed",
			)
			self.assertTrue(mgmt.send_template_message(gateway_name="GW-A", to="447700900123", template_name="w")["success"])
		send_text.assert_not_called()
		send_media.assert_not_called()
		send_template.assert_called_once()

	def test_gateway_without_account_cannot_send(self):
		self.gateway_perms["write"] = True
		with patch.object(bridge, "send_template") as send_template:
			result = mgmt.send_template_message(gateway_name="GW-NONE", to="447700900123", template_name="w")
		self.assertEqual(result["error"], "no_account")  # no default-account guess
		send_template.assert_not_called()

	def test_send_template_has_no_account_parameter(self):
		with self.assertRaises(TypeError):
			mgmt.send_template_message(gateway_name="GW-A", to="447700900123", template_name="w", account="ACC-B")

	# --- no cross-account listing ----------------------------------------

	def test_lists_require_a_gateway_or_a_permitted_account(self):
		with (
			patch.object(bridge, "list_messages") as lm,
			patch.object(bridge, "list_conversations") as lc,
			patch.object(bridge, "list_templates") as lt,
			patch.object(bridge, "list_drafts") as ld,
		):
			for result in (
				mgmt.list_messages(),
				mgmt.list_conversations(),
				mgmt.list_templates(),
				mgmt.list_template_drafts(),
			):
				self.assertEqual(result["success"], False)
				self.assertEqual(result["error"], "gateway_required")
		for mock in (lm, lc, lt, ld):
			mock.assert_not_called()

	def test_gateway_list_is_scoped_to_its_account(self):
		with (
			patch.object(bridge, "list_messages", return_value={"success": True, "messages": []}) as lm,
			patch.object(bridge, "list_conversations", return_value={"success": True, "conversations": []}) as lc,
			patch.object(bridge, "list_templates", return_value=[]) as lt,
			patch.object(bridge, "list_drafts", return_value=[]) as ld,
		):
			mgmt.list_messages(gateway_name="GW-B", phone="447700900123")
			mgmt.list_conversations(gateway_name="GW-B")
			mgmt.list_templates(gateway_name="GW-B")
			mgmt.list_template_drafts(gateway_name="GW-B")
		self.assertEqual(lm.call_args.args[0], "ACC-B")
		self.assertEqual(lc.call_args.args[0], "ACC-B")
		self.assertEqual(lt.call_args.args[0], "ACC-B")
		self.assertEqual(ld.call_args.kwargs["account"], "ACC-B")

	def test_non_admin_sees_only_accounts_of_gateways_they_can_read(self):
		self.frappe.get_list.return_value = []  # no readable gateway uses ACC-B
		with patch.object(bridge, "list_messages") as lm:
			with self.assertRaises(PermissionError):
				mgmt.list_messages(account="ACC-B")
		lm.assert_not_called()
		self.gateway_perms["read"] = False
		self.frappe.get_list.return_value = ["GW-A"]
		with patch.object(bridge, "list_messages") as lm:
			with self.assertRaises(PermissionError):
				mgmt.list_messages(gateway_name="GW-A")
			with self.assertRaises(PermissionError):
				mgmt.list_messages(account="ACC-A")
		lm.assert_not_called()

	def test_non_admin_with_a_readable_gateway_may_pass_its_account(self):
		self.frappe.get_list.return_value = ["GW-A"]
		with patch.object(bridge, "list_messages", return_value={"success": True, "messages": []}) as lm:
			self.assertTrue(mgmt.list_messages(account="ACC-A")["success"])
		self.assertEqual(lm.call_args.args[0], "ACC-A")

	def test_admin_may_pass_any_account_and_a_mismatched_account_is_refused(self):
		self.roles = ["Huf Admin"]
		with patch.object(bridge, "list_messages", return_value={"success": True, "messages": []}) as lm:
			self.assertTrue(mgmt.list_messages(account="ACC-Z")["success"])
			self.assertEqual(
				mgmt.list_messages(gateway_name="GW-A", account="ACC-B")["error"], "account_mismatch"
			)
		self.assertEqual(lm.call_count, 1)

	def test_template_detail_of_an_unreadable_account_is_refused(self):
		self.frappe.get_list.return_value = []
		with patch.object(bridge, "get_template", return_value={"success": True, "whatsapp_account": "ACC-B"}):
			with self.assertRaises(PermissionError):
				mgmt.get_template(name="hello-en_US")


class TestOutboundTypeEndpoints(unittest.TestCase):
	"""Every non-text send endpoint: authority, validation, opt-out, 24h window and the Gateway's own account."""

	def setUp(self):
		patcher = patch("huf.ai.whatsapp.management.frappe")
		self.frappe = patcher.start()
		self.addCleanup(patcher.stop)
		self.frappe.PermissionError = PermissionError
		self.frappe.db.exists.return_value = True
		self.frappe.db.get_value.side_effect = lambda doctype, name, field=None, *a, **k: "ACC-A" if doctype == "Gateway" else None
		self.roles = ["Desk User"]
		self.frappe.get_roles.side_effect = lambda: list(self.roles)
		self.write = True
		self.frappe.has_permission.side_effect = lambda doctype, ptype="read", doc=None, **kw: (
			self.write if doctype == "Gateway" and ptype == "write" else doctype == "Gateway"
		)
		self.opted_out = patch.object(mgmt, "_opted_out", return_value=False).start()
		self.window = patch.object(bridge, "window_state", return_value={"open": True}).start()
		patch.object(bridge, "is_available", return_value=True).start()
		patch.object(bridge, "resolve_account", side_effect=lambda n=None: {"name": n, "phone_id": "1"}).start()
		patch("huf.permissions.has_capability", return_value=False).start()
		self.addCleanup(patch.stopall)
		self.contact = {"name": {"formatted_name": "Ann"}, "phones": [{"phone": "+15551230000"}]}
		# endpoint -> (bridge function, kwargs of a valid call)
		self.cases = {
			"send_location_message": ("send_location", {"latitude": 1.5, "longitude": 2.5, "name": "Pin"}),
			"send_contacts_message": ("send_contacts", {"contacts": [self.contact]}),
			"send_reaction_message": ("send_reaction", {"message_id": "wamid.IN", "emoji": "\U0001F44D"}),
			"send_sticker_message": ("send_media", {"media_id": "77"}),
			"send_interactive_message": ("send_interactive", {"kind": "buttons", "body": "Pick", "buttons": json.dumps([{"id": "a", "title": "A"}])}),
			"send_media_message": ("send_media", {"kind": "image", "link": "https://a/b.png"}),
		}

	def call(self, endpoint, **kw):
		args = {"gateway_name": "GW-A", "to": "+44 7700 900123", **self.cases[endpoint][1], **kw}
		return getattr(mgmt, endpoint)(**args)

	def test_each_endpoint_sends_from_the_gateway_account_when_window_open(self):
		for endpoint, (fn, _kwargs) in self.cases.items():
			with patch.object(bridge, fn, return_value={"success": True, "message_id": "wamid.OUT"}) as sent:
				result = self.call(endpoint)
			self.assertTrue(result["success"], (endpoint, result))
			self.assertEqual(sent.call_args.args[:2], ("ACC-A", "447700900123"), endpoint)
			self.window.assert_called_with("GW-A", "447700900123")

	def test_write_authority_is_required(self):
		self.write = False
		for endpoint, (fn, _kwargs) in self.cases.items():
			with patch.object(bridge, fn) as sent:
				with self.assertRaises(PermissionError, msg=endpoint):
					self.call(endpoint)
			sent.assert_not_called()

	def test_gateway_name_is_required(self):
		for endpoint in self.cases:
			self.assertEqual(self.call(endpoint, gateway_name=None)["error"], "invalid_gateway", endpoint)
		self.frappe.db.exists.return_value = False
		self.assertEqual(self.call("send_location_message")["error"], "not_found")

	def test_window_closed_refuses_before_sending(self):
		self.window.return_value = {"open": False, "expires_at": None}
		for endpoint, (fn, _kwargs) in self.cases.items():
			with patch.object(bridge, fn) as sent:
				result = self.call(endpoint)
			self.assertEqual(result["error"], "window_closed", endpoint)
			self.assertIn("send_template_message", result["hint"])
			sent.assert_not_called()

	def test_opted_out_contact_is_refused_before_the_window_check(self):
		self.opted_out.return_value = True
		self.window.reset_mock()
		for endpoint, (fn, _kwargs) in self.cases.items():
			with patch.object(bridge, fn) as sent:
				result = self.call(endpoint)
			self.assertEqual(result["error"], "opted_out", endpoint)
			sent.assert_not_called()
		self.window.assert_not_called()

	def test_validation_errors_come_back_structured_without_sending(self):
		bad = {
			"send_location_message": {"latitude": 91},
			"send_contacts_message": {"contacts": [{"name": {}}]},
			"send_reaction_message": {"emoji": "no"},
			"send_sticker_message": {"media_id": "", "link": ""},
			"send_interactive_message": {"buttons": json.dumps([{"id": str(i), "title": str(i)} for i in range(4)])},
			"send_media_message": {"kind": "gif"},
		}
		for endpoint, override in bad.items():
			with patch.object(bridge, self.cases[endpoint][0]) as sent:
				result = self.call(endpoint, **override)
			self.assertEqual((result["success"], result["error"]), (False, "validation_failed"), (endpoint, result))
			self.assertTrue(result["errors"])
			sent.assert_not_called()
		self.window.assert_not_called()  # validation runs before the window check

	def test_invalid_json_arguments(self):
		self.assertEqual(self.call("send_contacts_message", contacts="{nope")["error"], "invalid_params")
		self.assertEqual(self.call("send_interactive_message", buttons="[oops")["error"], "invalid_params")

	def test_interactive_kinds_and_flow_gate(self):
		with patch.object(bridge, "send_interactive", return_value={"success": True}) as sent:
			ok = mgmt.send_interactive_message(
				gateway_name="GW-A", to="447700900123", kind="cta_url", body="See", display_text="Open", url="https://a.example",
			)
			lst = mgmt.send_interactive_message(
				gateway_name="GW-A", to="447700900123", kind="list", body="Menu", button_text="Open",
				sections=json.dumps([{"title": "S", "rows": [{"id": "1", "title": "One"}]}]), header="Hdr",
			)
			flow = mgmt.send_interactive_message(gateway_name="GW-A", to="447700900123", kind="flow", body="Go", flow_cta="Start")
		self.assertTrue(ok["success"] and lst["success"])
		self.assertEqual(flow["error"], "validation_failed")
		self.assertIn("flow_id_required", [e["code"] for e in flow["errors"]])
		self.assertEqual(sent.call_count, 2)
		self.assertEqual(sent.call_args_list[0].args[2], "cta_url")

	def test_reaction_remove(self):
		with patch.object(bridge, "send_reaction", return_value={"success": True}) as sent:
			result = mgmt.send_reaction_message(gateway_name="GW-A", to="447700900123", message_id="wamid.IN", remove=True)
		self.assertTrue(result["success"])
		self.assertTrue(sent.call_args.kwargs["remove"])

	def test_media_id_and_voice_are_passed_through(self):
		with patch.object(bridge, "send_media", return_value={"success": True}) as sent:
			mgmt.send_media_message(gateway_name="GW-A", to="447700900123", kind="audio", media_id="9", voice=True)
		self.assertEqual((sent.call_args.kwargs["media_id"], sent.call_args.kwargs["voice"]), ("9", True))

	def test_private_file_is_uploaded_after_the_gates_and_sent_by_id(self):
		file_doc = MagicMock(file_name="doc.pdf")
		file_doc.get_content.return_value = b"%PDF"
		self.frappe.get_doc.return_value = file_doc
		self.frappe.db.get_value.side_effect = lambda doctype, name, field=None, *a, **k: "ACC-A" if doctype == "Gateway" else "FILE-1"
		self.frappe.has_permission.side_effect = lambda doctype, ptype="read", doc=None, **kw: True
		with (
			patch.object(bridge, "upload_media", return_value={"success": True, "media_id": "MID1"}) as up,
			patch.object(bridge, "send_media", return_value={"success": True}) as sent,
		):
			result = mgmt.send_media_message(gateway_name="GW-A", to="447700900123", kind="document", file_url="/private/files/doc.pdf")
			self.assertTrue(result["success"], result)
			self.assertEqual(up.call_args.args[:4], ("ACC-A", b"%PDF", "application/pdf", "doc.pdf"))
			self.assertEqual((sent.call_args.kwargs["media_id"], sent.call_args.kwargs["filename"]), ("MID1", "doc.pdf"))
			self.window.return_value = {"open": False}
			up.reset_mock()
			self.assertEqual(mgmt.send_media_message(gateway_name="GW-A", to="447700900123", kind="document", file_url="/private/files/doc.pdf")["error"], "window_closed")
			up.assert_not_called()  # nothing is uploaded to Meta when the send would be refused

	def test_upload_media_file_endpoint(self):
		file_doc = MagicMock(file_name="s.webp")
		file_doc.get_content.return_value = b"RIFF"
		self.frappe.get_doc.return_value = file_doc
		self.frappe.db.get_value.side_effect = lambda doctype, name, field=None, *a, **k: "ACC-A" if doctype == "Gateway" else "FILE-1"
		self.frappe.has_permission.side_effect = lambda doctype, ptype="read", doc=None, **kw: True
		with patch.object(bridge, "upload_media", return_value={"success": True, "media_id": "M2"}) as up:
			result = mgmt.upload_media_file(gateway_name="GW-A", file_url="/private/files/s.webp", kind="sticker")
		self.assertEqual(result["media_id"], "M2")
		self.assertEqual(up.call_args.kwargs["kind"], "sticker")
		self.write = False
		self.frappe.has_permission.side_effect = lambda doctype, ptype="read", doc=None, **kw: doctype != "Gateway"
		with self.assertRaises(PermissionError):
			mgmt.upload_media_file(gateway_name="GW-A", file_url="/private/files/s.webp")

	def test_bridge_unavailable(self):
		with patch.object(bridge, "is_available", return_value=False):
			for endpoint in self.cases:
				self.assertEqual(self.call(endpoint), {"success": False, "error": "bridge_unavailable"}, endpoint)

	def test_bridge_error_is_converted(self):
		with patch.object(bridge, "send_location", side_effect=BridgeError({"error": "send_failed", "message": "boom", "kind": "rate_limit"})):
			result = self.call("send_location_message")
		self.assertEqual((result["success"], result["error"], result["kind"]), (False, "send_failed", "rate_limit"))


if __name__ == "__main__":
	unittest.main()
