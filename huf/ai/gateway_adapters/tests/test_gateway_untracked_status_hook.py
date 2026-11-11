# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""huf_gateway_delivery_status also fires for wamids with no Gateway Event (agent tool / template sends).

Unit tests drive ``gateway_webhook`` helpers with the hook patched; the end-to-end test posts a signed
``statuses`` payload through ``handle_gateway_webhook``.

Run with: bench --site <site> run-tests --module huf.ai.gateway_adapters.tests.test_gateway_untracked_status_hook
"""

import json
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai import gateway_webhook
from huf.ai.gateway_core.webhook_helpers import untracked_status_hook
from huf.ai.gateway_adapters.tests.test_whatsapp_webhook_security import (
	TestWhatsAppWebhookSecurity as _Security,
	_signature,
	APP_SECRET,
)

GW = "gw-untracked"


def _status(wamid, state, **extra):
	return {"id": wamid, "status": state, "recipient_id": "15550001111", **extra}


class TestUntrackedStatusHook(IntegrationTestCase):
	def setUp(self):
		self.wamid = f"wamid.UNTRACKED{frappe.generate_hash(length=8)}"

	def tearDown(self):
		frappe.cache().delete_value(f"huf_dlv:{GW}:{self.wamid}")

	def _run(self, statuses):
		with patch.object(gateway_webhook, "fire_hook") as hook:
			for s in statuses:
				untracked_status_hook(GW, _status(self.wamid, **s), gateway_webhook._reply_status_wins, gateway_webhook.fire_hook)
		return hook

	def test_delivered_then_read_fires_twice(self):
		hook = self._run([{"state": "delivered"}, {"state": "read"}])
		self.assertEqual(hook.call_count, 2)
		self.assertEqual(
			hook.call_args_list[0].kwargs,
			{"gateway": GW, "provider_message_id": self.wamid, "status": "delivered",
			 "error_code": None, "error_title": None, "event_name": None},
		)
		self.assertEqual(hook.call_args_list[1].kwargs["status"], "read")

	def test_replay_fires_nothing(self):
		hook = self._run([{"state": "delivered"}, {"state": "delivered"}])
		self.assertEqual(hook.call_count, 1)

	def test_late_sent_after_delivered_fires_nothing(self):
		hook = self._run([{"state": "delivered"}, {"state": "sent"}])
		self.assertEqual(hook.call_count, 1)

	def test_failed_fires_once_with_code_and_replay_is_silent(self):
		err = {"errors": [{"code": 131026, "title": "Message undeliverable"}]}
		hook = self._run([{"state": "failed", **err}, {"state": "failed", **err}])
		self.assertEqual(hook.call_count, 1)
		kw = hook.call_args.kwargs
		self.assertEqual((kw["status"], kw["error_code"], kw["error_title"]), ("failed", 131026, "Message undeliverable"))

	def test_failed_after_read_fires_nothing(self):
		hook = self._run([{"state": "read"}, {"state": "failed"}])
		self.assertEqual(hook.call_count, 1)

	def test_unknown_state_ignored(self):
		self.assertEqual(self._run([{"state": "deleted"}]).call_count, 0)


class TestUntrackedStatusEndToEnd(_Security):
	"""Signed statuses payloads through handle_gateway_webhook (inherits fixture; own tests only matter)."""

	def _post_status(self, wamid, state, **extra):
		payload = {
			"object": "whatsapp_business_account",
			"entry": [{"id": "WABA_FAKE", "changes": [{"field": "messages", "value": {
				"messaging_product": "whatsapp",
				"metadata": {"display_phone_number": "15550000000", "phone_number_id": f"55{self._suffix}"},
				"statuses": [_status(wamid, state, timestamp="1750000000", **extra)],
			}}]}],
		}
		body = self._set_post(payload, headers={})
		frappe.request.headers = {"X-Hub-Signature-256": _signature(APP_SECRET, body)}
		with patch.object(gateway_webhook, "fire_hook") as hook:
			result = gateway_webhook.handle_gateway_webhook()
		return result, hook

	def test_tool_sent_wamid_fires_once_per_transition_with_200(self):
		wamid = f"wamid.E2E{self._suffix}"
		before = self._gateway_event_count()
		_, h1 = self._post_status(wamid, "delivered")
		_, h2 = self._post_status(wamid, "delivered")
		result, h3 = self._post_status(wamid, "read")
		self.assertEqual((h1.call_count, h2.call_count, h3.call_count), (1, 0, 1))
		self.assertEqual(h1.call_args.kwargs["gateway"], self.gateway.name)
		self.assertTrue(result["success"])
		self.assertEqual(frappe.local.response.http_status_code, 200)
		self.assertEqual(self._gateway_event_count(), before)

	def test_matched_gateway_event_fires_exactly_once(self):
		wamid = f"wamid.E2EM{self._suffix}"
		real_get = frappe.db.get_value

		def get_value(doctype, *a, **kw):
			if doctype == "Gateway Event" and a and isinstance(a[0], dict) and "reply_message_id" in a[0]:
				return {"name": "GE-X", "reply_status": "", "delivery_error": ""}
			return real_get(doctype, *a, **kw)

		with patch.object(gateway_webhook.frappe.db, "get_value", side_effect=get_value), \
			patch.object(gateway_webhook.frappe.db, "set_value"):
			_, hook = self._post_status(wamid, "delivered")
		self.assertEqual(hook.call_count, 1)
		self.assertEqual(hook.call_args.kwargs["event_name"], "GE-X")
