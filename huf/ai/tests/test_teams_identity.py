"""Tests for Teams identity linking (huf.ai.gateways.teams.identity)."""

import sys
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.path.insert(0, "huf/testing")
import _stub_env  # noqa: E402

_stub_env.install()

import frappe  # noqa: E402
import pytest  # noqa: E402

from huf.ai.gateways import hooks as gw_hooks  # noqa: E402
from huf.ai.gateways.teams import contract as tc  # noqa: E402

_saved = {k: list(v) for k, v in gw_hooks._HANDLERS.items()}
_orig_whitelist = frappe.whitelist
WL = {}


def _wl(*a, **k):
	def deco(f):
		WL[f.__name__] = k.get("methods")
		return f

	return deco


frappe.whitelist = _wl
try:
	from huf.ai.gateways.teams import identity as ti  # noqa: E402
finally:
	frappe.whitelist = _orig_whitelist
	_registered_handlers = {k: list(v) for k, v in gw_hooks._HANDLERS.items()}
	gw_hooks._HANDLERS.clear()
	gw_hooks._HANDLERS.update(_saved)

PREFIX = gw_hooks.USER_VISIBLE_PREFIX
TENANT = "11111111-1111-1111-1111-111111111111"
AAD = "22222222-2222-2222-2222-222222222222"


class FakeCache:
	def __init__(self):
		self.d = {}

	def set_value(self, k, v, expires_in_sec=None):
		self.d[k] = v

	def get_value(self, k):
		return self.d.get(k)

	def delete_value(self, k):
		self.d.pop(k, None)


class Perm(Exception):
	pass


def _throw(msg, exc=Exception):
	raise exc(msg)


@pytest.fixture(autouse=True)
def env(monkeypatch):
	cache = FakeCache()
	counter = iter(range(10000))
	monkeypatch.setattr(ti, "_", lambda s: s)
	monkeypatch.setattr(ti, "_cache", lambda: cache)
	monkeypatch.setattr(frappe, "PermissionError", Perm, raising=False)
	monkeypatch.setattr(frappe, "throw", _throw, raising=False)
	monkeypatch.setattr(frappe, "local", SimpleNamespace(conf={"encryption_key": "secret-key"}), raising=False)
	monkeypatch.setattr(frappe, "session", SimpleNamespace(user="alice@x.com"), raising=False)
	monkeypatch.setattr(frappe, "generate_hash", lambda length=10: f"nonce{next(counter)}", raising=False)
	monkeypatch.setattr(frappe, "get_roles", lambda: ["System Manager"], raising=False)
	monkeypatch.setattr(frappe.utils, "get_url", lambda: "https://huf.test", raising=False)
	monkeypatch.setattr(frappe.utils, "now", lambda: "2026-01-01 00:00:00", raising=False)
	monkeypatch.setattr(frappe, "db", MagicMock(), raising=False)
	monkeypatch.setattr(ti, "_user_enabled", lambda u: u not in ("disabled@x.com",))
	return SimpleNamespace(cache=cache)


class Store:
	"""In-memory Linked rows keyed by (gateway, tenant, aad)."""

	def __init__(self, monkeypatch):
		self.rows = {}
		self.created = []
		self.revoked = []
		self.states = []
		self.confirmations = []
		monkeypatch.setattr(ti, "_supersede_pending", lambda *a: None)
		from huf.ai.gateways.teams import identity_confirm as tic

		monkeypatch.setattr(tic, "send_confirmation", lambda *a: self.confirmations.append(a) or "S1")
		monkeypatch.setattr(ti, "_find_link", self.find)
		monkeypatch.setattr(ti, "_user_link_in_tenant", self.by_user)
		monkeypatch.setattr(ti, "_create_link", self.create)
		monkeypatch.setattr(
			frappe.db, "set_value", lambda dt, n, *a, **k: self.revoked.append((n, a)), raising=False
		)

	def add(self, user="alice@x.com", source="Admin", gw="GW-1", tenant=TENANT, aad=AAD):
		self.rows[(gw, tenant, aad)] = SimpleNamespace(name=f"L-{aad[:2]}-{user}", user=user, source=source,
			external_id=aad)

	def find(self, g, t, e):
		return self.rows.get((g, t, e))

	def by_user(self, g, t, user):
		return next((r for (gg, tt, _e), r in self.rows.items() if gg == g and tt == t and r.user == user), None)

	def create(self, gateway, tenant, aad, user, source, label=None, linked_by=None, state="Linked"):
		self.created.append((gateway, tenant, aad, user, source, label, linked_by))
		self.states.append(state)
		if state == "Linked":  # a Pending row never resolves a user
			self.add(user, source, gateway, tenant, aad)
		return SimpleNamespace(name="NEW")


@pytest.fixture
def store(monkeypatch):
	return Store(monkeypatch)


def gw():
	return SimpleNamespace(name="GW-1", provider="Microsoft Teams", execution_user="svc@x.com")


def ev(tenant=TENANT, aad=AAD, from_extra=None, **kw):
	frm = {"id": "29:abc", "name": "Ada Lovelace"}
	if aad:
		frm["aadObjectId"] = aad
	frm.update(from_extra or {})
	activity = {
		"type": "message",
		"from": frm,
		"conversation": {"id": "a:1", "conversationType": "personal", "tenantId": tenant},
		"channelData": {"tenant": {"id": tenant}} if tenant else {},
	}
	return SimpleNamespace(name="EV-1", raw_payload=activity, agent_run=kw.pop("agent_run", None), **kw)


def denied(event=None):
	with pytest.raises(gw_hooks.GatewayHookDenied) as e:
		ti.resolve_run_user(gw(), event or ev())
	return e.value.reason


def token_from(reason):
	return reason.split("token=", 1)[1].strip()


# ---- resolve_user / hook ------------------------------------------------------
def test_resolve_user_linked(store):
	store.add()
	assert ti.resolve_user("GW-1", TENANT, AAD) == "alice@x.com"


def test_resolve_user_unlinked_none(store):
	assert ti.resolve_user("GW-1", TENANT, AAD) is None


def test_resolve_user_wrong_tenant(store):
	store.add()
	assert ti.resolve_user("GW-1", "other-tenant", AAD) is None


def test_resolve_user_empty_args(store):
	store.add()
	assert ti.resolve_user("GW-1", "", AAD) is None
	assert ti.resolve_user("GW-1", TENANT, "") is None


def test_resolve_user_disabled_and_guest(store):
	store.add(user="disabled@x.com")
	assert ti.resolve_user("GW-1", TENANT, AAD) is None
	store.add(user="Guest")
	assert ti.resolve_user("GW-1", TENANT, AAD) is None


def test_administrator_only_via_admin(store):
	store.add(user="Administrator", source="Self link")
	assert ti.resolve_user("GW-1", TENANT, AAD) is None
	store.add(user="Administrator", source="Admin")
	assert ti.resolve_user("GW-1", TENANT, AAD) == "Administrator"


def test_hook_linked_returns_user(store):
	store.add()
	assert ti.resolve_run_user(gw(), ev()) == "alice@x.com"


def test_hook_linked_but_disabled_denied(store):
	store.add(user="disabled@x.com")
	assert denied().startswith(PREFIX) and "disabled" in denied()


def test_hook_unlinked_denied_with_link_never_execution_user(store):
	reason = denied()
	assert reason.startswith(PREFIX)
	assert "Connect your Huf account" in reason
	assert "https://huf.test/huf/link-account?p=teams&token=" in reason
	assert "svc@x.com" not in reason


def test_hook_wrong_tenant_unlinked(store):
	store.add()
	assert "link-account" in denied(ev(tenant="99999999-9999-9999-9999-999999999999"))


def test_message_has_no_secret_or_ids(store):
	reason = denied()
	assert "secret-key" not in reason
	assert AAD not in reason and TENANT not in reason


# ---- guest / external ---------------------------------------------------------
def test_missing_aad_not_supported(store):
	reason = denied(ev(aad=""))
	assert "not supported" in reason and "token=" not in reason


def test_missing_tenant_not_supported(store):
	assert "not supported" in denied(ev(tenant=""))


def test_guest_user_type_not_supported(store):
	store.add()
	reason = denied(ev(from_extra={"userType": "Guest"}))
	assert "not supported" in reason and "token=" not in reason


def test_guest_in_properties_not_supported(store):
	assert "not supported" in denied(ev(from_extra={"properties": {"userType": "guest"}}))


def test_raw_payload_json_string(store):
	import json

	store.add()
	e = ev()
	e.raw_payload = json.dumps(e.raw_payload)
	assert ti.resolve_run_user(gw(), e) == "alice@x.com"


# ---- throttle / token ---------------------------------------------------------
def test_token_reused_within_window(store):
	t1 = token_from(denied())
	t2 = token_from(denied())
	assert t1 == t2


def test_token_throttle_per_principal(store):
	t1 = token_from(denied())
	t2 = token_from(denied(ev(aad="33333333-3333-3333-3333-333333333333")))
	assert t1 != t2


def test_token_replaced_after_use(store):
	t1 = token_from(denied())
	ti._cache().delete_value(ti._NONCE_PREFIX + ti._verify_token(t1)["n"])
	assert token_from(denied()) != t1


def test_token_ttl_is_ten_minutes():
	assert ti.TOKEN_TTL_SECONDS == 600


def test_token_expiry(monkeypatch):
	tok = ti.create_link_token("GW-1", TENANT, AAD)
	real = time.time
	monkeypatch.setattr(time, "time", lambda: real() + 601)
	with pytest.raises(Perm):
		ti._verify_token(tok)


def test_token_tamper():
	tok = ti.create_link_token("GW-1", TENANT, AAD)
	body, sig = tok.split(".")
	forged = ti._b64(ti.json.dumps({"g": "GW-1", "t": TENANT, "x": "evil", "e": 9999999999, "n": "nonce0"}).encode())
	for bad in (f"{forged}.{sig}", f"{body}.{'0' * 64}", "garbage", "", None):
		with pytest.raises(Perm):
			ti._verify_token(bad)


def test_token_replay_rejected(store):
	tok = ti.create_link_token("GW-1", TENANT, AAD)
	assert ti.confirm_teams_link(tok)["pending"] is True
	with pytest.raises(Perm):
		ti.confirm_teams_link(tok)


def test_token_other_secret_rejected(monkeypatch):
	tok = ti.create_link_token("GW-1", TENANT, AAD)
	monkeypatch.setattr(frappe, "local", SimpleNamespace(conf={"encryption_key": "different"}))
	with pytest.raises(Perm):
		ti._verify_token(tok)


# ---- preview / confirm --------------------------------------------------------
def test_preview_read_only_and_labels(store):
	tok = ti.create_link_token("GW-1", TENANT, AAD, "Ada")
	out = ti.preview_teams_link(tok)
	assert out["person_label"] == "Ada" and out["workspace_label"] == TENANT and out["user"] == "alice@x.com"
	assert not store.created
	assert ti._cache().get_value(ti._NONCE_PREFIX + "nonce0")  # not consumed


@pytest.mark.parametrize("user", ["Guest", "Administrator", "disabled@x.com", ""])
def test_confirm_requires_real_user(store, monkeypatch, user):
	monkeypatch.setattr(frappe, "session", SimpleNamespace(user=user))
	tok = ti.create_link_token("GW-1", TENANT, AAD)
	with pytest.raises(Perm):
		ti.confirm_teams_link(tok)
	with pytest.raises(Perm):
		ti.preview_teams_link(tok)
	assert not store.created


def test_confirm_creates_self_link(store):
	tok = ti.create_link_token("GW-1", TENANT, AAD, "Ada")
	assert ti.confirm_teams_link(tok) == {"linked": False, "pending": True, "user": "alice@x.com"}
	assert store.created == [("GW-1", TENANT, AAD, "alice@x.com", "Self link", "Ada", "alice@x.com")]
	assert store.states == ["Pending"] and store.confirmations == [("GW-1", "NEW", TENANT, AAD, "alice@x.com")]
	assert ti.resolve_user("GW-1", TENANT, AAD) is None  # Pending never resolves a user


def test_confirm_refuses_identity_linked_to_other_user(store):
	store.add(user="bob@x.com")
	with pytest.raises(Perm):
		ti.confirm_teams_link(ti.create_link_token("GW-1", TENANT, AAD))
	assert not store.created


def test_confirm_refuses_user_linked_to_other_aad_same_tenant(store):
	store.add(aad="44444444-4444-4444-4444-444444444444")
	with pytest.raises(Perm):
		ti.confirm_teams_link(ti.create_link_token("GW-1", TENANT, AAD))
	assert not store.created


def test_confirm_same_user_other_tenant_ok(store):
	store.add(tenant="other-tenant", aad="44444444-4444-4444-4444-444444444444")
	assert ti.confirm_teams_link(ti.create_link_token("GW-1", TENANT, AAD))["pending"]


def test_confirm_idempotent_same_user(store):
	store.add()
	assert ti.confirm_teams_link(ti.create_link_token("GW-1", TENANT, AAD))["linked"]
	assert not store.created and not store.confirmations


def test_confirm_revokes_pending_when_card_cannot_be_sent(store, monkeypatch):
	from huf.ai.gateways.teams import identity_confirm as tic

	def boom(*a):
		raise tic.ConfirmationUnavailable("no personal chat")

	monkeypatch.setattr(tic, "send_confirmation", boom)
	with pytest.raises(Exception):
		ti.confirm_teams_link(ti.create_link_token("GW-1", TENANT, AAD))
	assert store.revoked and store.revoked[-1][0] == "NEW" and store.revoked[-1][1][:2] == ("state", "Revoked")
	assert ti.resolve_user("GW-1", TENANT, AAD) is None


def test_preview_shows_tenant_guid_and_untrusted_label(store):
	out = ti.preview_teams_link(ti.create_link_token("GW-1", TENANT, AAD, "Totally The CEO"))
	assert out["tenant_id"] == TENANT and out["display_label_untrusted"] == "Totally The CEO"
	assert out["person_label"] == "Totally The CEO"


# ---- room denial / guest detection (T16) -------------------------------------
def room_ev(ctype="channel"):
	e = ev()
	e.raw_payload["conversation"]["conversationType"] = ctype
	return e


@pytest.mark.parametrize("ctype", ["channel", "groupChat"])
def test_room_denial_has_no_url_and_mints_no_token(store, ctype):
	reason = denied(room_ev(ctype))
	assert reason.startswith(PREFIX) and "personal chat" in reason and "connect" in reason
	assert "http" not in reason and "token" not in reason
	assert not [k for k in ti._cache().d if k.startswith((ti._NONCE_PREFIX, ti._PROMPT_PREFIX))]


def test_personal_denial_still_has_link(store):
	assert "link-account" in denied(room_ev("personal"))


def test_home_tenant_mismatch_is_guest(store):
	e = ev(from_extra={"tenantId": "99999999-9999-9999-9999-999999999999"})
	reason = denied(e)
	assert "not supported" in reason and "token=" not in reason


def test_conversation_vs_channeldata_tenant_mismatch_is_guest(store):
	e = ev()
	e.raw_payload["channelData"]["tenant"]["id"] = "99999999-9999-9999-9999-999999999999"
	assert "not supported" in denied(e)


def test_matching_tenant_claims_not_guest(store):
	e = ev(from_extra={"tenantId": TENANT.upper()})
	assert "link-account" in denied(e)


def test_is_guest_missing_aad_object_id():
	assert ti._is_guest({"from": {"id": "29:x"}, "conversation": {"tenantId": TENANT}}) is True


def _whitelist_methods():
	"""Read the @frappe.whitelist(methods=[...]) decorators from source (import-order independent)."""
	import ast
	import inspect

	tree = ast.parse(inspect.getsource(ti))
	found = {}
	for node in tree.body:
		if not isinstance(node, ast.FunctionDef):
			continue
		for dec in node.decorator_list:
			if isinstance(dec, ast.Call) and getattr(dec.func, "attr", "") == "whitelist":
				for kw in dec.keywords:
					if kw.arg == "methods":
						found[node.name] = ast.literal_eval(kw.value)
	return found


def test_post_only_decorators():
	wl = _whitelist_methods()
	assert wl["confirm_teams_link"] == ["POST"]
	assert wl["link_teams_user"] == ["POST"]
	assert wl["revoke_teams_link"] == ["POST"]
	assert wl["preview_teams_link"] == ["GET"]


# ---- admin --------------------------------------------------------------------
def _non_admin(monkeypatch, can_write=False):
	monkeypatch.setattr(frappe, "get_roles", lambda: ["Employee"])
	monkeypatch.setattr(frappe, "has_permission", lambda *a, **k: can_write, raising=False)


def test_admin_apis_denied_for_plain_user(store, monkeypatch):
	_non_admin(monkeypatch)
	for call in (
		lambda: ti.list_teams_links("GW-1"),
		lambda: ti.link_teams_user("GW-1", TENANT, AAD, "alice@x.com"),
		lambda: ti.revoke_teams_link("L1"),
	):
		with pytest.raises(Perm):
			call()


def test_admin_apis_allowed_with_gateway_write(store, monkeypatch):
	_non_admin(monkeypatch, can_write=True)
	frappe.get_all = MagicMock(return_value=[])
	assert ti.list_teams_links("GW-1") == []


def test_guest_denied_admin(store, monkeypatch):
	monkeypatch.setattr(frappe, "session", SimpleNamespace(user="Guest"))
	with pytest.raises(Perm):
		ti.list_teams_links("GW-1")


def test_admin_link_user(store):
	out = ti.link_teams_user("GW-1", TENANT, AAD, "bob@x.com")
	assert out["user"] == "bob@x.com"
	assert store.created[0][4] == "Admin"


def test_admin_link_rejects_guest_disabled_blank(store):
	for bad in ("Guest", "disabled@x.com"):
		with pytest.raises(Exception):
			ti.link_teams_user("GW-1", TENANT, AAD, bad)
	with pytest.raises(Exception):
		ti.link_teams_user("GW-1", "", AAD, "bob@x.com")


def test_admin_link_respects_one_per_tenant(store):
	store.add(user="bob@x.com", aad="44444444-4444-4444-4444-444444444444")
	with pytest.raises(Exception):
		ti.link_teams_user("GW-1", TENANT, AAD, "bob@x.com")


def test_admin_relink_updates_existing(store):
	store.add(user="bob@x.com")
	ti.link_teams_user("GW-1", TENANT, AAD, "carol@x.com")
	assert not store.created and store.revoked


def test_revoke_sets_state(store):
	assert ti.revoke_teams_link("L1") == {"name": "L1", "state": "Revoked"}


# ---- disconnect ---------------------------------------------------------------
def test_disconnect_revokes_only_that_principal(store):
	other = "55555555-5555-5555-5555-555555555555"
	store.add()
	store.add(user="bob@x.com", aad=other)
	assert ti.disconnect_current("GW-1", TENANT, AAD) is True
	assert len(store.revoked) == 1 and store.revoked[0][0] == f"L-{AAD[:2]}-alice@x.com"


def test_disconnect_unlinked_false(store):
	assert ti.disconnect_current("GW-1", TENANT, AAD) is False
	assert ti.disconnect_current("GW-1", "", AAD) is False
	assert not store.revoked


# ---- run success --------------------------------------------------------------
def test_on_run_success_records_agent_run(store):
	store.add()
	ti.on_run_success(gw(), ev(agent_run="AR-1"), "agent", None)
	assert store.revoked[-1][0] == "AR-1"
	vals = store.revoked[-1][1][0]
	assert vals["requester_user"] == "alice@x.com" and vals["requester_external_id"] == AAD
	assert vals["gateway"] == "GW-1"


def test_on_run_success_records_flow_run(store):
	store.add()
	ti.on_run_success(gw(), ev(), "flow", SimpleNamespace(name="FR-1"))
	assert store.revoked[-1][0] == "FR-1"
	assert store.revoked[-1][1][0]["gateway_event"] == "EV-1"


# ---- registration -------------------------------------------------------------
def test_hooks_registered_for_microsoft_teams():
	run = _registered_handlers[gw_hooks.RESOLVE_RUN_USER]
	assert [h for h in run if h[3] is ti.resolve_run_user and h[2] == "microsoft teams"]
	assert ti.HOOK_PROVIDER == tc.PROVIDER_LABEL.lower() != tc.PROVIDER_ID
	ok = _registered_handlers[gw_hooks.ON_RUN_SUCCESS]
	assert [h for h in ok if h[3] is ti.on_run_success and h[2] == "microsoft teams"]


def test_hook_dispatch_only_for_teams_gateway():
	gw_hooks._HANDLERS.clear()
	gw_hooks._HANDLERS.update(_registered_handlers)
	try:
		assert ti.resolve_run_user in gw_hooks._matching(gw_hooks.RESOLVE_RUN_USER, (gw(),))
		slack = SimpleNamespace(name="S", provider="slack")
		assert ti.resolve_run_user not in gw_hooks._matching(gw_hooks.RESOLVE_RUN_USER, (slack,))
	finally:
		gw_hooks._HANDLERS.clear()
		gw_hooks._HANDLERS.update(_saved)
