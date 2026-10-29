"""Credential problems are told apart: missing, rejected by the provider, or lacking a permission."""

import json
from unittest.mock import MagicMock, patch

import httpx
from frappe.tests import IntegrationTestCase

from huf.ai.tools import gmail, google_drive, google_sheets, slack
from huf.ai.tools.connection_test import test_connection
from huf.ai.tools.integration.provider_errors import invalid_recipients, normalize_recipients


def _resp(status: int, body: dict | None = None):
	r = MagicMock()
	r.status_code = status
	r.json.return_value = body if body is not None else {}

	def raise_for_status():
		if status >= 400:
			raise httpx.HTTPStatusError("boom", request=MagicMock(), response=r)

	r.raise_for_status.side_effect = raise_for_status
	return r


SECRET = "s3cret-value"
CREDS = {"client_id": "cid", "client_secret": SECRET, "refresh_token": "rt-" + SECRET}
REJECT_TAIL = "Reconnect Gmail in Integrations."


def _post_router(token_resp, api_resp):
	"""httpx.post is one global: answer the token URL and the API URL separately."""
	return lambda url, *a, **k: token_resp if "oauth2.googleapis.com" in url else api_resp


def _fake_credential(values):
	return lambda service, key, default=None: values.get(key, default)


class TestGmailCredentialErrors(IntegrationTestCase):
	def _send(self, token_resp=None, api_resp=None, creds=CREDS, **kwargs):
		args = {"to": "a@example.com", "subject": "s", "body": "b"}
		args.update(kwargs)
		with patch("huf.ai.tools.gmail.get_credential", side_effect=_fake_credential(dict(creds))), \
			patch("huf.ai.tools.gmail.set_credential"), \
			patch("huf.ai.tools.gmail.update_last_error"), \
			patch("httpx.post", side_effect=_post_router(token_resp, api_resp)) as post:
			out = json.loads(gmail.handle_send_email(**args))
			api_post = MagicMock(call_count=sum(1 for c in post.call_args_list if "gmail.googleapis.com" in c[0][0]))
			api_post.assert_not_called = lambda: self.assertEqual(api_post.call_count, 0)
			api_post.assert_called_once = lambda: self.assertEqual(api_post.call_count, 1)
			return out, api_post

	def test_missing_credentials(self):
		out, _ = self._send(creds={})
		self.assertFalse(out["success"])
		self.assertEqual(out["error"], "Gmail is not connected: add the client ID, client secret and refresh token in Integrations.")

	def test_invalid_grant(self):
		out, _ = self._send(token_resp=_resp(400, {"error": "invalid_grant", "error_description": "Token has been expired or revoked."}))
		self.assertEqual(out["error"], "Gmail rejected the saved credentials (token expired or revoked). " + REJECT_TAIL)

	def test_invalid_client(self):
		out, _ = self._send(token_resp=_resp(401, {"error": "invalid_client"}))
		self.assertEqual(out["error"], "Gmail rejected the saved credentials (the client ID or client secret is wrong). " + REJECT_TAIL)

	def test_unauthorized_client(self):
		out, _ = self._send(token_resp=_resp(400, {"error": "unauthorized_client"}))
		self.assertIn("this client is not allowed to use the requested access", out["error"])
		self.assertTrue(out["error"].endswith(REJECT_TAIL))

	def test_google_unreachable_or_down(self):
		out, _ = self._send(token_resp=_resp(503))
		self.assertIn("Google is not responding", out["error"])

	def test_api_401_means_rejected(self):
		out, _ = self._send(token_resp=_resp(200, {"access_token": "at", "expires_in": 3600}), api_resp=_resp(401, {"error": {"message": "Invalid Credentials"}}))
		self.assertEqual(out["error"], "Gmail rejected the saved credentials (token expired or revoked). " + REJECT_TAIL)

	def test_insufficient_scopes(self):
		body = {"error": {"code": 403, "message": "Request had insufficient authentication scopes.", "status": "PERMISSION_DENIED",
			"details": [{"reason": "ACCESS_TOKEN_SCOPE_INSUFFICIENT"}]}}
		out, _ = self._send(token_resp=_resp(200, {"access_token": "at", "expires_in": 3600}), api_resp=_resp(403, body))
		self.assertEqual(out["error"], "Gmail needs the gmail.send permission: reconnect with that scope.")

	def test_no_secret_leaks(self):
		for token_resp in (_resp(400, {"error": "invalid_grant", "error_description": SECRET}), _resp(401, {"error": "invalid_client"})):
			out, _ = self._send(token_resp=token_resp)
			self.assertNotIn(SECRET, json.dumps(out))
			self.assertNotIn("rt-", json.dumps(out))

	def test_invalid_recipient_never_calls_gmail(self):
		out, api_post = self._send(to="not-an-email")
		self.assertFalse(out["success"])
		self.assertIn("valid email address", out["error"])
		api_post.assert_not_called()

	def test_semicolon_list_is_sent_comma_joined(self):
		ok = _resp(200, {"id": "1"})
		out, api_post = self._send(token_resp=_resp(200, {"access_token": "at", "expires_in": 3600}), api_resp=ok, to="a@example.com; B <b@example.org>")
		self.assertTrue(out["success"])
		api_post.assert_called_once()


class TestRecipientHelpers(IntegrationTestCase):
	def test_valid_lists(self):
		for value in ("a@b.co", "a@b.co, c@d.org", "a@b.co;c@d.org", "Ann <a@b.co>"):
			self.assertEqual(invalid_recipients(value), [], value)

	def test_invalid_entries(self):
		self.assertEqual(invalid_recipients("not-an-email"), ["not-an-email"])
		self.assertEqual(invalid_recipients("a@b.co, nope"), ["nope"])
		self.assertEqual(invalid_recipients("a@b"), ["a@b"])
		self.assertTrue(invalid_recipients(""))

	def test_normalize(self):
		self.assertEqual(normalize_recipients("a@b.co; c@d.org,e@f.io"), "a@b.co, c@d.org, e@f.io")


class TestSlackAndGoogleErrors(IntegrationTestCase):
	def test_slack_missing_token(self):
		with patch("huf.ai.tools.slack.get_credential", return_value=None), patch("huf.ai.tools.slack.update_last_error"):
			out = json.loads(slack.handle_send_message(channel="C1", text="hi"))
		self.assertEqual(out["error"], "Slack is not connected: add the bot token in Integrations.")

	def _slack(self, body):
		# A channel written as an ID passes through untouched. Anything else is looked up by name with a
		# GET to conversations.list, so a short fake like "C1" would reach the real Slack: the GET is
		# patched to fail loudly so these tests can never touch the network.
		def no_network(*args, **kwargs):
			raise AssertionError("test reached the network: " + str(args[:1]))

		with patch("huf.ai.tools.slack.get_credential", return_value="xoxb-fake"), patch("huf.ai.tools.slack.update_last_error"), \
			patch("httpx.get", side_effect=no_network), patch("httpx.post", return_value=_resp(200, body)):
			return json.loads(slack.handle_send_message(channel="C01234567", text="hi"))["error"]

	def test_slack_revoked(self):
		self.assertEqual(self._slack({"ok": False, "error": "token_revoked"}),
			"Slack rejected the saved token (token revoked). Reconnect Slack in Integrations.")

	def test_slack_invalid_auth(self):
		self.assertIn("rejected the saved token", self._slack({"ok": False, "error": "invalid_auth"}))

	def test_slack_missing_scope(self):
		msg = self._slack({"ok": False, "error": "missing_scope", "needed": "chat:write", "provided": "channels:read"})
		self.assertIn("Slack needs the chat:write permission", msg)

	def test_slack_channel_not_found(self):
		self.assertIn("could not find that channel", self._slack({"ok": False, "error": "channel_not_found"}))

	def _google(self, module, handler, token_resp, api_resp=None, **kwargs):
		with patch.object(module, "get_credential", side_effect=_fake_credential(dict(CREDS))), patch.object(module, "update_last_error"), \
			patch("httpx.post", return_value=token_resp), \
			patch.object(module.requests, "get", return_value=api_resp), patch.object(module.requests, "put", return_value=api_resp):
			return json.loads(handler(**kwargs))["error"]

	def test_sheets_revoked(self):
		msg = self._google(google_sheets, google_sheets.handle_read_sheet, _resp(400, {"error": "invalid_grant"}), spreadsheet_id="x")
		self.assertEqual(msg, "Google Sheets rejected the saved credentials (token expired or revoked). Reconnect Google Sheets in Integrations.")

	def test_drive_revoked(self):
		msg = self._google(google_drive, google_drive.handle_list_files, _resp(400, {"error": "invalid_client"}))
		self.assertIn("Google Drive rejected the saved credentials", msg)

	def test_sheets_scope_and_not_found(self):
		ok = _resp(200, {"access_token": "at"})
		scope = {"error": {"status": "PERMISSION_DENIED", "message": "Request had insufficient authentication scopes."}}
		self.assertEqual(self._google(google_sheets, google_sheets.handle_read_sheet, ok, _resp(403, scope), spreadsheet_id="x"),
			"Google Sheets needs the spreadsheets permission: reconnect with that scope.")
		self.assertIn("could not find that spreadsheet", self._google(google_sheets, google_sheets.handle_read_sheet, ok, _resp(404), spreadsheet_id="x"))

	def test_drive_scope(self):
		ok = _resp(200, {"access_token": "at"})
		scope = {"error": {"status": "PERMISSION_DENIED", "errors": [{"reason": "insufficientPermissions"}]}}
		self.assertIn("needs the drive.readonly permission", self._google(google_drive, google_drive.handle_list_files, ok, _resp(403, scope)))


class TestConnectionTest(IntegrationTestCase):
	def _run(self, service, creds, token_resp=None, api_resp=None, post_body=None):
		router = (lambda url, *a, **k: _resp(200, post_body)) if post_body is not None else _post_router(token_resp, api_resp)
		with patch("httpx.post", side_effect=router), \
			patch("httpx.get", return_value=api_resp) as get:
			return test_connection(service=service, credentials=creds), get

	def test_gmail_connected_reads_profile_only(self):
		out, get = self._run("gmail", CREDS, _resp(200, {"access_token": "at"}), _resp(200, {"emailAddress": "me@example.com"}))
		self.assertEqual(
			out,
			{"status": "Connected", "code": "ok", "message": "Connected to Gmail as me@example.com.", "account": "me@example.com"},
		)
		self.assertTrue(get.call_args[0][0].endswith("/users/me/profile"))

	def test_gmail_rejected(self):
		out, _ = self._run("gmail", CREDS, _resp(400, {"error": "invalid_grant"}))
		self.assertEqual(out["status"], "Rejected")
		self.assertEqual(out["code"], "rejected")
		self.assertIn("token expired or revoked", out["message"])
		# on the Integrations screen the next step is a sentence, not "Reconnect Gmail in Integrations"
		self.assertNotIn("in Integrations", out["message"])
		self.assertNotIn(SECRET, json.dumps(out))

	def test_nothing_saved_is_not_connected_not_rejected(self):
		out, get = self._run("gmail", {})
		self.assertEqual((out["status"], out["code"]), ("Not connected", "no_credentials"))
		self.assertTrue(out["message"].startswith("No credentials saved yet"))
		self.assertNotIn("wrong", out["message"])
		get.assert_not_called()

	def test_partly_filled_names_what_is_missing(self):
		out, _ = self._run("gmail", {"client_id": "cid"})
		self.assertEqual((out["status"], out["code"]), ("Not connected", "missing_credentials"))
		self.assertIn("the client secret and the refresh token", out["message"])

	def test_slack_nothing_saved(self):
		out, _ = self._run("slack", {})
		self.assertEqual((out["status"], out["code"]), ("Not connected", "no_credentials"))
		self.assertIn("bot token", out["message"])

	def test_slack_reports_workspace_as_account(self):
		out, _ = self._run("slack", {"token": "xoxb-fake"}, api_resp=None, post_body={"ok": True, "team": "Tridz", "user": "huf_live"})
		self.assertEqual((out["status"], out["account"]), ("Connected", "Tridz"))

	def test_network_failure_is_unreachable_not_rejected_credentials(self):
		with patch("httpx.post", side_effect=httpx.ConnectError("down")):
			out = test_connection(service="slack", credentials={"token": "xoxb-fake"})
		self.assertEqual(out["code"], "unreachable")

	def test_saved_check_is_remembered_and_clears_the_old_error(self):
		import frappe

		name = frappe.get_all("Integration Settings", filters={"service": "slack"}, pluck="name", limit=1)
		if not name:
			self.skipTest("needs a saved Slack integration")
		before = frappe.db.get_value("Integration Settings", name[0], ["last_error", "last_test_status"], as_dict=True)
		frappe.db.set_value("Integration Settings", name[0], "last_error", "Slack could not find that channel.")
		try:
			with patch("huf.ai.tools.connection_test._resolve_credentials", return_value={"token": "xoxb-fake"}), \
				patch("httpx.post", return_value=_resp(200, {"ok": True, "team": "Tridz", "user": "huf_live"})):
				out = test_connection(service="slack", setting=name[0])
			row = frappe.db.get_value(
				"Integration Settings", name[0], ["last_error", "last_test_status", "account_label"], as_dict=True
			)
			self.assertEqual(out["status"], "Connected")
			self.assertEqual((row.last_test_status, row.account_label), ("Connected", "Tridz"))
			self.assertFalse(row.last_error)
		finally:
			frappe.db.set_value("Integration Settings", name[0], {"last_error": before.last_error, "last_test_status": before.last_test_status})

	def test_gmail_send_only_scope_is_still_connected(self):
		scope = {"error": {"status": "PERMISSION_DENIED", "details": [{"reason": "ACCESS_TOKEN_SCOPE_INSUFFICIENT"}]}}
		out, _ = self._run("gmail", CREDS, _resp(200, {"access_token": "at"}), _resp(403, scope))
		self.assertEqual(out["status"], "Connected")

	def test_not_connected(self):
		out, _ = self._run("gmail", {})
		self.assertEqual(out["status"], "Not connected")

	def test_slack_connected_and_rejected(self):
		out, _ = self._run("slack", {"token": "xoxb-x"}, api_resp=_resp(200, {"ok": True, "team": "Acme", "user": "huf"}))
		self.assertEqual(out["status"], "Connected")
		out, _ = self._run("slack", {"token": "xoxb-x"}, api_resp=_resp(200, {"ok": False, "error": "invalid_auth"}))
		self.assertEqual(out["status"], "Rejected")

	def test_sheets_mints_token_only(self):
		out, get = self._run("google_sheets", CREDS, _resp(200, {"access_token": "at"}))
		self.assertEqual(out["status"], "Connected")
		get.assert_not_called()

	def test_drive_about(self):
		out, get = self._run("google_drive", CREDS, _resp(200, {"access_token": "at"}), _resp(200, {"user": {"emailAddress": "d@example.com"}}))
		self.assertEqual(out["status"], "Connected")
		self.assertIn("/drive/v3/about", get.call_args[0][0])

	def test_unknown_service_refused(self):
		import frappe
		with self.assertRaises(frappe.ValidationError):
			test_connection(service="github")
