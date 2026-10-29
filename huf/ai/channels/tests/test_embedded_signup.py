"""BE-ESIGNUP: Meta Embedded Signup (direct / broker / broker_server), Graph calls mocked."""

from __future__ import annotations

import secrets
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.channels import embedded_signup as es

TOKEN = "EAAB" + "x" * 40
CODE = "AQD-one-time-code-123"
WABA = "1122334455667788"
PHONE = "9988776655443322"
APP_SECRET = "app-secret-" + "s" * 16
BROKER_KEY = "hsk_brokerkey_" + "k" * 20
MOD = "huf.ai.channels.embedded_signup"


def resp(status=200, body=None):
	r = MagicMock()
	r.status_code = status
	r.json.return_value = body if body is not None else {}
	return r


class FakeRequests:
	"""Routes requests.get/post by URL; records calls."""

	def __init__(self, *, oauth=None, subscribe=None, register=None, broker=None):
		self.calls = []
		self.oauth = oauth or resp(200, {"access_token": TOKEN})
		self.subscribe = subscribe or resp(200, {"success": True})
		self.register = register or resp(200, {"success": True})
		self.broker = broker or resp(200, {"access_token": TOKEN, "webhook_signing_secret": "sig-" + "z" * 20})

	def get(self, url, **kw):
		self.calls.append(("GET", url, kw))
		assert kw.get("timeout")
		return self.oauth

	def post(self, url, **kw):
		self.calls.append(("POST", url, kw))
		assert kw.get("timeout")
		if url.endswith("/subscribed_apps"):
			return self.subscribe
		if url.endswith("/register"):
			return self.register
		return self.broker

	def urls(self, method):
		return [c[1] for c in self.calls if c[0] == method]


def configure(**over):
	s = frappe.get_single(es.SETTINGS)
	s.enabled = 1
	s.mode = "direct"
	s.facebook_app_id = "424242"
	s.config_id = "cfg-1"
	s.graph_version = "v21.0"
	s.app_secret = APP_SECRET
	s.broker_url = ""
	s.tenant_id = ""
	s.broker_api_key = ""
	s.allowed_tenants = []
	for k, v in over.items():
		s.set(k, v)
	s.save(ignore_permissions=True)
	return s


class _Base(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		self.created = []

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.flags.pop("huf_es_test", None)
		super().tearDown()

	def all_text(self):
		rows = frappe.get_all("Error Log", fields=["method", "error"], order_by="creation desc", limit=20)
		return " ".join(f"{r.method} {r.error}" for r in rows)


class TestConfig(_Base):
	def test_config_has_no_secrets_and_gates_enabled(self):
		configure()
		cfg = es.get_signup_config()
		self.assertEqual(set(cfg), {"enabled", "app_id", "config_id", "graph_version"})
		self.assertTrue(cfg["enabled"])
		self.assertNotIn(APP_SECRET, str(cfg))
		configure(enabled=0)
		self.assertFalse(es.get_signup_config()["enabled"])
		configure(app_secret="")
		frappe.db.set_single_value(es.SETTINGS, "app_secret", "")
		self.assertFalse(es.get_signup_config()["enabled"])

	def test_permission(self):
		configure()
		user = "esignup_plain@example.com"
		if not frappe.db.exists("User", user):
			frappe.get_doc({"doctype": "User", "email": user, "first_name": "Plain", "send_welcome_email": 0}).insert(
				ignore_permissions=True
			)
		frappe.set_user(user)
		with self.assertRaises(frappe.PermissionError):
			es.get_signup_config()
		with self.assertRaises(frappe.PermissionError):
			es.complete_signup(CODE, WABA, PHONE)
		with self.assertRaises(frappe.PermissionError):
			es.save_settings({"enabled": 1})

	def test_settings_admin_hides_secrets_and_write_only(self):
		configure()
		view = es.get_settings_admin()
		self.assertTrue(view["app_secret_set"])
		self.assertNotIn(APP_SECRET, str(view))
		es.save_settings({"config_id": "cfg-2", "app_secret": ""})
		self.assertEqual(frappe.get_single(es.SETTINGS).get_password("app_secret"), APP_SECRET)
		es.save_settings({"app_secret": "new-secret-value-1"})
		self.assertEqual(frappe.get_single(es.SETTINGS).get_password("app_secret"), "new-secret-value-1")


class TestCompleteSignupDirect(_Base):
	def tearDown(self):
		for gw in self.created:
			settings = frappe.db.get_value("Gateway", gw, "integration_settings")
			frappe.delete_doc("Gateway", gw, force=True, ignore_permissions=True)
			if settings:
				frappe.delete_doc("Integration Settings", settings, force=True, ignore_permissions=True)
		super().tearDown()

	def run_signup(self, fake=None, **kw):
		fake = fake or FakeRequests()
		with patch(f"{MOD}.requests", fake):
			out = es.complete_signup(CODE, WABA, PHONE, **kw)
		self.created.append(out["gateway"])
		return out, fake

	def test_direct_flow(self):
		configure()
		name = "ES Gateway " + secrets.token_hex(3)
		out, fake = self.run_signup(gateway_name=name)
		# exchange
		self.assertEqual(fake.urls("GET"), ["https://graph.facebook.com/v21.0/oauth/access_token"])
		params = fake.calls[0][2]["params"]
		self.assertEqual((params["client_id"], params["client_secret"], params["code"]), ("424242", APP_SECRET, CODE))
		# subscribe + register
		self.assertIn(f"https://graph.facebook.com/v21.0/{WABA}/subscribed_apps", fake.urls("POST"))
		reg = [c for c in fake.calls if c[1].endswith(f"/{PHONE}/register")][0]
		self.assertEqual(reg[2]["json"]["messaging_product"], "whatsapp")
		self.assertRegex(reg[2]["json"]["pin"], r"^\d{6}$")
		self.assertEqual(reg[2]["headers"]["Authorization"], f"Bearer {TOKEN}")
		self.assertEqual(out["pin"], reg[2]["json"]["pin"])
		# gateway + credential store
		self.assertEqual(out["gateway"], name)
		gw = frappe.get_doc("Gateway", name)
		self.assertEqual(gw.provider, "WhatsApp")
		self.assertTrue(gw.is_enabled)
		creds = frappe.get_doc("Integration Settings", gw.integration_settings)
		stored = {r.key: r.get_password("value") for r in creds.credentials}
		self.assertEqual(stored["access_token"], TOKEN)
		self.assertEqual(stored["phone_number_id"], PHONE)
		self.assertEqual(stored["business_account_id"], WABA)
		self.assertEqual(stored["app_secret"], APP_SECRET)
		# return shape; token/secrets never returned
		self.assertEqual({"gateway", "setup_stage", "webhook_url", "verify_token_hint", "warnings", "pin"}, set(out))
		blob = str(out)
		for secret in (TOKEN, APP_SECRET, stored["webhook_verify_token"]):
			self.assertNotIn(secret, blob)
		self.assertIn("handle_gateway_webhook", out["webhook_url"])

	def test_given_pin_not_echoed_and_rerun_updates(self):
		configure()
		name = "ES Gateway " + secrets.token_hex(3)
		out, _ = self.run_signup(gateway_name=name, pin="123456")
		self.assertNotIn("pin", out)
		n_settings = frappe.db.count("Integration Settings")
		out2, _f = self.run_signup(gateway_name=name, pin="123456")
		self.assertEqual(out2["gateway"], name)
		self.assertEqual(frappe.db.count("Integration Settings"), n_settings)

	def test_register_failure_is_warning_not_fatal(self):
		configure()
		fake = FakeRequests(register=resp(400, {"error": {"message": f"bad pin for {TOKEN}", "code": 100}}))
		out, _f = self.run_signup(fake, gateway_name="ES Gateway " + secrets.token_hex(3))
		self.assertEqual(len(out["warnings"]), 1)
		self.assertNotIn(TOKEN, str(out))

	def test_exchange_failure_no_gateway_and_no_secret_in_error_log(self):
		configure()
		fake = FakeRequests(oauth=resp(400, {"error": {"message": f"Invalid code {CODE} {APP_SECRET}", "code": 100}}))
		before = frappe.db.count("Gateway")
		with patch(f"{MOD}.requests", fake):
			with self.assertRaises(frappe.ValidationError) as cm:
				es.complete_signup(CODE, WABA, PHONE, gateway_name="ES Never")
		self.assertEqual(frappe.db.count("Gateway"), before)
		for secret in (APP_SECRET, CODE):
			self.assertNotIn(secret, str(cm.exception))
			self.assertNotIn(secret, self.all_text())

	def test_network_exception_is_redacted(self):
		configure()
		fake = FakeRequests()
		fake.get = MagicMock(side_effect=RuntimeError(f"boom ?client_secret={APP_SECRET}&code={CODE}"))
		with patch(f"{MOD}.requests", fake):
			with self.assertRaises(frappe.ValidationError) as cm:
				es.complete_signup(CODE, WABA, PHONE)
		self.assertNotIn(APP_SECRET, str(cm.exception))
		self.assertNotIn(APP_SECRET, self.all_text())

	def test_disabled_and_bad_ids(self):
		configure(enabled=0)
		with self.assertRaises(frappe.ValidationError):
			es.complete_signup(CODE, WABA, PHONE)
		configure()
		with self.assertRaises(frappe.ValidationError):
			es.complete_signup(CODE, "abc", PHONE)
		with self.assertRaises(frappe.ValidationError):
			es.complete_signup(CODE, WABA, PHONE, pin="12")

	def test_broker_mode(self):
		configure(mode="broker", broker_url="https://cloud.huf.example/api/method/huf.ai.channels.embedded_signup.broker_exchange",
			tenant_id="acme", broker_api_key=BROKER_KEY, app_secret="")
		out, fake = self.run_signup(gateway_name="ES Gateway " + secrets.token_hex(3))
		post = fake.calls[0]
		self.assertTrue(post[1].startswith("https://cloud.huf.example/"))
		self.assertEqual(post[2]["json"], {"code": CODE, "waba_id": WABA, "phone_number_id": PHONE})
		self.assertEqual(post[2]["headers"]["Authorization"], f"Bearer {BROKER_KEY}")
		self.assertEqual(post[2]["headers"]["X-Huf-Tenant"], "acme")
		self.assertEqual(fake.urls("GET"), [])
		creds = frappe.get_doc("Integration Settings", frappe.db.get_value("Gateway", out["gateway"], "integration_settings"))
		self.assertEqual({r.key: r.get_password("value") for r in creds.credentials}["access_token"], TOKEN)
		self.assertNotIn(TOKEN, str(out))

	def test_broker_requires_https(self):
		configure(mode="broker", broker_url="http://insecure.example/x", tenant_id="acme", broker_api_key=BROKER_KEY)
		with patch.dict(frappe.conf, {"developer_mode": 0}):
			with patch(f"{MOD}.requests", FakeRequests()):
				with self.assertRaises(frappe.ValidationError):
					es.complete_signup(CODE, WABA, PHONE)


class TestBrokerServer(_Base):
	def setUp(self):
		super().setUp()
		configure(mode="broker_server")
		self.key = es.create_tenant_key("acme", "https://acme.example")["api_key"]
		self._req = getattr(frappe.local, "request", None)
		self._form = frappe.local.form_dict
		frappe.local.request_ip = f"10.{secrets.randbelow(250)}.{secrets.randbelow(250)}.{secrets.randbelow(250)}"

	def tearDown(self):
		frappe.local.request = self._req
		frappe.local.form_dict = self._form
		super().tearDown()

	def call(self, *, tenant="acme", key=None, https=True, code=CODE, fake=None, developer=False):
		headers = {"X-Huf-Tenant": tenant}
		k = self.key if key is None else key
		if k:
			headers["Authorization"] = f"Bearer {k}"
		if https:
			headers["X-Forwarded-Proto"] = "https"
		frappe.local.request = SimpleNamespace(headers=headers, scheme="http", method="POST")
		frappe.local.form_dict = frappe._dict(code=code, waba_id=WABA, cmd="x")
		with patch(f"{MOD}.requests", fake or FakeRequests()), patch.dict(frappe.conf, {"developer_mode": 1 if developer else 0}):
			return es.broker_exchange()

	def audit(self):
		return frappe.get_all("Embedded Signup Audit", fields=["outcome", "reason", "tenant_id"], order_by="creation desc", limit=3)

	def test_accepts_valid_tenant_and_audits_without_token(self):
		fake = FakeRequests()
		out = self.call(fake=fake)
		self.assertEqual(out["access_token"], TOKEN)
		self.assertNotEqual(out["webhook_signing_secret"], APP_SECRET)
		self.assertNotIn(APP_SECRET, str(out))
		row = self.audit()[0]
		self.assertEqual((row.outcome, row.tenant_id), ("Success", "acme"))
		self.assertNotIn(TOKEN, str(frappe.get_all("Embedded Signup Audit", fields=["*"])))
		self.assertEqual(fake.urls("GET"), ["https://graph.facebook.com/v21.0/oauth/access_token"])

	def test_stored_hash_not_plaintext(self):
		row = frappe.get_single(es.SETTINGS).allowed_tenants[0]
		self.assertEqual(row.api_key_hash, es.hash_api_key(self.key))
		self.assertNotEqual(row.api_key_hash, self.key)

	def test_rejects_bad_key_unknown_tenant_missing_key(self):
		for kw in ({"key": "wrong"}, {"tenant": "ghost"}, {"tenant": ""}):
			with self.assertRaises(frappe.AuthenticationError):
				self.call(**kw)
		self.assertEqual(self.audit()[0].outcome, "Rejected")

	def test_rejects_disabled_tenant(self):
		s = frappe.get_single(es.SETTINGS)
		s.allowed_tenants[0].enabled = 0
		s.save(ignore_permissions=True)
		with self.assertRaises(frappe.AuthenticationError):
			self.call()

	def test_https_rule(self):
		with self.assertRaises(frappe.PermissionError):
			self.call(https=False)
		self.assertEqual(self.audit()[0].reason, "https_required")
		self.assertEqual(self.call(https=False, developer=True)["access_token"], TOKEN)

	def test_not_in_broker_server_mode(self):
		configure(mode="direct")
		with self.assertRaises(frappe.PermissionError):
			self.call()

	def test_meta_failure_is_audited_and_not_leaky(self):
		fake = FakeRequests(oauth=resp(400, {"error": {"message": f"bad {CODE}", "code": 100}}))
		with self.assertRaises(frappe.ValidationError) as cm:
			self.call(fake=fake)
		self.assertNotIn(CODE, str(cm.exception))
		self.assertNotIn(CODE, self.all_text())
		self.assertEqual(self.audit()[0].outcome, "Failed")
