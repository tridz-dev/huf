import json
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.path.insert(0, "huf/ai/tests")
import _stub_env  # noqa: E402

_stub_env.install()

import frappe  # noqa: E402
import pytest  # noqa: E402

from huf.ai.gateways import slack_api  # noqa: E402

# Under the stub, @frappe.whitelist() is a MagicMock call that would replace the endpoints;
# import with an identity decorator, then restore the shared stub attribute.
_original_whitelist = frappe.whitelist
frappe.whitelist = lambda *a, **k: (lambda fn: fn)
sys.modules.pop("huf.ai.gateways.slack_setup", None)
try:
	from huf.ai.gateways import slack_setup  # noqa: E402
finally:
	frappe.whitelist = _original_whitelist


class Perm(Exception):
	pass


class Thrown(Exception):
	pass


class FakeCache:
	def __init__(self):
		self.d = {}

	def set_value(self, k, v, expires_in_sec=None):
		self.d[k] = v

	def get_value(self, k):
		return self.d.get(k)


class Row:
	def __init__(self, key, value):
		self.key = key
		self._v = value

	def get_password(self, _f):
		return self._v


GW = "slack-main"


@pytest.fixture
def env(monkeypatch):
	cache = FakeCache()
	state = SimpleNamespace(roles=["System Manager"], has_perm=False, token="xoxb-secret-1",
		secret="sign-secret-1", provider="Slack", cache=cache)
	monkeypatch.setattr(frappe, "cache", lambda: cache)
	monkeypatch.setattr(frappe, "get_roles", lambda: state.roles)
	monkeypatch.setattr(frappe, "has_permission", lambda *a, **k: state.has_perm)
	monkeypatch.setattr(frappe, "PermissionError", Perm, raising=False)

	def throw(msg, exc=None, *a, **k):
		raise (exc or Thrown)(msg)

	monkeypatch.setattr(frappe, "throw", throw)
	monkeypatch.setattr(frappe.utils, "get_url", lambda: "https://huf.example.com/", raising=False)

	def get_doc(doctype, name=None):
		if doctype == "Gateway":
			return SimpleNamespace(name=name, gateway_name="My Slack", provider=state.provider,
				integration_settings="IS-1")
		creds = []
		if state.token:
			creds.append(Row("token", state.token))
		if state.secret:
			creds.append(Row("signing_secret", state.secret))
		return SimpleNamespace(credentials=creds)

	monkeypatch.setattr(frappe, "get_doc", get_doc)
	state.api = MagicMock()
	state.api.last_headers = {}
	monkeypatch.setattr(slack_setup, "get_slack_api", lambda gw: state.api)
	state.info = {"team": "Acme", "missing_scopes": [], "granted_scopes": list(slack_api.REQUIRED_BOT_SCOPES)}
	monkeypatch.setattr(slack_api, "inspect_token", lambda api: state.info)
	return state


def by_id(checks):
	return {c["id"]: c for c in checks}


# ---- manifest ----------------------------------------------------------
def test_manifest_scopes_and_events(env):
	m = slack_setup.get_slack_manifest(GW)
	assert m["oauth_config"]["scopes"]["bot"] == slack_api.REQUIRED_BOT_SCOPES
	assert m["settings"]["event_subscriptions"]["bot_events"] == [
		"message.channels", "message.groups", "message.im", "message.mpim", "app_mention"]


def test_manifest_request_url(env):
	m = slack_setup.get_slack_manifest(GW)
	assert m["settings"]["event_subscriptions"]["request_url"] == (
		"https://huf.example.com/api/method/huf.ai.gateways.slack_events.handle_slack_event?gateway_name=slack-main")


def test_manifest_url_encodes_gateway_name(env):
	m = slack_setup.get_slack_manifest("my gw")
	assert m["settings"]["event_subscriptions"]["request_url"].endswith("gateway_name=my%20gw")


def test_manifest_interactivity_and_flags(env):
	s = slack_setup.get_slack_manifest(GW)["settings"]
	assert s["interactivity"]["is_enabled"] is True
	assert s["interactivity"]["request_url"].endswith("slack_interactivity.handle_slack_interaction?gateway_name=slack-main")
	assert s["org_deploy_enabled"] is False
	assert s["socket_mode_enabled"] is False


def test_manifest_has_no_secrets_and_is_json(env):
	text = json.dumps(slack_setup.get_slack_manifest(GW))
	assert "xoxb" not in text and "sign-secret" not in text


def test_manifest_display_name_trimmed(env, monkeypatch):
	orig = frappe.get_doc

	def doc(dt, name=None):
		d = orig(dt, name)
		if dt == "Gateway":
			d.gateway_name = "x" * 80
		return d

	monkeypatch.setattr(frappe, "get_doc", doc)
	m = slack_setup.get_slack_manifest(GW)
	assert len(m["display_information"]["name"]) == 35


# ---- permission --------------------------------------------------------
def test_permission_denied_everywhere(env):
	env.roles = ["Guest"]
	for call in (
		lambda: slack_setup.get_slack_manifest(GW),
		lambda: slack_setup.verify_slack_setup(GW),
		lambda: slack_setup.send_test_dm(GW, slack_user_id="U123"),
		lambda: slack_setup.get_slack_setup_status(GW),
	):
		with pytest.raises(Perm):
			call()
	env.api.conversations_open.assert_not_called()
	assert env.cache.d == {}


def test_gateway_write_permission_allows(env):
	env.roles = ["Guest"]
	env.has_perm = True
	assert slack_setup.get_slack_manifest(GW)


def test_non_slack_gateway_rejected(env):
	env.provider = "Telegram"
	with pytest.raises(Thrown):
		slack_setup.get_slack_manifest(GW)


# ---- verify ------------------------------------------------------------
def test_verify_all_ok(env):
	env.cache.d[slack_setup.URL_VERIFIED_KEY.format(GW)] = "2026-01-01T00:00:00+00:00"
	checks = slack_setup.verify_slack_setup(GW)
	assert all(c["ok"] for c in checks if not c.get("informational"))
	by_id = {c["id"]: c for c in checks}
	assert by_id["direct_policy"]["status"] == "warn" and by_id["direct_policy"]["informational"]
	assert set(by_id(checks)) == {"token_present", "token_kind", "auth_test", "scopes",
		"signing_secret", "request_url", "slack_connect"}
	assert "Acme" in by_id(checks)["auth_test"]["detail"]


def test_verify_check_shape(env):
	for c in slack_setup.verify_slack_setup(GW):
		assert {"id", "ok", "plain_title", "detail", "how_to_fix"} <= set(c)


def test_verify_no_token(env):
	env.token = ""
	c = by_id(slack_setup.verify_slack_setup(GW))
	assert not c["token_present"]["ok"] and not c["token_kind"]["ok"]
	assert not c["auth_test"]["ok"] and not c["scopes"]["ok"]


def test_verify_rejects_user_token(env):
	env.token = "xoxp-user-token"
	c = by_id(slack_setup.verify_slack_setup(GW))
	assert not c["token_kind"]["ok"]
	assert "xoxb-" in c["token_kind"]["how_to_fix"]
	assert not c["auth_test"]["ok"]
	env.api.auth_test.assert_not_called()


def test_verify_unknown_token_shape(env):
	env.token = "garbage"
	assert not by_id(slack_setup.verify_slack_setup(GW))["token_kind"]["ok"]


def test_verify_missing_scopes_listed(env):
	env.info = {"team": "Acme", "missing_scopes": ["im:write", "chat:write"]}
	c = by_id(slack_setup.verify_slack_setup(GW))["scopes"]
	assert not c["ok"] and "im:write" in c["detail"] and "chat:write" in c["detail"]


def test_verify_auth_failure(env, monkeypatch):
	def boom(api):
		raise slack_api.SlackApiError("auth.test", "invalid_auth", 200)

	monkeypatch.setattr(slack_api, "inspect_token", boom)
	c = by_id(slack_setup.verify_slack_setup(GW))
	assert not c["auth_test"]["ok"] and "invalid_auth" in c["auth_test"]["detail"]
	assert not c["scopes"]["ok"]


def test_verify_no_signing_secret(env):
	env.secret = ""
	assert not by_id(slack_setup.verify_slack_setup(GW))["signing_secret"]["ok"]


def test_verify_request_url_not_confirmed(env):
	c = by_id(slack_setup.verify_slack_setup(GW))["request_url"]
	assert not c["ok"] and "Save Request URL" in c["how_to_fix"]


def test_slack_connect_is_informational(env):
	c = by_id(slack_setup.verify_slack_setup(GW))["slack_connect"]
	assert c["ok"] and c["informational"]


def test_verify_caches_result_without_secrets(env):
	slack_setup.verify_slack_setup(GW)
	cached = env.cache.d["huf_slack_verify:" + GW]
	assert cached["all_ok"] is False  # request URL not yet confirmed
	assert "checked_at" in cached
	text = json.dumps(cached)
	assert "xoxb-secret" not in text and "sign-secret" not in text


def test_verify_all_ok_ignores_informational(env):
	env.cache.d[slack_setup.URL_VERIFIED_KEY.format(GW)] = "t"
	slack_setup.verify_slack_setup(GW)
	assert env.cache.d["huf_slack_verify:" + GW]["all_ok"] is True


def test_status_reads_cache(env):
	assert slack_setup.get_slack_setup_status(GW)["verified"] is False
	env.cache.d[slack_setup.URL_VERIFIED_KEY.format(GW)] = "t"
	slack_setup.verify_slack_setup(GW)
	s = slack_setup.get_slack_setup_status(GW)
	assert s["verified"] and s["request_url_verified"] and s["checks"]


# ---- test DM -----------------------------------------------------------
def test_dm_by_user_id(env):
	env.api.conversations_open.return_value = "D1"
	assert slack_setup.send_test_dm(GW, slack_user_id="U012ABC")["ok"]
	env.api.conversations_open.assert_called_once_with(["U012ABC"])
	env.api.post_message.assert_called_once_with("D1", "Huf is connected")


def test_dm_by_email(env):
	env.api.users_lookup_by_email.return_value = "U9XYZ"
	env.api.conversations_open.return_value = "D2"
	slack_setup.send_test_dm(GW, email="a@b.co")
	env.api.conversations_open.assert_called_once_with(["U9XYZ"])


def test_dm_email_not_found(env):
	env.api.users_lookup_by_email.return_value = None
	with pytest.raises(Thrown):
		slack_setup.send_test_dm(GW, email="a@b.co")
	env.api.post_message.assert_not_called()


@pytest.mark.parametrize("uid", ["C0123456", "general", "#general", "U1", "U12 34", "u012abc"])
def test_dm_rejects_non_user_targets(env, uid):
	with pytest.raises(Thrown):
		slack_setup.send_test_dm(GW, slack_user_id=uid)
	env.api.post_message.assert_not_called()


def test_dm_requires_exactly_one_target(env):
	for kw in ({}, {"slack_user_id": "U012ABC", "email": "a@b.co"}):
		with pytest.raises(Thrown):
			slack_setup.send_test_dm(GW, **kw)
	env.api.post_message.assert_not_called()


def test_dm_bad_email(env):
	with pytest.raises(Thrown):
		slack_setup.send_test_dm(GW, email="nope")


def test_dm_refuses_user_token(env):
	env.token = "xoxp-user"
	with pytest.raises(Thrown):
		slack_setup.send_test_dm(GW, slack_user_id="U012ABC")
	env.api.post_message.assert_not_called()


def test_dm_slack_error_is_plain_and_secret_free(env):
	env.api.conversations_open.side_effect = slack_api.SlackApiError("conversations.open", "missing_scope")
	with pytest.raises(Thrown) as e:
		slack_setup.send_test_dm(GW, slack_user_id="U012ABC")
	assert "missing_scope" in str(e.value) and "xoxb" not in str(e.value)


# ---- slack_events url_verification cache write --------------------------
def _import_slack_events(monkeypatch):
	"""Import slack_events with scoped stubs (monkeypatch undoes every sys.modules change)."""
	import types

	if "frappe.rate_limiter" not in sys.modules:
		rl = types.ModuleType("frappe.rate_limiter")
		rl.rate_limit = lambda *a, **k: (lambda fn: fn)
		monkeypatch.setitem(sys.modules, "frappe.rate_limiter", rl)
	if "huf.ai.gateway_service" not in sys.modules:
		gs = types.ModuleType("huf.ai.gateway_service")
		gs.ingest_gateway_event = MagicMock()
		monkeypatch.setitem(sys.modules, "huf.ai.gateway_service", gs)
	# Always give the challenge response a plain fake so the result does not depend on werkzeug.
	w, wr = types.ModuleType("werkzeug"), types.ModuleType("werkzeug.wrappers")
	wr.Response = lambda body, status=200, mimetype=None: SimpleNamespace(body=body, status=status)
	w.wrappers = wr
	monkeypatch.setitem(sys.modules, "werkzeug", w)
	monkeypatch.setitem(sys.modules, "werkzeug.wrappers", wr)

	monkeypatch.setattr(frappe, "whitelist", lambda *a, **k: (lambda fn: fn))
	monkeypatch.delitem(sys.modules, "huf.ai.gateways.slack_events", raising=False)
	from huf.ai.gateways import slack_events

	monkeypatch.delitem(sys.modules, "huf.ai.gateways.slack_events", raising=False)
	return slack_events


def _post(monkeypatch, payload, signature_error=None):
	events = _import_slack_events(monkeypatch)
	body = json.dumps(payload).encode()
	req = SimpleNamespace(get_data=lambda as_text=False: body, headers={}, args={"gateway_name": GW})
	monkeypatch.setattr(frappe, "request", req, raising=False)
	monkeypatch.setattr(events, "_verify_slack_signature", lambda *a, **k: signature_error)
	monkeypatch.setattr(frappe.local, "response", SimpleNamespace(), raising=False)
	return events.handle_slack_event()


def test_url_verification_records_cache(env, monkeypatch):
	res = _post(monkeypatch, {"type": "url_verification", "challenge": "abc"})
	assert "abc" in res.body
	assert env.cache.d["huf_slack_url_verified:" + GW]


def test_url_verification_unsigned_does_not_record(env, monkeypatch):
	_post(monkeypatch, {"type": "url_verification", "challenge": "abc"}, "bad_signature")
	assert "huf_slack_url_verified:" + GW not in env.cache.d


def test_recorded_url_verification_satisfies_verify_check(env, monkeypatch):
	_post(monkeypatch, {"type": "url_verification", "challenge": "abc"})
	assert by_id(slack_setup.verify_slack_setup(GW))["request_url"]["ok"]


def test_scoped_stubs_do_not_leak(env, monkeypatch):
	keys = ("huf.ai.gateway_service", "frappe.rate_limiter", "werkzeug", "werkzeug.wrappers",
		"huf.ai.gateways.slack_events")
	before = {k: sys.modules.get(k) for k in keys}
	whitelist = frappe.whitelist
	with monkeypatch.context() as m:
		_post(m, {"type": "url_verification", "challenge": "abc"})
	assert {k: sys.modules.get(k) for k in keys} == before
	assert frappe.whitelist is whitelist
