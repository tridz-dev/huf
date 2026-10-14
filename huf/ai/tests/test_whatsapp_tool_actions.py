# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Tests for the bridge-backed WhatsApp agent tool: privilege gating (A8),
bridge routing for send_message, recipient normalisation, the Graph version
constant, and the list_templates / create_template actions.
"""

from __future__ import annotations

import json
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
	"""Patch the active WhatsApp Integration Settings to carry these credential rows."""
	doc = SimpleNamespace(credentials=[_Row(key, value) for key, value in flags.items()])
	return patch.multiple(
		whatsapp.frappe,
		get_all=MagicMock(return_value=[SimpleNamespace(name="IS-1")]),
		get_doc=MagicMock(return_value=doc),
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
		]
		self.mock_available, self.mock_resolve, _default, self.mock_window, *_ = (p.start() for p in self._patches)
		self.post = patch.object(whatsapp.requests, "post", return_value=FakeResponse(body={"messages": [{"id": "wamid.9"}]})).start()
		self.addCleanup(patch.stopall)

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

	def test_server_management_setting_also_allows_proactive_send(self):
		with _settings(allow_whatsapp_management="yes"):
			result = self._send()
		self.assertTrue(result["success"])

	def test_settings_read_failure_fails_closed(self):
		with patch.object(whatsapp.frappe, "get_all", side_effect=RuntimeError("db down")):
			result = self._send(allow_proactive=True)
		self.assertEqual(result["error"], "proactive_send_not_permitted")
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
		creds.assert_called_once_with()
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

	def test_unknown_gateway_is_treated_as_proactive(self):
		self.mock_window.return_value = {"open": True}
		with patch.object(whatsapp, "_gateway_account_name", return_value=None):
			result = self._send(gateway_name="NOPE")
		self.assertEqual(result["error"], "proactive_send_not_permitted")
		self.mock_window.assert_not_called()

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
		mock_tpl.assert_called_once_with("WA-1", "15551234567", "t", ["a"])

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
		self.addCleanup(patch.stopall)

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
		self.assertEqual(result["error"], "gateway_required")
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
					body="Hello {{1}}",
				)
			)
		self.assertTrue(result["success"])
		self.assertEqual(result["data"]["name"], "TPL-2")
		account_name, payload = mock_create.call_args.args
		self.assertEqual(account_name, "WA-1")
		self.assertEqual(payload["template_name"], "promo")
		self.assertEqual(payload["body"], "Hello {{1}}")

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


if __name__ == "__main__":
	unittest.main()
