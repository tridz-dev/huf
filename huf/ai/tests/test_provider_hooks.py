# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

import unittest
from types import SimpleNamespace

from huf.ai import gateway_service
from huf.ai.gateway_adapters import provider_hooks


class TestProviderHooksRegistry(unittest.TestCase):
	def setUp(self):
		self._saved = dict(provider_hooks._HOOKS)

	def tearDown(self):
		provider_hooks._HOOKS.clear()
		provider_hooks._HOOKS.update(self._saved)

	def test_register_get_call(self):
		provider_hooks.register("Demo", "x", lambda a, b=1: a + b)
		self.assertEqual(provider_hooks.get("Demo", "x")(1, b=2), 3)
		self.assertEqual(provider_hooks.call("Demo", "x", 5), 6)

	def test_unregistered_uses_default_and_call_raises(self):
		self.assertIsNone(provider_hooks.get("Demo", "nope"))
		self.assertEqual(provider_hooks.get("Demo", "nope", "d"), "d")
		self.assertEqual(provider_hooks.get(None, "nope", "d"), "d")
		with self.assertRaises(LookupError):
			provider_hooks.call("Demo", "nope")

	def test_providers_isolated(self):
		provider_hooks.register("A", "h", lambda: "a")
		self.assertIsNone(provider_hooks.get("B", "h"))

	def test_whatsapp_and_telegram_registered(self):
		self.assertTrue(provider_hooks.get("WhatsApp", "send_reply"))
		self.assertTrue(provider_hooks.get("WhatsApp", "consent_required")())
		self.assertFalse(provider_hooks.get("Telegram", "consent_required")())
		self.assertTrue(provider_hooks.get("Telegram", "send_reply"))  # registered by WP-1b
		self.assertEqual(provider_hooks.call("Telegram", "normalize_sender", "Sender", 42), "42")


class TestCallSiteDefaults(unittest.TestCase):
	def test_unregistered_provider_falls_back(self):
		self.assertEqual(gateway_service._whatsapp_send_errors("Demo"), ())
		self.assertEqual(gateway_service._normalize_sender_for_provider("Demo", "Sender", 123), "123")
		self.assertFalse(gateway_service._consent_enabled("Demo"))
		self.assertEqual(gateway_service._linked_sender_ids("g", "Demo", "123"), ["123"])
		self.assertEqual(gateway_service._reply_parts_for_run("run", "Demo"), [])
		gw = SimpleNamespace(provider="Demo")
		self.assertEqual(gateway_service._save_event_media(None, gw), [])
		self.assertIsNone(gateway_service._maybe_mark_read_typing(None, gw))

	def test_whatsapp_sender_normalised(self):
		norm = gateway_service._normalize_sender_for_provider
		self.assertEqual(norm("WhatsApp", "Sender", "+91 98765-43210"), "919876543210")
		self.assertEqual(norm("WhatsApp", "Room", "x"), "x")

	def test_hook_is_used_when_registered(self):
		provider_hooks.register("Demo2", "media_save", lambda e, g: ["/files/a"])
		try:
			self.assertEqual(
				gateway_service._save_event_media(None, SimpleNamespace(provider="Demo2")), ["/files/a"]
			)
		finally:
			provider_hooks._HOOKS.pop(("Demo2", "media_save"), None)

	def test_typing_hook_called_for_registered_provider(self):
		calls = []
		provider_hooks.register("Demo3", "typing", lambda e, g: calls.append((e, g)))
		try:
			gateway_service._maybe_mark_read_typing("ev", SimpleNamespace(provider="Demo3"))
		finally:
			provider_hooks._HOOKS.pop(("Demo3", "typing"), None)
		self.assertEqual(len(calls), 1)


class TestLoaderIsolation(unittest.TestCase):
	def test_broken_telegram_module_does_not_unregister_whatsapp(self):
		import importlib
		import sys
		from unittest.mock import patch

		from huf.ai.gateway_adapters import provider_hooks as ph

		saved_hooks = dict(ph._HOOKS)
		saved_loaded = ph._loaded
		real_import = importlib.import_module

		def fake_import(name, *args, **kwargs):
			if name.endswith(".telegram_hooks"):
				raise ImportError("simulated broken telegram module")
			return real_import(name, *args, **kwargs)

		try:
			ph._HOOKS.clear()
			ph._loaded = False
			for mod in ("huf.ai.gateway_adapters.whatsapp_hooks", "huf.ai.gateway_adapters.telegram_hooks"):
				sys.modules.pop(mod, None)
			with patch.object(importlib, "import_module", side_effect=fake_import):
				self.assertIsNotNone(ph.get("WhatsApp", "normalize_sender"))
				self.assertIsNone(ph.get("Telegram", "normalize_sender"))
		finally:
			ph._HOOKS.clear()
			ph._HOOKS.update(saved_hooks)
			ph._loaded = saved_loaded


class TestGenericHooksRegistered(unittest.TestCase):
	"""Every hook the generic gateway code calls unconditionally for a provider must be registered."""

	WHATSAPP = (
		"send_errors",
		"error_text",
		"normalize_sender",
		"consent_required",
		"linked_sender_ids",
		"adapter_context",
		"extra_event_fields",
		"recover_reply_parts",
		"send_reply",
		"inbound_kind",
		"media_save",
		"typing",
		"reply_target",
		"send_parts",
		"webhook_signals",
		"failed_status",
		"mark_read_typing",
	)
	TELEGRAM = (
		"error_text",
		"normalize_sender",
		"consent_required",
		"record_pending_room",
		"send_reply",
		"inbound_kind",
		"media_save",
		"typing",
		"reply_finished",
		"attempt_reply_parts",
		"ingest_update",
	)

	def test_whatsapp_hooks(self):
		for name in self.WHATSAPP:
			self.assertIsNotNone(provider_hooks.get("WhatsApp", name), name)

	def test_telegram_hooks(self):
		for name in self.TELEGRAM:
			self.assertIsNotNone(provider_hooks.get("Telegram", name), name)

	def test_whatsapp_does_not_record_pending_rooms(self):
		self.assertIsNone(provider_hooks.get("WhatsApp", "record_pending_room"))
