import json
import pathlib
import sys
from pathlib import Path

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "testing"))
import _stub_env  # noqa: E402

_stub_env.install()

import jwt  # noqa: E402
import pytest  # noqa: E402
import teams_jwt_fixtures as fx  # noqa: E402

from huf.ai.gateway_adapters.teams import TeamsGatewayAdapter  # noqa: E402
from huf.ai.gateways.teams import contract as tc  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures" / "teams"


def test_constants():
	assert tc.CONTRACT_VERSION == "teams-p0/1"
	assert tc.PROVIDER_ID == TeamsGatewayAdapter.provider_id == "microsoft_teams"
	assert tc.PROVIDER_LABEL == "Microsoft Teams"
	prios = [p for _, p in tc.HOOK_PRIORITY_ORDER]
	assert prios == sorted(prios) and tc.HOOK_PRIORITY_TENANT < tc.HOOK_PRIORITY_CARD_ACTION


def test_dataclasses_frozen():
	m = tc.TeamsMeta(tenant_id="t")
	with pytest.raises(Exception):
		m.tenant_id = "x"
	r = tc.TeamsAuthResult(False, tc.REASON_EXPIRED, {})
	assert r.ok is False and r.reason in tc.AUTH_REASONS
	assert [k.value for k in tc.TeamsActivityKind] == ["message", "card_action", "install", "uninstall", "ignored"]


def test_stubs_raise():
	with pytest.raises(NotImplementedError):
		tc.verify_bearer("", app_id="a", activity_service_url="u", fetch_json=lambda u: {}, now=lambda: 0)
	with pytest.raises(NotImplementedError):
		tc.get_bot_token(app_id="a", app_password="p", tenant_id="t")
	with pytest.raises(NotImplementedError):
		tc.enqueue(gateway="g", kind="reply", payload={}, idempotency_key="k")
	with pytest.raises(NotImplementedError):
		tc.upsert_reference("g", tc.TeamsMeta())
	with pytest.raises(NotImplementedError):
		tc.resolve_user("g", "t", "u")
	assert set(tc.PROTOCOLS) == {
		"teams_auth.verify_bearer",
		"teams_auth.get_bot_token",
		"teams_outbox.enqueue",
		"teams_refs.upsert_reference",
		"teams_identity.resolve_user",
	}


def test_fixtures_load():
	files = sorted(FIXTURES.glob("*.json"))
	assert len(files) == 8
	for f in files:
		act = json.loads(f.read_text())
		assert act["type"] and act["serviceUrl"] and act["channelData"]["tenant"]["id"]
	ch = json.loads((FIXTURES / "channel_mention.json").read_text())
	assert ";messageid=" in ch["conversation"]["id"]
	assert any(e["type"] == "mention" for e in ch["entities"]) and "<at>" in ch["text"]
	inv = json.loads((FIXTURES / "invoke_card_action.json").read_text())
	assert inv["name"] == "adaptiveCard/action" and inv["value"]["action"]["data"]["session"]


def test_make_token_roundtrip():
	jwks = fx.fake_fetch_json()(fx.JWKS_URL)
	token = fx.make_token()
	header = jwt.get_unverified_header(token)
	key = jwt.PyJWK(jwks["keys"][0]).key
	claims = jwt.decode(
		token, key, algorithms=["RS256"], audience=fx.DEFAULT_APP_ID, issuer=fx.DEFAULT_ISSUER,
		options={"verify_exp": False, "verify_nbf": False},
	)
	assert header["kid"] == fx.DEFAULT_KID and claims["serviceurl"] == fx.DEFAULT_SERVICE_URL
	assert claims["exp"] > fx.FIXED_NOW
	assert fx.fixed_clock()() == fx.FIXED_NOW
	assert "iss" not in jwt.decode(fx.make_token(iss=None), options={"verify_signature": False})


def test_fetcher_records_calls():
	calls = []
	f = fx.fake_fetch_json(calls=calls)
	assert f(fx.OPENID_URL)["jwks_uri"] == fx.JWKS_URL
	assert calls == [fx.OPENID_URL]
	assert fx.OPENID_URL == tc.OPENID_METADATA_URL


def test_adapter_tenant_and_injection():
	schema = {f.key: f for f in TeamsGatewayAdapter.credential_schema.fields}
	assert schema["tenant_id"].label == "Directory (tenant) ID" and schema["tenant_id"].required
	with pytest.raises(ValueError):
		TeamsGatewayAdapter({"app_id": "a", "app_password": "p"})
	jf, tf, now = object(), object(), lambda: 1.0
	a = TeamsGatewayAdapter(
		{"app_id": "a", "app_password": "p", "tenant_id": "t"}, jwks_fetcher=jf, token_fetcher=tf, now=now
	)
	assert (a._jwks_fetcher, a._token_fetcher, a._now) == (jf, tf, now)
