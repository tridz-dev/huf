import json
import logging
import sys
from email.utils import formatdate

sys.path.insert(0, "huf/ai/tests")
import _stub_env  # noqa: E402

_stub_env.install()

import pytest  # noqa: E402

from huf.ai.gateways import teams_api as api  # noqa: E402
from huf.ai.gateways.teams_contract import BOT_TOKEN_SCOPE  # noqa: E402

SECRET = "s3cr3t-client-secret"
TOKEN = "tok-abc-123-SENSITIVE"
SVC = "https://smba.trafficmanager.net/emea"
CONV = "19:abc@thread.tacv2;messageid=1700000000000"
CREDS = {"app_id": "app-1", "app_password": SECRET, "tenant_id": "tenant-guid"}


class Resp:
	def __init__(self, status=200, body=None, headers=None):
		self.status_code = status
		self._body = body
		self.headers = headers or {}

	def json(self):
		if self._body is None:
			raise ValueError("no json")
		return self._body


class FakeHttp:
	def __init__(self, *responses):
		self.responses = list(responses)
		self.calls = []

	def __call__(self, method, url, *, headers, json=None, data=None, timeout=10):
		self.calls.append({"method": method, "url": url, "headers": headers, "json": json, "data": data})
		r = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
		if isinstance(r, Exception):
			raise r
		return r


class FakeCache:
	def __init__(self):
		self.store = {}
		self.ttls = {}

	def get_value(self, k):
		return self.store.get(k)

	def set_value(self, k, v, expires_in_sec=None):
		self.store[k] = v
		self.ttls[k] = expires_in_sec

	def delete_value(self, k):
		self.store.pop(k, None)


@pytest.fixture
def cache(monkeypatch):
	c = FakeCache()
	monkeypatch.setattr(api, "_cache", lambda: c)
	return c


def tok_resp(token=TOKEN, expires=3600):
	return Resp(200, {"access_token": token, "expires_in": expires, "token_type": "Bearer"})


NOSLEEP = lambda s: None  # noqa: E731


# ---- token ----
def test_token_acquisition_request_shape(cache):
	http = FakeHttp(tok_resp())
	t = api.get_bot_token(CREDS, http=http, now=lambda: 1000.0, sleep=NOSLEEP)
	assert t == TOKEN
	c = http.calls[0]
	assert c["method"] == "POST"
	assert c["url"] == "https://login.microsoftonline.com/tenant-guid/oauth2/v2.0/token"
	assert c["data"]["grant_type"] == "client_credentials"
	assert c["data"]["client_id"] == "app-1" and c["data"]["scope"] == BOT_TOKEN_SCOPE


def test_token_cached_key_and_ttl(cache):
	http = FakeHttp(tok_resp(expires=3600))
	api.get_bot_token(CREDS, gateway_name="gw1", http=http, now=lambda: 1000.0)
	assert "teams:token:gw1" in cache.store
	assert cache.ttls["teams:token:gw1"] == 3300
	api.get_bot_token(CREDS, gateway_name="gw1", http=http, now=lambda: 1100.0)
	assert len(http.calls) == 1


def test_cache_key_defaults_to_app_id(cache):
	api.get_bot_token(CREDS, http=FakeHttp(tok_resp()), now=lambda: 0.0)
	assert "teams:token:app-1" in cache.store


def test_cache_expiry_refetches(cache):
	http = FakeHttp(tok_resp("t1"), tok_resp("t2"))
	assert api.get_bot_token(CREDS, http=http, now=lambda: 0.0) == "t1"
	assert api.get_bot_token(CREDS, http=http, now=lambda: 3299.0) == "t1"
	assert api.get_bot_token(CREDS, http=http, now=lambda: 3301.0) == "t2"
	assert len(http.calls) == 2


def test_short_lived_token_not_cached(cache):
	api.get_bot_token(CREDS, http=FakeHttp(tok_resp(expires=200)), now=lambda: 0.0)
	assert cache.store == {}


def test_refresh_flag_invalidates(cache):
	http = FakeHttp(tok_resp("t1"), tok_resp("t2"))
	api.get_bot_token(CREDS, http=http, now=lambda: 0.0)
	assert api.get_bot_token(CREDS, http=http, now=lambda: 1.0, refresh=True) == "t2"


def test_token_one_transient_retry_then_ok(cache):
	sleeps = []
	http = FakeHttp(Resp(503, {}), tok_resp())
	assert api.get_bot_token(CREDS, http=http, now=lambda: 0.0, sleep=sleeps.append) == TOKEN
	assert len(http.calls) == 2 and len(sleeps) == 1


def test_token_retry_only_once(cache):
	http = FakeHttp(Resp(503, {}))
	with pytest.raises(api.TeamsApiError) as ei:
		api.get_bot_token(CREDS, http=http, now=lambda: 0.0, sleep=NOSLEEP)
	assert ei.value.status == 503 and len(http.calls) == 2


def test_token_no_retry_on_invalid_client(cache):
	http = FakeHttp(Resp(401, {"error": "invalid_client", "error_description": f"bad {SECRET}"}))
	with pytest.raises(api.TeamsApiError) as ei:
		api.get_bot_token(CREDS, http=http, now=lambda: 0.0, sleep=NOSLEEP)
	assert len(http.calls) == 1 and ei.value.code == "invalid_client"
	assert not api.is_transient(ei.value)


def test_token_missing_access_token(cache):
	with pytest.raises(api.TeamsApiError) as ei:
		api.get_bot_token(CREDS, http=FakeHttp(Resp(200, {"expires_in": 3600})), now=lambda: 0.0)
	assert ei.value.code == "invalid_token_response"


def test_token_missing_or_bad_creds(cache):
	with pytest.raises(api.TeamsApiError) as ei:
		api.get_bot_token({"app_id": "a"}, http=FakeHttp(tok_resp()))
	assert ei.value.code == "missing_credentials"
	with pytest.raises(api.TeamsApiError) as ei:
		api.get_bot_token({**CREDS, "tenant_id": "x/../evil.com?"}, http=FakeHttp(tok_resp()))
	assert ei.value.code == "invalid_tenant_id"


def test_token_transport_error_no_secret(cache):
	http = FakeHttp(RuntimeError(f"boom {SECRET}"))
	with pytest.raises(api.TeamsApiError) as ei:
		api.get_bot_token(CREDS, http=http, now=lambda: 0.0, sleep=NOSLEEP)
	assert SECRET not in str(ei.value) and SECRET not in repr(ei.value)
	assert ei.value.__cause__ is None and ei.value.status == 0 and api.is_transient(ei.value)


# ---- connector ----
def test_post_activity_shape_and_quoting():
	http = FakeHttp(Resp(200, {"id": "act-1"}))
	out = api.post_activity(SVC + "/", CONV, {"type": "message", "text": "hi"}, token=TOKEN, http=http)
	assert out["id"] == "act-1"
	c = http.calls[0]
	assert c["method"] == "POST"
	assert c["url"] == "https://smba.trafficmanager.net/emea/v3/conversations/" + (
		"19%3Aabc%40thread.tacv2%3Bmessageid%3D1700000000000/activities"
	)
	assert c["headers"]["Authorization"] == f"Bearer {TOKEN}"
	assert c["json"] == {"type": "message", "text": "hi"}


def test_url_quoting_blocks_path_injection():
	http = FakeHttp(Resp(200, {"id": "x"}))
	api.post_activity(SVC, "a/../../evil?x=1#f", {}, token=TOKEN, http=http)
	url = http.calls[0]["url"]
	assert "/../" not in url and "?" not in url and "#" not in url
	assert url.endswith("/activities")


def test_missing_id_raises():
	for body in ({}, {"id": ""}, {"id": 5}, None):
		with pytest.raises(api.TeamsApiError) as ei:
			api.post_activity(SVC, CONV, {}, token=TOKEN, http=FakeHttp(Resp(200, body)))
		assert ei.value.code == "missing_activity_id"


def test_update_activity_put_shape():
	http = FakeHttp(Resp(200, {"id": "act-1"}))
	api.update_activity(SVC, CONV, "act;1", {"type": "message"}, token=TOKEN, http=http)
	c = http.calls[0]
	assert c["method"] == "PUT"
	assert c["url"].endswith("/activities/act%3B1") and "/v3/conversations/19%3A" in c["url"]
	assert c["json"] == {"type": "message"}


def test_create_personal_conversation_payload():
	http = FakeHttp(Resp(201, {"id": "a:1conv", "activityId": "x"}))
	cid = api.create_personal_conversation(SVC, "tenant-1", "28:app-1", "aad-user", token=TOKEN, http=http)
	assert cid == "a:1conv"
	c = http.calls[0]
	assert c["method"] == "POST" and c["url"] == "https://smba.trafficmanager.net/emea/v3/conversations"
	assert c["json"] == {
		"bot": {"id": "28:app-1"},
		"isGroup": False,
		"members": [{"id": "aad-user"}],
		"tenantId": "tenant-1",
		"channelData": {"tenant": {"id": "tenant-1"}},
	}


def test_create_conversation_missing_id():
	with pytest.raises(api.TeamsApiError):
		api.create_personal_conversation(SVC, "t", "b", "u", token=TOKEN, http=FakeHttp(Resp(200, {})))


def test_401_triggers_single_retoken(cache):
	tokens = FakeHttp(tok_resp("old"), tok_resp("new"))
	provider = api.make_token_provider(CREDS, http=tokens, now=lambda: 0.0, sleep=NOSLEEP)
	conn = FakeHttp(Resp(401, {}), Resp(200, {"id": "ok"}))
	out = api.post_activity(SVC, CONV, {}, token=provider, http=conn)
	assert out["id"] == "ok" and len(tokens.calls) == 2
	assert [c["headers"]["Authorization"] for c in conn.calls] == ["Bearer old", "Bearer new"]


def test_401_twice_raises_no_loop(cache):
	tokens = FakeHttp(tok_resp("old"), tok_resp("new"))
	provider = api.make_token_provider(CREDS, http=tokens, now=lambda: 0.0)
	conn = FakeHttp(Resp(401, {}))
	with pytest.raises(api.TeamsApiError) as ei:
		api.post_activity(SVC, CONV, {}, token=provider, http=conn)
	assert ei.value.status == 401 and len(conn.calls) == 2 and not api.is_transient(ei.value)


def test_401_with_static_token_no_retry():
	conn = FakeHttp(Resp(401, {}))
	with pytest.raises(api.TeamsApiError):
		api.post_activity(SVC, CONV, {}, token=TOKEN, http=conn)
	assert len(conn.calls) == 1


def test_429_retry_after_seconds():
	conn = FakeHttp(Resp(429, {"error": {"code": "TooManyRequests"}}, {"Retry-After": "7"}))
	with pytest.raises(api.TeamsApiError) as ei:
		api.post_activity(SVC, CONV, {}, token=TOKEN, http=conn, sleep=NOSLEEP)
	assert ei.value.status == 429 and ei.value.retry_after == 7.0 and ei.value.code == "TooManyRequests"
	assert len(conn.calls) == 1 and api.is_transient(ei.value)


def test_429_retry_after_http_date():
	hdr = formatdate(1000 + 42, usegmt=True)
	conn = FakeHttp(Resp(429, {}, {"Retry-After": hdr}))
	with pytest.raises(api.TeamsApiError) as ei:
		api.post_activity(SVC, CONV, {}, token=TOKEN, http=conn, now=lambda: 1000.0)
	assert ei.value.retry_after == 42.0


def test_retry_after_garbage_and_clamp():
	for raw, want in (("soon", None), ("-5", 0.0), ("999999999", float(api.MAX_RETRY_AFTER))):
		conn = FakeHttp(Resp(429, {}, {"Retry-After": raw}))
		with pytest.raises(api.TeamsApiError) as ei:
			api.post_activity(SVC, CONV, {}, token=TOKEN, http=conn)
		assert ei.value.retry_after == want


def test_5xx_single_quick_retry_then_surface():
	conn = FakeHttp(Resp(502, {}))
	with pytest.raises(api.TeamsApiError) as ei:
		api.post_activity(SVC, CONV, {}, token=TOKEN, http=conn, sleep=NOSLEEP)
	assert ei.value.status == 502 and len(conn.calls) == 2 and api.is_transient(ei.value)


def test_5xx_then_success():
	conn = FakeHttp(Resp(503, {}), Resp(200, {"id": "z"}))
	assert api.post_activity(SVC, CONV, {}, token=TOKEN, http=conn, sleep=NOSLEEP)["id"] == "z"


def test_is_transient_matrix():
	T = api.TeamsApiError
	assert all(api.is_transient(T(s)) for s in (0, 408, 429, 500, 503))
	assert not any(api.is_transient(T(s)) for s in (400, 401, 403, 404))
	assert not api.is_transient(ValueError("x"))


# ---- secrets ----
def test_no_secrets_in_str_repr_or_logs(cache, caplog):
	caplog.set_level(logging.DEBUG)
	bad = Resp(400, {"error": {"code": "BadArgument", "message": f"{TOKEN} {SECRET}"}})
	provider = api.make_token_provider(CREDS, http=FakeHttp(tok_resp()), now=lambda: 0.0)
	with pytest.raises(api.TeamsApiError) as ei:
		api.post_activity(SVC, CONV, {}, token=provider, http=FakeHttp(bad))
	blob = str(ei.value) + repr(ei.value) + repr(ei.value.args) + caplog.text
	assert TOKEN not in blob and SECRET not in blob
	assert "BadArgument" in str(ei.value)


def test_transport_error_message_has_no_header_echo():
	conn = FakeHttp(ConnectionError(f"Bearer {TOKEN}"))
	with pytest.raises(api.TeamsApiError) as ei:
		api.post_activity(SVC, CONV, {}, token=TOKEN, http=conn, sleep=NOSLEEP)
	assert TOKEN not in str(ei.value) + repr(ei.value) and ei.value.status == 0


def test_error_code_sanitised():
	e = api.TeamsApiError(400, code="bad code\n<script>")
	assert "\n" not in str(e) and "<" not in str(e)


# ---- SSRF ----
GOOD = [
	"https://smba.trafficmanager.net/emea",
	"https://smba.trafficmanager.net/emea/",
	"https://SMBA.TrafficManager.net/amer//",
	"https://smba.botframework.com/",
	"https://a.b.teams.microsoft.com/x/y",
	"https://smba.trafficmanager.net:443/emea",
]


@pytest.mark.parametrize("url", GOOD)
def test_ssrf_allows_good(url):
	out = api.validate_service_url(url)
	assert out.startswith("https://") and not out.endswith("/")


def test_ssrf_normalises_path():
	assert api.validate_service_url("https://smba.trafficmanager.net/amer//x/") == (
		"https://smba.trafficmanager.net/amer/x"
	)
	assert api.validate_service_url("https://SMBA.trafficmanager.net") == "https://smba.trafficmanager.net"


HOSTILE = [
	"http://smba.trafficmanager.net/emea",
	"ftp://smba.trafficmanager.net/",
	"https://evil-botframework.com/",
	"https://botframework.com.evil.io/",
	"https://botframework.com/",
	"https://smba.trafficmanager.net.evil.com/",
	"https://user:pw@smba.trafficmanager.net/",
	"https://smba.trafficmanager.net@evil.com/",
	"https://evil.com\\@smba.trafficmanager.net/",
	"https://smba.trafficmanager.net:8443/",
	"https://smba.trafficmanager.net:/",
	"https://smba.trafficmanager.net./",
	"https://127.0.0.1/",
	"https://[::1]/",
	"https://169.254.169.254/",
	"https://2130706433/",
	"https://localhost/",
	"https://smba.trafficmanager.net/../admin",
	"https://smba.trafficmanager.net/%2e%2e/admin",
	"https://smba.trafficmanager.net/?x=1",
	"https://smba.trafficmanager.net/#f",
	"https://smba.trafficmanager.net/a b",
	" https://smba.trafficmanager.net/",
	"https://smba.trafficmanager.net/\r\nHost: evil",
	"https://smba.trafficmanager.net․evil.com/",
	"https://.botframework.com/",
	"https://teams.microsoft.com.evil.com/",
	"//smba.trafficmanager.net/",
	"",
	None,
	"javascript:alert(1)",
]


@pytest.mark.parametrize("url", HOSTILE)
def test_ssrf_rejects_hostile(url):
	with pytest.raises(api.TeamsApiError) as ei:
		api.validate_service_url(url)
	assert ei.value.code == "invalid_service_url"


def test_ssrf_applied_to_every_call():
	http = FakeHttp(Resp(200, {"id": "x"}))
	evil = "https://evil.com/"
	for fn in (
		lambda: api.post_activity(evil, CONV, {}, token=TOKEN, http=http),
		lambda: api.update_activity(evil, CONV, "a", {}, token=TOKEN, http=http),
		lambda: api.create_personal_conversation(evil, "t", "b", "u", token=TOKEN, http=http),
	):
		with pytest.raises(api.TeamsApiError):
			fn()
	assert http.calls == []
