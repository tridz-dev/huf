"""Unit tests for huf/ai/gateways/teams_tenant.py (frappe is a MagicMock stub)."""

from __future__ import annotations

import json
import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _stub_env  # noqa: E402

_stub_env.install()

import frappe  # noqa: E402
import pytest  # noqa: E402

_original_whitelist = frappe.whitelist
frappe.whitelist = lambda *a, **k: (lambda fn: fn)
sys.modules.pop("huf.ai.gateways.teams_tenant", None)
try:
	from huf.ai.gateways import teams_tenant as tt  # noqa: E402
finally:
	frappe.whitelist = _original_whitelist

from huf.ai.gateways import hooks  # noqa: E402
from huf.ai.gateways import teams_contract as tc  # noqa: E402

HOME = "11111111-1111-4111-8111-111111111111"
OTHER = "22222222-2222-4222-8222-222222222222"
FOREIGN = "33333333-3333-4333-8333-333333333333"


class PermErr(Exception):
	pass


class ValErr(Exception):
	pass


class NotFound(Exception):
	pass


def _throw(msg, exc=None, *a, **k):
	raise (exc or Exception)(msg)


class State:
	def __init__(self):
		self.rows = {}
		self.roles = ["System Manager"]
		self.has_perm = False
		self.gateways = {"gw1"}
		self.saved = []


@pytest.fixture(autouse=True)
def env(monkeypatch):
	st = State()
	tt.clear_cache()
	frappe.PermissionError = PermErr
	frappe.ValidationError = ValErr
	frappe.DoesNotExistError = NotFound
	monkeypatch.setattr(frappe, "throw", _throw)
	monkeypatch.setattr(frappe, "_", lambda s: s, raising=False)
	monkeypatch.setattr(frappe, "get_roles", lambda *a: st.roles)
	monkeypatch.setattr(frappe, "has_permission", lambda *a, **k: st.has_perm)
	monkeypatch.setattr(frappe.flags, "gateway_filter_reason", None, raising=False)

	def get_value(doctype, name, fields, as_dict=False):
		return st.rows.get(name)

	def exists(doctype, name=None):
		if doctype == "Gateway":
			return name in st.gateways
		return name in st.rows

	frappe.db = SimpleNamespace(get_value=get_value, exists=exists)

	class Doc:
		def __init__(self, data):
			self.data = dict(data)

		def update(self, v):
			self.data.update(v)

		def save(self, **k):
			st.rows[self.data["gateway"]] = self.data
			st.saved.append(dict(self.data))

		insert = save

	monkeypatch.setattr(frappe, "get_doc", lambda dt, name=None: Doc({"gateway": name, **st.rows.get(name, {})}) if isinstance(dt, str) and dt == tt.SETTINGS_DOCTYPE else Doc(dt))
	yield st
	tt.clear_cache()


def gw(home=HOME, name="gw1"):
	creds = [SimpleNamespace(key="tenant_id", get_password=lambda _f, h=home: h)] if home else []
	settings = SimpleNamespace(credentials=creds)
	g = SimpleNamespace(name=name, provider="Microsoft Teams", integration_settings="is1")
	g._settings = settings
	return g


@pytest.fixture(autouse=True)
def creds(monkeypatch, env):
	real = frappe.get_doc

	def get_doc(dt, name=None):
		if dt == "Integration Settings":
			return SimpleNamespace(credentials=env_creds["v"])
		return real(dt, name)

	env_creds = {"v": [SimpleNamespace(key="tenant_id", get_password=lambda _f: HOME)]}
	monkeypatch.setattr(frappe, "get_doc", get_doc)
	return env_creds


def ctx(tenant=HOME, conv_tenant=None):
	raw = {"channelData": {"tenant": {"id": tenant}} if tenant else {}, "conversation": {}}
	if conv_tenant:
		raw["conversation"]["tenantId"] = conv_tenant
	return {"raw_payload": raw}


# ---- GUID validation -----------------------------------------------------------
def test_normalize_guid_lowercases():
	assert tt.normalize_guid(HOME.upper()) == HOME


@pytest.mark.parametrize(
	"bad", ["", None, "contoso.onmicrosoft.com", "{" + HOME + "}", HOME + "x", "1234", 5, HOME[:-1]]
)
def test_normalize_guid_rejects(bad):
	assert tt.normalize_guid(bad) == ""


def test_parse_dedupes_and_splits():
	text = f"{HOME}\n{OTHER.upper()}\n\n{HOME}, {FOREIGN}"
	assert tt.parse_tenant_text(text) == [HOME, OTHER, FOREIGN]


def test_parse_strict_rejects_domain():
	with pytest.raises(ValErr):
		tt.parse_tenant_text("contoso.com", strict=True)


def test_parse_lenient_skips_garbage():
	assert tt.parse_tenant_text(f"junk\n{HOME}") == [HOME]


def test_normalize_text_roundtrip():
	assert tt.normalize_tenant_text(f"{HOME.upper()}\n{OTHER}") == f"{HOME}\n{OTHER}"


# ---- settings / defaults -------------------------------------------------------
def test_defaults_without_record():
	s = tt.get_settings("gw1")
	assert s["private_output_policy"] == "Private when records touched"
	assert tt.get_allowed_tenants("gw1") == []


def test_settings_read_from_row(env):
	env.rows["gw1"] = {"allowed_tenants": f"{OTHER}", "private_output_policy": "Channel", "bot_handle": ""}
	tt.clear_cache()
	assert tt.get_settings("gw1")["private_output_policy"] == "Channel"
	assert tt.get_allowed_tenants("gw1") == [OTHER]


# ---- allowlist semantics -------------------------------------------------------
def test_empty_list_allows_home_only():
	assert tt.is_tenant_allowed(gw(), HOME)
	assert not tt.is_tenant_allowed(gw(), OTHER)


def test_empty_list_and_no_home_denies_all(creds):
	creds["v"] = []
	assert not tt.is_tenant_allowed(gw(), HOME)


def test_home_case_insensitive(creds):
	creds["v"] = [SimpleNamespace(key="tenant_id", get_password=lambda _f: HOME.upper())]
	assert tt.is_tenant_allowed(gw(), HOME)


def test_explicit_list_overrides_home(env):
	env.rows["gw1"] = {"allowed_tenants": OTHER}
	assert tt.is_tenant_allowed(gw(), OTHER.upper())
	assert not tt.is_tenant_allowed(gw(), HOME)


def test_missing_or_bad_tenant_rejected():
	assert not tt.is_tenant_allowed(gw(), None)
	assert not tt.is_tenant_allowed(gw(), "contoso.com")


def test_allowlist_change_takes_effect_after_clear(env):
	assert not tt.is_tenant_allowed(gw(), OTHER)
	env.rows["gw1"] = {"allowed_tenants": OTHER}
	assert not tt.is_tenant_allowed(gw(), OTHER)  # still cached
	tt.clear_cache("gw1")
	assert tt.is_tenant_allowed(gw(), OTHER)


def test_cache_expires(env, monkeypatch):
	tt.get_settings("gw1")
	env.rows["gw1"] = {"allowed_tenants": OTHER}
	t = [tt.time.monotonic() + tt.CACHE_TTL_SECONDS + 1]
	monkeypatch.setattr(tt.time, "monotonic", lambda: t[0])
	assert tt.get_allowed_tenants("gw1") == [OTHER]


# ---- filter --------------------------------------------------------------------
def test_filter_home_passes():
	assert tt.pre_ingest_filter(gw(), ctx(HOME)) is True


def test_filter_foreign_rejected_and_reason():
	assert tt.pre_ingest_filter(gw(), ctx(FOREIGN)) is False
	assert frappe.flags.gateway_filter_reason == "tenant_not_allowed"


def test_filter_missing_tenant_rejected():
	assert tt.pre_ingest_filter(gw(), ctx(None)) is False
	assert tt.pre_ingest_filter(gw(), {}) is False
	assert tt.pre_ingest_filter(gw(), None) is False


def test_filter_conversation_tenant_fallback():
	assert tt.pre_ingest_filter(gw(), ctx(None, HOME.upper())) is True


def test_filter_conflicting_claims_rejected():
	assert tt.pre_ingest_filter(gw(), ctx(HOME, FOREIGN)) is False


def test_filter_malformed_payload_rejected():
	assert tt.pre_ingest_filter(gw(), {"raw_payload": {"channelData": "x", "conversation": 3}}) is False


# ---- hook registration ---------------------------------------------------------
def test_hook_registered_for_provider_and_priority():
	entries = [h for h in hooks._HANDLERS.get(hooks.PRE_INGEST_FILTER, []) if h[3] is tt.pre_ingest_filter]
	if not entries:  # other tests may have cleared the registry; re-import registers again
		import importlib

		frappe.whitelist = lambda *a, **k: (lambda fn: fn)
		importlib.reload(tt)
		entries = [h for h in hooks._HANDLERS.get(hooks.PRE_INGEST_FILTER, []) if h[3] is tt.pre_ingest_filter]
	assert len(entries) >= 1
	prio, _seq, prov, _fn = entries[-1]
	assert prio == tc.HOOK_PRIORITY_TENANT == 20
	assert prov == "microsoft teams"


def test_hook_dispatch_drops_foreign_only_for_teams():
	hooks.clear()
	hooks.register(hooks.PRE_INGEST_FILTER, tt.pre_ingest_filter, provider="Microsoft Teams", priority=20)
	assert hooks.call_all(hooks.PRE_INGEST_FILTER, gw(), ctx(FOREIGN)) == [False]
	slack = SimpleNamespace(provider="Slack", name="s")
	assert hooks.call_all(hooks.PRE_INGEST_FILTER, slack, {}) == []
	hooks.clear()


# ---- whitelisted APIs ----------------------------------------------------------
def test_get_requires_permission(env):
	env.roles = ["Guest"]
	with pytest.raises(PermErr):
		tt.get_teams_settings("gw1")


def test_get_allowed_via_gateway_permission(env):
	env.roles = ["Desk User"]
	env.has_perm = True
	assert tt.get_teams_settings("gw1")["allowed_tenant_list"] == []


def test_save_denied_without_permission(env):
	env.roles = ["Desk User"]
	with pytest.raises(PermErr):
		tt.save_teams_settings("gw1", allowed_tenants=HOME)
	assert env.saved == []


def test_save_rejects_free_form_tenant(env):
	with pytest.raises(ValErr):
		tt.save_teams_settings("gw1", allowed_tenants="contoso.onmicrosoft.com")
	assert env.saved == []


def test_save_normalizes_and_invalidates_cache(env):
	tt.get_settings("gw1")
	out = tt.save_teams_settings("gw1", allowed_tenants=[OTHER.upper(), HOME])
	assert out["allowed_tenant_list"] == [OTHER, HOME]
	assert tt.is_tenant_allowed(gw(), OTHER)


def test_save_unknown_gateway_and_policy(env):
	with pytest.raises(NotFound):
		tt.save_teams_settings("nope")
	with pytest.raises(ValErr):
		tt.save_teams_settings("gw1", private_output_policy="Whatever")


# ---- doctype json --------------------------------------------------------------
def test_doctype_json_field_order():
	path = os.path.join(
		os.path.dirname(__file__), "..", "..", "huf", "doctype", "teams_gateway_settings", "teams_gateway_settings.json"
	)
	meta = json.load(open(path))
	names = [f["fieldname"] for f in meta["fields"]]
	assert meta["field_order"] == names == [
		"gateway", "allowed_tenants", "bot_handle", "app_package_version",
		"private_output_policy", "help_text_override",
	]
	g = meta["fields"][0]
	assert g["unique"] == 1 and g["reqd"] == 1 and g["options"] == "Gateway"
	assert meta["autoname"] == "field:gateway"
	assert meta["fields"][4]["default"] == "Private when records touched"
	assert [p["role"] for p in meta["permissions"]] == ["System Manager"]
