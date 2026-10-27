"""WP-E2E: offline end-to-end tests of the Microsoft Teams pipeline through the REAL webhook handler.

Real: ``handle_gateway_webhook`` (werkzeug request), JWT verification against a fake OpenID/JWKS server,
``ingest_update`` hook, Gateway Event persistence, admission and routing, ``process_gateway_event``,
the reply hooks, the Bot Framework client (token + Bot Connector over loopback HTTP), conversation
references, readiness and ``verify_teams_connection``. All on the bench's Frappe site inside the test
transaction.

Faked (seams): the fake Bot Framework services of ``huf.tests.teams_fixtures`` (OpenID/JWKS, AAD token
endpoint, Bot Connector) on 127.0.0.1; ``auth._set_test_openid_url``; ``client._AUTHORITY_BASE``;
``frappe.enqueue`` (captured, then the queued job is run inline); ``run_agent_sync`` (no LLM); and
``_test_only_allow_loopback_service_url`` -- the production ``refs.validate_service_url`` only accepts
https Microsoft hosts and has no test seam, so it is wrapped to also accept the fake loopback base.
"""

import json
import os
import unittest
from contextlib import ExitStack, contextmanager, suppress
from unittest.mock import patch
from urllib.parse import quote

os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")  # importing litellm must not fetch the network

import frappe
import jwt as pyjwt
from frappe.tests import IntegrationTestCase
from werkzeug.test import EnvironBuilder

from huf.ai import gateway_webhook
from huf.ai.gateway_service import preview_gateway_readiness, process_gateway_event
from huf.ai.teams import auth, client, diagnostics, refs
from huf.tests import teams_fixtures as tf

GATEWAY_ROLE = "Huf Gateway User"
APP_PASSWORD = "e2e-app-password-do-not-leak"  # noqa: S105 (test value)
WEBHOOK_PATH = "/api/method/huf.ai.gateway_webhook.handle_gateway_webhook"
PERSONAL_AAD = "aaaaaaaa-0000-4000-8000-000000000001"


@contextmanager
def _test_only_allow_loopback_service_url(base_url):
	"""TEST ONLY. ``refs.validate_service_url`` accepts https Microsoft hosts only and has no test seam,
	so wrap it to also accept the fake Bot Connector's loopback ``base_url``; everything else (including
	attacker hosts) still goes through the real validator."""
	real = refs.validate_service_url

	def validate(url):
		if isinstance(url, str) and url.startswith(base_url):
			return url.rstrip("/")
		return real(url)

	with patch.object(refs, "validate_service_url", validate):
		yield


class TestTeamsE2E(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.suffix = frappe.generate_hash(length=6)
		self._created = []
		self._stack = ExitStack()
		self.addCleanup(self._teardown)

		self.svc = self._stack.enter_context(tf.fake_bot_services())
		self.svc.set_jwks(tf.build_jwks(tf.default_signing_key()))
		auth._set_test_openid_url(self.svc.openid_url)
		self._stack.callback(auth._set_test_openid_url, None)
		self._stack.enter_context(patch.object(client, "_AUTHORITY_BASE", self.svc.base_url))
		self._stack.enter_context(_test_only_allow_loopback_service_url(self.svc.base_url))
		self.service_url = self.svc.connector_url

		self.enqueued = []
		self._stack.enter_context(patch.object(frappe, "enqueue", side_effect=self._capture_enqueue))
		self.agent_calls = []
		self.agent_reply = "pong"
		self._stack.enter_context(
			patch("huf.ai.agent.integration.run_agent_sync", side_effect=self._fake_agent)
		)
		self._stack.enter_context(
			patch("huf.ai.gateway_service._throttle_outbound_send", lambda *a, **k: None)
		)

		self._make_gateway()
		self.enqueued.clear()  # drop jobs queued by fixture creation (e.g. User -> create_contact)
		client.clear_token_cache(tf.TENANT_ID, tf.BOT_APP_ID)

	# -- scaffolding ---------------------------------------------------------------------------

	def _capture_enqueue(self, method, **kwargs):
		self.enqueued.append((method, kwargs))

	def _fake_agent(self, **kwargs):
		self.agent_calls.append(kwargs)
		return {"success": True, "response": self.agent_reply, "agent_run_id": None}

	def _make_gateway(self):
		from huf.testing.factories import make_agent, make_ai_model, make_ai_provider

		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": f"teams-e2e-{self.suffix}@example.com",
				"first_name": "TeamsE2E",
				"send_welcome_email": 0,
			}
		)
		user.append("roles", {"role": GATEWAY_ROLE})
		user.insert(ignore_permissions=True)
		self.exec_user = user.name
		if frappe.db.exists("AI Provider", "Test_Provider"):
			provider = frappe.get_doc("AI Provider", "Test_Provider")
		else:
			provider = make_ai_provider(provider_name="Test_Provider")
		self.model = make_ai_model(provider=provider.name, model_name=f"teams-e2e-{self.suffix}")
		self.agent = make_agent(
			agent_name=f"Teams E2E Agent {self.suffix}",
			provider=provider.name,
			model=self.model.name,
			allowed_users=[{"user": self.exec_user}],
		)
		self.integration = frappe.get_doc(
			{
				"doctype": "Integration Settings",
				"service": "microsoft_teams",
				"credentials": [
					{"key": "app_id", "value": tf.BOT_APP_ID},
					{"key": "app_password", "value": APP_PASSWORD},
					{"key": "tenant_id", "value": tf.TENANT_ID},
				],
			}
		).insert(ignore_permissions=True)
		self.gateway = frappe.get_doc(
			{
				"doctype": "Gateway",
				"gateway_name": f"Teams E2E {self.suffix}",
				"provider": "Microsoft Teams",
				"is_enabled": 1,
				"execution_user": self.exec_user,
				"direct_policy": "Allow list",
				"room_policy": "Open",
				"room_sender_policy": "Open",
				"mention_required": 1,
				"default_target_type": "Agent",
				"default_agent": self.agent.name,
				"integration_settings": self.integration.name,
			}
		).insert(ignore_permissions=True)
		self.name = self.gateway.name
		self._approve_sender(PERSONAL_AAD)

	def _approve_sender(self, external_id):
		frappe.get_doc(
			{
				"doctype": "Gateway Access Entry",
				"gateway": self.name,
				"entry_type": "Sender",
				"provider": "Microsoft Teams",
				"external_id": external_id,
				"state": "Approved",
			}
		).insert(ignore_permissions=True)

	def _teardown(self):
		frappe.set_user("Administrator")
		frappe.local.request = None
		self._stack.close()
		client.clear_token_cache(tf.TENANT_ID, tf.BOT_APP_ID)
		for conversation_id in (
			"a:1QxCcZ3gA-personal-fixture",
			tf.CHANNEL_CONVERSATION_BASE,
		):
			frappe.cache.delete_value(refs._cache_key(tf.BOT_APP_ID, conversation_id))
		frappe.db.rollback()
		for doctype, filters in (
			("Gateway Event", {"gateway": self.name}),
			("Gateway Access Entry", {"gateway": self.name}),
			("Agent Run", {"agent": self.agent.name}),
		):
			for docname in frappe.get_all(doctype, filters=filters, pluck="name"):
				frappe.delete_doc(doctype, docname, ignore_permissions=True, force=True)
		for doctype, docname in (
			("Gateway", self.name),
			("Integration Settings", self.integration.name),
			("Agent", self.agent.name),
			("AI Model", self.model.name),
			("User", self.exec_user),
		):
			with suppress(frappe.exceptions.ValidationError, frappe.exceptions.LinkExistsError):
				frappe.delete_doc(doctype, docname, ignore_permissions=True, force=True)
		frappe.db.commit()

	def post(self, activity, token=None, *, gateway=None, authorization=True):
		"""POST an activity through the real handler; returns (result, http_status)."""
		body = json.dumps(activity).encode()
		headers = {"Content-Type": "application/json"}
		if authorization:
			headers["Authorization"] = "Bearer " + (
				token if token is not None else tf.make_bot_token(activity)
			)
		request = EnvironBuilder(
			path=WEBHOOK_PATH,
			method="POST",
			query_string={"gateway_name": gateway or self.name},
			data=body,
			headers=headers,
		).get_request()
		frappe.local.request = request
		frappe.local.response = frappe._dict()
		frappe.local.request_ip = "127.0.0.1"
		try:
			result = gateway_webhook.handle_gateway_webhook()
			return result, frappe.local.response.get("http_status_code", 200)
		finally:
			frappe.local.request = None

	def events(self):
		return frappe.get_all(
			"Gateway Event",
			filters={"gateway": self.name},
			fields=["name", "status", "verified_sender", "conversation_id", "thread_id", "provider_event_id"],
		)

	def reference(self, conversation_id):
		return refs.get_reference(self.name, tf.BOT_APP_ID, conversation_id)

	def run_queued(self):
		"""Run the job the webhook enqueued, as the worker would (inline)."""
		self.assertEqual(len(self.enqueued), 1, self.enqueued)
		method, kwargs = self.enqueued[0]
		self.assertEqual(method, "huf.ai.gateway_service.process_gateway_event")
		try:
			return process_gateway_event(kwargs["event_name"])
		finally:
			frappe.set_user("Administrator")

	def assert_nothing_happened(self, conversation_id="a:1QxCcZ3gA-personal-fixture"):
		self.assertEqual(self.events(), [])
		self.assertIsNone(self.reference(conversation_id))
		self.assertEqual(self.enqueued, [])
		self.assertEqual(self.agent_calls, [])

	def connector_posts(self):
		return self.svc.requests("connector")

	# -- (1)(2)(3) happy path ------------------------------------------------------------------

	def test_personal_message_round_trip(self):
		activity = tf.personal_message("ping", service_url=self.service_url)
		result, status = self.post(activity)

		self.assertEqual(status, 200)
		self.assertTrue(result["success"], result)
		events = self.events()
		self.assertEqual(len(events), 1)
		self.assertEqual(events[0].verified_sender, 1)
		self.assertEqual(events[0].conversation_id, "a:1QxCcZ3gA-personal-fixture")
		self.assertEqual(events[0].provider_event_id, activity["id"])
		self.assertEqual(events[0].status, "Queued")
		reference = self.reference("a:1QxCcZ3gA-personal-fixture")
		self.assertIsNotNone(reference)
		self.assertEqual(reference["serviceUrl"], self.service_url.rstrip("/"))
		self.assertEqual(reference["bot_id"], tf.BOT_ID)
		self.assertEqual(self.agent_calls, [])  # nothing runs until the queued job does

		outcome = self.run_queued()

		self.assertEqual(len(self.agent_calls), 1)
		call = self.agent_calls[0]
		self.assertEqual(call["channel_id"], f"gateway:{self.name}")
		self.assertEqual(call["agent_name"], self.agent.name)
		self.assertIn("ping", call["prompt"])
		self.assertEqual(outcome["status"], "Succeeded", outcome)

		posts = self.connector_posts()
		self.assertEqual(len(posts), 1)
		post = posts[0]
		self.assertEqual(
			post.path, f"/v3/conversations/{quote('a:1QxCcZ3gA-personal-fixture', safe='')}/activities"
		)
		self.assertTrue(post.has_authorization)
		self.assertEqual(post.body["type"], "message")
		self.assertEqual(post.body["text"], "pong")
		self.assertEqual(post.body["from"], {"id": tf.BOT_ID})
		self.assertEqual(post.body["conversation"], {"id": "a:1QxCcZ3gA-personal-fixture"})
		token_requests = self.svc.requests("token")
		self.assertEqual(len(token_requests), 1)
		self.assertTrue(token_requests[0].body["client_secret_sent"])
		self.assertNotIn(APP_PASSWORD, json.dumps([r.body for r in self.svc.requests()]))

		event = frappe.get_doc("Gateway Event", events[0].name)
		self.assertEqual(event.status, "Succeeded")
		self.assertEqual(event.reply_message_id, outcome["provider_message_id"])
		self.assertTrue(event.reply_message_id.startswith("fake-activity-"))
		self.assertEqual(event.reply_status, "sent")

	# -- (4) rejected tokens -------------------------------------------------------------------

	def test_bad_tokens_are_rejected_with_no_side_effects(self):
		activity = tf.personal_message("ping", service_url=self.service_url)
		for variant, factory in tf.TOKEN_VARIANTS.items():
			with self.subTest(variant=variant):
				result, status = self.post(activity, factory(activity))
				self.assertEqual(status, 401, result)
				self.assertEqual(result, {"success": False, "error": "Provider verification failed"})
				self.assert_nothing_happened()
		with self.subTest(variant="no_authorization_header"):
			_, status = self.post(activity, authorization=False)
			self.assertEqual(status, 401)
			self.assert_nothing_happened()
		with self.subTest(variant="garbage_token"):
			_, status = self.post(activity, "not.a.jwt")
			self.assertEqual(status, 401)
			self.assert_nothing_happened()
		self.assertEqual(self.connector_posts(), [])

	def test_disallowed_service_url_is_dropped_even_with_a_valid_token(self):
		activity = tf.personal_message("ping", service_url="https://attacker.example.com/")
		result, status = self.post(activity)  # token serviceUrl claim matches the body
		self.assertEqual(status, 200)
		self.assertEqual(result, {"success": True, "ignored": "service_url"})
		self.assert_nothing_happened()

	# -- (5) ignored activity types ------------------------------------------------------------

	def test_non_message_activities_are_ignored(self):
		cases = {
			"typing": tf.typing_activity(service_url=self.service_url),
			"conversationupdate": tf.conversation_update(service_url=self.service_url),
			"messagereaction": tf.message_reaction(service_url=self.service_url),
		}
		for kind, activity in cases.items():
			with self.subTest(kind=kind):
				result, status = self.post(activity)
				self.assertEqual(status, 200)
				self.assertEqual(result, {"success": True, "ignored": kind})
				self.assertEqual(self.events(), [])
				self.assertEqual(self.enqueued, [])
				self.assertEqual(self.agent_calls, [])

	# -- (6) channels --------------------------------------------------------------------------

	def test_channel_mention_replies_into_the_thread(self):
		activity = tf.channel_mention_message(service_url=self.service_url)
		result, status = self.post(activity)
		self.assertEqual(status, 200, result)
		(event_row,) = self.events()
		self.assertEqual(event_row.conversation_id, tf.CHANNEL_CONVERSATION_BASE)
		self.assertEqual(event_row.thread_id, tf.CHANNEL_ROOT_MESSAGE_ID)
		self.assertTrue(self.reference(tf.CHANNEL_CONVERSATION_BASE))
		self.assertNotIn(
			f"<at>{tf.BOT_NAME}</at>", frappe.db.get_value("Gateway Event", event_row.name, "message_text")
		)

		self.run_queued()

		self.assertEqual(len(self.agent_calls), 1)
		(post,) = self.connector_posts()
		thread_conversation = f"{tf.CHANNEL_CONVERSATION_BASE};messageid={tf.CHANNEL_ROOT_MESSAGE_ID}"
		self.assertEqual(post.path, f"/v3/conversations/{quote(thread_conversation, safe='')}/activities")
		self.assertEqual(post.body["conversation"], {"id": thread_conversation})
		self.assertTrue(post.has_authorization)
		self.assertEqual(post.body["text"], "pong")

	def test_channel_message_without_mention_is_gated(self):
		result, status = self.post(tf.channel_message(service_url=self.service_url))
		self.assertEqual(status, 200)
		self.assertTrue(result["success"])
		(event_row,) = self.events()  # the event is recorded, but rejected by the mention gate
		event = frappe.get_doc("Gateway Event", event_row.name)
		self.assertEqual(event.status, "Rejected")
		self.assertIn("must mention", event.error_message)
		self.assertEqual(self.enqueued, [])
		self.assertEqual(self.agent_calls, [])
		self.assertEqual(self.connector_posts(), [])
		# Observed (not a requirement): a gated message still stores the reference and counts as a
		# verified first message for readiness, because both happen before admission.
		self.assertIsNotNone(self.reference(tf.CHANNEL_CONVERSATION_BASE))
		self.assertTrue(self.readiness()["teams-first-message"])

	# -- (7) tenants ---------------------------------------------------------------------------

	def test_other_tenant_message_is_ignored(self):
		activity = tf.message_from_other_tenant(service_url=self.service_url)
		result, status = self.post(activity)
		self.assertEqual(status, 200)
		self.assertEqual(result, {"success": True, "ignored": "tenant"})
		self.assert_nothing_happened(tf.CHANNEL_CONVERSATION_BASE)

	# -- (8) idempotency -----------------------------------------------------------------------

	def test_duplicate_delivery_runs_the_agent_once(self):
		activity = tf.personal_message("ping", service_url=self.service_url)
		first, _ = self.post(activity)
		second, status = self.post(activity)
		self.assertEqual(status, 200)
		self.assertTrue(second["success"])
		self.assertTrue(second.get("duplicate"), second)
		self.assertEqual(second["event_name"], first["event_name"])
		self.assertEqual(len(self.events()), 1)
		self.run_queued()  # asserts exactly one enqueue
		self.assertEqual(len(self.agent_calls), 1)
		self.assertEqual(len(self.connector_posts()), 1)

	# -- (9) readiness -------------------------------------------------------------------------

	def readiness(self):
		checks = {c["id"]: c for c in preview_gateway_readiness(self.name)["checks"]}
		return {cid: c["done"] for cid, c in checks.items() if cid.startswith("teams-")}

	def test_readiness_follows_the_pipeline_stages(self):
		before = self.readiness()
		self.assertEqual(
			before,
			{
				"teams-credentials": True,
				"teams-messaging-endpoint": True,
				"teams-first-message": False,
				"teams-mention-policy": True,
				"teams-allowed-tenants": True,
			},
		)
		# A conversationUpdate stores a reference but is not a verified inbound message.
		self.post(tf.conversation_update(service_url=self.service_url))
		self.assertFalse(self.readiness()["teams-first-message"])

		self.post(tf.personal_message("ping", service_url=self.service_url))
		self.assertTrue(self.readiness()["teams-first-message"])

		frappe.db.set_value("Gateway", self.name, "is_enabled", 0)
		self.assertFalse(self.readiness()["teams-messaging-endpoint"])
		frappe.db.set_value("Gateway", self.name, {"is_enabled": 1, "mention_required": 0})
		self.assertFalse(self.readiness()["teams-mention-policy"])

	# -- (10) verify connection ----------------------------------------------------------------

	def test_verify_teams_connection_ok_and_never_leaks_the_token(self):
		access_token = pyjwt.encode(
			{"appid": tf.BOT_APP_ID, "tid": tf.TENANT_ID, "aud": "https://api.botframework.com"},
			"k" * 32,
			algorithm="HS256",
		)
		self.svc.script(
			"token",
			tf.Step(200, body={"token_type": "Bearer", "expires_in": 3600, "access_token": access_token}),
		)
		frappe.cache.delete_value(diagnostics._RATE_PREFIX + self.name)

		result = diagnostics.verify_teams_connection(self.name)

		self.assertTrue(result["ok"], result)
		self.assertEqual(
			[s["id"] for s in result["steps"]],
			["credentials", "token", "token_claims", "endpoint", "reference"],
		)
		self.assertTrue(all(s["ok"] for s in result["steps"][:4]), result)
		self.assertFalse(result["steps"][4]["ok"])  # nobody has messaged the bot yet
		dumped = json.dumps(result)
		self.assertNotIn(access_token, dumped)
		self.assertNotIn(APP_PASSWORD, dumped)
		self.assertEqual(len(self.svc.requests("token")), 1)
		self.assertEqual(self.connector_posts(), [])  # verification sends no Teams message
		client.clear_token_cache(tf.TENANT_ID, tf.BOT_APP_ID)


if __name__ == "__main__":
	unittest.main()
