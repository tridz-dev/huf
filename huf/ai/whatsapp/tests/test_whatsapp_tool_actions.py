# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Tests for the bridge-backed WhatsApp agent tool: privilege gating (A8),
bridge routing for send_message, recipient normalisation, the Graph version
constant, and the list_templates / create_template actions.
"""

from __future__ import annotations

import json

import frappe
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from huf.ai.gateway_adapters import whatsapp_bridge as bridge
from huf.ai.tools import whatsapp


class FakeResponse:
	def __init__(self, status_code=200, body=None):
		self.status_code = status_code
		self._body = body or {}
		self.text = json.dumps(self._body)

	def json(self):
		return self._body


class _Row:
	def __init__(self, key, value):
		self.key = key
		self.value = value

	def get_password(self, fieldname):
		return self.value


def _settings(**flags):
	"""Bind the run to gateway GW-1 with write authority and these per-gateway flags set."""
	return patch.multiple(
		whatsapp,
		_run_gateway=MagicMock(return_value="GW-1"),
		_authorize=MagicMock(return_value=None),
		_scope_refusal=MagicMock(return_value=None),  # recipient scope has its own suite (test_whatsapp_send_scope)
		_server_flag=MagicMock(side_effect=lambda gateway, name: whatsapp._is_truthy(flags.get(name))),
	)


def _creds():
	return patch.object(whatsapp, "_get_whatsapp_credentials", return_value=("PN1", "token"))


def _account(name="WA-1"):
	return {"name": name, "phone_id": "PN1", "token": "t", "url": "https://graph.facebook.com", "version": "v21.0"}


class TestWhatsAppToolGating(unittest.TestCase):
	def setUp(self):
		self._patches = [
			patch.object(bridge, "is_available", return_value=False),
			patch.object(bridge, "resolve_account", return_value=None),
			patch.object(bridge, "resolve_default_account", return_value=None),
			patch.object(bridge, "window_state", return_value={"open": False}),
			_settings(),
			_creds(),
			patch.object(whatsapp, "_gateway_account_name", return_value="WA-1"),
			patch.object(whatsapp, "_is_opted_out", return_value=False),
		]
		self.mock_available, self.mock_resolve, _default, self.mock_window, *_ = (p.start() for p in self._patches)
		self.post = patch.object(whatsapp.requests, "post", return_value=FakeResponse(body={"messages": [{"id": "wamid.9"}]})).start()
		self.addCleanup(patch.stopall)
		# every send (even without a run) is now claimed and counted: start from a clean slate
		frappe.db.delete("WhatsApp Send Key", {"gateway": ["like", "GW-%"]})
		self.addCleanup(frappe.db.delete, "WhatsApp Send Key", {"gateway": ["like", "GW-%"]})

	def _send(self, **overrides):
		kwargs = {"to": "+1 (555) 123-4567", "message": "hi"}
		kwargs.update(overrides)
		return json.loads(whatsapp.handle_action("send_message", **kwargs))

	def test_proactive_send_without_gateway_is_refused_by_default(self):
		result = self._send()
		self.assertFalse(result["success"])
		self.assertEqual(result["error"], "proactive_send_not_permitted")
		self.post.assert_not_called()

	def test_llm_supplied_allow_proactive_is_ignored(self):
		result = self._send(allow_proactive=True)
		self.assertEqual(result["error"], "proactive_send_not_permitted")
		self.post.assert_not_called()

	def test_llm_supplied_management_flag_does_not_enable_proactive_send(self):
		result = self._send(allow_whatsapp_management=True)
		self.assertEqual(result["error"], "proactive_send_not_permitted")
		self.post.assert_not_called()

	def test_llm_supplied_flags_are_ignored_even_when_server_setting_is_off(self):
		with _settings(allow_proactive="false"):
			result = self._send(allow_proactive=True, allow_whatsapp_management=True)
		self.assertEqual(result["error"], "proactive_send_not_permitted")
		self.post.assert_not_called()

	def test_server_setting_allows_proactive_send(self):
		with _settings(allow_proactive="1"):
			result = self._send()
		self.assertTrue(result["success"])
		self.post.assert_called_once()

	def test_server_setting_truthy_and_falsy_values(self):
		for value, allowed in (("1", True), ("true", True), ("YES", True), ("on", False), ("false", False), ("0", False), ("", False)):
			with self.subTest(value=value), _settings(allow_proactive=value):
				self.post.reset_mock()
				result = self._send()
				self.assertEqual(result.get("success", False), allowed)
				self.assertEqual(self.post.called, allowed)

	def test_management_setting_does_not_allow_proactive_send(self):
		with _settings(allow_whatsapp_management="yes"):
			result = self._send()
		self.assertEqual(result["error"], "proactive_send_not_permitted")

	def test_settings_read_failure_fails_closed(self):
		with patch.object(whatsapp.frappe.db, "get_value", side_effect=RuntimeError("db down")):
			result = self._send(allow_proactive=True)
		self.assertFalse(result["success"])
		self.post.assert_not_called()

	def test_open_window_allows_send_without_flag(self):
		self.mock_window.return_value = {"open": True}
		result = self._send(gateway_name="GW-1")
		self.assertTrue(result["success"])
		self.mock_window.assert_called_once_with("GW-1", "15551234567")

	def test_closed_window_requires_flag(self):
		result = self._send(gateway_name="GW-1")
		self.assertEqual(result["error"], "proactive_send_not_permitted")
		self.post.assert_not_called()

	def test_unreadable_window_fails_closed(self):
		self.mock_window.side_effect = RuntimeError("db down")
		result = self._send(gateway_name="GW-1")
		self.assertEqual(result["error"], "proactive_send_not_permitted")
		self.post.assert_not_called()

	def test_send_template_is_not_gated(self):
		result = json.loads(
			whatsapp.handle_action(
				"send_template",
				to="15551234567",
				template_name="order_update",
			)
		)
		self.assertTrue(result["success"])

	def test_create_template_refused_without_management_flag(self):
		with patch.object(bridge, "create_template") as mock_create:
			result = json.loads(
				whatsapp.handle_action("create_template", template_name="promo", category="MARKETING", language_code="en")
			)
		self.assertEqual(result["error"], "management_not_permitted")
		mock_create.assert_not_called()

	def test_create_template_not_enabled_by_allow_proactive(self):
		with (
			_settings(allow_proactive="1"),
			patch.object(bridge, "is_available", return_value=True),
			patch.object(bridge, "resolve_account", return_value=_account()),
			patch.object(bridge, "resolve_default_account", return_value=_account()),
			patch.object(bridge, "create_template") as mock_create,
		):
			result = json.loads(whatsapp.handle_action("create_template", template_name="promo"))
		self.assertEqual(result["error"], "management_not_permitted")
		mock_create.assert_not_called()

	def test_credentials_in_kwargs_are_discarded(self):
		with patch.object(whatsapp, "_get_whatsapp_credentials", return_value=("SERVER", "server-tok")) as creds:
			with patch.object(whatsapp.requests, "get", return_value=FakeResponse(body={"id": "x"})) as mock_get:
				whatsapp.handle_action("get_account_info", phone_number_id="EVIL", access_token="evil-tok")
		creds.assert_called_once()
		self.assertIn("/SERVER", mock_get.call_args.args[0])
		self.assertEqual(mock_get.call_args.kwargs["headers"]["Authorization"], "Bearer server-tok")

	def test_registry_does_not_expose_credential_parameters(self):
		from huf.ai.tools._registry import WHATSAPP_TOOLS

		names = {p["fieldname"] for p in WHATSAPP_TOOLS[0]["parameters"]}
		self.assertNotIn("access_token", names)
		self.assertNotIn("phone_number_id", names)

	def test_gateway_pins_sending_account_and_window_check(self):
		self.mock_window.return_value = {"open": True}
		with (
			patch.object(bridge, "is_available", return_value=True),
			patch.object(bridge, "resolve_account", return_value=_account("WA-1")) as mock_resolve,
			patch.object(bridge, "send_text", return_value={"success": True, "name": "WM-1", "message_id": "m"}) as mock_send,
		):
			result = self._send(gateway_name="GW-1", whatsapp_account="OTHER")
		self.assertTrue(result["success"])
		mock_resolve.assert_called_with("WA-1")
		self.assertEqual(mock_send.call_args.args[0], "WA-1")

	def test_send_template_routes_through_bridge(self):
		with (
			patch.object(bridge, "is_available", return_value=True),
			patch.object(bridge, "resolve_account", return_value=_account()),
			patch.object(bridge, "resolve_default_account", return_value=_account()),
			patch.object(bridge, "send_template", return_value={"success": True, "name": "WM-2", "message_id": "m2"}) as mock_tpl,
		):
			result = json.loads(
				whatsapp.handle_action("send_template", to="15551234567", template_name="t", parameters=["a"])
			)
		self.assertTrue(result["success"])
		mock_tpl.assert_called_once_with("WA-1", "15551234567", "t", ["a"], gateway_name="GW-1")

	def test_create_template_ignores_llm_supplied_management_flag(self):
		with (
			patch.object(bridge, "is_available", return_value=True),
			patch.object(bridge, "resolve_account", return_value=_account()),
			patch.object(bridge, "resolve_default_account", return_value=_account()),
			patch.object(bridge, "create_template") as mock_create,
		):
			result = json.loads(
				whatsapp.handle_action(
					"create_template", allow_whatsapp_management=True, allow_proactive=True, template_name="promo"
				)
			)
		self.assertEqual(result["error"], "management_not_permitted")
		mock_create.assert_not_called()

	def test_create_template_allowed_by_server_setting(self):
		with (
			_settings(allow_whatsapp_management="true", auto_submit_templates="true"),
			patch.object(bridge, "is_available", return_value=True),
			patch.object(bridge, "resolve_account", return_value=_account()),
			patch.object(bridge, "resolve_default_account", return_value=_account()),
			patch.object(bridge, "create_template", return_value={"success": True, "name": "TPL-3"}) as mock_create,
		):
			result = json.loads(whatsapp.handle_action("create_template", template_name="promo", category="MARKETING"))
		self.assertTrue(result["success"])
		mock_create.assert_called_once()

	def test_list_templates_without_bridge_returns_bridge_unavailable(self):
		result = json.loads(whatsapp.handle_action("list_templates"))
		self.assertFalse(result["success"])
		self.assertEqual(result["error"], "bridge_unavailable")


class TestWhatsAppToolBridgeRouting(unittest.TestCase):
	def setUp(self):
		# Proactive sends are allowed by the server-side setting, not by LLM kwargs.
		self._settings = _settings(allow_proactive="1")
		self._settings.start()
		self.addCleanup(self._settings.stop)
		_creds().start()
		patch.object(whatsapp, "_is_opted_out", return_value=False).start()
		patch.object(whatsapp, "_gateway_account_name", return_value="WA-1").start()
		self.addCleanup(patch.stopall)
		# every send (even without a run) is now claimed and counted: start from a clean slate
		frappe.db.delete("WhatsApp Send Key", {"gateway": ["like", "GW-%"]})
		self.addCleanup(frappe.db.delete, "WhatsApp Send Key", {"gateway": ["like", "GW-%"]})

	def test_send_message_uses_bridge_send_text_when_account_resolvable(self):
		with (
			patch.object(bridge, "is_available", return_value=True),
			patch.object(bridge, "resolve_account", return_value=_account()),
			patch.object(bridge, "resolve_default_account", return_value=_account()),
			patch.object(bridge, "send_text", return_value={"success": True, "name": "WM-1", "message_id": "wamid.1", "status": "Sent"}) as mock_send,
			patch.object(whatsapp.requests, "post") as mock_post,
		):
			result = json.loads(whatsapp.handle_action("send_message", to="+1 555-123-4567", message="hello"))
		self.assertTrue(result["success"])
		self.assertEqual(result["data"]["message_id"], "wamid.1")
		mock_send.assert_called_once_with("WA-1", "15551234567", "hello")
		mock_post.assert_not_called()

	def test_send_message_bridge_error_payload_is_returned(self):
		with (
			patch.object(bridge, "is_available", return_value=True),
			patch.object(bridge, "resolve_account", return_value=_account()),
			patch.object(bridge, "resolve_default_account", return_value=_account()),
			patch.object(bridge, "send_text", side_effect=bridge.BridgeError({"success": False, "error": "send_failed"})),
		):
			result = json.loads(whatsapp.handle_action("send_message", to="15551234567", message="hi"))
		self.assertEqual(result, {"success": False, "error": "send_failed"})

	def test_send_message_falls_back_to_graph_when_no_account(self):
		with (
			patch.object(bridge, "is_available", return_value=True),
			patch.object(bridge, "resolve_account", return_value={"error": "no_account"}),
			patch.object(bridge, "resolve_default_account", return_value={"error": "no_account"}),
			patch.object(whatsapp.requests, "post", return_value=FakeResponse(body={"messages": [{"id": "wamid.2"}]})) as mock_post,
		):
			result = json.loads(
				whatsapp.handle_action(
					"send_message",
					to="15551234567",
					message="hi",
				)
			)
		self.assertTrue(result["success"])
		mock_post.assert_called_once()

	def test_graph_url_uses_bridge_default_version(self):
		self.assertEqual(whatsapp.META_GRAPH_URL, f"https://graph.facebook.com/{bridge.GRAPH_DEFAULT_VERSION}")
		self.assertNotIn("v18.0", whatsapp.META_GRAPH_URL)
		with (
			patch.object(bridge, "is_available", return_value=False),
			patch.object(whatsapp.requests, "post", return_value=FakeResponse(body={"messages": [{"id": "wamid.3"}]})) as mock_post,
		):
			whatsapp.handle_action("send_message", to="15551234567", message="hi")
		self.assertTrue(mock_post.call_args.args[0].startswith(f"https://graph.facebook.com/{bridge.GRAPH_DEFAULT_VERSION}/"))

	def test_send_template_normalizes_recipient(self):
		with patch.object(bridge, "is_available", return_value=False), patch.object(whatsapp.requests, "post", return_value=FakeResponse(body={"messages": [{"id": "wamid.4"}]})) as mock_post:
			whatsapp.handle_action(
				"send_template",
				to="+1 (555) 123-4567",
				template_name="order_update",
			)
		self.assertEqual(mock_post.call_args.kwargs["json"]["to"], "15551234567")


class TestWhatsAppToolTemplateActions(unittest.TestCase):
	def setUp(self):
		_settings().start()
		patch.object(whatsapp, "_gateway_account_name", return_value="WA-1").start()
		patch.object(whatsapp, "_is_opted_out", return_value=False).start()
		self.addCleanup(patch.stopall)
		# every send (even without a run) is now claimed and counted: start from a clean slate
		frappe.db.delete("WhatsApp Send Key", {"gateway": ["like", "GW-%"]})
		self.addCleanup(frappe.db.delete, "WhatsApp Send Key", {"gateway": ["like", "GW-%"]})

	def test_list_templates_returns_bridge_rows(self):
		rows = [{"name": "TPL-1", "template_name": "promo", "status": "APPROVED"}]
		with (
			patch.object(bridge, "is_available", return_value=True),
			patch.object(bridge, "resolve_account", return_value=_account("WA-1")),
			patch.object(bridge, "list_templates", return_value=rows) as mock_list,
		):
			result = json.loads(whatsapp.handle_action("list_templates", whatsapp_account="WA-1", status="APPROVED"))
		self.assertTrue(result["success"])
		self.assertEqual(result["data"], rows)
		mock_list.assert_called_once_with("WA-1", "APPROVED")

	def test_list_templates_with_a_gateway_uses_only_that_gateways_account(self):
		with (
			patch.object(bridge, "is_available", return_value=True),
			patch.object(whatsapp, "_gateway_account_name", return_value="WA-GW"),
			patch.object(bridge, "resolve_account", return_value=_account("WA-GW")),
			patch.object(bridge, "resolve_default_account", return_value=_account("DEFAULT")),
			patch.object(bridge, "list_templates", return_value=[]) as mock_list,
		):
			whatsapp.handle_action("list_templates", gateway_name="GW-1", whatsapp_account="OTHER")
		mock_list.assert_called_once_with("WA-GW", None)

	def test_gateway_without_account_never_falls_back_to_the_default_account(self):
		with (
			patch.object(bridge, "is_available", return_value=True),
			patch.object(whatsapp, "_gateway_account_name", return_value=""),
			patch.object(bridge, "resolve_default_account", return_value=_account("DEFAULT")) as default,
			patch.object(bridge, "list_templates") as mock_list,
		):
			result = json.loads(whatsapp.handle_action("list_templates", gateway_name="GW-1"))
		self.assertEqual(result["error"], "no_account")
		default.assert_not_called()
		mock_list.assert_not_called()

	def test_create_template_with_management_setting_calls_bridge(self):
		with (
			_settings(allow_whatsapp_management="1", auto_submit_templates="1"),
			patch.object(bridge, "is_available", return_value=True),
			patch.object(bridge, "resolve_account", return_value=_account()),
			patch.object(bridge, "resolve_default_account", return_value=_account()),
			patch.object(
				bridge,
				"create_template",
				return_value={"success": True, "name": "TPL-2", "status": "PENDING", "id": "123"},
			) as mock_create,
		):
			result = json.loads(
				whatsapp.handle_action(
					"create_template",
					template_name="promo",
					category="MARKETING",
					language_code="en_US",
					body="Hello {{1}}, welcome",
				)
			)
		self.assertTrue(result["success"])
		self.assertEqual(result["data"]["name"], "TPL-2")
		account_name, payload = mock_create.call_args.args
		self.assertEqual(account_name, "WA-1")
		self.assertEqual(payload["template_name"], "promo")
		self.assertEqual(payload["body"], "Hello {{1}}, welcome")

	def test_create_template_bridge_unavailable(self):
		with (
			_settings(allow_whatsapp_management="1"),
			patch.object(bridge, "is_available", return_value=False),
		):
			result = json.loads(
				whatsapp.handle_action(
					"create_template",
					template_name="promo",
					category="MARKETING",
					language_code="en",
				)
			)
		self.assertEqual(result["error"], "bridge_unavailable")

	def test_unknown_action_lists_new_actions(self):
		result = json.loads(whatsapp.handle_action("nope"))
		self.assertFalse(result["success"])
		self.assertIn("list_templates", result["error"])
		self.assertIn("create_template", result["error"])


class TestWhatsAppToolTypedSends(unittest.TestCase):
	"""send_image/video/audio/document/sticker, send_location, send_contact, send_reaction, send_buttons/list/cta_url."""

	# action -> kwargs of a valid call, and the Graph message type it must produce
	CASES = {
		"send_image": ({"link": "https://cdn.example/a.png", "caption": "hi"}, "image"),
		"send_video": ({"link": "https://cdn.example/a.mp4"}, "video"),
		"send_audio": ({"media_id": "55", "voice": True}, "audio"),
		"send_document": ({"link": "https://cdn.example/a.pdf", "filename": "a.pdf"}, "document"),
		"send_sticker": ({"media_id": "77"}, "sticker"),
		"send_location": ({"latitude": 12.5, "longitude": 77.5, "name": "Office"}, "location"),
		"send_contact": ({"contact_name": "Ann Lee", "contact_phone": "+15551230000"}, "contacts"),
		"send_reaction": ({"message_id": "wamid.IN1", "emoji": "\U0001F44D"}, "reaction"),
		"send_buttons": ({"body": "Pick", "buttons": [{"id": "a", "title": "A"}, {"id": "b", "title": "B"}]}, "interactive"),
		"send_list": ({"body": "Menu", "button_text": "Open", "sections": [{"title": "S", "rows": [{"id": "1", "title": "One"}]}]}, "interactive"),
		"send_cta_url": ({"body": "See", "display_text": "Open", "url": "https://shop.example/x"}, "interactive"),
	}

	def setUp(self):
		for p in (
			patch.object(bridge, "is_available", return_value=False),
			patch.object(bridge, "resolve_account", return_value=None),
			patch.object(bridge, "resolve_default_account", return_value=None),
			patch.object(bridge, "window_state", return_value={"open": False}),
			_settings(),
			_creds(),
			patch.object(whatsapp, "_gateway_account_name", return_value="WA-1"),
			patch.object(whatsapp, "_is_opted_out", return_value=False),
		):
			p.start()
		self.post = patch.object(whatsapp.requests, "post", return_value=FakeResponse(body={"messages": [{"id": "wamid.9"}]})).start()
		self.addCleanup(patch.stopall)
		# every send (even without a run) is now claimed and counted: start from a clean slate
		frappe.db.delete("WhatsApp Send Key", {"gateway": ["like", "GW-%"]})
		self.addCleanup(frappe.db.delete, "WhatsApp Send Key", {"gateway": ["like", "GW-%"]})

	def run_action(self, action, **overrides):
		kwargs = {"to": "+1 (555) 123-4567", **self.CASES[action][0], **overrides}
		return json.loads(whatsapp.handle_action(action, **kwargs))

	def test_every_typed_action_is_refused_without_window_or_server_flag(self):
		for action in self.CASES:
			self.post.reset_mock()
			result = self.run_action(action, allow_proactive=True, allow_whatsapp_management=True)  # LLM-supplied flags are ignored
			self.assertEqual(result["error"], "proactive_send_not_permitted", action)
			self.post.assert_not_called()

	def test_server_flag_allows_each_action_and_sends_the_right_type(self):
		for action, (_kw, mtype) in self.CASES.items():
			self.post.reset_mock()
			with _settings(allow_proactive="1"):
				result = self.run_action(action)
			self.assertTrue(result["success"], (action, result))
			body = self.post.call_args.kwargs["json"]
			self.assertEqual((body["type"], body["to"]), (mtype, "15551234567"), action)
			self.assertIn(mtype, body)

	def test_open_window_allows_without_flag(self):
		with patch.object(bridge, "window_state", return_value={"open": True}):
			for action in self.CASES:
				self.post.reset_mock()
				result = self.run_action(action, gateway_name="GW-1")
				self.assertTrue(result["success"], (action, result))
				self.post.assert_called_once()

	def test_opted_out_contact_is_refused_even_with_flag_and_open_window(self):
		with patch.object(whatsapp, "_is_opted_out", return_value=True), patch.object(bridge, "window_state", return_value={"open": True}), _settings(allow_proactive="1"):
			for action in self.CASES:
				result = self.run_action(action, gateway_name="GW-1")
				self.assertEqual(result["error"], "opted_out", action)
		self.post.assert_not_called()

	def test_is_opted_out_consults_the_gateway_service(self):
		patch.stopall()  # drop the setUp stubs; test the real helper with only the DB and service mocked
		with (
			patch.object(whatsapp.frappe.db, "exists", return_value=True),
			patch("huf.ai.gateway_service.is_opted_out", return_value=True) as service,
		):
			self.assertTrue(whatsapp._is_opted_out({"gateway_name": "GW-1"}, "15551234567"))
			service.assert_called_once_with("GW-1", "15551234567")
			self.assertTrue(whatsapp._is_opted_out({}, "15551234567"))  # no gateway: fails closed
		with (
			patch.object(whatsapp.frappe.db, "exists", return_value=True),
			patch("huf.ai.gateway_service.is_opted_out", side_effect=RuntimeError("db")),
		):
			self.assertTrue(whatsapp._is_opted_out({"gateway_name": "GW-1"}, "15551234567"))  # fails closed

	def test_validation_fails_before_any_network_call(self):
		bad = {
			"send_image": {"link": "ftp://x", "caption": "c"},
			"send_audio": {"caption": "not allowed"},
			"send_sticker": {"caption": "not allowed"},
			"send_location": {"latitude": 100},
			"send_contact": {"contact_name": ""},
			"send_reaction": {"emoji": "text"},
			"send_buttons": {"buttons": [{"id": str(i), "title": str(i)} for i in range(4)]},
			"send_list": {"sections": [{"title": "S", "rows": [{"id": str(i), "title": "t"} for i in range(11)]}]},
			"send_cta_url": {"url": "http://insecure.example"},
		}
		with _settings(allow_proactive="1"):
			for action, override in bad.items():
				result = self.run_action(action, **override)
				self.assertEqual(result["error"], "validation_failed", (action, result))
		self.post.assert_not_called()

	def test_buttons_and_sections_may_arrive_as_json_strings(self):
		with _settings(allow_proactive="1"):
			result = self.run_action("send_buttons", buttons=json.dumps([{"id": "a", "title": "A"}]))
			self.assertTrue(result["success"], result)
			bad = self.run_action("send_buttons", buttons="[nope")
		self.assertIn("JSON", bad["error"])

	def test_reaction_remove_sends_empty_emoji(self):
		with _settings(allow_proactive="1"):
			result = self.run_action("send_reaction", remove=True, emoji="")
		self.assertTrue(result["success"])
		self.assertEqual(self.post.call_args.kwargs["json"]["reaction"], {"message_id": "wamid.IN1", "emoji": ""})

	def test_contacts_list_argument(self):
		contacts = json.dumps([{"name": {"formatted_name": "Bob"}, "emails": [{"email": "b@x.co"}]}])
		with _settings(allow_proactive="1"):
			result = self.run_action("send_contact", contacts=contacts)
		self.assertTrue(result["success"], result)
		self.assertEqual(self.post.call_args.kwargs["json"]["contacts"][0]["emails"], [{"email": "b@x.co"}])

	def test_bridge_account_routes_through_the_bridge(self):
		with (
			patch.object(whatsapp, "_resolve_bridge_account", return_value=_account("WA-9")),
			patch.object(bridge, "send_location", return_value={"success": True, "message_id": "wamid.B", "name": "WM-1"}) as send_location,
			patch.object(bridge, "send_interactive", return_value={"success": True, "message_id": "wamid.C"}) as send_interactive,
			patch.object(bridge, "send_media", return_value={"success": True, "message_id": "wamid.D"}) as send_media,
			patch.object(bridge, "send_reaction", return_value={"success": True, "message_id": "wamid.E"}) as send_reaction,
			_settings(allow_proactive="1"),
		):
			self.assertEqual(self.run_action("send_location")["data"]["message_id"], "wamid.B")
			self.assertTrue(self.run_action("send_buttons")["success"])
			self.assertTrue(self.run_action("send_sticker")["success"])
			self.assertTrue(self.run_action("send_reaction")["success"])
		self.assertEqual(send_location.call_args.args[:2], ("WA-9", "15551234567"))
		self.assertEqual(send_interactive.call_args.args[2], "buttons")
		self.assertEqual((send_media.call_args.args[2], send_media.call_args.kwargs["media_id"]), ("sticker", "77"))
		self.assertEqual(send_reaction.call_args.args[2:4], ("wamid.IN1", "\U0001F44D"))
		self.post.assert_not_called()

	def test_bridge_validation_error_and_permission_error_are_reported(self):
		with (
			patch.object(whatsapp, "_resolve_bridge_account", return_value=_account()),
			patch.object(bridge, "send_location", side_effect=bridge.BridgeError({"success": False, "error": "send_failed", "kind": "rate_limit"})),
			_settings(allow_proactive="1"),
		):
			self.assertEqual(self.run_action("send_location")["kind"], "rate_limit")
		with (
			patch.object(whatsapp, "_resolve_bridge_account", return_value=_account()),
			patch.object(bridge, "send_contacts", side_effect=whatsapp.frappe.PermissionError),
			_settings(allow_proactive="1"),
		):
			self.assertEqual(self.run_action("send_contact")["error"], "permission_denied")

	def test_registry_lists_every_action(self):
		from huf.ai.tools._registry import WHATSAPP_TOOLS

		tool = WHATSAPP_TOOLS[0]
		action_desc = next(p for p in tool["parameters"] if p["fieldname"] == "action")["description"]
		names = {p["fieldname"] for p in tool["parameters"]}
		for action in self.CASES:
			self.assertIn(action, action_desc)
			self.assertIn(action, tool["description"])
		for param in ("latitude", "longitude", "emoji", "message_id", "sections", "display_text", "button_text", "media_id", "voice", "contact_name"):
			self.assertIn(param, names)
		self.assertEqual(len(names), len(tool["parameters"]))  # no duplicate parameter names


if __name__ == "__main__":
	unittest.main()
