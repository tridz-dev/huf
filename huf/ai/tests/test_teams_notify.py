"""Tests for proactive Teams notifications (huf.ai.gateways.teams.messaging.notify)."""

import importlib
import json
import pathlib
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "testing"))
import _stub_env  # noqa: E402

_stub_env.install()

import frappe  # noqa: E402
from huf.ai.tests.unit_support import SupportCase  # noqa: E402

_orig_whitelist = frappe.whitelist
frappe.whitelist = lambda *a, **k: (lambda f: f)
try:
	sys.modules.pop("huf.ai.gateways.teams.messaging.notify", None)
	tn = importlib.import_module("huf.ai.gateways.teams.messaging.notify")
finally:
	frappe.whitelist = _orig_whitelist

TENANT = "11111111-1111-1111-1111-111111111111"
OTHER = "99999999-9999-9999-9999-999999999999"
AAD = "22222222-2222-2222-2222-222222222222"
SURL = "https://smba.trafficmanager.net/emea/"


class Perm(Exception):
	pass


class FakeCache:
	def __init__(self):
		self.d = {}
		self.ttl = {}

	def get_value(self, k):
		return self.d.get(k)

	def set_value(self, k, v, expires_in_sec=None):
		self.d[k] = v
		self.ttl[k] = expires_in_sec

	def delete_value(self, k):
		self.d.pop(k, None)


class World:
	def __init__(self):
		self.links = [{"team_id": TENANT, "external_id": AAD, "user": "bob@x.com"}]
		self.refs = []
		self.created = []
		self.upserts = []
		self.enqueued = []
		self.fail_enqueue = False
		self.api_error = None
		self.has_write = False
		self.roles = []
		self.gw = SimpleNamespace(name="GW-1", provider="Microsoft Teams", is_enabled=1, integration_settings="IS")


def _fx_w(self):
	monkeypatch = self.monkeypatch
	world = World()
	cache = FakeCache()
	world.cache = cache
	monkeypatch.setattr(tn, "_", lambda s: s)
	monkeypatch.setattr(tn, "_cache", lambda: cache)
	monkeypatch.setattr(frappe, "PermissionError", Perm, raising=False)
	monkeypatch.setattr(frappe, "throw", lambda m, e=Exception: (_ for _ in ()).throw(e(m)), raising=False)
	monkeypatch.setattr(frappe, "session", SimpleNamespace(user="carol@x.com"), raising=False)
	monkeypatch.setattr(frappe, "get_roles", lambda: world.roles, raising=False)
	monkeypatch.setattr(frappe, "has_permission", lambda *a, **k: world.has_write, raising=False)
	monkeypatch.setattr(frappe, "log_error", lambda *a, **k: None, raising=False)
	monkeypatch.setattr(frappe, "db", MagicMock(), raising=False)
	monkeypatch.setattr(frappe.db, "exists", lambda dt, n: n == "GW-1", raising=False)
	monkeypatch.setattr(frappe, "get_doc", lambda dt, n=None: world.gw, raising=False)

	def get_all(dt, filters=None, **k):
		if dt == tn.LINK_DOCTYPE:
			return [r for r in world.links if r["user"] == filters["user"]][:1]
		if dt == tn.REF_DOCTYPE:
			return [r for r in world.refs if r["tenant_id"] == filters["tenant_id"] and r.get("service_url")][:1]
		return []

	monkeypatch.setattr(frappe, "get_all", get_all, raising=False)
	monkeypatch.setattr(
		tn.teams_refs,
		"get_personal_reference",
		lambda g, t, a: next(
			(r for r in world.refs if r["tenant_id"] == t and r.get("user_aad_id") == a and r.get("installed")),
			None,
		),
	)
	monkeypatch.setattr(tn.teams_refs, "upsert_reference", lambda g, meta, **k: world.upserts.append(meta) or "REF")
	monkeypatch.setattr(
		tn.teams_tenant, "get_gateway_credential", lambda gw, k: {"app_id": "app", "app_password": "pw-SECRET", "tenant_id": TENANT}[k]
	)
	monkeypatch.setattr(tn.teams_api, "make_token_provider", lambda creds, **k: (lambda refresh=False: "tok"))

	def create(url, tenant, bot, aad, *, token, **k):
		world.created.append((url, tenant, bot, aad))
		if world.api_error:
			raise tn.teams_api.TeamsApiError(403, code=world.api_error)
		return "a:new-conv"

	monkeypatch.setattr(tn.teams_api, "create_personal_conversation", create)

	def enqueue(gw, snap, kind, payload, key):
		if world.fail_enqueue:
			raise RuntimeError("db down")
		world.enqueued.append((gw, snap, kind, payload, key))
		return f"OB-{len(world.enqueued)}"

	monkeypatch.setattr(tn.teams_outbox, "enqueue", enqueue)
	return world


def add_ref(w, tenant=TENANT, aad=AAD, installed=1, surl=SURL):
	w.refs.append(
		{
			"name": f"R-{tenant[:2]}",
			"tenant_id": tenant,
			"user_aad_id": aad,
			"installed": installed,
			"service_url": surl,
			"conversation_id": "a:conv1",
		}
	)


def send(**kw):
	args = {"gateway": "GW-1", "user": "bob@x.com", "text": "hello"}
	args.update(kw)
	return tn.send_teams_notification(**args)


class TestModule(SupportCase):
	# ---- permissions
	def test_admin_allowed(self):
		w = self.use(_fx_w)
		w.roles = ["System Manager"]
		add_ref(w)
		assert send()["success"]

	def test_gateway_writer_allowed(self):
		w = self.use(_fx_w)
		w.has_write = True
		add_ref(w)
		assert send()["success"]

	def test_self_allowed(self):
		w = self.use(_fx_w)
		monkeypatch = self.monkeypatch
		monkeypatch.setattr(frappe, "session", SimpleNamespace(user="bob@x.com"), raising=False)
		add_ref(w)
		assert send()["success"]

	def test_other_user_denied(self):
		w = self.use(_fx_w)
		add_ref(w)
		with self.assertRaises(Perm):
			send()
		assert not w.enqueued

	def test_guest_denied(self):
		w = self.use(_fx_w)
		monkeypatch = self.monkeypatch
		monkeypatch.setattr(frappe, "session", SimpleNamespace(user="Guest"), raising=False)
		with self.assertRaises(Perm):
			send(user="Guest")

	# ---- target validation
	def test_unlinked_user(self):
		w = self.use(_fx_w)
		w.roles = ["System Manager"]
		res = send(user="nobody@x.com")
		assert not res["success"] and "linked" in res["error"]

	def test_email_or_aad_not_accepted(self):
		w = self.use(_fx_w)
		w.roles = ["System Manager"]
		assert not send(user=AAD)["success"]

	def test_disabled_gateway(self):
		w = self.use(_fx_w)
		w.roles = ["System Manager"]
		w.gw.is_enabled = 0
		assert "disabled" in send()["error"]

	def test_non_teams_gateway(self):
		w = self.use(_fx_w)
		w.roles = ["System Manager"]
		w.gw.provider = "Slack"
		assert "not a Microsoft Teams" in send()["error"]

	def test_missing_gateway(self):
		w = self.use(_fx_w)
		w.roles = ["System Manager"]
		assert "not found" in send(gateway="NOPE")["error"]

	# ---- conversation resolution
	def test_existing_reference_used(self):
		w = self.use(_fx_w)
		w.roles = ["System Manager"]
		add_ref(w)
		res = send()
		assert res == {"success": True, "outbox": "OB-1", "deduped": False}
		_, snap, kind, payload, _k = w.enqueued[0]
		assert kind == "proactive" and snap["conversation_id"] == "a:conv1" and snap["tenant_id"] == TENANT
		assert not w.created

	def test_creates_conversation_when_not_installed(self):
		w = self.use(_fx_w)
		w.roles = ["System Manager"]
		add_ref(w, aad="someone-else", installed=1)  # supplies service_url for the tenant
		res = send()
		assert res["success"]
		assert w.created == [(SURL, TENANT, "app", AAD)]
		assert w.upserts[0].conversation_id == "a:new-conv" and w.upserts[0].user_aad_id == AAD
		assert w.enqueued[0][1]["conversation_id"] == "a:new-conv"

	def test_no_service_url_clear_error(self):
		w = self.use(_fx_w)
		w.roles = ["System Manager"]
		res = send()
		assert not res["success"] and "not messaged or installed" in res["error"]
		assert not w.created and not w.enqueued

	def test_create_conversation_api_error_surfaced(self):
		w = self.use(_fx_w)
		w.roles = ["System Manager"]
		add_ref(w, aad="other")
		w.api_error = "BotNotInstalled"
		res = send()
		assert not res["success"] and "Teams refused" in res["error"] and "BotNotInstalled" in res["error"] and "403" in res["error"]
		assert not w.enqueued

	def test_tenant_isolation_reference(self):
		w = self.use(_fx_w)
		w.roles = ["System Manager"]
		add_ref(w, tenant=OTHER)  # same aad, other tenant: must be ignored
		res = send()
		assert not res["success"]
		assert not w.created and not w.enqueued

	def test_tenant_isolation_service_url(self):
		w = self.use(_fx_w)
		w.roles = ["System Manager"]
		add_ref(w, tenant=OTHER, aad="x", surl="https://evil.botframework.com/")
		assert "not messaged" in send()["error"]
		assert not w.created

	def test_helper_user_reference(self):
		w = self.use(_fx_w)
		add_ref(w)
		info = tn.teams_user_reference("GW-1", "bob@x.com")
		assert info["tenant_id"] == TENANT and info["aad_id"] == AAD and info["reference"]["conversation_id"] == "a:conv1"
		assert tn.teams_user_reference("GW-1", "zed@x.com") is None

	# ---- dedupe
	def test_dedupe_within_ttl(self):
		w = self.use(_fx_w)
		w.roles = ["System Manager"]
		add_ref(w)
		first = send(dedupe_key="inv-1", dedupe_hours=2)
		second = send(dedupe_key="inv-1")
		assert first["deduped"] is False and second == {"success": True, "outbox": None, "deduped": True}
		assert len(w.enqueued) == 1
		assert list(w.cache.ttl.values()) == [7200]

	def test_dedupe_distinct_keys(self):
		w = self.use(_fx_w)
		w.roles = ["System Manager"]
		add_ref(w)
		send(dedupe_key="a")
		send(dedupe_key="b")
		assert len(w.enqueued) == 2 and w.enqueued[0][4] != w.enqueued[1][4]

	def test_dedupe_key_hash_scoped(self):
		w = self.use(_fx_w)
		k1 = tn._idempotency_key("G1", TENANT, AAD, "k")
		assert k1 == tn._idempotency_key("G1", TENANT, AAD, "k")
		assert k1 != tn._idempotency_key("G2", TENANT, AAD, "k")
		assert k1 != tn._idempotency_key("G1", OTHER, AAD, "k")
		assert tn._idempotency_key("G1", TENANT, AAD, None) != tn._idempotency_key("G1", TENANT, AAD, None)

	def test_dedupe_released_on_enqueue_failure(self):
		w = self.use(_fx_w)
		w.roles = ["System Manager"]
		add_ref(w)
		w.fail_enqueue = True
		res = send(dedupe_key="k")
		assert not res["success"] and not w.cache.d
		w.fail_enqueue = False
		assert send(dedupe_key="k")["outbox"] == "OB-1"

	def test_dedupe_released_on_conversation_failure(self):
		w = self.use(_fx_w)
		w.roles = ["System Manager"]
		add_ref(w, aad="other")
		w.api_error = "nope"
		assert not send(dedupe_key="k")["success"]
		assert not w.cache.d

	# ---- content
	def test_text_capped_and_cleaned(self):
		w = self.use(_fx_w)
		w.roles = ["System Manager"]
		add_ref(w)
		send(text="a\x00b\x07" + "x" * 5000)
		act = w.enqueued[0][3]["activity"]
		assert len(act["text"]) == 3000 and "\x00" not in act["text"] and "\x07" not in act["text"]
		assert act["textFormat"] == "plain"

	def test_empty_content_rejected(self):
		w = self.use(_fx_w)
		w.roles = ["System Manager"]
		add_ref(w)
		assert "text or a card" in send(text="  ")["error"]

	def test_card_attachment(self):
		w = self.use(_fx_w)
		w.roles = ["System Manager"]
		add_ref(w)
		card = {"type": "AdaptiveCard", "version": "1.4", "body": []}
		assert send(text=None, card=card)["success"]
		att = w.enqueued[0][3]["activity"]["attachments"][0]
		assert att["contentType"] == tn.CARD_CONTENT_TYPE and att["content"] == card

	def test_card_as_json_string(self):
		w = self.use(_fx_w)
		w.roles = ["System Manager"]
		add_ref(w)
		assert send(text=None, card=json.dumps({"type": "AdaptiveCard", "body": []}))["success"]

	def test_card_validation(self):
		for bad in [["x"], {"type": "Other"}, {"body": []}, "{not json"]:
			with self.subTest(bad=bad):
				self.reset_fixtures()
				w = self.use(_fx_w)
				w.roles = ["System Manager"]
				add_ref(w)
				assert not send(text=None, card=bad)["success"]

	def test_card_size_cap(self):
		w = self.use(_fx_w)
		w.roles = ["System Manager"]
		add_ref(w)
		big = {"type": "AdaptiveCard", "body": [{"type": "TextBlock", "text": "y" * 30000}]}
		assert "too large" in send(text=None, card=big)["error"]

	def test_outbox_payload_has_no_secrets(self):
		w = self.use(_fx_w)
		w.roles = ["System Manager"]
		add_ref(w)
		send()
		blob = json.dumps(w.enqueued[0])
		assert "pw-SECRET" not in blob and "tok" not in w.enqueued[0][3]
		w2_snap = w.enqueued[0][1]
		assert set(w2_snap) == {"conversation_ref", "conversation_id", "service_url", "tenant_id"}

	def test_created_path_payload_has_no_secrets(self):
		w = self.use(_fx_w)
		w.roles = ["System Manager"]
		add_ref(w, aad="other")
		send()
		assert "pw-SECRET" not in json.dumps(w.enqueued[0])
