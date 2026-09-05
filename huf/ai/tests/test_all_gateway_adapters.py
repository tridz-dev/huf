"""Unit tests for Discord, Email, SMS, Google Chat, and Teams Gateway Adapters."""

import json
import time
import unittest
from unittest.mock import MagicMock, patch

from huf.ai.gateway_adapters.email import EmailGatewayAdapter
from huf.ai.gateway_adapters.google_chat import GoogleChatGatewayAdapter
from huf.ai.gateway_adapters.teams import TeamsGatewayAdapter
from huf.ai.gateway_adapters.types import GatewayInboundRequest, GatewayReply

# --- Google Chat Bearer-JWT test fixtures --------------------------------
#
# Real Google Chat apps authenticate every inbound event with an
# `Authorization: Bearer <JWT>` header signed by
# chat@system.gserviceaccount.com (RS256, verified against Google's
# published x509 certs). These tests mint a throwaway RSA keypair and a
# self-signed certificate standing in for Google's, and inject it via the
# adapter's `jwks_fetcher` constructor hook -- no real network call and no
# real Google credential is used or required.

_GOOGLE_CHAT_ISSUER = "chat@system.gserviceaccount.com"
_TEST_KID = "test-kid-1"
_TEST_AUDIENCE = "123456789012"  # stand-in for a GCP project number


def _generate_test_keypair_and_cert():
	"""Build a throwaway RSA keypair + self-signed PEM cert for JWT tests."""
	import datetime

	from cryptography import x509
	from cryptography.hazmat.primitives import hashes, serialization
	from cryptography.hazmat.primitives.asymmetric import rsa
	from cryptography.x509.oid import NameOID

	private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
	subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "test.invalid")])
	now = datetime.datetime.now(datetime.timezone.utc)
	cert = (
		x509.CertificateBuilder()
		.subject_name(subject)
		.issuer_name(issuer)
		.public_key(private_key.public_key())
		.serial_number(x509.random_serial_number())
		.not_valid_before(now - datetime.timedelta(days=1))
		.not_valid_after(now + datetime.timedelta(days=1))
		.sign(private_key, hashes.SHA256())
	)
	pem_private = private_key.private_bytes(
		encoding=serialization.Encoding.PEM,
		format=serialization.PrivateFormat.PKCS8,
		encryption_algorithm=serialization.NoEncryption(),
	).decode("utf-8")
	pem_cert = cert.public_bytes(serialization.Encoding.PEM).decode("utf-8")
	return pem_private, pem_cert


def _make_jwt(private_key_pem, *, kid=_TEST_KID, issuer=_GOOGLE_CHAT_ISSUER, audience=_TEST_AUDIENCE, exp_delta=300):
	import jwt as pyjwt

	now = int(time.time())
	claims = {"iss": issuer, "aud": audience, "iat": now, "exp": now + exp_delta}
	return pyjwt.encode(claims, private_key_pem, algorithm="RS256", headers={"kid": kid})


class TestAllGatewayAdapters(unittest.TestCase):

	def test_email_adapter_inbound_and_outbound(self):
		import frappe

		original_sendmail = getattr(frappe, "sendmail", None)
		mock_sendmail = MagicMock()
		frappe.sendmail = mock_sendmail

		try:
			adapter = EmailGatewayAdapter({"webhook_secret": "mysecret", "sender_email": "bot@example.com"})

			req = GatewayInboundRequest(
				body=b'{"from": "user@example.com", "to": "bot@example.com", "body": "Need help", "message_id": "email_1"}',
				headers={"X-Webhook-Secret": "mysecret"},
				query={},
				method="POST",
			)

			self.assertTrue(adapter.verify_inbound(req))
			event = adapter.normalize_inbound(req)
			self.assertEqual(event.sender_id, "user@example.com")
			self.assertEqual(event.message_text, "Need help")

			reply = GatewayReply(
				conversation_id="user@example.com",
				text="Got your email",
			)
			delivery = adapter.send_reply(reply)
			self.assertEqual(delivery.provider_response["status"], "sent")
			mock_sendmail.assert_called_once()
		finally:
			if original_sendmail:
				frappe.sendmail = original_sendmail


	def test_email_adapter_wrong_secret_rejected(self):
		adapter = EmailGatewayAdapter({"webhook_secret": "mysecret"})

		req = GatewayInboundRequest(
			body=b"{}",
			headers={"X-Webhook-Secret": "wrong-secret"},
			query={},
			method="POST",
		)

		self.assertFalse(adapter.verify_inbound(req))

	def test_email_adapter_missing_token_rejected(self):
		adapter = EmailGatewayAdapter({"webhook_secret": "mysecret"})

		req = GatewayInboundRequest(
			body=b"{}",
			headers={},
			query={},
			method="POST",
		)

		self.assertFalse(adapter.verify_inbound(req))

	def test_email_adapter_uses_hmac_compare_digest(self):
		adapter = EmailGatewayAdapter({"webhook_secret": "mysecret"})

		req = GatewayInboundRequest(
			body=b"{}",
			headers={"X-Webhook-Secret": "mysecret"},
			query={},
			method="POST",
		)

		with patch(
			"huf.ai.gateway_adapters.email.hmac.compare_digest", return_value=True
		) as mock_compare:
			self.assertTrue(adapter.verify_inbound(req))
			mock_compare.assert_called_once_with("mysecret", "mysecret")


	# -- Google Chat: inbound Bearer-JWT verification (G1/G5) --------------

	def _google_chat_adapter(self, **credential_overrides):
		credentials = {
			"audience": _TEST_AUDIENCE,
			"service_account_key": "",
			"webhook_url": "",
		}
		credentials.update(credential_overrides)
		return GoogleChatGatewayAdapter(credentials, jwks_fetcher=lambda **_: self._certs)

	def setUp(self):
		self._private_key_pem, pem_cert = _generate_test_keypair_and_cert()
		self._certs = {_TEST_KID: pem_cert}

	def test_google_chat_adapter_valid_jwt_is_accepted(self):
		token = _make_jwt(self._private_key_pem)
		adapter = self._google_chat_adapter()

		req = GatewayInboundRequest(
			body=b'{"space": {"name": "spaces/1"}, "user": {"displayName": "Alice"}, "message": {"text": "Hi Chat", "name": "msg1"}}',
			headers={"Authorization": f"Bearer {token}"},
			query={},
			method="POST",
		)

		self.assertTrue(adapter.verify_inbound(req))
		event = adapter.normalize_inbound(req)
		self.assertEqual(event.conversation_id, "spaces/1")
		self.assertEqual(event.message_text, "Hi Chat")

	def test_google_chat_adapter_body_token_alone_is_rejected(self):
		"""The retired body-level `token` field must never authenticate a request."""
		adapter = self._google_chat_adapter()

		req = GatewayInboundRequest(
			body=b'{"token": "mytoken", "space": {"name": "spaces/1"}, "message": {"text": "Hi Chat"}}',
			headers={},
			query={},
			method="POST",
		)

		self.assertFalse(adapter.verify_inbound(req))
		with self.assertRaises(ValueError):
			adapter.normalize_inbound(req)

	def test_google_chat_adapter_missing_authorization_header_is_rejected(self):
		adapter = self._google_chat_adapter()
		req = GatewayInboundRequest(body=b"{}", headers={}, query={}, method="POST")
		self.assertFalse(adapter.verify_inbound(req))

	def test_google_chat_adapter_expired_jwt_is_rejected(self):
		token = _make_jwt(self._private_key_pem, exp_delta=-60)
		adapter = self._google_chat_adapter()
		req = GatewayInboundRequest(body=b"{}", headers={"Authorization": f"Bearer {token}"}, query={}, method="POST")
		self.assertFalse(adapter.verify_inbound(req))

	def test_google_chat_adapter_wrong_issuer_is_rejected(self):
		token = _make_jwt(self._private_key_pem, issuer="not-google-chat@example.com")
		adapter = self._google_chat_adapter()
		req = GatewayInboundRequest(body=b"{}", headers={"Authorization": f"Bearer {token}"}, query={}, method="POST")
		self.assertFalse(adapter.verify_inbound(req))

	def test_google_chat_adapter_wrong_audience_is_rejected(self):
		token = _make_jwt(self._private_key_pem, audience="999999999999")
		adapter = self._google_chat_adapter()
		req = GatewayInboundRequest(body=b"{}", headers={"Authorization": f"Bearer {token}"}, query={}, method="POST")
		self.assertFalse(adapter.verify_inbound(req))

	def test_google_chat_adapter_no_configured_audience_fails_closed(self):
		"""No configured audience means nothing can be verified against -- fail closed."""
		token = _make_jwt(self._private_key_pem)
		adapter = self._google_chat_adapter(audience="")
		req = GatewayInboundRequest(body=b"{}", headers={"Authorization": f"Bearer {token}"}, query={}, method="POST")
		self.assertFalse(adapter.verify_inbound(req))

	def test_google_chat_adapter_unknown_kid_is_rejected(self):
		"""A JWT signed with a key not in Google's published cert set must fail."""
		other_private_key_pem, _ = _generate_test_keypair_and_cert()
		token = _make_jwt(other_private_key_pem, kid="some-other-kid")
		adapter = self._google_chat_adapter()
		req = GatewayInboundRequest(body=b"{}", headers={"Authorization": f"Bearer {token}"}, query={}, method="POST")
		self.assertFalse(adapter.verify_inbound(req))

	# -- Google Chat: outbound authentication & routing (G6) ---------------

	def test_google_chat_adapter_send_reply_prefers_event_space_over_webhook_url(self):
		"""A configured webhook_url must not silently override per-event space routing."""
		mock_post = MagicMock()
		mock_post.return_value.json.return_value = {"name": "spaces/1/messages/100"}
		mock_token_post = MagicMock()
		mock_token_post.return_value.json.return_value = {"access_token": "at-123", "expires_in": 3600}

		service_account_key = json.dumps(
			{"client_email": "bot@proj.iam.gserviceaccount.com", "private_key": self._private_key_pem}
		)
		adapter = GoogleChatGatewayAdapter(
			{
				"audience": _TEST_AUDIENCE,
				"service_account_key": service_account_key,
				# A fixed webhook is configured, but the reply below carries its
				# own space -- that must win, not this webhook.
				"webhook_url": "https://chat.googleapis.com/v1/spaces/FIXED/messages?key=abc",
			},
			http_post=mock_post,
			token_http_post=mock_token_post,
		)

		reply = GatewayReply(conversation_id="spaces/1", text="Chat Reply")
		delivery = adapter.send_reply(reply)

		self.assertEqual(delivery.provider_message_id, "spaces/1/messages/100")
		called_url = mock_post.call_args.args[0]
		self.assertIn("spaces/1/messages", called_url)
		self.assertNotIn("FIXED", called_url)
		called_headers = mock_post.call_args.kwargs["headers"]
		self.assertEqual(called_headers["Authorization"], "Bearer at-123")

	def test_google_chat_adapter_send_reply_falls_back_to_webhook_when_no_space(self):
		mock_post = MagicMock()
		mock_post.return_value.json.return_value = {"name": "webhook-msg-1"}

		adapter = GoogleChatGatewayAdapter(
			{
				"audience": _TEST_AUDIENCE,
				"service_account_key": "",
				"webhook_url": "https://chat.googleapis.com/v1/spaces/FIXED/messages?key=abc",
			},
			http_post=mock_post,
		)

		# conversation_id does not start with "spaces/" -> no per-event REST route.
		reply = GatewayReply(conversation_id="unknown-conversation", text="Chat Reply")
		delivery = adapter.send_reply(reply)

		self.assertEqual(delivery.provider_message_id, "webhook-msg-1")
		called_headers = mock_post.call_args.kwargs["headers"]
		self.assertNotIn("Authorization", called_headers)

	def test_google_chat_adapter_send_reply_without_auth_or_webhook_raises(self):
		adapter = GoogleChatGatewayAdapter(
			{"audience": _TEST_AUDIENCE, "service_account_key": "", "webhook_url": ""},
			http_post=MagicMock(),
		)
		reply = GatewayReply(conversation_id="unknown-conversation", text="Chat Reply")
		with self.assertRaises(ValueError):
			adapter.send_reply(reply)

	def test_google_chat_adapter_send_reply_to_space_without_service_account_key_raises(self):
		"""A per-event space with no service-account credential must not fall back to an unauthenticated call."""
		adapter = GoogleChatGatewayAdapter(
			{
				"audience": _TEST_AUDIENCE,
				"service_account_key": "",
				"webhook_url": "https://chat.googleapis.com/v1/spaces/FIXED/messages?key=abc",
			},
			http_post=MagicMock(),
		)
		reply = GatewayReply(conversation_id="spaces/1", text="Chat Reply")
		with self.assertRaises(ValueError):
			adapter.send_reply(reply)

	def test_teams_adapter(self):
		mock_post = MagicMock()
		mock_post.return_value.json.return_value = {"id": "act_999"}

		adapter = TeamsGatewayAdapter(
			{"app_id": "appid", "app_password": "apppass"},
			http_post=mock_post,
		)

		req = GatewayInboundRequest(
			body=b'{"id": "act_1", "from": {"id": "user1"}, "conversation": {"id": "conv1"}, "text": "Hi Teams"}',
			headers={"Authorization": "Bearer token"},
			query={},
			method="POST",
		)

		event = adapter.normalize_inbound(req)
		self.assertEqual(event.sender_id, "user1")
		self.assertEqual(event.message_text, "Hi Teams")

		reply = GatewayReply(
			conversation_id="conv1",
			text="Teams Reply",
		)
		delivery = adapter.send_reply(reply)
		self.assertEqual(delivery.provider_message_id, "act_999")
