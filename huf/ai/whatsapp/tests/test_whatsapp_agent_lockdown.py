# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""WP-1: the WhatsApp agent tool is bound to the current run's gateway and fails closed."""

from __future__ import annotations

import json
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe

from huf.ai.gateway_adapters import whatsapp_bridge as bridge
from huf.ai.tools import _registry, whatsapp


def _tool_schema() -> dict:
	tool = next(t for t in _registry.WHATSAPP_TOOLS if t["tool_name"] == "whatsapp")
	return tool


class TestSchemaSnapshot(unittest.TestCase):
	def test_model_cannot_see_gateway_or_account(self):
		names = {p["name"] if isinstance(p, dict) and "name" in p else p.get("fieldname") for p in _tool_schema()["parameters"]}
		self.assertNotIn("gateway_name", names)
		self.assertNotIn("whatsapp_account", names)
		self.assertIn("cursor", names)
		self.assertNotIn("gateway_name", json.dumps(_tool_schema()["parameters"]))


class TestRunGatewayBinding(unittest.TestCase):
	def tearDown(self):
		patch.stopall()

	def test_no_run_context_fails_closed_for_every_action(self):
		with patch.object(whatsapp, "_run_gateway", return_value=""), patch.object(whatsapp.requests, "post") as post:
			for action in ("send_message", "send_template", "list_messages", "get_account_info", "list_templates"):
				result = json.loads(whatsapp.handle_action(action, to="15551234567", message="x", template_name="t"))
				self.assertEqual(result["error"], "gateway_context_required", action)
			post.assert_not_called()

	def test_forged_gateway_and_account_are_discarded(self):
		seen = {}

		def fake_send(kwargs):
			seen.update(kwargs)
			return "{}"

		def fake_idempotent_send(action, kwargs, gateway_name):
			# The durable send-key claim inserts a row linked to the Gateway; "GW-OWN" is not a real
			# Gateway, so run the dispatch step directly and keep the test about argument binding.
			return fake_send(kwargs)

		with patch.object(whatsapp, "_run_gateway", return_value="GW-OWN"), patch.object(
			whatsapp, "_authorize", return_value=None
		), patch.object(whatsapp, "_scope_refusal", return_value=None), patch.object(
			whatsapp, "_idempotent_send", side_effect=fake_idempotent_send
		):
			whatsapp.handle_action("send_message", to="1", message="x", gateway_name="GW-OTHER", whatsapp_account="WA-OTHER")
		self.assertEqual(seen["gateway_name"], "GW-OWN")
		self.assertNotIn("whatsapp_account", seen)

	def test_tool_cannot_reach_another_gateway_credentials_or_account(self):
		with patch.object(whatsapp, "_gateway_account_name", side_effect=lambda g: f"WA-{g}") as name, patch.object(
			bridge, "is_available", return_value=True
		), patch.object(bridge, "resolve_account", side_effect=lambda a: {"name": a}):
			acct = whatsapp._resolve_bridge_account({"gateway_name": "GW-OWN", "whatsapp_account": "WA-OTHER"})
		self.assertEqual(acct["name"], "WA-GW-OWN")
		name.assert_called_once_with("GW-OWN")

	def test_no_gateway_has_no_credentials_and_no_account(self):
		self.assertEqual(whatsapp._get_whatsapp_credentials({}), ("", ""))
		with patch.object(bridge, "is_available", return_value=True), patch.object(
			bridge, "resolve_default_account"
		) as default:
			self.assertIsNone(whatsapp._resolve_bridge_account({}))
		default.assert_not_called()

	def test_run_gateway_comes_from_conversation_channel(self):
		def get_value(doctype, name, field=None, as_dict=False):
			if doctype == "Agent Run":
				return "CONV-1"
			if doctype == "Agent Conversation":
				return "gateway:GW-A"
			return {"provider": "WhatsApp", "is_enabled": 1}

		with patch.object(whatsapp.frappe, "flags", SimpleNamespace(huf_current_agent_run_id="RUN-1")), patch.object(
			whatsapp.frappe.db, "get_value", side_effect=get_value
		):
			self.assertEqual(whatsapp._run_gateway(), "GW-A")

	def test_chat_run_and_disabled_gateway_are_unbound(self):
		with patch.object(whatsapp.frappe, "flags", SimpleNamespace(huf_current_agent_run_id="RUN-1")), patch.object(
			whatsapp.frappe.db, "get_value", side_effect=lambda d, n, f=None, as_dict=False: "CONV" if d == "Agent Run" else "chat:x"
		):
			self.assertEqual(whatsapp._run_gateway(), "")
		with patch.object(whatsapp.frappe, "flags", SimpleNamespace(huf_current_agent_run_id=None)):
			self.assertEqual(whatsapp._run_gateway(), "")

		def disabled(doctype, name, field=None, as_dict=False):
			if doctype == "Agent Run":
				return "C"
			if doctype == "Agent Conversation":
				return "gateway:GW-A"
			return {"provider": "WhatsApp", "is_enabled": 0}

		with patch.object(whatsapp.frappe, "flags", SimpleNamespace(huf_current_agent_run_id="RUN-1")), patch.object(
			whatsapp.frappe.db, "get_value", side_effect=disabled
		):
			self.assertEqual(whatsapp._run_gateway(), "")


class TestTrustedGateway(unittest.TestCase):
	def test_trusted_binding_wins_only_inside_the_block(self):
		with patch.object(whatsapp.frappe.db, "get_value", return_value={"provider": "WhatsApp", "is_enabled": 1}):
			with whatsapp.trusted_gateway("GW-F"):
				self.assertEqual(whatsapp._run_gateway(), "GW-F")
			self.assertEqual(whatsapp._run_gateway(), "")

	def test_trusted_binding_to_a_disabled_gateway_fails_closed(self):
		with patch.object(whatsapp.frappe.db, "get_value", return_value={"provider": "WhatsApp", "is_enabled": 0}):
			with whatsapp.trusted_gateway("GW-F"):
				self.assertEqual(whatsapp._run_gateway(), "")

	def test_model_args_cannot_bind_the_trusted_gateway(self):
		with patch.object(whatsapp, "_authorize", return_value=None):
			result = json.loads(whatsapp.handle_action("send_message", to="1", message="x", gateway_name="GW", trusted_gateway="GW"))
		self.assertEqual(result["error"], "gateway_context_required")


class TestAuthority(unittest.TestCase):
	def tearDown(self):
		patch.stopall()

	def test_template_creation_without_write_authority_is_refused_before_any_send(self):
		with patch.object(whatsapp, "_run_gateway", return_value="GW"), patch(
			"huf.ai.whatsapp.management._send_authority", side_effect=frappe.PermissionError("no")
		), patch.object(whatsapp, "_create_template") as send:
			result = json.loads(whatsapp.handle_action("create_template", template_name="t"))
		self.assertEqual(result["error"], "permission_denied")
		send.assert_not_called()

	def test_trusted_draft_bypass_rechecks_authority(self):
		with patch("huf.ai.whatsapp.management._send_authority", side_effect=frappe.PermissionError("no")), patch.object(
			bridge, "create_draft"
		) as draft:
			result = json.loads(whatsapp._create_template_draft({"name": "WA"}, {}, "GW"))
		self.assertEqual(result["error"], "permission_denied")
		draft.assert_not_called()

	def test_reads_need_read_authority(self):
		with patch.object(whatsapp, "_run_gateway", return_value="GW"), patch(
			"huf.ai.whatsapp.management._gateway_read_allowed", return_value=False
		), patch.object(whatsapp, "_list_messages") as listing:
			result = json.loads(whatsapp.handle_action("list_messages", to="1"))
		self.assertEqual(result["error"], "permission_denied")
		listing.assert_not_called()


class TestPerGatewayFlags(unittest.TestCase):
	def test_flag_reads_the_named_gateway_only(self):
		with patch.object(whatsapp.frappe.db, "get_value", return_value=1) as get_value:
			self.assertTrue(whatsapp._server_flag("GW-A", "allow_proactive"))
		get_value.assert_called_once_with("Gateway", "GW-A", "agent_allow_proactive")

	def test_flag_fails_closed(self):
		self.assertFalse(whatsapp._server_flag("", "allow_proactive"))
		self.assertFalse(whatsapp._server_flag("GW", "unknown"))
		with patch.object(whatsapp.frappe.db, "get_value", side_effect=RuntimeError):
			self.assertFalse(whatsapp._server_flag("GW", "allow_proactive"))

	def test_management_flag_does_not_allow_proactive(self):
		def get_value(doctype, name, field):
			return 1 if field == "agent_allow_template_management" else 0

		with patch.object(whatsapp.frappe.db, "get_value", side_effect=get_value):
			self.assertFalse(whatsapp._server_flag("GW", "allow_proactive"))
			self.assertTrue(whatsapp._server_flag("GW", "allow_whatsapp_management"))

	def test_no_integration_settings_first_row_lookup_remains(self):
		import inspect

		self.assertNotIn("get_all", inspect.getsource(whatsapp))


class TestListMessages(unittest.TestCase):
	def tearDown(self):
		patch.stopall()

	def _call(self, **kwargs):
		page = {"success": True, "items": [{"message_id": "wamid.1"}], "next_cursor": "c2", "has_more": True}
		with patch.object(whatsapp, "_run_gateway", return_value="GW"), patch.object(
			whatsapp, "_authorize", return_value=None
		), patch("huf.ai.whatsapp.management.list_message_log", return_value=page) as log:
			return json.loads(whatsapp.handle_action("list_messages", **kwargs)), log

	def test_scoped_to_run_gateway_and_contact_with_wamid_and_cursor(self):
		result, log = self._call(to="+1 555 123 4567", cursor="c1", gateway_name="OTHER")
		kw = log.call_args.kwargs
		self.assertEqual((kw["gateway_name"], kw["phone"], kw["cursor"]), ("GW", "15551234567", "c1"))
		self.assertEqual(result["data"]["items"][0]["message_id"], "wamid.1")
		self.assertEqual(result["data"]["next_cursor"], "c2")

	def test_contact_is_required(self):
		result, log = self._call()
		self.assertEqual(result["error"], "contact_required")
		log.assert_not_called()

	def test_limit_is_clamped_and_never_raises(self):
		for raw, expected in (("abc", 20), (None, 20), (0, 1), (-5, 1), (10_000, 50), ("7", 7), ([], 20)):
			_, log = self._call(to="1", limit=raw)
			self.assertEqual(log.call_args.kwargs["limit"], expected, raw)

	def test_get_account_info_uses_run_gateway_credentials(self):
		resp = SimpleNamespace(status_code=200, json=lambda: {"id": "PN"}, text="")
		with patch.object(whatsapp, "_run_gateway", return_value="GW"), patch.object(
			whatsapp, "_authorize", return_value=None
		), patch.object(whatsapp, "_gateway_integration_credentials", return_value=("PN", "tok")) as creds, patch.object(
			whatsapp.requests, "get", return_value=resp
		) as get:
			result = json.loads(whatsapp.handle_action("get_account_info", gateway_name="OTHER"))
		self.assertTrue(result["success"])
		creds.assert_called_once_with("GW")
		self.assertIn("/PN", get.call_args.args[0])


class TestGatewayValidation(unittest.TestCase):
	def setUp(self):
		# frappe.throw() translates its message. On a cold site cache the first translation load would
		# otherwise happen inside a test that has frappe.db.get_value/exists mocked, and it leaves the
		# shared Redis connection out of step for the rest of the process (later cache reads then
		# return the wrong replies). Warm it here, with the real db, before any mock is active.
		frappe._("warm translation cache")
		frappe.get_meta("Gateway")

	def _gw(self, **fields):
		from huf.huf.doctype.gateway.gateway import Gateway

		gw = Gateway.__new__(Gateway)
		base = {"provider": "WhatsApp", "is_enabled": 1, "name": "GW-B", "whatsapp_account": "WA-1",
			"whatsapp_business_account_id": "WABA-1"}
		base.update(fields)
		gw.__dict__.update(base)
		gw.get = lambda key, default=None: base.get(key, default)
		gw._load_integration_credentials = lambda: {"phone_number_id": base.get("phone", "PN1")}
		return gw

	def _db(self, other_phone=None, other_account=None, account_phone="PN1"):
		def get_value(doctype, filters, field=None, *a, **k):
			if doctype == "WhatsApp Account":
				return account_phone
			if isinstance(filters, dict) and "phone_number_id" in filters:
				return other_phone
			if isinstance(filters, dict) and "whatsapp_account" in filters:
				return other_account
			return None

		return patch.multiple(
			frappe.db, get_value=MagicMock(side_effect=get_value), exists=MagicMock(return_value=True)
		)

	def test_duplicate_enabled_phone_id_rejected(self):
		with self._db(other_phone="GW-A"), patch.object(bridge, "is_available", return_value=True):
			with self.assertRaises(frappe.ValidationError):
				self._gw()._validate_whatsapp()

	def test_account_phone_must_equal_gateway_phone(self):
		with self._db(account_phone="PN-OTHER"), patch.object(bridge, "is_available", return_value=True):
			with self.assertRaises(frappe.ValidationError):
				self._gw()._validate_whatsapp()

	def test_account_shared_with_another_enabled_gateway_rejected(self):
		with self._db(other_account="GW-A"), patch.object(bridge, "is_available", return_value=True):
			with self.assertRaises(frappe.ValidationError):
				self._gw()._validate_whatsapp()

	def test_account_without_gateway_phone_rejected(self):
		with self._db(), patch.object(bridge, "is_available", return_value=True):
			with self.assertRaises(frappe.ValidationError):
				self._gw(phone="")._validate_whatsapp()

	def test_matching_unique_account_passes(self):
		with self._db(), patch.object(bridge, "is_available", return_value=True):
			self._gw()._validate_whatsapp()

	def test_whatsapp_account_is_a_link(self):
		meta = frappe.get_meta("Gateway")
		field = meta.get_field("whatsapp_account")
		self.assertEqual((field.fieldtype, field.options), ("Link", "WhatsApp Account"))


if __name__ == "__main__":
	unittest.main()
