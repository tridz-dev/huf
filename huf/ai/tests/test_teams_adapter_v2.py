"""Tests for the rewritten Teams adapter (verify / normalize / send)."""

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, "huf/ai/tests")
import _stub_env  # noqa: E402

_stub_env.install()

import pytest  # noqa: E402
import teams_jwt_fixtures as jf  # noqa: E402

from huf.ai.gateway_adapters.conformance import assert_adapter_conforms  # noqa: E402
from huf.ai.gateway_adapters.teams import TeamsGatewayAdapter  # noqa: E402
from huf.ai.gateway_adapters.types import (  # noqa: E402
	GatewayInboundRequest,
	GatewayReply,
	NormalizedGatewayEvent,
)
from huf.ai.gateways import teams_api, teams_auth  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures" / "teams"
APP = jf.DEFAULT_APP_ID
BOT = "28:" + APP
TENANT = "00000000-0000-0000-0000-00000000aaaa"
SECRET = "s3cr3t-app-password-XYZ"
CREDS = {"app_id": APP, "app_password": SECRET, "tenant_id": TENANT}
CHANNEL = "19:fakechannel@thread.tacv2"
SVC = "https://smba.trafficmanager.net/amer/"


def load(name):
	return json.loads((FIXTURES / f"{name}.json").read_text())


def req(activity, token=None, headers=None):
	body = json.dumps(activity).encode()
	h = dict(headers or {})
	if token:
		h["Authorization"] = f"Bearer {token}"
	return GatewayInboundRequest(body=body, headers=h)


def ref_row(**kw):
	row = {
		"name": "REF-1",
		"gateway": "gw1",
		"tenant_id": TENANT,
		"conversation_id": CHANNEL,
		"conversation_type": "channel",
		"service_url": SVC,
		"bot_id": BOT,
	}
	row.update(kw)
	return row


class FakeOutbox:
	def __init__(self):
		self.calls = []

	def enqueue(self, gateway, snapshot, kind, payload, idempotency_key):
		self.calls.append((gateway, snapshot, kind, payload, idempotency_key))
		return "OUT-1"


def make(**kw):
	kw.setdefault("fetch_json", jf.fake_fetch_json())
	kw.setdefault("now", jf.fixed_clock())
	return TeamsGatewayAdapter(CREDS, **kw)


@pytest.fixture(autouse=True)
def _fresh_auth_cache():
	teams_auth._reset_cache()


# ---- normalize -------------------------------------------------------------------------


@pytest.mark.parametrize(
	"name,kind",
	[
		("channel_mention", "message"),
		("personal_message", "message"),
		("group_chat_message", "message"),
		("foreign_tenant_message", "message"),
		("invoke_card_action", "card_action"),
		("installation_add", "install"),
		("installation_remove", "uninstall"),
		("conversation_update", "install"),
	],
)
def test_fixture_kind(name, kind):
	ev = make().normalize_inbound(req(load(name)))
	assert isinstance(ev, NormalizedGatewayEvent)
	assert ev.raw_payload["huf_kind"] == kind
	assert ev.provider_event_id == load(name)["id"]


def test_channel_mention_fields():
	ev = make().normalize_inbound(req(load("channel_mention")))
	assert ev.message_text == "summarise open tickets"
	assert ev.mentioned is True
	assert ev.is_room is True
	assert ev.thread_id == "1700000000100"
	assert ev.sender_id == "00000000-0000-0000-0000-0000000000u1"
	assert ev.display_name == "Ada Example"
	assert ev.conversation_id.startswith(CHANNEL)
	assert ev.raw_payload["tenant_id"] == TENANT
	assert ev.raw_payload["service_url"] == SVC


def test_personal_counts_as_mentioned_and_not_room():
	ev = make().normalize_inbound(req(load("personal_message")))
	assert ev.mentioned is True
	assert ev.is_room is False


def test_group_chat_is_room():
	ev = make().normalize_inbound(req(load("group_chat_message")))
	assert ev.is_room is True


def test_group_chat_without_mention_not_mentioned():
	a = load("group_chat_message")
	a["entities"] = []
	ev = make().normalize_inbound(req(a))
	assert ev.mentioned is False


def test_mention_of_other_user_not_mentioned_and_text_kept():
	a = load("channel_mention")
	a["text"] = "<at>Bob</at> hi"
	a["entities"] = [{"type": "mention", "text": "<at>Bob</at>", "mentioned": {"id": "29:bob", "name": "Bob"}}]
	ev = make().normalize_inbound(req(a))
	assert ev.mentioned is False
	assert "<at>Bob</at>" in ev.message_text


def test_mentions_of_bot_and_other_only_strips_bot():
	a = load("channel_mention")
	a["text"] = "<at>Huf Bot</at>   ask  <at>Bob</at>\t now"
	a["entities"].append({"type": "mention", "text": "<at>Bob</at>", "mentioned": {"id": "29:bob"}})
	ev = make().normalize_inbound(req(a))
	assert ev.message_text == "ask <at>Bob</at> now"


def test_whitespace_normalised():
	a = load("channel_mention")
	a["text"] = "  <at>Huf Bot</at>  a   b  \n\n  c  "
	ev = make().normalize_inbound(req(a))
	assert ev.message_text == "a b\nc"


def test_foreign_tenant_kept_in_raw_payload():
	ev = make().normalize_inbound(req(load("foreign_tenant_message")))
	assert ev.raw_payload["tenant_id"] == load("foreign_tenant_message")["channelData"]["tenant"]["id"]
	assert ev.raw_payload["tenant_id"] != TENANT


def test_thread_from_reply_to_id_when_no_suffix():
	a = load("personal_message")
	a["replyToId"] = "abc"
	assert make().normalize_inbound(req(a)).thread_id == "abc"


def test_sender_falls_back_to_from_id():
	a = load("personal_message")
	del a["from"]["aadObjectId"]
	assert make().normalize_inbound(req(a)).sender_id == a["from"]["id"]


def test_sender_supplied_huf_kind_is_ignored():
	a = load("personal_message")
	a["huf_kind"] = "card_action"
	assert make().normalize_inbound(req(a)).raw_payload["huf_kind"] == "message"


def test_non_message_has_empty_text():
	a = load("installation_add")
	a["text"] = "hello"
	assert make().normalize_inbound(req(a)).message_text == ""


def test_attachments_with_url_kept():
	a = load("personal_message")
	a["attachments"] = [{"contentType": "image/png", "contentUrl": "https://x/y.png", "name": "y.png"}, {"contentType": "t"}]
	ev = make().normalize_inbound(req(a))
	assert len(ev.attachments) == 1


def test_invalid_json_raises():
	with pytest.raises(ValueError):
		make().normalize_inbound(GatewayInboundRequest(body=b"{nope"))


def test_non_object_json_raises():
	with pytest.raises(ValueError):
		make().normalize_inbound(GatewayInboundRequest(body=b"[1]"))


def test_other_conversation_update_ignored():
	a = load("conversation_update")
	a["membersAdded"] = [{"id": "29:someone-else"}]
	assert make().normalize_inbound(req(a)).raw_payload["huf_kind"] == "ignored"


def test_unknown_invoke_ignored():
	a = load("invoke_card_action")
	a["name"] = "composeExtension/query"
	assert make().normalize_inbound(req(a)).raw_payload["huf_kind"] == "ignored"


def test_missing_activity_id_gets_stable_synthetic_id():
	a = load("personal_message")
	del a["id"]
	e1 = make().normalize_inbound(req(a))
	e2 = make().normalize_inbound(req(a))
	assert e1.provider_event_id == e2.provider_event_id != ""


# ---- verify ----------------------------------------------------------------------------


def _activity():
	return load("channel_mention") | {"serviceUrl": jf.DEFAULT_SERVICE_URL}


def test_verify_valid():
	tok = jf.make_token()
	assert make().verify_inbound(req(_activity(), tok)) is True


def test_verify_lowercase_header_name():
	tok = jf.make_token()
	r = GatewayInboundRequest(body=json.dumps(_activity()).encode(), headers={"authorization": f"Bearer {tok}"})
	assert make().verify_inbound(r) is True


def test_verify_wrong_audience():
	assert make().verify_inbound(req(_activity(), jf.make_token(aud="other-app"))) is False


def test_verify_expired():
	tok = jf.make_token(exp=int(jf.FIXED_NOW) - 3600)
	assert make().verify_inbound(req(_activity(), tok)) is False


def test_verify_service_url_mismatch():
	tok = jf.make_token(serviceUrl="https://smba.trafficmanager.net/emea/")
	assert make().verify_inbound(req(_activity(), tok)) is False


def test_verify_missing_header():
	assert make().verify_inbound(req(_activity())) is False


def test_verify_any_bearer_string_no_longer_passes():
	assert make().verify_inbound(req(_activity(), "garbage")) is False


def test_verify_metadata_failure_fails_closed():
	def boom(url):
		raise RuntimeError("down")

	assert make(fetch_json=boom).verify_inbound(req(_activity(), jf.make_token())) is False


def test_verify_bad_body_never_raises():
	r = GatewayInboundRequest(body=b"\xff\xfe", headers={"Authorization": "Bearer x"})
	assert make().verify_inbound(r) is False


# ---- send (outbox) ---------------------------------------------------------------------


def lookup_for(row):
	calls = []

	def lookup(conversation_id, gateway, app_id):
		calls.append((conversation_id, gateway, app_id))
		return row

	lookup.calls = calls
	return lookup


def test_reply_enqueues_with_reference_service_url():
	ob = FakeOutbox()
	ad = make(outbox=ob, reference_lookup=lookup_for(ref_row()))
	d = ad.send_reply(GatewayReply(conversation_id=CHANNEL, text="hi", thread_id="900", reply_to_provider_message_id="900"))
	assert d.provider_message_id == "outbox:OUT-1" and d.accepted
	gw, snap, kind, payload, key = ob.calls[0]
	assert gw == "gw1" and kind == "reply"
	assert snap["service_url"].startswith("https://smba.trafficmanager.net")
	assert snap["tenant_id"] == TENANT and snap["conversation_ref"] == "REF-1"
	assert snap["conversation_id"] == f"{CHANNEL};messageid=900"
	assert payload["activity"]["type"] == "message"
	assert payload["activity"]["replyToId"] == "900"
	assert payload["activity"]["textFormat"] == "markdown"
	assert key.startswith("reply:")


def test_reply_idempotency_key_deterministic_and_text_sensitive():
	def key(text, reply_to="900"):
		ob = FakeOutbox()
		ad = make(outbox=ob, reference_lookup=lookup_for(ref_row()))
		ad.send_reply(GatewayReply(conversation_id=CHANNEL, text=text, reply_to_provider_message_id=reply_to))
		return ob.calls[0][4]

	assert key("a") == key("a")
	assert key("a") != key("b")
	assert key("a") != key("a", "901")


def test_reply_personal_no_thread_suffix():
	ob = FakeOutbox()
	row = ref_row(conversation_id="a:1x", conversation_type="personal")
	make(outbox=ob, reference_lookup=lookup_for(row)).send_reply(
		GatewayReply(conversation_id="a:1x", text="yo", thread_id="5")
	)
	assert ob.calls[0][1]["conversation_id"] == "a:1x"


def test_reply_without_reference_raises():
	ad = make(outbox=FakeOutbox(), reference_lookup=lookup_for(None))
	with pytest.raises(ValueError):
		ad.send_reply(GatewayReply(conversation_id=CHANNEL, text="hi"))


@pytest.mark.parametrize(
	"url",
	[
		"http://smba.trafficmanager.net/amer/",
		"https://evil.example.com/",
		"https://169.254.169.254/",
		"https://smba.trafficmanager.net.evil.com/",
		"",
	],
)
def test_hostile_reference_service_url_rejected(url):
	ob = FakeOutbox()
	ad = make(outbox=ob, reference_lookup=lookup_for(ref_row(service_url=url)))
	with pytest.raises(Exception):
		ad.send_reply(GatewayReply(conversation_id=CHANNEL, text="hi"))
	assert ob.calls == []


def test_gateway_name_passed_to_lookup():
	lk = lookup_for(ref_row())
	make(outbox=FakeOutbox(), reference_lookup=lk, gateway_name="gw1").send_reply(
		GatewayReply(conversation_id=CHANNEL, text="hi")
	)
	assert lk.calls[0] == (CHANNEL, "gw1", APP)


# ---- send (direct) ---------------------------------------------------------------------


class Resp:
	def __init__(self, status=200, body=None):
		self.status_code = status
		self._b = body
		self.headers = {}

	def json(self):
		return self._b


class FakeHttp:
	def __init__(self, activity_body):
		self.calls = []
		self.activity_body = activity_body

	def __call__(self, method, url, *, headers, json=None, data=None, timeout=10):
		self.calls.append({"method": method, "url": url, "json": json, "headers": headers})
		if "oauth2" in url:
			return Resp(200, {"access_token": "tok-SENSITIVE", "expires_in": 3600})
		return Resp(200, self.activity_body)


class FakeCache:
	def __init__(self):
		self.d = {}

	def get_value(self, k):
		return self.d.get(k)

	def set_value(self, k, v, expires_in_sec=None):
		self.d[k] = v

	def delete_value(self, k):
		self.d.pop(k, None)


@pytest.fixture(autouse=True)
def _cache(monkeypatch):
	monkeypatch.setattr(teams_api, "_cache", lambda: FakeCache())


def test_direct_reply_posts_via_http():
	http = FakeHttp({"id": "act-9"})
	ad = make(direct=True, http=http, reference_lookup=lookup_for(ref_row()))
	d = ad.send_reply(GatewayReply(conversation_id=CHANNEL, text="hello", thread_id="900"))
	assert d.provider_message_id == "act-9"
	post = [c for c in http.calls if "/v3/conversations/" in c["url"]][0]
	assert post["url"].startswith("https://smba.trafficmanager.net/amer/v3/conversations/")
	assert post["json"]["text"] == "hello"
	assert post["headers"]["Authorization"] == "Bearer tok-SENSITIVE"


def test_direct_reply_missing_id_raises():
	ad = make(direct=True, http=FakeHttp({}), reference_lookup=lookup_for(ref_row()))
	with pytest.raises(Exception):
		ad.send_reply(GatewayReply(conversation_id=CHANNEL, text="hello"))


# ---- cards -----------------------------------------------------------------------------


CARD = {"type": "AdaptiveCard", "version": "1.5", "body": []}


def test_card_direct_posts_adaptive_attachment():
	http = FakeHttp({"id": "card-1"})
	ad = make(direct=True, http=http, reference_lookup=lookup_for(ref_row()))
	d = ad.send_adaptive_card(CHANNEL, CARD)
	assert d.provider_message_id == "card-1"
	post = [c for c in http.calls if "/activities" in c["url"]][0]
	att = post["json"]["attachments"][0]
	assert att["contentType"] == "application/vnd.microsoft.card.adaptive"
	assert att["content"] == CARD


def test_card_missing_id_raises_not_fabricated():
	ad = make(direct=True, http=FakeHttp({"status": "ok"}), reference_lookup=lookup_for(ref_row()))
	with pytest.raises(Exception) as ei:
		ad.send_adaptive_card(CHANNEL, CARD)
	assert "teams-card-" not in str(ei.value)


def test_card_enqueues_kind_card():
	ob = FakeOutbox()
	ad = make(outbox=ob, reference_lookup=lookup_for(ref_row()))
	d = ad.send_adaptive_card(CHANNEL, copy.deepcopy(CARD))
	assert d.provider_message_id == "outbox:OUT-1"
	assert ob.calls[0][2] == "card" and ob.calls[0][4].startswith("card:")


def test_card_hostile_service_url_rejected():
	ad = make(outbox=FakeOutbox(), reference_lookup=lookup_for(ref_row(service_url="https://evil.test/")))
	with pytest.raises(Exception):
		ad.send_adaptive_card(CHANNEL, CARD)


# ---- misc ------------------------------------------------------------------------------


def test_no_hardcoded_service_url_in_source():
	src = (Path(__file__).parents[1] / "gateway_adapters" / "teams.py").read_text()
	assert "smba.trafficmanager" not in src
	assert "teams-card-" not in src


def test_repr_has_no_secret():
	assert SECRET not in repr(make())


def test_missing_credentials_raises():
	with pytest.raises(ValueError):
		TeamsGatewayAdapter({"app_id": "a"})


def test_errors_do_not_leak_secrets():
	ad = make(outbox=FakeOutbox(), reference_lookup=lookup_for(ref_row(service_url="https://evil.test/")))
	with pytest.raises(Exception) as ei:
		ad.send_reply(GatewayReply(conversation_id=CHANNEL, text="hi"))
	assert SECRET not in str(ei.value)


def test_conformance_helper():
	tok = jf.make_token()
	ad = make(outbox=FakeOutbox(), reference_lookup=lookup_for(ref_row()))
	ev = assert_adapter_conforms(
		ad, req(_activity(), tok), GatewayReply(conversation_id=CHANNEL, text="ok")
	)
	assert ev.raw_payload["huf_kind"] == "message"


# ---- T16: reply idempotency keys, gateway-scoped lookup -------------------------------------


def _send(ad, ob, **kw):
	ad.send_reply(GatewayReply(conversation_id=CHANNEL, text=kw.pop("text", "Done."), **kw))
	return ob.calls[-1][4]


def test_identical_text_in_personal_chat_is_not_deduped():
	ob = FakeOutbox()
	ad = make(outbox=ob, reference_lookup=lookup_for(ref_row()), gateway_name="gw1")
	assert _send(ad, ob) != _send(ad, ob)
	# a different adapter instance (a later send) is also distinct
	ad2 = make(outbox=ob, reference_lookup=lookup_for(ref_row()), gateway_name="gw1")
	assert _send(ad2, ob) not in {ob.calls[0][4], ob.calls[1][4]}


def test_retry_of_same_reply_object_keeps_key():
	ob = FakeOutbox()
	ad = make(outbox=ob, reference_lookup=lookup_for(ref_row()), gateway_name="gw1")
	reply = GatewayReply(conversation_id=CHANNEL, text="Done.")
	ad.send_reply(reply)
	ad.send_reply(reply)
	assert ob.calls[0][4] == ob.calls[1][4]


def test_event_id_derived_key_dedupes_true_retries_only():
	ob = FakeOutbox()
	ad = make(outbox=ob, reference_lookup=lookup_for(ref_row()), gateway_name="gw1")
	a = _send(ad, ob, reply_to_provider_message_id="act-1")
	b = _send(ad, ob, reply_to_provider_message_id="act-1")
	c = _send(ad, ob, reply_to_provider_message_id="act-2")
	d = _send(ad, ob, reply_to_provider_message_id="act-1", text="Other")
	assert a == b and len({a, c, d}) == 3


def test_thread_root_as_reply_to_is_not_an_event_id():
	ob = FakeOutbox()
	ad = make(outbox=ob, reference_lookup=lookup_for(ref_row()), gateway_name="gw1")
	k1 = _send(ad, ob, thread_id="root-1", reply_to_provider_message_id="root-1")
	k2 = _send(ad, ob, thread_id="root-1", reply_to_provider_message_id="root-1")
	assert k1 != k2


def test_default_lookup_requires_gateway_and_scopes_query(monkeypatch):
	import sys
	import types

	from huf.ai.gateway_adapters import teams as teams_mod

	seen = []
	fr = types.SimpleNamespace(get_all=lambda dt, **kw: seen.append(kw) or [{"name": "R", "gateway": "gw1"}])
	monkeypatch.setitem(sys.modules, "frappe", fr)
	assert teams_mod._default_reference_lookup(CHANNEL, None, APP) is None  # no gateway: fail closed
	assert seen == []
	assert teams_mod._default_reference_lookup(CHANNEL, "gw1", APP)["name"] == "R"
	assert seen[0]["filters"]["gateway"] == "gw1"
