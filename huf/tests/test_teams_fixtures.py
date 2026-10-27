"""Self-tests for teams_fixtures (plain unittest, no Frappe site, no real network).

Run from the huf/tests directory:
    python -m unittest test_teams_fixtures -v
"""

from __future__ import annotations

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import jwt as pyjwt  # noqa: E402
from jwt.algorithms import RSAAlgorithm  # noqa: E402

import teams_fixtures as tf  # noqa: E402

SECRET = "sekret-value-do-not-log-9f8e7d"


def _public_key_for(jwks: dict, kid: str):
    for jwk in jwks["keys"]:
        if jwk.get("kid") == kid:
            return RSAAlgorithm.from_jwk(json.dumps(jwk))
    return None


def _verify(token: str, jwks: dict, *, audience: str = tf.BOT_APP_ID, issuer: str = tf.BOT_FRAMEWORK_ISSUER):
    """Verify like the adapter should: kid lookup in JWKS, RS256, aud, iss, 5 min skew."""
    kid = pyjwt.get_unverified_header(token).get("kid")
    key = _public_key_for(jwks, kid) if kid else None
    if key is None:
        raise LookupError(f"kid {kid!r} not in JWKS")
    return pyjwt.decode(
        token,
        key=key,
        algorithms=["RS256"],
        audience=audience,
        issuer=issuer,
        leeway=tf.CLOCK_SKEW_SECONDS,
    )


class ActivityBuilderTests(unittest.TestCase):
    def test_personal_message_shape(self):
        act = tf.personal_message("hi")
        self.assertEqual(act["type"], "message")
        self.assertEqual(act["channelId"], "msteams")
        self.assertEqual(act["serviceUrl"], tf.DEFAULT_SERVICE_URL)
        self.assertEqual(act["conversation"]["conversationType"], "personal")
        self.assertTrue(act["conversation"]["id"].startswith("a:"))
        self.assertEqual(act["recipient"]["id"], tf.BOT_ID)
        self.assertIn("id", act["from"])
        self.assertEqual(act["text"], "hi")

    def test_group_chat_message(self):
        act = tf.group_chat_message()
        self.assertEqual(act["conversation"]["conversationType"], "groupChat")
        self.assertTrue(act["conversation"]["id"].startswith("19:"))

    def test_channel_mention_has_entity_and_thread(self):
        act = tf.channel_mention_message()
        self.assertEqual(act["conversation"]["conversationType"], "channel")
        self.assertIn(";messageid=", act["conversation"]["id"])
        mentions = [e for e in act["entities"] if e["type"] == "mention"]
        self.assertEqual(len(mentions), 1)
        self.assertEqual(mentions[0]["mentioned"]["id"], tf.BOT_ID)
        self.assertIn("<at>", act["text"])
        self.assertEqual(act["channelData"]["tenant"]["id"], tf.TENANT_ID)

    def test_channel_message_without_mention(self):
        act = tf.channel_message()
        self.assertEqual(act["entities"], [])

    def test_reply_message_sets_reply_to(self):
        act = tf.reply_message("1712345670000")
        self.assertEqual(act["replyToId"], "1712345670000")

    def test_conversation_update_members_added(self):
        act = tf.conversation_update()
        self.assertEqual(act["type"], "conversationUpdate")
        self.assertEqual(act["membersAdded"][0]["id"], tf.BOT_ID)

    def test_installation_update_action(self):
        self.assertEqual(tf.installation_update("remove")["action"], "remove")

    def test_non_message_types(self):
        self.assertEqual(tf.typing_activity()["type"], "typing")
        self.assertEqual(tf.message_reaction(["like"])["reactionsAdded"], [{"type": "like"}])
        inv = tf.invoke_activity("fileConsent/invoke", {"action": "decline"})
        self.assertEqual((inv["type"], inv["name"], inv["value"]["action"]), ("invoke", "fileConsent/invoke", "decline"))

    def test_file_download_attachment(self):
        act = tf.message_with_file_download()
        att = act["attachments"][0]
        self.assertEqual(att["contentType"], "application/vnd.microsoft.teams.file.download.info")
        self.assertTrue(att["content"]["downloadUrl"].startswith("https://"))
        self.assertIn("uniqueId", att["content"])

    def test_inline_html_attachment(self):
        act = tf.message_with_inline_html()
        self.assertEqual(act["attachments"][0]["contentType"], "text/html")

    def test_other_tenant(self):
        act = tf.message_from_other_tenant()
        self.assertEqual(act["channelData"]["tenant"]["id"], tf.OTHER_TENANT_ID)
        self.assertNotEqual(act["channelData"]["tenant"]["id"], tf.TENANT_ID)

    def test_builders_are_json_serialisable(self):
        for act in (
            tf.personal_message(), tf.group_chat_message(), tf.channel_mention_message(),
            tf.channel_message(), tf.reply_message("1"), tf.conversation_update(),
            tf.installation_update(), tf.typing_activity(), tf.message_reaction(),
            tf.invoke_activity(), tf.message_with_file_download(), tf.message_with_inline_html(),
            tf.message_from_other_tenant(),
        ):
            json.dumps(act)


class TokenToolkitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key = tf.default_signing_key()
        cls.jwks = tf.build_jwks(cls.key)
        cls.activity = tf.channel_mention_message()

    def test_jwks_shape_and_endorsements(self):
        jwk = self.jwks["keys"][0]
        self.assertEqual(jwk["kty"], "RSA")
        self.assertEqual(jwk["kid"], tf.DEFAULT_KID)
        self.assertEqual(jwk["alg"], "RS256")
        self.assertIn("msteams", jwk["endorsements"])
        self.assertNotIn("d", jwk)  # no private material

    def test_openid_config_shape(self):
        cfg = tf.build_openid_config()
        self.assertEqual(cfg["issuer"], "https://api.botframework.com")
        self.assertEqual(cfg["jwks_uri"], "https://login.botframework.com/v1/.well-known/keys")
        self.assertIn("RS256", cfg["id_token_signing_alg_values_supported"])

    def test_happy_path_verifies_with_pyjwt(self):
        token = tf.make_bot_token(self.activity)
        claims = _verify(token, self.jwks)
        self.assertEqual(claims["aud"], tf.BOT_APP_ID)
        self.assertEqual(claims["iss"], tf.BOT_FRAMEWORK_ISSUER)
        self.assertEqual(claims[tf.SERVICE_URL_CLAIM], self.activity["serviceUrl"])

    def test_forged_signature_rejected(self):
        with self.assertRaises(pyjwt.InvalidSignatureError):
            _verify(tf.forged_token(self.activity), self.jwks)

    def test_wrong_audience_rejected(self):
        with self.assertRaises(pyjwt.InvalidAudienceError):
            _verify(tf.wrong_audience_token(self.activity), self.jwks)

    def test_wrong_issuer_rejected(self):
        with self.assertRaises(pyjwt.InvalidIssuerError):
            _verify(tf.wrong_issuer_token(self.activity), self.jwks)

    def test_expired_rejected_beyond_skew(self):
        with self.assertRaises(pyjwt.ExpiredSignatureError):
            _verify(tf.expired_token(self.activity), self.jwks)

    def test_service_url_mismatch_detected(self):
        token = tf.service_url_mismatch_token(self.activity)
        claims = _verify(token, self.jwks)  # signature/aud/iss are fine
        self.assertNotEqual(claims[tf.SERVICE_URL_CLAIM], self.activity["serviceUrl"])

    def test_unknown_kid_not_in_jwks(self):
        token = tf.unknown_kid_token(self.activity)
        with self.assertRaises(LookupError):
            _verify(token, self.jwks)

    def test_every_variant_fails_verification_except_service_url(self):
        # service_url_mismatch is a structurally valid token; its failure is the
        # serviceUrl-claim comparison covered by test_service_url_mismatch_detected.
        for name, factory in tf.TOKEN_VARIANTS.items():
            if name == "service_url_mismatch":
                continue
            with self.subTest(variant=name), self.assertRaises(Exception):
                _verify(factory(self.activity), self.jwks)

    def test_fake_openid_and_jwks_endpoints_serve_verifiable_keys(self):
        with tf.fake_bot_services() as s:
            s.set_jwks(self.jwks)
            s.set_openid(tf.build_openid_config(jwks_uri=s.jwks_url))
            status, _, cfg = tf.http_request("GET", s.openid_url)
            self.assertEqual(status, 200)
            status, _, served = tf.http_request("GET", cfg["jwks_uri"])
            self.assertEqual(status, 200)
            token = tf.make_bot_token(self.activity)
            self.assertEqual(_verify(token, served)["aud"], tf.BOT_APP_ID)


class FakeTokenEndpointTests(unittest.TestCase):
    def test_records_form_without_secret_and_scripts_failures(self):
        with tf.fake_bot_services() as s:
            url = s.token_url_for(tf.TENANT_ID)
            form = {
                "grant_type": "client_credentials",
                "client_id": tf.BOT_APP_ID,
                "client_secret": SECRET,
                "scope": "https://api.botframework.com/.default",
            }
            s.script("token", 401, ((429, {"Retry-After": "7"})), 502, 504, 500)
            statuses = []
            for _ in range(5):
                status, headers, _body = tf.http_request("POST", url, form=form)
                statuses.append((status, headers.get("Retry-After")))
            self.assertEqual(statuses, [(401, None), (429, "7"), (502, None), (504, None), (500, None)])

            status, _, body = tf.http_request("POST", url, form=form)
            self.assertEqual(status, 200)
            self.assertEqual(body["token_type"], "Bearer")
            self.assertEqual(body["expires_in"], 3600)
            self.assertTrue(body["access_token"].startswith("fake-access-token"))

            records = s.requests("token")
            self.assertEqual(len(records), 6)
            first = records[0]
            self.assertEqual(first.method, "POST")
            self.assertEqual(first.path, f"/{tf.TENANT_ID}/oauth2/v2.0/token")
            self.assertEqual(first.body["grant_type"], "client_credentials")
            self.assertEqual(first.body["client_id"], tf.BOT_APP_ID)
            self.assertEqual(first.body["scope"], "https://api.botframework.com/.default")
            self.assertTrue(first.body["client_secret_sent"])
            self.assertNotIn("client_secret", first.body)
            self.assertNotIn(SECRET, json.dumps([r.body for r in records]))
            self.assertNotIn(SECRET, repr(records))

    def test_unknown_path_is_404(self):
        with tf.fake_bot_services() as s:
            status, _, _ = tf.http_request("GET", s.base_url + "/nope")
            self.assertEqual(status, 404)


class FakeConnectorTests(unittest.TestCase):
    def test_scripted_429_then_200(self):
        conv = "19:channelfixture0001@thread.tacv2;messageid=1712345670000"
        payload = {"type": "message", "text": "hello", "textFormat": "markdown"}
        with tf.fake_bot_services() as s:
            s.script("connector", (429, {"Retry-After": "1"}), 200)
            url = f"{s.connector_url}v3/conversations/{conv}/activities"
            headers = {"Authorization": "Bearer fake-access-token-1", "Content-Type": "application/json"}

            status1, headers1, _ = tf.http_request("POST", url, json_body=payload, headers=headers)
            status2, _, body2 = tf.http_request("POST", url, json_body=payload, headers=headers)

            self.assertEqual((status1, headers1.get("Retry-After")), (429, "1"))
            self.assertEqual(status2, 200)
            self.assertTrue(body2["id"].startswith("fake-activity-"))

            records = s.requests("connector")
            self.assertEqual(len(records), 2)
            for rec in records:
                self.assertEqual(rec.method, "POST")
                self.assertTrue(rec.has_authorization)
                self.assertEqual(rec.headers.get("Authorization"), "<present>")
                self.assertNotIn("fake-access-token-1", repr(rec))
                self.assertEqual(rec.body, payload)
                self.assertTrue(rec.path.startswith("/v3/conversations/19:channelfixture0001@thread.tacv2"))

    def test_reply_path_and_missing_authorization_recorded(self):
        with tf.fake_bot_services() as s:
            s.script("connector", 502, 504)
            base = f"{s.connector_url}v3/conversations/a:abc/activities"
            self.assertEqual(tf.http_request("POST", base, json_body={"type": "message"})[0], 502)
            self.assertEqual(tf.http_request("POST", base + "/1712345678901", json_body={"type": "message"})[0], 504)
            status, _, body = tf.http_request("POST", base + "/1712345678901", json_body={"type": "message"})
            self.assertEqual(status, 200)
            self.assertIn("id", body)
            records = s.requests("connector")
            self.assertFalse(records[0].has_authorization)
            self.assertTrue(records[2].path.endswith("/activities/1712345678901"))


if __name__ == "__main__":
    unittest.main()
