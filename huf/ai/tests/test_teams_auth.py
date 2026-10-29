import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "testing"))
import _stub_env  # noqa: E402

_stub_env.install()

import jwt  # noqa: E402
from huf.ai.tests.unit_support import SupportCase  # noqa: E402
import teams_jwt_fixtures as fx  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402

from huf.ai.gateways.teams import auth as teams_auth  # noqa: E402
from huf.ai.gateways.teams import contract as tc  # noqa: E402

T = fx.FIXED_NOW
URL = fx.DEFAULT_SERVICE_URL


def _fx_clean(self):
	teams_auth._reset_cache()
	yield
	teams_auth._reset_cache()


def verify(token, *, fetch=None, now=T, url=URL, app_id=fx.DEFAULT_APP_ID, header=None, **kw):
	return teams_auth.verify_bearer(
		header if header is not None else f"Bearer {token}",
		app_id=app_id,
		activity_service_url=url,
		fetch_json=fetch or fx.fake_fetch_json(),
		now=fx.fixed_clock(now),
		**kw,
	)


class TestModule(SupportCase):
	def setUp(self):
		super().setUp()
		self.use(_fx_clean)
	def test_valid_token_passes(self):
		r = verify(fx.make_token())
		assert r.ok and r.reason == tc.REASON_OK
		assert r.claims["aud"] == fx.DEFAULT_APP_ID

	def test_signature_matches_contract_shape(self):
		import inspect

		sig = inspect.signature(teams_auth.verify_bearer)
		assert "tenant_id" in sig.parameters and sig.parameters["tenant_id"].default is None

	def test_bad_signature(self):
		other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
		r = verify(fx.make_token(key=other))
		assert (r.ok, r.reason, r.claims) == (False, tc.REASON_BAD_SIGNATURE, {})

	def test_unknown_kid_after_refresh(self):
		calls = []
		f = fx.fake_fetch_json(calls=calls)
		assert verify(fx.make_token(), fetch=f).ok
		n = len(calls)
		later = T + 120
		r = verify(fx.make_token(kid="nope", now=later), fetch=f, now=later)
		assert r.reason == tc.REASON_UNKNOWN_KEY
		assert len(calls) == n + 2  # exactly one forced refresh (metadata + jwks)

	def test_unknown_kid_refresh_rate_limited(self):
		calls = []
		f = fx.fake_fetch_json(calls=calls)
		verify(fx.make_token(), fetch=f)
		n = len(calls)
		for i in range(10):
			r = verify(fx.make_token(kid=f"x{i}"), fetch=f)
			assert r.reason == tc.REASON_UNKNOWN_KEY
		assert len(calls) == n

	def test_kid_rotation_refresh_picks_up_new_key(self):
		assert verify(fx.make_token(), fetch=fx.fake_fetch_json()).ok
		later = T + 120
		f2 = fx.fake_fetch_json(kids=("rot-2",))
		r = verify(fx.make_token(kid="rot-2", now=later), fetch=f2, now=later)
		assert r.ok

	def test_missing_kid_header(self):
		tok = jwt.encode(
			{"iss": fx.DEFAULT_ISSUER, "aud": fx.DEFAULT_APP_ID}, fx.get_private_key(), algorithm="RS256"
		)
		assert verify(tok).reason == tc.REASON_UNKNOWN_KEY

	def test_wrong_audience(self):
		assert verify(fx.make_token(aud="someone-else")).reason == tc.REASON_BAD_AUDIENCE

	def test_audience_list_ok(self):
		assert verify(fx.make_token(aud=["x", fx.DEFAULT_APP_ID])).ok

	def test_missing_audience(self):
		assert verify(fx.make_token(aud=None)).reason == tc.REASON_BAD_AUDIENCE

	def test_wrong_issuer(self):
		assert verify(fx.make_token(iss="https://evil.example.com")).reason == tc.REASON_BAD_ISSUER

	def test_missing_issuer(self):
		assert verify(fx.make_token(iss=None)).reason == tc.REASON_BAD_ISSUER

	def test_entra_issuer_not_accepted_without_tenant(self):
		iss = "https://login.microsoftonline.com/tenant-1/v2.0"
		assert verify(fx.make_token(iss=iss)).reason == tc.REASON_BAD_ISSUER

	def test_entra_issuer_single_tenant(self):
		for tmpl in tc.ENTRA_ISSUER_TEMPLATES:
			with self.subTest(tmpl=tmpl):
				iss = tmpl.format(tenant_id="tenant-1")
				calls = []
				entra_meta = teams_auth.ENTRA_METADATA_TEMPLATE.format(tenant_id="tenant-1")
				jwks_uri = "https://login.microsoftonline.com/tenant-1/discovery/v2.0/keys"
				jwk = fx.make_jwk()
				jwk.pop("endorsements")

				def fetch(url):
					calls.append(url)
					if url == entra_meta:
						return {"issuer": iss, "jwks_uri": jwks_uri}
					if url == jwks_uri:
						return {"keys": [jwk]}
					raise AssertionError(url)

				r = verify(fx.make_token(iss=iss), fetch=fetch, tenant_id="tenant-1")
				assert r.ok
				assert fx.OPENID_URL not in calls

	def test_entra_issuer_wrong_tenant_rejected(self):
		iss = tc.ENTRA_ISSUER_TEMPLATES[0].format(tenant_id="other")
		assert verify(fx.make_token(iss=iss), tenant_id="tenant-1").reason == tc.REASON_BAD_ISSUER

	def test_bot_issuer_still_ok_with_tenant(self):
		assert verify(fx.make_token(), tenant_id="tenant-1").ok

	def test_expired(self):
		assert verify(fx.make_token(exp=int(T) - 301)).reason == tc.REASON_EXPIRED

	def test_expired_within_skew_ok(self):
		assert verify(fx.make_token(exp=int(T) - 299)).ok

	def test_missing_exp(self):
		assert verify(fx.make_token(exp=None)).reason == tc.REASON_EXPIRED

	def test_not_yet_valid(self):
		assert verify(fx.make_token(nbf=int(T) + 301)).reason == tc.REASON_NOT_YET_VALID

	def test_not_yet_valid_within_skew_ok(self):
		assert verify(fx.make_token(nbf=int(T) + 299)).ok

	def test_alg_none_rejected(self):
		tok = jwt.encode(
			{"iss": fx.DEFAULT_ISSUER, "aud": fx.DEFAULT_APP_ID, "exp": int(T) + 99}, None, algorithm="none",
			headers={"kid": fx.DEFAULT_KID},
		)
		assert verify(tok).reason == tc.REASON_BAD_ALGORITHM

	def test_hs256_confused_deputy_rejected(self):
		import base64
		import hashlib
		import hmac

		from cryptography.hazmat.primitives import serialization

		pub = fx.get_private_key().public_key().public_bytes(
			serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
		)

		def b64(d):
			return base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=")

		head = b64({"alg": "HS256", "typ": "JWT", "kid": fx.DEFAULT_KID})
		body = b64({"iss": fx.DEFAULT_ISSUER, "aud": fx.DEFAULT_APP_ID, "exp": int(T) + 99, "serviceurl": URL})
		sig = base64.urlsafe_b64encode(hmac.new(pub, head + b"." + body, hashlib.sha256).digest()).rstrip(b"=")
		tok = (head + b"." + body + b"." + sig).decode()
		r = verify(tok)
		assert (r.ok, r.reason) == (False, tc.REASON_BAD_ALGORITHM)

	def test_rs512_rejected(self):
		r = verify(fx.make_token(algorithm="RS512"))
		assert r.reason == tc.REASON_BAD_ALGORITHM

	def test_service_url_mismatch(self):
		assert verify(fx.make_token(), url="https://evil.example.com/").reason == tc.REASON_SERVICE_URL_MISMATCH

	def test_service_url_missing_claim(self):
		assert verify(fx.make_token(serviceurl=None)).reason == tc.REASON_SERVICE_URL_MISMATCH

	def test_service_url_empty_activity(self):
		assert verify(fx.make_token(), url="").reason == tc.REASON_SERVICE_URL_MISMATCH

	def test_service_url_normalised(self):
		assert verify(fx.make_token(), url="HTTPS://SMBA.trafficmanager.net/amer").ok
		assert verify(fx.make_token(serviceurl="https://smba.trafficmanager.net/amer"), url=URL).ok

	def test_service_url_camel_case_claim_fallback(self):
		tok = jwt.encode(
			{"iss": fx.DEFAULT_ISSUER, "aud": fx.DEFAULT_APP_ID, "exp": int(T) + 99, "serviceUrl": URL},
			fx.get_private_key(), algorithm="RS256", headers={"kid": fx.DEFAULT_KID},
		)
		assert verify(tok).ok

	def test_missing_header(self):
		for hdr in ["", None]:
			with self.subTest(hdr=hdr):
				r = teams_auth.verify_bearer(
					hdr, app_id="a", activity_service_url=URL, fetch_json=fx.fake_fetch_json(), now=fx.fixed_clock()
				)
				assert r.reason == tc.REASON_MISSING_HEADER

	def test_garbled_header(self):
		for hdr in ["Bearer", "Basic abc", "Bearer a b", "Bearer not.a.jwt", "token"]:
			with self.subTest(hdr=hdr):
				assert verify("", header=hdr).reason == tc.REASON_MALFORMED_TOKEN

	def test_endorsement_missing_msteams(self):
		f = fx.fake_fetch_json()

		def fetch(url):
			r = f(url)
			if url == fx.JWKS_URL:
				r = {"keys": [dict(k, endorsements=["webchat"]) for k in r["keys"]]}
			return r

		assert verify(fx.make_token(), fetch=fetch).reason == tc.REASON_BAD_ENDORSEMENT

	def test_endorsements_absent_skips_check(self):
		f = fx.fake_fetch_json()

		def fetch(url):
			r = f(url)
			if url == fx.JWKS_URL:
				r = {"keys": [{k: v for k, v in key.items() if k != "endorsements"} for key in r["keys"]]}
			return r

		assert verify(fx.make_token(), fetch=fetch).ok

	def test_jwks_fetched_once_in_100_verifies(self):
		calls = []
		f = fx.fake_fetch_json(calls=calls)
		for _ in range(100):
			assert verify(fx.make_token(), fetch=f).ok
		assert calls.count(fx.JWKS_URL) == 1 and calls.count(fx.OPENID_URL) == 1

	def test_cache_expires_after_24h(self):
		calls = []
		f = fx.fake_fetch_json(calls=calls)
		verify(fx.make_token(), fetch=f)
		later = T + tc.JWKS_CACHE_SECONDS + 1
		assert verify(fx.make_token(now=later), fetch=f, now=later).ok
		assert calls.count(fx.JWKS_URL) == 2

	def test_metadata_failure_fails_closed(self):
		def boom(url):
			raise OSError("down")

		r = verify(fx.make_token(), fetch=boom)
		assert (r.ok, r.reason) == (False, tc.REASON_METADATA_UNAVAILABLE)

	def test_jwks_failure_fails_closed(self):
		def fetch(url):
			if url == fx.JWKS_URL:
				raise TimeoutError("x")
			return fx.fake_openid_metadata()

		assert verify(fx.make_token(), fetch=fetch).reason == tc.REASON_METADATA_UNAVAILABLE

	def test_garbage_metadata_fails_closed(self):
		assert verify(fx.make_token(), fetch=lambda u: {"nope": 1}).reason == tc.REASON_METADATA_UNAVAILABLE

	def test_never_raises_on_odd_input(self):
		r = teams_auth.verify_bearer(
			"Bearer " + "a" * 5000, app_id=None, activity_service_url=None, fetch_json=None, now=None
		)
		assert not r.ok and r.reason in tc.AUTH_REASONS

	def test_failure_results_are_in_contract_and_leak_no_token(self):
		caplog = self.caplog
		caplog.set_level("DEBUG")
		tok = fx.make_token(aud="other")
		r = verify(tok)
		assert r.reason in tc.AUTH_REASONS and r.claims == {}
		sig = tok.split(".")[2]
		assert tok not in repr(r) and sig not in repr(r)
		assert tok not in caplog.text and sig not in caplog.text

	def test_no_token_in_logs_on_metadata_error(self):
		caplog = self.caplog
		caplog.set_level("DEBUG")
		tok = fx.make_token()

		def boom(url):
			raise OSError(tok)  # even if an exception carries the token, it is not logged

		verify(tok, fetch=boom)
		assert tok not in caplog.text
