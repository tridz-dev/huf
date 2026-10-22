# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Real-doctype WhatsApp gateway integration tests (T9).

``TestWhatsAppFullStack`` needs frappe_whatsapp installed and is skipped
otherwise. ``TestWhatsAppCoreWithoutBridge`` asserts the degraded behaviour on
a site without it. Only outbound HTTP to Meta is faked: frappe_whatsapp calls
``frappe.integrations.utils.make_request`` (which uses ``get_request_session``),
the bridge's template sync uses ``whatsapp_bridge._default_get`` and the
direct-mode adapter uses its injectable ``http_post``.
"""

from __future__ import annotations

import hashlib
import hmac
import importlib
import json
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import now_datetime

from huf.ai import gateway_webhook
from huf.ai.whatsapp import management as mgmt
from huf.ai.gateway_adapters import GatewayInboundRequest, whatsapp_bridge as bridge
from huf.ai.gateway_adapters.types import GatewayReply
from huf.ai.gateway_adapters.whatsapp import WhatsAppGatewayAdapter, WhatsAppWindowClosed
from huf.ai.gateway_service import process_gateway_event

APP_SECRET = "full-stack-secret"
PHONE_ID = "5550001111"
SENDER = "15551234567"
EXEC_USER = "wa-fullstack-exec@example.com"


class _Resp:
	def __init__(self, payload, status=200):
		self._payload = payload
		self.status_code = status
		self.headers = {"content-type": "application/json"}
		self.text = json.dumps(payload)

	def raise_for_status(self):
		if self.status_code >= 400:
			raise RuntimeError(f"HTTP {self.status_code}")

	def json(self):
		return self._payload


class FakeMeta:
	"""Stand-in for the requests session used by frappe.integrations.utils."""

	def __init__(self):
		self.calls = []
		self.template_list = {"data": []}

	def request(self, method, url, data=None, headers=None, json=None, params=None, **kwargs):
		body = data if json is None else json
		if isinstance(body, (str, bytes)):
			try:
				body = globals()["json"].loads(body)
			except ValueError:
				pass
		self.calls.append({"method": method, "url": url, "body": body, "headers": headers or {}})
		if url.endswith("/messages"):
			return _Resp({"messages": [{"id": f"wamid.OUT{len(self.calls)}"}]})
		if url.endswith("/message_templates") and method == "POST":
			return _Resp({"id": "meta-tpl-1", "status": "PENDING"})
		return _Resp({"success": True})

	def posts(self, suffix):
		return [c for c in self.calls if c["method"] == "POST" and c["url"].endswith(suffix)]


def _signed_request(payload):
	raw = json.dumps(payload).encode()
	sig = "sha256=" + hmac.new(APP_SECRET.encode(), raw, hashlib.sha256).hexdigest()
	return GatewayInboundRequest(raw, headers={"X-Hub-Signature-256": sig}, query={}, method="POST")


def _payload(messages=None, statuses=None):
	value = {"messaging_product": "whatsapp", "metadata": {"phone_number_id": PHONE_ID}}
	if messages is not None:
		value["messages"] = messages
		value["contacts"] = [{"wa_id": SENDER, "profile": {"name": "Ann"}}]
	if statuses is not None:
		value["statuses"] = statuses
	return {"entry": [{"id": "biz", "changes": [{"field": "messages", "value": value}]}]}


def _text_msg(wamid, text="hello"):
	return {"from": "+1 555 123 4567", "id": wamid, "type": "text", "text": {"body": text}}


class TestWhatsAppFullStack(IntegrationTestCase):
	def _build_fixtures(self):
		cls = self
		if not frappe.db.exists("Role", "Huf Gateway User"):
			frappe.get_doc({"doctype": "Role", "role_name": "Huf Gateway User"}).insert(ignore_permissions=True)
		if not frappe.db.exists("User", EXEC_USER):
			user = frappe.get_doc(
				{"doctype": "User", "email": EXEC_USER, "first_name": "WA Exec", "send_welcome_email": 0}
			).insert(ignore_permissions=True)
			user.add_roles("Huf Gateway User")

		suffix = frappe.generate_hash(length=6)
		cls.account = frappe.get_doc(
			{
				"doctype": "WhatsApp Account",
				"account_name": f"FS Account {suffix}",
				"status": "Active",
				"url": "https://graph.facebook.com",
				"version": "v21.0",
				"phone_id": PHONE_ID,
				"business_id": "biz-1",
				"app_id": "app-1",
				"token": "meta-access-token",
				"webhook_verify_token": "verify-me",
				"is_default_outgoing": 1,
			}
		).insert(ignore_permissions=True)

		cls.integration = frappe.get_doc(
			{
				"doctype": "Integration Settings",
				"service": "whatsapp",
				"credentials": [
					{"key": "phone_number_id", "value": PHONE_ID},
					{"key": "access_token", "value": "meta-access-token"},
					{"key": "webhook_verify_token", "value": "verify-me"},
					{"key": "app_secret", "value": APP_SECRET},
				],
			}
		).insert(ignore_permissions=True)

		cls.gateway = frappe.get_doc(
			{
				"doctype": "Gateway",
				"gateway_name": f"FS WhatsApp {suffix}",
				"provider": "WhatsApp",
				"is_enabled": 1,
				"integration_settings": cls.integration.name,
				"whatsapp_account": cls.account.name,
				"execution_user": EXEC_USER,
				"direct_policy": "Allow list",
			}
		).insert(ignore_permissions=True)

		frappe.get_doc(
			{
				"doctype": "Gateway Access Entry",
				"gateway": cls.gateway.name,
				"entry_type": "Sender",
				"provider": "WhatsApp",
				"external_id": SENDER,
				"state": "Approved",
			}
		).insert(ignore_permissions=True)

	def setUp(self):
		if not bridge.is_available():
			self.skipTest("frappe_whatsapp is not installed on this site; full-stack tests need the real doctypes")
		frappe.set_user("Administrator")
		self._build_fixtures()
		self.meta = FakeMeta()
		for target, new in (
			("frappe.utils.get_url", lambda *a, **k: "http://gw-wa-full.localhost"),
			("frappe.integrations.utils.get_request_session", lambda: self.meta),
			("huf.ai.gateway_adapters.whatsapp_bridge._default_get", self._meta_get),
			("huf.ai.gateway_adapters.whatsapp_bridge._default_post", self._meta_post),
			("huf.ai.gateway_webhook._ingest_rate_gate", lambda: None),
		):
			patcher = patch(target, new)
			patcher.start()
			self.addCleanup(patcher.stop)
		self._prev_request = getattr(frappe.local, "request", None)
		frappe.local.request = SimpleNamespace(args={"gateway_name": self.gateway.name})
		if not getattr(frappe.local, "response", None):
			frappe.local.response = frappe._dict()
		self._prev_request_ip = getattr(frappe.local, "request_ip", None)
		frappe.local.request_ip = "127.0.0.1"  # rate_limit on whitelisted endpoints needs an identity
		self.addCleanup(self._restore_request)
		# trusted bridge sends commit for status-webhook matching; keep test data rollback-able
		commit = patch.object(frappe.db, "commit")
		commit.start()
		self.addCleanup(commit.stop)
		# no worker is running; never really enqueue
		enq = patch("frappe.enqueue")
		enq.start()
		self.addCleanup(enq.stop)

	def tearDown(self):
		frappe.db.rollback()

	def _restore_request(self):
		frappe.local.request = self._prev_request
		frappe.local.request_ip = self._prev_request_ip

	def _meta_get(self, url, **kwargs):
		self.meta.calls.append({"method": "GET", "url": url, "body": None, "headers": kwargs.get("headers", {})})
		return _Resp(self.meta.template_list)

	def _meta_post(self, url, **kwargs):
		"""Huf pushes templates / edits straight to Graph with requests; route that into the fake Meta."""
		return self.meta.request("POST", url, json=kwargs.get("json"), data=kwargs.get("data"), headers=kwargs.get("headers"))

	# ----------------------------------------------------------------- helpers
	def _post_webhook(self, payload):
		request = _signed_request(payload)
		with patch("huf.ai.gateway_webhook._inbound_request", return_value=request):
			return gateway_webhook.handle_gateway_webhook()

	def _events(self, wamid=None):
		filters = {"gateway": self.gateway.name}
		if wamid:
			filters["provider_event_id"] = wamid
		return frappe.get_all("Gateway Event", filters=filters, pluck="name")

	def _inbound(self, wamid):
		result = self._post_webhook(_payload([_text_msg(wamid)]))
		self.assertTrue(result["success"], result)
		return result

	def _outgoing_count(self):
		return frappe.db.count("WhatsApp Message", {"type": "Outgoing", "whatsapp_account": self.account.name})

	def _make_template(self, name="fs_welcome", **extra):
		values = {
			"template_name": name,
			"category": "UTILITY",
			"language": "en",
			"language_code": "en_US",
			"body": "Hello {{1}}, welcome",
			"sample_values": "Ann",
		}
		values.update(extra)
		return mgmt.create_template(account=self.account.name, payload=values)

	# ------------------------------------------------------------------- tests
	def test_01_fixtures_resolve_account_and_credentials(self):
		acct = bridge.resolve_account(self.account.name)
		self.assertEqual(acct["token"], "meta-access-token")
		self.assertTrue(bridge.account_matches_phone_id(self.account.name, PHONE_ID))
		status = mgmt.get_setup_status(self.gateway.name)
		self.assertTrue(status["connector_available"])
		gw = status["gateway"]
		self.assertTrue(gw["enabled"])  # regression: Gateway field is is_enabled
		self.assertTrue(gw["app_secret_present"])
		self.assertEqual(gw["whatsapp_account"], self.account.name)
		self.assertNotIn(APP_SECRET, json.dumps(status))

	def test_02_inbound_creates_one_event_and_replay_is_deduped(self):
		result = self._inbound("wamid.IN1")
		self.assertEqual((result["ingested"], result["duplicates"]), (1, 0))
		events = self._events("wamid.IN1")
		self.assertEqual(len(events), 1)
		event = frappe.get_doc("Gateway Event", events[0])
		self.assertEqual(event.sender_id, SENDER)
		self.assertEqual(event.verified_sender, 1)
		self.assertEqual(event.message_text, "hello")
		# admitted via the approved Gateway Access Entry (no default route -> Unrouted, not Rejected)
		self.assertNotEqual(event.status, "Rejected", event.error_message)
		# mirrored once into frappe_whatsapp
		self.assertEqual(frappe.db.count("WhatsApp Message", {"message_id": "wamid.IN1", "type": "Incoming"}), 1)

		replay = self._post_webhook(_payload([_text_msg("wamid.IN1")]))
		self.assertEqual((replay["ingested"], replay["duplicates"]), (0, 1))
		self.assertEqual(len(self._events("wamid.IN1")), 1)
		self.assertEqual(frappe.db.count("WhatsApp Message", {"message_id": "wamid.IN1"}), 1)

	def test_03_status_only_payload_acks_without_new_event(self):
		before = len(self._events())
		result = self._post_webhook(
			_payload(statuses=[{"id": "wamid.unknown", "status": "delivered", "recipient_id": SENDER}])
		)
		self.assertTrue(result["success"])
		self.assertEqual((result["messages"], result["statuses"]), (0, 1))
		self.assertEqual(len(self._events()), before)

	def test_04_message_status_updates_real_whatsapp_message(self):
		sent = bridge.send_text(self.account.name, SENDER, "to be delivered", trusted=True)
		self.assertTrue(frappe.db.exists("WhatsApp Message", {"message_id": sent["message_id"]}))
		result = self._post_webhook(
			_payload(statuses=[{"id": sent["message_id"], "status": "delivered", "recipient_id": SENDER}])
		)
		self.assertEqual(result["forwarded"], 1)
		self.assertEqual(frappe.db.get_value("WhatsApp Message", sent["name"], "status"), "delivered")

	def test_05_template_status_payload_updates_templates_row(self):
		created = self._make_template("fs_status_tpl")
		self.assertTrue(created["success"], created)
		self.assertEqual(frappe.db.get_value("WhatsApp Templates", created["name"], "status"), "PENDING")
		payload = {
			"entry": [
				{
					"id": "biz-1",
					"changes": [
						{
							"field": "message_template_status_update",
							"value": {"event": "APPROVED", "message_template_id": "meta-tpl-1"},
						}
					],
				}
			]
		}
		result = self._post_webhook(payload)
		self.assertEqual((result["template_updates"], result["forwarded"]), (1, 1))
		self.assertEqual(frappe.db.get_value("WhatsApp Templates", created["name"], "status"), "APPROVED")
		self.assertEqual(len(self._events()), 0)

	def test_06_window_open_after_inbound_and_closed_after_24h(self):
		self.assertFalse(bridge.window_state(self.gateway.name, SENDER)["open"])
		self._inbound("wamid.IN2")
		state = bridge.window_state(self.gateway.name, "+1 (555) 123-4567")
		self.assertTrue(state["open"], state)
		event_name = self._events("wamid.IN2")[0]
		frappe.db.set_value(
			"Gateway Event", event_name, "received_at", now_datetime() - timedelta(hours=25)
		)
		self.assertFalse(bridge.window_state(self.gateway.name, SENDER)["open"])

	def test_07_bridge_send_text_creates_one_message_and_one_meta_post(self):
		before = self._outgoing_count()
		result = bridge.send_text(self.account.name, "+1 555 123 4567", "hi there", trusted=True)
		self.assertTrue(result["success"])
		self.assertEqual(self._outgoing_count(), before + 1)
		posts = self.meta.posts("/messages")
		self.assertEqual(len(posts), 1)
		self.assertTrue(posts[0]["url"].endswith(f"/v21.0/{PHONE_ID}/messages"))
		self.assertEqual(posts[0]["body"]["to"], SENDER)
		self.assertEqual(posts[0]["body"]["text"]["body"], "hi there")
		self.assertEqual(posts[0]["headers"]["authorization"], "Bearer meta-access-token")

	def test_08_adapter_reply_via_bridge_when_window_open(self):
		self._inbound("wamid.IN3")
		event = frappe.get_doc("Gateway Event", self._events("wamid.IN3")[0])
		before = self._outgoing_count()
		gateway = frappe.get_doc("Gateway", self.gateway.name)
		delivery = gateway_webhook.send_gateway_reply(gateway, event, "agent answer")
		self.assertTrue(delivery.provider_message_id)
		self.assertEqual(self._outgoing_count(), before + 1)
		self.assertEqual(len(self.meta.posts("/messages")), 1)
		self.assertEqual(self.meta.posts("/messages")[0]["body"]["context"]["message_id"], "wamid.IN3")

	def test_09_adapter_reply_refused_when_window_closed(self):
		gateway = frappe.get_doc("Gateway", self.gateway.name)
		event = SimpleNamespace(conversation_id=SENDER, provider_event_id="wamid.none")
		with self.assertRaises(WhatsAppWindowClosed):
			gateway_webhook.send_gateway_reply(gateway, event, "too late")
		self.assertEqual(self.meta.posts("/messages"), [])

	def test_10_create_sync_delete_template_lifecycle(self):
		created = self._make_template("fs_lifecycle")
		self.assertTrue(created["success"], created)
		name = created["name"]
		self.assertTrue(frappe.db.exists("WhatsApp Templates", name))
		self.assertEqual(created["id"], "meta-tpl-1")
		tpl_posts = self.meta.posts("/message_templates")
		self.assertEqual(len(tpl_posts), 1)
		self.assertEqual(tpl_posts[0]["body"]["name"], "fs_lifecycle")

		listed = mgmt.list_templates(account=self.account.name)
		self.assertIn(name, [t["name"] for t in listed["templates"]])

		self.meta.template_list = {"data": [{"name": "fs_lifecycle", "status": "APPROVED", "id": "meta-tpl-1"}]}
		synced = mgmt.sync_templates(account=self.account.name)
		self.assertEqual((synced["success"], synced["updated"]), (True, 1), synced)
		self.assertEqual(frappe.db.get_value("WhatsApp Templates", name, "status"), "APPROVED")
		self.assertEqual(self.meta.calls[-1]["method"], "GET")

		deleted = mgmt.delete_template(name=name)
		self.assertTrue(deleted["success"], deleted)
		self.assertFalse(frappe.db.exists("WhatsApp Templates", name))
		self.assertTrue([c for c in self.meta.calls if c["method"] == "DELETE"])

	def test_11_send_template_message_posts_name_and_parameters(self):
		created = self._make_template("fs_send_tpl")
		self.assertTrue(created["success"], created)
		frappe.db.set_value(
			"WhatsApp Templates", created["name"], {"status": "APPROVED", "sample_values": "Ann"}
		)
		self.meta.calls.clear()
		result = mgmt.send_template_message(
			to="+1 555 123 4567", template_name="fs_send_tpl", body_params=json.dumps(["Ann"]), gateway_name=self.gateway.name
		)
		self.assertTrue(result["success"], result)
		# regression: the Link field holds the template document name, not the bare Meta name
		self.assertEqual(frappe.db.get_value("WhatsApp Message", result["name"], "template"), created["name"])
		posts = self.meta.posts("/messages")
		self.assertEqual(len(posts), 1)
		body = posts[0]["body"]
		self.assertEqual(body["type"], "template")
		self.assertEqual(body["to"], SENDER)
		self.assertEqual(body["template"]["name"], "fs_send_tpl")
		self.assertIn({"type": "text", "text": "Ann"}, body["template"]["components"][0]["parameters"])

	def test_11b_trusted_template_send_skips_user_permission_check(self):
		created = self._make_template("fs_trusted_tpl")
		frappe.db.set_value("WhatsApp Templates", created["name"], "status", "APPROVED")
		frappe.set_user(EXEC_USER)
		try:
			with self.assertRaises(frappe.PermissionError):
				bridge.send_template(self.account.name, SENDER, "fs_trusted_tpl", ["Ann"])
			result = bridge.send_template(self.account.name, SENDER, "fs_trusted_tpl", ["Ann"], trusted=True)
		finally:
			frappe.set_user("Administrator")
		self.assertTrue(result["success"], result)

	def test_12_send_text_message_window_policy(self):
		before = self._outgoing_count()
		closed = mgmt.send_text_message(gateway_name=self.gateway.name, to=SENDER, text="hello?")
		self.assertEqual((closed["success"], closed["error"]), (False, "window_closed"))
		self.assertEqual(self.meta.posts("/messages"), [])
		self.assertEqual(self._outgoing_count(), before)

		self._inbound("wamid.IN4")
		opened = mgmt.send_text_message(gateway_name=self.gateway.name, to=SENDER, text="now open")
		self.assertTrue(opened["success"], opened)
		self.assertEqual(len(self.meta.posts("/messages")), 1)
		self.assertEqual(self._outgoing_count(), before + 1)


class TestWhatsAppMultiGateway(IntegrationTestCase):
	"""Two Gateways, two WhatsApp Accounts, two phone numbers: nothing may leak between them."""

	PHONE_A, PHONE_B = "5550001111", "5550002222"
	SECRET_A, SECRET_B = "secret-app-a", "secret-app-b"
	WABA_A, WABA_B = "waba-a", "waba-b"

	def setUp(self):
		if not bridge.is_available():
			self.skipTest("frappe_whatsapp is not installed on this site; multi-gateway tests need the real doctypes")
		frappe.set_user("Administrator")
		if not frappe.db.exists("Role", "Huf Gateway User"):
			frappe.get_doc({"doctype": "Role", "role_name": "Huf Gateway User"}).insert(ignore_permissions=True)
		if not frappe.db.exists("User", EXEC_USER):
			user = frappe.get_doc(
				{"doctype": "User", "email": EXEC_USER, "first_name": "WA Exec", "send_welcome_email": 0}
			).insert(ignore_permissions=True)
			user.add_roles("Huf Gateway User")
		self.suffix = frappe.generate_hash(length=6)
		self.agent = frappe.get_doc(
			{
				"doctype": "Agent",
				"agent_name": f"WA Multi Agent {self.suffix}",
				"agent_modality": "Both",
				"instructions": "Multi-gateway fixture.",
				"allowed_users": [{"user": EXEC_USER}],
			}
		).insert(ignore_permissions=True)
		self.account_a, self.gateway_a = self._make_pair("A", self.PHONE_A, self.SECRET_A, self.WABA_A, default=1)
		self.account_b, self.gateway_b = self._make_pair("B", self.PHONE_B, self.SECRET_B, self.WABA_B)
		self.meta = FakeMeta()
		self.agent_calls = []

		def fake_run(**kwargs):
			self.agent_calls.append(kwargs)
			return {"response": f"reply {len(self.agent_calls)}", "agent_run_id": f"fake-run-{len(self.agent_calls)}"}

		for target, new in (
			("frappe.utils.get_url", lambda *a, **k: "http://gw-wa-full.localhost"),
			("frappe.integrations.utils.get_request_session", lambda: self.meta),
			("huf.ai.gateway_adapters.whatsapp_bridge._default_get", self._meta_get),
			("huf.ai.gateway_adapters.whatsapp_bridge._default_post", self._meta_post),
			("huf.ai.gateway_webhook._ingest_rate_gate", lambda: None),
			("huf.ai.gateway_service._throttle_outbound_send", lambda *a, **k: None),
			("huf.ai.agent_integration.run_agent_sync", fake_run),
		):
			patcher = patch(target, new)
			patcher.start()
			self.addCleanup(patcher.stop)
		self._prev_request = getattr(frappe.local, "request", None)
		if not getattr(frappe.local, "response", None):
			frappe.local.response = frappe._dict()
		self._prev_request_ip = getattr(frappe.local, "request_ip", None)
		frappe.local.request_ip = "127.0.0.1"
		self.addCleanup(self._restore)
		for target in (patch.object(frappe.db, "commit"), patch("frappe.enqueue")):
			target.start()
			self.addCleanup(target.stop)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def _restore(self):
		frappe.local.request = self._prev_request
		frappe.local.request_ip = self._prev_request_ip

	def _meta_get(self, url, **kwargs):
		self.meta.calls.append({"method": "GET", "url": url, "body": None, "headers": kwargs.get("headers", {})})
		return _Resp(self.meta.template_list)

	def _meta_post(self, url, **kwargs):
		"""Huf pushes templates / edits straight to Graph with requests; route that into the fake Meta."""
		return self.meta.request("POST", url, json=kwargs.get("json"), data=kwargs.get("data"), headers=kwargs.get("headers"))

	def _make_pair(self, label, phone, secret, waba, default=0):
		account = frappe.get_doc(
			{
				"doctype": "WhatsApp Account",
				"account_name": f"MG {label} {self.suffix}",
				"status": "Active",
				"url": "https://graph.facebook.com",
				"version": "v21.0",
				"phone_id": phone,
				"business_id": waba,
				"app_id": f"app-{label}",
				"token": f"token-{label}",
				"webhook_verify_token": f"verify-{label}-{self.suffix}",
				"is_default_outgoing": default,
			}
		).insert(ignore_permissions=True)
		gateway = self._make_gateway(f"MG {label} {self.suffix}", phone, secret, account.name)
		return account, gateway

	def _integration(self, phone, secret):
		return frappe.get_doc(
			{
				"doctype": "Integration Settings",
				"service": "whatsapp",
				"credentials": [
					{"key": "phone_number_id", "value": phone},
					{"key": "access_token", "value": "token"},
					{"key": "webhook_verify_token", "value": "verify"},
					{"key": "app_secret", "value": secret},
				],
			}
		).insert(ignore_permissions=True)

	def _make_gateway(self, name, phone, secret, account, enabled=1, approve=True):
		gateway = frappe.get_doc(
			{
				"doctype": "Gateway",
				"gateway_name": name,
				"provider": "WhatsApp",
				"is_enabled": enabled,
				"integration_settings": self._integration(phone, secret).name,
				"whatsapp_account": account,
				"execution_user": EXEC_USER,
				"direct_policy": "Allow list",
				"default_target_type": "Agent",
				"default_agent": self.agent.name,
			}
		).insert(ignore_permissions=True)
		if approve:
			frappe.get_doc(
				{
					"doctype": "Gateway Access Entry",
					"gateway": gateway.name,
					"entry_type": "Sender",
					"provider": "WhatsApp",
					"external_id": SENDER,
					"state": "Approved",
				}
			).insert(ignore_permissions=True)
		return gateway

	# ----------------------------------------------------------------- helpers
	def _post(self, gateway, payload, secret):
		raw = json.dumps(payload).encode()
		sig = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
		request = GatewayInboundRequest(raw, headers={"X-Hub-Signature-256": sig}, query={}, method="POST")
		frappe.local.request = SimpleNamespace(args={"gateway_name": gateway.name})
		with patch("huf.ai.gateway_webhook._inbound_request", return_value=request):
			return gateway_webhook.handle_gateway_webhook()

	@staticmethod
	def _inbound_payload(phone, waba, wamid, text="hello"):
		value = {
			"messaging_product": "whatsapp",
			"metadata": {"phone_number_id": phone},
			"messages": [_text_msg(wamid, text)],
			"contacts": [{"wa_id": SENDER, "profile": {"name": "Ann"}}],
		}
		return {"entry": [{"id": waba, "changes": [{"field": "messages", "value": value}]}]}

	@staticmethod
	def _template_payload(waba, template_id, name, language, event):
		value = {
			"event": event,
			"message_template_id": template_id,
			"message_template_name": name,
			"message_template_language": language,
			"reason": "NONE",
		}
		return {"entry": [{"id": waba, "changes": [{"field": "message_template_status_update", "value": value}]}]}

	def _events(self, gateway, wamid=None):
		filters = {"gateway": gateway.name}
		if wamid:
			filters["provider_event_id"] = wamid
		return frappe.get_all("Gateway Event", filters=filters, pluck="name")

	def _state(self, account, docname):
		key = bridge.state_key(account, docname)
		return frappe.db.get_value(bridge.STATE_DOCTYPE, key, ["status", "whatsapp_account"], as_dict=True)

	def _local_template(self, account, name, language, template_id):
		return bridge._import_template(
			account.name,
			{
				"name": name, "language": language, "status": "PENDING", "category": "UTILITY", "id": template_id,
				"components": [{"type": "BODY", "text": "Hello"}],
			},
		)

	# ------------------------------------------------------------------- tests
	def test_gateway_derives_and_stores_phone_number_id(self):
		self.assertEqual(frappe.db.get_value("Gateway", self.gateway_a.name, "phone_number_id"), self.PHONE_A)
		self.assertEqual(frappe.db.get_value("Gateway", self.gateway_b.name, "phone_number_id"), self.PHONE_B)

	def test_same_customer_keeps_separate_windows_events_and_conversations(self):
		self.assertTrue(self._post(self.gateway_a, self._inbound_payload(self.PHONE_A, self.WABA_A, "wamid.A1"), self.SECRET_A)["success"])
		# the number wrote to gateway A only: A's window is open, B's is not
		self.assertTrue(bridge.window_state(self.gateway_a.name, SENDER)["open"])
		self.assertFalse(bridge.window_state(self.gateway_b.name, SENDER)["open"])
		self.assertEqual(len(self._events(self.gateway_a)), 1)
		self.assertEqual(self._events(self.gateway_b), [])

		self.assertTrue(self._post(self.gateway_b, self._inbound_payload(self.PHONE_B, self.WABA_B, "wamid.B1"), self.SECRET_B)["success"])
		self.assertTrue(bridge.window_state(self.gateway_b.name, SENDER)["open"])
		self.assertEqual(len(self._events(self.gateway_a)), 1)
		self.assertEqual(len(self._events(self.gateway_b)), 1)

		# each inbound is mirrored under its own account
		self.assertEqual(frappe.db.get_value("WhatsApp Message", {"message_id": "wamid.A1"}, "whatsapp_account"), self.account_a.name)
		self.assertEqual(frappe.db.get_value("WhatsApp Message", {"message_id": "wamid.B1"}, "whatsapp_account"), self.account_b.name)

		# one conversation per gateway for the same customer number
		for gateway, wamid in ((self.gateway_a, "wamid.A1"), (self.gateway_b, "wamid.B1")):
			process_gateway_event(self._events(gateway, wamid)[0])
			frappe.set_user("Administrator")
		self.assertEqual(
			sorted((c["channel_id"], c["external_id"]) for c in self.agent_calls),
			sorted([(f"gateway:{self.gateway_a.name}", SENDER), (f"gateway:{self.gateway_b.name}", SENDER)]),
		)

	def test_each_gateway_replies_only_from_its_own_account(self):
		for gateway, phone, waba, secret, wamid in (
			(self.gateway_a, self.PHONE_A, self.WABA_A, self.SECRET_A, "wamid.RA"),
			(self.gateway_b, self.PHONE_B, self.WABA_B, self.SECRET_B, "wamid.RB"),
		):
			self.assertTrue(self._post(gateway, self._inbound_payload(phone, waba, wamid), secret)["success"])
			process_gateway_event(self._events(gateway, wamid)[0])
			frappe.set_user("Administrator")
		all_posts = self.meta.posts("/messages")
		is_read = lambda p: isinstance(p["body"], dict) and p["body"].get("status") == "read"  # noqa: E731
		reads = [p for p in all_posts if is_read(p)]
		posts = [p for p in all_posts if not is_read(p)]
		self.assertEqual(sorted(p["url"].split("/")[-2] for p in reads), sorted([self.PHONE_A, self.PHONE_B]))
		self.assertEqual(len(posts), 2, self.meta.calls)
		urls = [p["url"] for p in posts]
		self.assertEqual(sum(u.endswith(f"/{self.PHONE_A}/messages") for u in urls), 1, urls)
		self.assertEqual(sum(u.endswith(f"/{self.PHONE_B}/messages") for u in urls), 1, urls)
		self.assertEqual(frappe.db.count("WhatsApp Message", {"type": "Outgoing", "whatsapp_account": self.account_a.name}), 1)
		self.assertEqual(frappe.db.count("WhatsApp Message", {"type": "Outgoing", "whatsapp_account": self.account_b.name}), 1)
		bearers = {p["url"].split("/")[-2]: (p["headers"].get("authorization") or p["headers"].get("Authorization")) for p in posts}
		self.assertEqual(bearers[self.PHONE_A], "Bearer token-A")
		self.assertEqual(bearers[self.PHONE_B], "Bearer token-B")

	def test_app_secret_is_per_gateway(self):
		forged = self._post(self.gateway_b, self._inbound_payload(self.PHONE_B, self.WABA_B, "wamid.BAD"), self.SECRET_A)
		self.assertEqual(forged["success"], False)
		self.assertEqual(self._events(self.gateway_b), [])

	def test_unknown_payload_phone_id_is_ignored_with_a_warning(self):
		# B's phone number id arriving at A's callback: signed correctly, but not A's number
		result = self._post(self.gateway_a, self._inbound_payload(self.PHONE_B, self.WABA_B, "wamid.WRONG"), self.SECRET_A)
		self.assertTrue(result["success"])
		self.assertEqual((result["messages"], result["ignored"]), (0, 1))
		self.assertEqual(self._events(self.gateway_a), [])
		self.assertEqual(self._events(self.gateway_b), [])
		self.assertEqual(frappe.db.count("WhatsApp Message", {"message_id": "wamid.WRONG"}), 0)
		self.assertIn(f"phone number id {self.PHONE_B} ignored", frappe.db.get_value("Gateway", self.gateway_a.name, "last_error"))

	def test_template_update_affects_only_the_waba_account_even_with_same_name(self):
		doc_a = self._local_template(self.account_a, "promo", "en_US", "tid-a")
		# frappe_whatsapp keeps template_name unique site-wide, so the other account's row gets its own
		# template_name/docname while it is still called "promo" on Meta (actual_name)
		doc_b = self._local_template(self.account_b, "promo_b", "en_GB", "tid-b")
		frappe.db.set_value("WhatsApp Templates", doc_b, "actual_name", "promo")
		self.assertEqual((doc_a, doc_b), ("promo-en_US", "promo_b-en_GB"))

		# WABA A's update arrives at gateway B's callback: it is still account A's
		result = self._post(self.gateway_b, self._template_payload(self.WABA_A, "tid-a", "promo", "en_US", "REJECTED"), self.SECRET_B)
		self.assertTrue(result["success"], result)
		self.assertEqual(self._state(self.account_a.name, doc_a)["status"], "REJECTED")
		self.assertIsNone(self._state(self.account_b.name, doc_b))
		self.assertIsNone(self._state(self.account_b.name, doc_a))
		self.assertEqual(frappe.db.get_value("WhatsApp Templates", doc_a, "status"), "REJECTED")  # forwarded by Meta id
		self.assertEqual(frappe.db.get_value("WhatsApp Templates", doc_b, "status"), "PENDING")

		# and WABA B's update lands on B only, leaving A's state alone
		self._post(self.gateway_a, self._template_payload(self.WABA_B, "tid-b", "promo", "en_GB", "APPROVED"), self.SECRET_A)
		self.assertEqual(self._state(self.account_b.name, doc_b)["status"], "APPROVED")
		self.assertEqual(self._state(self.account_a.name, doc_a)["status"], "REJECTED")

		# account A's webhook naming B's template (name + language only) must not touch B's document
		self._post(self.gateway_a, self._template_payload(self.WABA_A, "", "promo", "en_GB", "PAUSED"), self.SECRET_A)
		self.assertEqual(self._state(self.account_b.name, doc_b)["status"], "APPROVED")
		self.assertIsNone(self._state(self.account_a.name, doc_b))

	def test_template_update_for_unknown_waba_is_ignored(self):
		doc_a = self._local_template(self.account_a, "orphan", "en_US", "tid-o")
		result = self._post(self.gateway_a, self._template_payload("waba-unknown", "tid-o", "orphan", "en_US", "REJECTED"), self.SECRET_A)
		self.assertTrue(result["success"])
		self.assertEqual(result["forwarded"], 0)
		self.assertIsNone(self._state(self.account_a.name, doc_a))
		self.assertEqual(frappe.db.get_value("WhatsApp Templates", doc_a, "status"), "PENDING")

	def test_template_docname_owned_by_another_account_is_never_overwritten(self):
		payload = {"template_name": "shared_name", "category": "UTILITY", "language": "en", "language_code": "en_US", "body": "Hello {{1}}, welcome", "sample_values": "Ann"}
		first = mgmt.create_template(account=self.account_a.name, payload=payload)
		self.assertTrue(first["success"], first)
		before = len(self.meta.posts("/message_templates"))
		second = mgmt.create_template(gateway_name=self.gateway_b.name, payload=payload)
		self.assertEqual(second["error"], "template_name_taken_by_other_account", second)
		self.assertEqual(len(self.meta.posts("/message_templates")), before)  # nothing sent to Meta
		self.assertEqual(frappe.db.get_value("WhatsApp Templates", first["name"], "whatsapp_account"), self.account_a.name)

		# a sync of account B that meets the same docname skips it and says why
		self.meta.template_list = {"data": [{"name": "shared_name", "language": "en_US", "status": "APPROVED", "category": "UTILITY", "id": "x1"}]}
		synced = mgmt.sync_templates(gateway_name=self.gateway_b.name)
		self.assertEqual((synced["imported"], synced["skipped"]), (0, 1))
		self.assertIn("template_name_taken_by_other_account", synced["skipped_reasons"][0])
		self.assertEqual(frappe.db.get_value("WhatsApp Templates", first["name"], "whatsapp_account"), self.account_a.name)

	def test_template_send_is_scoped_to_the_sending_account(self):
		doc_a = self._local_template(self.account_a, "only_a", "en_US", "tid-oa")
		frappe.db.set_value("WhatsApp Templates", doc_a, "status", "APPROVED")
		with self.assertRaises(bridge.BridgeError) as cm:
			bridge.send_template(self.account_b.name, SENDER, doc_a, [], trusted=True)
		self.assertEqual(cm.exception.payload["error"], "template_not_found")
		self.assertEqual(self.meta.posts("/messages"), [])

	def test_listings_are_isolated_between_accounts(self):
		for gateway, phone, waba, secret, wamid in (
			(self.gateway_a, self.PHONE_A, self.WABA_A, self.SECRET_A, "wamid.LA"),
			(self.gateway_b, self.PHONE_B, self.WABA_B, self.SECRET_B, "wamid.LB"),
		):
			self._post(gateway, self._inbound_payload(phone, waba, wamid), secret)
		doc_a = self._local_template(self.account_a, "list_a", "en_US", "tid-la")
		doc_b = self._local_template(self.account_b, "list_b", "en_US", "tid-lb")

		a_msgs = {m["message_id"] for m in mgmt.list_messages(gateway_name=self.gateway_a.name)["messages"]}
		b_msgs = {m["message_id"] for m in mgmt.list_messages(gateway_name=self.gateway_b.name)["messages"]}
		self.assertEqual((a_msgs & {"wamid.LA", "wamid.LB"}, b_msgs & {"wamid.LA", "wamid.LB"}), ({"wamid.LA"}, {"wamid.LB"}))
		a_conv = mgmt.list_conversations(gateway_name=self.gateway_a.name)["conversations"]
		self.assertEqual({c["last_message"]["whatsapp_account"] for c in a_conv}, {self.account_a.name})
		self.assertEqual({t["name"] for t in mgmt.list_templates(gateway_name=self.gateway_a.name)["templates"]}, {doc_a})
		self.assertEqual({t["name"] for t in mgmt.list_templates(gateway_name=self.gateway_b.name)["templates"]}, {doc_b})

		# no gateway / account: nothing is listed across accounts
		for result in (mgmt.list_messages(), mgmt.list_conversations(), mgmt.list_templates(), mgmt.list_template_drafts()):
			self.assertEqual((result["success"], result["error"]), (False, "gateway_required"))

	def test_drafts_and_states_are_per_account(self):
		payload = json.dumps({"template_name": "dr_promo", "category": "UTILITY", "language_code": "en_US", "body": "Hi {{1}}, welcome", "sample_values": "Ann"})
		draft_a = mgmt.create_template_draft(gateway_name=self.gateway_a.name, payload=payload)
		self.assertTrue(draft_a["success"], draft_a)
		self.assertEqual(frappe.db.get_value("WhatsApp Template Draft", draft_a["name"], "whatsapp_account"), self.account_a.name)
		self.assertEqual(len(mgmt.list_template_drafts(gateway_name=self.gateway_a.name)["drafts"]), 1)
		self.assertEqual(mgmt.list_template_drafts(gateway_name=self.gateway_b.name)["drafts"], [])

		# the same docname has one state row per account
		bridge.record_template_state(docname="dr_promo-en_US", account=self.account_a.name, status="APPROVED")
		bridge.record_template_state(docname="dr_promo-en_US", account=self.account_b.name, status="REJECTED")
		self.assertEqual(self._state(self.account_a.name, "dr_promo-en_US")["status"], "APPROVED")
		self.assertEqual(self._state(self.account_b.name, "dr_promo-en_US")["status"], "REJECTED")
		self.assertTrue(bridge.state_key(self.account_a.name, "dr_promo-en_US").startswith(self.account_a.name))

	def test_plain_desk_user_has_no_template_management_and_no_cross_account_reads(self):
		frappe.set_user(EXEC_USER)  # Huf Gateway User: no System Manager / Huf Admin / WhatsApp permissions
		payload = json.dumps({"template_name": "nope", "category": "UTILITY", "language_code": "en_US", "body": "x"})
		for call in (
			lambda: mgmt.create_template(gateway_name=self.gateway_a.name, payload=payload),
			lambda: mgmt.edit_template(name="nope-en_US", payload=payload),
			lambda: mgmt.delete_template(name="nope-en_US"),
			lambda: mgmt.sync_templates(gateway_name=self.gateway_a.name),
			lambda: mgmt.approve_template_draft(name="x"),
			lambda: mgmt.reject_template_draft(name="x"),
			lambda: mgmt.create_template_draft(gateway_name=self.gateway_a.name, payload=payload),
			lambda: mgmt.send_template_message(gateway_name=self.gateway_a.name, to=SENDER, template_name="nope"),
			lambda: mgmt.send_text_message(gateway_name=self.gateway_a.name, to=SENDER, text="x"),
			lambda: mgmt.send_media_message(gateway_name=self.gateway_a.name, to=SENDER, kind="image", link="https://a/b.png"),
			lambda: mgmt.list_messages(gateway_name=self.gateway_a.name),
			lambda: mgmt.list_conversations(account=self.account_a.name),
			lambda: mgmt.list_templates(account=self.account_a.name),
		):
			with self.assertRaises(frappe.PermissionError):
				call()
		self.assertEqual(self.meta.posts("/messages"), [])

	def test_duplicate_enabled_phone_number_id_is_rejected(self):
		with self.assertRaises(frappe.ValidationError) as cm:
			self._make_gateway(f"MG dup {self.suffix}", self.PHONE_A, "s", "", approve=False)
		self.assertIn(self.gateway_a.name, str(cm.exception))
		self.assertIn(self.PHONE_A, str(cm.exception))

		# allowed while disabled; enabling it is what fails
		spare = self._make_gateway(f"MG spare {self.suffix}", self.PHONE_A, "s", "", enabled=0, approve=False)
		self.assertEqual(spare.phone_number_id, self.PHONE_A)
		spare.is_enabled = 1
		with self.assertRaises(frappe.ValidationError):
			spare.save()
		# once the owner is disabled the number is free again, and the owner is not blocked by itself
		self.gateway_a.reload()
		self.gateway_a.save()
		self.gateway_a.is_enabled = 0
		self.gateway_a.save()
		spare.reload()
		spare.is_enabled = 1
		spare.save()
		self.assertEqual(frappe.db.get_value("Gateway", spare.name, "is_enabled"), 1)

	def test_linked_account_must_exist_and_match_the_phone_number_id(self):
		self.gateway_a.reload()
		self.gateway_a.whatsapp_account = "No Such Account"
		with self.assertRaises(frappe.ValidationError) as cm:
			self.gateway_a.save()
		# the field is a Link since WP-1, so Frappe's link validation rejects a missing account first
		self.assertTrue(
			"does not exist" in str(cm.exception) or "Could not find" in str(cm.exception),
			str(cm.exception),
		)
		self.gateway_a.reload()
		self.gateway_a.whatsapp_account = self.account_b.name  # B's account carries B's phone id
		with self.assertRaises(frappe.ValidationError) as cm:
			self.gateway_a.save()
		# B's account is already linked to the enabled gateway B, which is refused before the phone-id check
		self.assertIn("already linked to the enabled gateway", str(cm.exception))
		self.gateway_a.reload()
		self.gateway_a.whatsapp_account = self.account_a.name
		self.gateway_a.save()

	def test_gateway_without_account_is_not_mirrored_and_never_uses_the_default_account(self):
		bare = self._make_gateway(f"MG bare {self.suffix}", "5550003333", "secret-c", "")
		result = self._post(bare, self._inbound_payload("5550003333", "waba-c", "wamid.BARE"), "secret-c")
		self.assertTrue(result["success"], result)
		self.assertEqual(len(self._events(bare)), 1)
		# account A is the default outgoing account, yet nothing was mirrored into it
		self.assertEqual(frappe.db.count("WhatsApp Message", {"message_id": "wamid.BARE"}), 0)
		self.assertEqual(bridge.resolve_account(None), {"error": "no_account"})


class TestWhatsAppCoreWithoutBridge(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		if bridge.is_available():
			self.skipTest("frappe_whatsapp is installed; these assertions cover the core-only site")

	def test_core_modules_import_without_frappe_whatsapp(self):
		for module in (
			"huf.ai.gateway_adapters.whatsapp_bridge",
			"huf.ai.gateway_adapters.whatsapp",
			"huf.ai.whatsapp.management",
			"huf.ai.gateway_webhook",
		):
			importlib.import_module(module)
		self.assertIsNone(bridge.resolve_account(None))
		self.assertFalse(bridge.forward_status({"field": "messages", "value": {"statuses": []}}))

	def test_management_api_reports_bridge_unavailable(self):
		status = mgmt.get_setup_status()
		self.assertTrue(status["success"])
		self.assertFalse(status["connector_available"])
		self.assertIsInstance(status["gateways"], list)
		self.assertNotIn("accounts", status)
		for result in (
			mgmt.list_templates(),
			mgmt.create_template(payload={"template_name": "x_y", "category": "UTILITY", "language_code": "en"}),
			mgmt.sync_templates(),
			mgmt.delete_template(name="x"),
			mgmt.send_template_message(gateway_name="G", to="15551234567", template_name="x_y"),
			mgmt.send_text_message(gateway_name="G", to="15551234567", text="hi"),
			mgmt.list_messages(),
			mgmt.list_conversations(),
		):
			self.assertEqual(result, {"success": False, "error": "bridge_unavailable"})

	def test_adapter_direct_mode_send_with_patched_http(self):
		calls = []

		def fake_post(url, *, json, headers, timeout):
			calls.append((url, json, headers))
			return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"messages": [{"id": "wamid.D1"}]})

		adapter = WhatsAppGatewayAdapter(
			{
				"phone_number_id": PHONE_ID,
				"access_token": "tok",
				"webhook_verify_token": "v",
				"app_secret": APP_SECRET,
			},
			http_post=fake_post,
			gateway_context={"whatsapp_account": "ignored-without-bridge"},
		)
		delivery = adapter.send_reply(GatewayReply(conversation_id="+1 555 123 4567", text="direct"))
		self.assertEqual(delivery.provider_message_id, "wamid.D1")
		self.assertEqual(len(calls), 1)
		url, body, headers = calls[0]
		self.assertTrue(url.endswith(f"/{PHONE_ID}/messages"))
		self.assertEqual((body["to"], body["text"]["body"]), (SENDER, "direct"))
		self.assertEqual(headers["Authorization"], "Bearer tok")

		tpl = adapter.send_template("15551234567", "welcome", "en_US", ["Ann"])
		self.assertEqual(tpl.provider_message_id, "wamid.D1")
		self.assertEqual(calls[1][1]["template"]["name"], "welcome")
