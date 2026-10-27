"""Unit tests for huf/ai/gateways/teams_diagnostics.py (frappe is a MagicMock stub)."""

from __future__ import annotations

import json
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _stub_env  # noqa: E402

_stub_env.install()

import frappe  # noqa: E402
import pytest  # noqa: E402

_original_whitelist = frappe.whitelist
frappe.whitelist = lambda *a, **k: (lambda fn: fn)
for _m in ("huf.ai.gateways.teams_diagnostics", "huf.ai.gateways.teams_tenant"):
	sys.modules.pop(_m, None)
try:
	from huf.ai.gateways import teams_diagnostics as td  # noqa: E402
finally:
	frappe.whitelist = _original_whitelist

from huf.ai.gateways import teams_api, teams_tenant  # noqa: E402
from huf.ai.gateways import teams_contract as tc  # noqa: E402

CANARY_SECRET = "CANARY-APP-SECRET-9f3a"
CANARY_TOKEN = "CANARYTOKEN123456"
CANARY_TEXT = "CANARY private message body"
CANARY_URL = "https://files.example.com/CANARY-file.pdf"
HOME = "11111111-1111-4111-8111-111111111111"
OTHER = "22222222-2222-4222-8222-222222222222"


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
		self.roles = ["System Manager"]
		self.has_perm = False
		self.provider = "Microsoft Teams"
		self.creds = {"app_id": "app-1", "app_password": CANARY_SECRET, "tenant_id": HOME}
		self.tables = {}
		self.calls = []
		self.linked = 3
		self.settings = {}
		self.raise_on = set()


def _plain(f):
	return f.split(" as ")[-1].strip() if " as " in f else f


@pytest.fixture
def env(monkeypatch):
	st = State()
	teams_tenant.clear_cache()
	frappe.PermissionError = PermErr
	frappe.ValidationError = ValErr
	frappe.DoesNotExistError = NotFound
	monkeypatch.setattr(frappe, "throw", _throw)
	monkeypatch.setattr(frappe, "_", lambda s: s, raising=False)
	monkeypatch.setattr(frappe, "get_roles", lambda *a: st.roles)
	monkeypatch.setattr(frappe, "has_permission", lambda *a, **k: st.has_perm)
	monkeypatch.setattr(frappe.utils, "get_url", lambda *a: "https://site.example.com", raising=False)
	monkeypatch.setattr(frappe.utils, "now_datetime", lambda: __import__("datetime").datetime(2026, 10, 27, 12), raising=False)

	def get_all(doctype, **kw):
		st.calls.append((doctype, kw))
		if doctype in st.raise_on:
			raise RuntimeError("db exploded " + CANARY_SECRET)
		rows = st.tables.get(doctype, [])
		fields = [_plain(f) for f in kw.get("fields", [])]
		flt = kw.get("filters") or {}
		rows = [r for r in rows if all(r.get(k) == v for k, v in flt.items() if k == "status")]
		out = [{k: v for k, v in r.items() if k in fields} for r in rows]
		return out[: kw.get("limit_page_length", 20)]

	def count(doctype, filters=None):
		st.calls.append((doctype + ":count", {"filters": filters}))
		return st.linked

	monkeypatch.setattr(
		frappe, "db", SimpleNamespace(exists=lambda dt, n=None: n == "gw1", count=count), raising=False
	)
	monkeypatch.setattr(frappe, "get_all", get_all)

	def get_doc(dt, name=None):
		if dt == "Integration Settings":
			rows = [SimpleNamespace(key=k, get_password=lambda _f, v=v: v) for k, v in st.creds.items()]
			return SimpleNamespace(credentials=rows)
		return SimpleNamespace(name=name, provider=st.provider, integration_settings="is1")

	monkeypatch.setattr(frappe, "get_doc", get_doc)
	monkeypatch.setattr(teams_tenant, "get_settings", lambda gw: {"allowed_tenants": st.settings.get("allowed", ""),
		"app_package_version": st.settings.get("ver", "")})
	monkeypatch.setattr(td, "_token_fn", lambda creds, gateway_name=None: "tok-" + CANARY_TOKEN)
	yield st
	teams_tenant.clear_cache()


def by_id(report):
	return {c["id"]: c for c in report["checks"]}


def run(env):
	return td.teams_diagnose("gw1")


# ------------------------------------------------------------ permission/provider

def test_system_manager_ok(env):
	assert run(env)["checks"]


def test_gateway_write_permission_ok(env):
	env.roles, env.has_perm = ["Desk User"], True
	assert run(env)["checks"]


def test_non_admin_denied(env):
	env.roles = ["Desk User"]
	with pytest.raises(PermErr):
		td.teams_diagnose("gw1")
	with pytest.raises(PermErr):
		td.teams_support_bundle("gw1")


def test_wrong_provider_rejected(env):
	env.provider = "Slack"
	with pytest.raises(ValErr):
		td.teams_diagnose("gw1")
	with pytest.raises(ValErr):
		td.teams_support_bundle("gw1")


def test_unknown_gateway(env):
	with pytest.raises(NotFound):
		td.teams_diagnose("nope")


def test_blank_gateway(env):
	with pytest.raises(ValErr):
		td.teams_diagnose("")


# ------------------------------------------------------------------ credentials

def test_credentials_pass(env):
	c = by_id(run(env))
	assert c["credentials_present"]["status"] == "pass"
	assert c["credential_expiry"]["status"] == "info"


def test_credentials_missing_fail(env):
	env.creds["app_password"] = ""
	c = by_id(run(env))
	assert c["credentials_present"]["status"] == "fail"
	assert "app_password" in c["credentials_present"]["detail"]
	assert c["token_acquisition"]["status"] == "fail"


# ------------------------------------------------------------------------ token

def test_token_pass(env):
	assert by_id(run(env))["token_acquisition"]["status"] == "pass"


@pytest.mark.parametrize("code,needle", [("invalid_client", "secret"), ("unauthorized_client", "Tenant"),
	("invalid_tenant_id", "tenant"), ("weird_code", "Retry")])
def test_token_failure_mapping(env, monkeypatch, code, needle):
	def boom(creds, gateway_name=None):
		raise teams_api.TeamsApiError(401, code=code)

	monkeypatch.setattr(td, "_token_fn", boom)
	c = by_id(run(env))["token_acquisition"]
	assert c["status"] == "fail"
	assert needle in c["how_to_fix"]
	assert CANARY_SECRET not in json.dumps(c)


def test_token_failure_with_leaky_exception_message(env, monkeypatch):
	def boom(creds, gateway_name=None):
		raise teams_api.TeamsApiError(400, code="invalid_client")

	monkeypatch.setattr(td, "_token_fn", boom)
	assert "Bearer" not in json.dumps(run(env))


# --------------------------------------------------------------------- endpoint

def test_endpoint_url_exact_route(env):
	c = by_id(run(env))["messaging_endpoint"]
	assert c["detail"] == ("https://site.example.com/api/method/huf.ai.gateway_webhook."
		"handle_gateway_webhook?gateway_name=gw1")
	assert c["status"] == "pass"


def test_endpoint_http_warns(env, monkeypatch):
	monkeypatch.setattr(frappe.utils, "get_url", lambda *a: "http://site.local")
	assert by_id(run(env))["messaging_endpoint"]["status"] == "warn"


# ---------------------------------------------------------------------- tenants

def test_tenants_empty_warns(env):
	assert by_id(run(env))["allowed_tenants"]["status"] == "warn"


def test_tenants_configured_pass(env):
	env.settings["allowed"] = OTHER
	assert by_id(run(env))["allowed_tenants"]["status"] == "pass"


# ----------------------------------------------------------------- inbound/rejects

def test_no_inbound_warns(env):
	c = by_id(run(env))["last_inbound"]
	assert c["status"] == "warn" and "help" in c["how_to_fix"]


def test_last_inbound_pass(env):
	env.tables["Gateway Event"] = [{"name": "e1", "status": "Succeeded", "received_at": "2026-10-27 11:00:00",
		"message_text": CANARY_TEXT}]
	c = by_id(run(env))["last_inbound"]
	assert c["status"] == "pass"
	assert CANARY_TEXT not in json.dumps(run(env))


def test_rejections_none_pass(env):
	assert by_id(run(env))["rejections_24h"]["status"] == "pass"


def test_rejections_grouped_warn_counts_only(env):
	env.tables["Gateway Event"] = [
		{"name": "e1", "status": "Rejected", "error_message": "tenant_not_allowed", "n": 4, "received_at": "x"},
		{"name": "e2", "status": "Rejected", "error_message": "bad_signature token=" + CANARY_TOKEN, "n": 1, "received_at": "x"},
	]
	rep = run(env)
	c = by_id(rep)["rejections_24h"]
	assert c["status"] == "warn"
	assert "tenant_not_allowed: 4" in c["detail"]
	assert CANARY_TOKEN not in json.dumps(rep)


# ---------------------------------------------------------------- references/outbox

def test_references_none_warns(env):
	assert by_id(run(env))["conversation_references"]["status"] == "warn"
	assert by_id(run(env))["private_send_ready"]["status"] == "warn"


def test_references_counts_and_private_ready(env):
	env.tables["Teams Conversation Reference"] = [
		{"conversation_type": "personal", "n": 5}, {"conversation_type": "channel", "n": 2}]
	c = by_id(run(env))
	assert "personal: 5" in c["conversation_references"]["detail"]
	assert c["private_send_ready"]["status"] == "pass"


def test_outbox_clean_pass(env):
	env.tables["Teams Outbound Message"] = [{"status": "Sent", "n": 9}]
	assert by_id(run(env))["outbox"]["status"] == "pass"


def test_outbox_failed_warns(env):
	env.tables["Teams Outbound Message"] = [{"status": "Failed", "n": 2}]
	assert by_id(run(env))["outbox"]["status"] == "warn"


def test_outbox_dead_fails_with_names_and_trimmed_error(env):
	env.tables["Teams Outbound Message"] = [
		{"status": "Dead", "n": 1, "name": "OUT-1", "last_error": "x" * 500 + " Bearer " + CANARY_TOKEN}]
	rep = run(env)
	c = by_id(rep)["outbox"]
	assert c["status"] == "fail" and "OUT-1" in c["detail"]
	assert CANARY_TOKEN not in json.dumps(rep)
	bundle = td.teams_support_bundle("gw1")
	assert len(bundle["dead_letters"][0]["last_error"]) <= td.ERROR_CLIP


# ------------------------------------------------------------------ links/package

def test_linked_users(env):
	assert by_id(run(env))["linked_users"]["status"] == "pass"
	env.linked = 0
	assert by_id(run(env))["linked_users"]["status"] == "warn"


def test_package_version(env):
	assert "No version" in by_id(run(env))["app_package"]["detail"]
	env.settings["ver"] = "1.2.3"
	assert "1.2.3" in by_id(run(env))["app_package"]["detail"]


# ------------------------------------------------------------------ robustness

def test_one_check_raising_does_not_break_rest(env):
	env.raise_on.add("Gateway Event")
	rep = run(env)
	c = by_id(rep)
	assert c["last_inbound"]["status"] == "fail"
	assert c["rejections_24h"]["status"] == "fail"
	assert c["credentials_present"]["status"] == "pass"
	assert c["outbox"]["status"] in ("pass", "warn", "fail")
	assert CANARY_SECRET not in json.dumps(rep)


def test_queries_bounded_and_not_n_plus_one(env):
	env.tables["Teams Outbound Message"] = [{"status": "Dead", "n": 1, "name": f"O{i}", "last_error": "e"} for i in range(60)]
	run(env)
	assert all("limit_page_length" in kw for dt, kw in env.calls if not dt.endswith(":count"))
	assert all(kw["limit_page_length"] <= 50 for dt, kw in env.calls if not dt.endswith(":count"))
	assert len(env.calls) <= 8


def test_summary_counts(env):
	rep = run(env)
	assert sum(rep["summary"].values()) == len(rep["checks"])
	for c in rep["checks"]:
		assert set(c) == {"id", "status", "title", "detail", "how_to_fix"}
		assert c["status"] in ("pass", "warn", "fail", "info")


def test_secrets_absent_everywhere(env):
	env.tables["Gateway Event"] = [{"name": "e", "status": "Rejected", "error_message": "secret=" + CANARY_SECRET,
		"n": 1, "received_at": "t", "message_text": CANARY_TEXT, "raw_payload": CANARY_URL}]
	env.tables["Teams Outbound Message"] = [{"status": "Dead", "n": 1, "name": "O1",
		"last_error": "password=" + CANARY_SECRET, "payload": CANARY_TEXT}]
	blob = json.dumps(run(env)) + json.dumps(td.teams_support_bundle("gw1"))
	for canary in (CANARY_SECRET, CANARY_TOKEN, CANARY_TEXT, CANARY_URL):
		assert canary not in blob


# ---------------------------------------------------------------- support bundle

def test_bundle_shape_and_json_able(env):
	env.settings["ver"] = "2.0.0"
	b = td.teams_support_bundle("gw1")
	json.dumps(b)
	assert b["contract_version"] == tc.CONTRACT_VERSION
	assert b["app_package_version"] == "2.0.0"
	assert b["fields_configured"] == ["app_id", "app_secret", "tenant_id"]
	assert {"id", "status"} == set(b["checks"][0])
	assert "creds" not in b


def test_bundle_has_no_endpoint_or_detail_text(env):
	b = json.dumps(td.teams_support_bundle("gw1"))
	assert "handle_gateway_webhook" not in b and "tok-" not in b
