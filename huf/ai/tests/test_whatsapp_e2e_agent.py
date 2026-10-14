# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Agent-routed end-to-end WhatsApp acceptance (T9b).

"A configured adapter handles an inbound WhatsApp event, keeps conversation
continuity, and sends a policy-compliant reply."

Real: signed webhook -> ``handle_gateway_webhook`` -> ``ingest_gateway_event`` ->
``process_gateway_event`` -> adapter send, with a real ``Agent`` as the Gateway
default target, a real execution user, a real Gateway Access Entry and (bridge
mode) the real frappe_whatsapp doctypes. Faked: only the LLM boundary
(``huf.ai.agent_integration.run_agent_sync``) and the Meta HTTP boundary.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import now_datetime

from huf.ai import gateway_webhook
from huf.ai.gateway_adapters import GatewayInboundRequest, whatsapp_bridge as bridge

APP_SECRET = "e2e-agent-secret"
PHONE_ID = "5550002222"
SENDER = "15559876543"
EXEC_USER = "wa-e2e-agent-exec@example.com"
REPLY = "Agent says hi"


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
	"""Records every Meta Graph POST (both the frappe_whatsapp session and direct requests)."""

	def __init__(self):
		self.calls = []

	def _record(self, method, url, body):
		if isinstance(body, (str, bytes)):
			try:
				body = json.loads(body)
			except ValueError:
				pass
		self.calls.append({"method": method, "url": url, "body": body})
		return _Resp({"messages": [{"id": f"wamid.OUT{len(self.calls)}"}]})

	# requests-session shape used by frappe.integrations.utils.make_request
	def request(self, method, url, data=None, headers=None, json=None, params=None, **kwargs):
		return self._record(method, url, data if json is None else json)

	# requests.post shape used by the direct-mode adapter
	def post(self, url, *, json=None, headers=None, timeout=None, **kwargs):
		return self._record("POST", url, json)

	def sends(self):
		return [c for c in self.calls if c["method"] == "POST" and c["url"].endswith("/messages")]


def _signed_request(payload):
	raw = json.dumps(payload).encode()
	sig = "sha256=" + hmac.new(APP_SECRET.encode(), raw, hashlib.sha256).hexdigest()
	return GatewayInboundRequest(raw, headers={"X-Hub-Signature-256": sig}, query={}, method="POST")


def _payload(sender, message):
	value = {
		"messaging_product": "whatsapp",
		"metadata": {"phone_number_id": PHONE_ID},
		"messages": [message],
		"contacts": [{"wa_id": sender, "profile": {"name": "Bea"}}],
	}
	return {"entry": [{"id": "biz", "changes": [{"field": "messages", "value": value}]}]}


def _text_msg(wamid, text="hello agent", sender="+1 555 987 6543", quoted=None):
	msg = {"from": sender, "id": wamid, "type": "text", "text": {"body": text}}
	if quoted:
		msg["context"] = {"id": quoted, "from": PHONE_ID}
	return msg


class _E2EMixin:
	"""Shared harness. ``USE_BRIDGE`` selects bridge (frappe_whatsapp) vs direct mode."""

	USE_BRIDGE = False

	def _ensure_user(self):
		if not frappe.db.exists("Role", "Huf Gateway User"):
			frappe.get_doc({"doctype": "Role", "role_name": "Huf Gateway User"}).insert(ignore_permissions=True)
		if not frappe.db.exists("User", EXEC_USER):
			user = frappe.get_doc(
				{"doctype": "User", "email": EXEC_USER, "first_name": "WA E2E", "send_welcome_email": 0}
			).insert(ignore_permissions=True)
			user.add_roles("Huf Gateway User")

	def _build_fixtures(self, approve_sender=True):
		self._ensure_user()
		suffix = frappe.generate_hash(length=6)
		self.agent = frappe.get_doc(
			{
				"doctype": "Agent",
				"agent_name": f"WA E2E Agent {suffix}",
				"agent_modality": "Both",
				"instructions": "E2E acceptance fixture.",
				"allowed_users": [{"user": EXEC_USER}],
			}
		).insert(ignore_permissions=True)

		gateway_values = {
			"doctype": "Gateway",
			"gateway_name": f"E2E WhatsApp {suffix}",
			"provider": "WhatsApp",
			"is_enabled": 1,
			"execution_user": EXEC_USER,
			"direct_policy": "Allow list",
			"default_target_type": "Agent",
			"default_agent": self.agent.name,
		}
		if self.USE_BRIDGE:
			self.account = frappe.get_doc(
				{
					"doctype": "WhatsApp Account",
					"account_name": f"E2E Account {suffix}",
					"status": "Active",
					"url": "https://graph.facebook.com",
					"version": "v21.0",
					"phone_id": PHONE_ID,
					"business_id": "biz-2",
					"app_id": "app-2",
					"token": "meta-access-token",
					"webhook_verify_token": "verify-me",
					"is_default_outgoing": 1,
				}
			).insert(ignore_permissions=True)
			gateway_values["whatsapp_account"] = self.account.name

		self.integration = frappe.get_doc(
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
		gateway_values["integration_settings"] = self.integration.name
		self.gateway = frappe.get_doc(gateway_values).insert(ignore_permissions=True)

		if approve_sender:
			frappe.get_doc(
				{
					"doctype": "Gateway Access Entry",
					"gateway": self.gateway.name,
					"entry_type": "Sender",
					"provider": "WhatsApp",
					"external_id": SENDER,
					"state": "Approved",
				}
			).insert(ignore_permissions=True)

	def _start(self, approve_sender=True):
		frappe.set_user("Administrator")
		self._build_fixtures(approve_sender)
		self.meta = FakeMeta()
		self.agent_calls = []
		patches = [
			("frappe.utils.get_url", lambda *a, **k: "http://e2e.localhost"),
			("huf.ai.gateway_webhook._ingest_rate_gate", lambda: None),
			("huf.ai.gateway_service._throttle_outbound_send", lambda *a, **k: None),
		]
		if self.USE_BRIDGE:
			patches.append(("frappe.integrations.utils.get_request_session", lambda: self.meta))
		else:
			patches.append(("requests.post", self.meta.post))
		for target, new in patches:
			patcher = patch(target, new)
			patcher.start()
			self.addCleanup(patcher.stop)

		def fake_run(**kwargs):
			self.agent_calls.append(kwargs)
			return {"response": REPLY, "agent_run_id": f"fake-run-{len(self.agent_calls)}"}

		llm = patch("huf.ai.agent_integration.run_agent_sync", side_effect=fake_run)
		self.run_mock = llm.start()
		self.addCleanup(llm.stop)

		self._prev_request = getattr(frappe.local, "request", None)
		frappe.local.request = SimpleNamespace(args={"gateway_name": self.gateway.name})
		if not getattr(frappe.local, "response", None):
			frappe.local.response = frappe._dict()
		self.addCleanup(lambda: setattr(frappe.local, "request", self._prev_request))
		# trusted bridge sends commit for status-webhook matching; keep test data rollback-able
		commit = patch.object(frappe.db, "commit")
		commit.start()
		self.addCleanup(commit.stop)
		enq = patch("frappe.enqueue")  # no worker; the test calls process_gateway_event itself
		enq.start()
		self.addCleanup(enq.stop)
		self.addCleanup(frappe.set_user, "Administrator")
		self.addCleanup(frappe.db.rollback)

	# ---------------------------------------------------------------- helpers
	def _post(self, message):
		request = _signed_request(_payload(SENDER, message))
		with patch("huf.ai.gateway_webhook._inbound_request", return_value=request):
			return gateway_webhook.handle_gateway_webhook()

	def _event_name(self, wamid):
		names = frappe.get_all(
			"Gateway Event",
			filters={"gateway": self.gateway.name, "provider_event_id": wamid},
			pluck="name",
		)
		self.assertEqual(len(names), 1, names)
		return names[0]

	def _process(self, event_name):
		from huf.ai.gateway_service import process_gateway_event

		try:
			return process_gateway_event(event_name)
		finally:
			frappe.set_user("Administrator")

	def _event(self, name):
		return frappe.get_doc("Gateway Event", name)

	# ------------------------------------------------------------------ cases
	def test_a_b_d_inbound_runs_agent_and_replies_once_in_window(self):
		result = self._post(_text_msg("wamid.E1"))
		self.assertTrue(result["success"], result)
		event_name = self._event_name("wamid.E1")
		event = self._event(event_name)
		self.assertEqual((event.status, event.target_type, event.target_agent), ("Queued", "Agent", self.agent.name))
		self.assertEqual(event.sender_id, SENDER)

		out = self._process(event_name)
		event = self._event(event_name)
		self.assertEqual(event.status, "Succeeded", event.error_message)
		self.assertEqual(out["status"], "Succeeded")

		self.assertEqual(self.run_mock.call_count, 1)
		kwargs = self.agent_calls[0]
		self.assertEqual(kwargs["agent_name"], self.agent.name)
		self.assertEqual(kwargs["channel_id"], f"gateway:{self.gateway.name}")
		self.assertEqual(kwargs["external_id"], SENDER)
		self.assertIn("hello agent", kwargs["prompt"])

		sends = self.meta.sends()
		self.assertEqual(len(sends), 1, self.meta.calls)
		body = sends[0]["body"]
		self.assertEqual(body["to"], SENDER)
		self.assertEqual(body["type"], "text")
		self.assertEqual(body["text"]["body"], REPLY)
		self.assertEqual(body["context"]["message_id"], "wamid.E1")
		if self.USE_BRIDGE:
			self.assertEqual(
				frappe.db.count("WhatsApp Message", {"type": "Outgoing", "whatsapp_account": self.account.name}), 1
			)

	def test_c_second_and_quoting_inbound_reuse_external_id(self):
		for wamid, quoted in (("wamid.C1", None), ("wamid.C2", None), ("wamid.C3", "wamid.C1")):
			self.assertTrue(self._post(_text_msg(wamid, quoted=quoted))["success"])
			self._process(self._event_name(wamid))
			self.assertEqual(self._event(self._event_name(wamid)).status, "Succeeded")
		self.assertEqual(self.run_mock.call_count, 3)
		ids = {c["external_id"] for c in self.agent_calls}
		self.assertEqual(ids, {SENDER}, ids)
		self.assertEqual({c["channel_id"] for c in self.agent_calls}, {f"gateway:{self.gateway.name}"})
		# quoting must not fragment the conversation into a thread
		self.assertFalse(self._event(self._event_name("wamid.C3")).thread_id)
		self.assertEqual(len(self.meta.sends()), 3)
		self.assertEqual(
			[s["body"]["context"]["message_id"] for s in self.meta.sends()], ["wamid.C1", "wamid.C2", "wamid.C3"]
		)

	def _close_window(self, wamid):
		name = self._event_name(wamid)
		frappe.db.set_value("Gateway Event", name, "received_at", now_datetime() - timedelta(hours=25))
		return name

	def test_e_window_closed_without_fallback_fails_cleanly_with_no_post(self):
		self.assertTrue(self._post(_text_msg("wamid.W1"))["success"])
		name = self._close_window("wamid.W1")
		out = self._process(name)
		event = self._event(name)
		self.assertEqual(event.status, "Failed")
		self.assertEqual(out["status"], "Failed")
		self.assertIn("24-hour", event.error_message)
		self.assertIn("Fallback template", event.error_message)
		self.assertNotIn("Traceback", event.error_message)
		self.assertEqual(self.meta.sends(), [])

	def test_e_window_closed_with_fallback_template_sends_one_template(self):
		frappe.db.set_value("Gateway", self.gateway.name, "fallback_template", "e2e_fallback")
		# regression: the exec user (Huf Gateway User) cannot create WhatsApp Message itself;
		# the gateway-internal fallback path must still deliver (trusted send, like send_text)
		if self.USE_BRIDGE:
			self.assertFalse(frappe.has_permission("WhatsApp Message", "create", user=EXEC_USER))
			tpl = frappe.get_doc(
				{
					"doctype": "WhatsApp Templates",
					"template_name": "e2e_fallback",
					"actual_name": "e2e_fallback",
					"whatsapp_account": self.account.name,
					"category": "UTILITY",
					"language": "en",
					"language_code": "en_US",
					"status": "APPROVED",
					"body": "We have a reply for you",
				}
			)
			tpl.flags.ignore_permissions = True
			tpl.db_insert()
		self.assertTrue(self._post(_text_msg("wamid.W2"))["success"])
		name = self._close_window("wamid.W2")
		self._process(name)
		self.assertEqual(self._event(name).status, "Succeeded", self._event(name).error_message)
		sends = self.meta.sends()
		self.assertEqual(len(sends), 1, self.meta.calls)
		body = sends[0]["body"]
		self.assertEqual(body["type"], "template")
		self.assertEqual(body["template"]["name"], "e2e_fallback")
		self.assertEqual(body["to"], SENDER)

	def test_g_duplicate_wamid_one_event_and_one_agent_run(self):
		first = self._post(_text_msg("wamid.D1"))
		second = self._post(_text_msg("wamid.D1"))
		self.assertEqual((first["ingested"], first["duplicates"]), (1, 0))
		self.assertEqual((second["ingested"], second["duplicates"]), (0, 1))
		name = self._event_name("wamid.D1")  # asserts exactly one
		self._process(name)
		self._process(name)  # a redelivered job must not re-run the agent
		self.assertEqual(self.run_mock.call_count, 1)
		self.assertEqual(len(self.meta.sends()), 1)


class TestWhatsAppE2EAgentBridge(_E2EMixin, IntegrationTestCase):
	USE_BRIDGE = True

	def setUp(self):
		if not bridge.is_available():
			self.skipTest("frappe_whatsapp is not installed on this site; bridge-mode E2E needs it")
		self._start()


class TestWhatsAppE2EAgentDirect(_E2EMixin, IntegrationTestCase):
	"""Direct mode: Gateway has no whatsapp_account; adapter posts to Meta itself."""

	USE_BRIDGE = False

	def setUp(self):
		self._start()


class TestWhatsAppE2EAgentUnapproved(_E2EMixin, IntegrationTestCase):
	"""(f) Sender without an approved Gateway Access Entry: no Run, no send."""

	USE_BRIDGE = False

	def setUp(self):
		self._start(approve_sender=False)

	# the shared positive cases do not apply to this fixture
	test_a_b_d_inbound_runs_agent_and_replies_once_in_window = None
	test_c_second_and_quoting_inbound_reuse_external_id = None
	test_e_window_closed_without_fallback_fails_cleanly_with_no_post = None
	test_e_window_closed_with_fallback_template_sends_one_template = None
	test_g_duplicate_wamid_one_event_and_one_agent_run = None

	def test_f_unapproved_sender_never_runs_or_sends(self):
		self._post(_text_msg("wamid.U1"))
		name = self._event_name("wamid.U1")
		event = self._event(name)
		self.assertEqual(event.status, "Rejected")
		self.assertIn("not approved", event.error_message)
		self._process(name)
		self.assertEqual(self._event(name).status, "Rejected")
		self.assertEqual(self.run_mock.call_count, 0)
		self.assertEqual(self.meta.calls, [])
