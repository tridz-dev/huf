"""Tests for Slack identity mapping (huf.ai.gateways.slack.identity) and its doctype JSON."""

import datetime as _dt
import json
import unittest
import pathlib
import sys
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "testing"))
import _stub_env  # noqa: E402

_stub_env.install()

import frappe  # noqa: E402
from huf.ai.tests.unit_support import SupportCase  # noqa: E402

_TC = unittest.TestCase()

from huf.ai.gateways import hooks as gw_hooks  # noqa: E402

# Import identity with a passthrough @frappe.whitelist, without leaving its hook
# registrations behind for other test modules.
_saved_handlers = {k: list(v) for k, v in gw_hooks._HANDLERS.items()}
_orig_whitelist = frappe.whitelist
frappe.whitelist = lambda *a, **k: (lambda f: f)
try:
	from huf.ai.gateways.slack import identity  # noqa: E402
finally:
	frappe.whitelist = _orig_whitelist
	gw_hooks._HANDLERS.clear()
	gw_hooks._HANDLERS.update(_saved_handlers)

ROOT = pathlib.Path(__file__).resolve().parents[2]
HOOK_REASON_PREFIX = gw_hooks.USER_VISIBLE_PREFIX


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


def _fx_env(self):
	monkeypatch = self.monkeypatch
	cache = FakeCache()
	counter = iter(range(10000))
	monkeypatch.setattr(identity, "_", lambda s: s)
	monkeypatch.setattr(identity, "_cache", lambda: cache)
	monkeypatch.setattr(frappe, "PermissionError", Perm, raising=False)
	monkeypatch.setattr(frappe, "throw", _throw, raising=False)
	monkeypatch.setattr(frappe, "local", SimpleNamespace(conf={"encryption_key": "secret-key"}), raising=False)
	monkeypatch.setattr(frappe, "session", SimpleNamespace(user="alice@x.com"), raising=False)
	monkeypatch.setattr("frappe.utils.now_datetime", _dt.datetime.now)
	monkeypatch.setattr(frappe, "generate_hash", lambda length=10: f"nonce{next(counter)}", raising=False)
	monkeypatch.setattr(frappe, "get_roles", lambda: ["System Manager"], raising=False)
	monkeypatch.setattr(frappe.utils, "get_url", lambda: "https://huf.test", raising=False)
	monkeypatch.setattr(frappe.utils, "now", lambda: "2026-01-01 00:00:00", raising=False)
	monkeypatch.setattr(frappe, "db", MagicMock(), raising=False)
	monkeypatch.setattr(identity, "_user_enabled", lambda u: u not in ("disabled@x.com",))
	return SimpleNamespace(cache=cache)


def gw(policy="Ask to link account"):
	return SimpleNamespace(name="GW-1", provider="slack", unmapped_policy=policy, integration_settings="IS")


def _get_doc(*a, **k):
	"""Gateway for doctype lookups; an insertable stand-in for dict-built docs (Slack Action Session)."""
	if a and isinstance(a[0], dict):
		return SimpleNamespace(name="AS-1", insert=lambda **kw: None)
	return gw()


def ev(sender="U1", team="T1", **kw):
	payload = {"team_id": team, "event": {"channel": "C1"}}
	payload.update(kw.pop("payload", {}))
	return SimpleNamespace(
		name="EV-1", sender_id=sender, conversation_id="C1", thread_id="1.1", raw_payload=payload,
		agent_run=kw.pop("agent_run", None), **kw,
	)


def link(user="alice@x.com", source="Admin"):
	return SimpleNamespace(name="L1", user=user, source=source)


















# ---- auto-map -----------------------------------------------------------------
def _auto_setup(monkeypatch, info=None, users=("bob@x.com",), flag="1", workspace="T1"):
	created = []
	base = {"team_id": "T1", "is_bot": False, "deleted": False, "is_restricted": False,
		"is_ultra_restricted": False, "profile": {"email": "Bob@X.com"}}
	base.update(info or {})
	api = SimpleNamespace(users_info=lambda uid: base)
	monkeypatch.setattr(identity, "_find_link", lambda g, t, e: None)
	monkeypatch.setattr(identity, "get_gateway_credential", lambda g, k: flag)
	monkeypatch.setattr(identity, "get_slack_api", lambda g: api)
	monkeypatch.setattr("huf.ai.gateways.slack.api.inspect_token", lambda a: {"team_id": workspace})
	monkeypatch.setattr(frappe, "get_all", lambda *a, **k: list(users), raising=False)
	monkeypatch.setattr(identity, "_create_link", lambda *a, **k: created.append(a))
	monkeypatch.setattr(identity, "_has_revoked", lambda g, t, e: False)
	return created




















# ---- self-link token ----------------------------------------------------------
def fake_confirm(monkeypatch, send):
	"""Temporarily install a fake identity_confirm (no sys.modules / package attribute leaks)."""
	import types as _t

	import huf.ai.gateways.slack as pkg

	mod = _t.ModuleType("huf.ai.gateways.slack.identity_confirm")
	mod.send_confirmation = send
	monkeypatch.setitem(sys.modules, "huf.ai.gateways.slack.identity_confirm", mod)
	monkeypatch.setattr(pkg, "identity_confirm", mod, raising=False)








































# ---- JSON sanity --------------------------------------------------------------
JSONS = [
	"huf/doctype/gateway_identity_link/gateway_identity_link.json",
	"huf/doctype/agent_run/agent_run.json",
	"huf/doctype/flow_run/flow_run.json",
	"huf/doctype/gateway/gateway.json",
]






# ---- A1b: URL, throttle, preview labels ----------------------------------------
def _ask(monkeypatch, event=None):
	monkeypatch.setattr(identity, "_find_link", lambda g, t, e: None)
	monkeypatch.setattr(identity, "get_gateway_credential", lambda g, k: "")
	with _TC.assertRaises(gw_hooks.GatewayHookDenied) as exc:
		identity.resolve_run_user(gw(), event or ev())
	return exc.exception.reason


_AUTOUSE = (_fx_env,)


class TestModule(SupportCase):
	# ---- lookup -------------------------------------------------------------------
	def test_linked_hit(self):
		monkeypatch = self.monkeypatch
		monkeypatch.setattr(identity, "_find_link", lambda g, t, e: link())
		assert identity.resolve_run_user(gw(), ev()) == "alice@x.com"

	def test_lookup_passes_team_and_sender(self):
		monkeypatch = self.monkeypatch
		seen = []
		monkeypatch.setattr(identity, "_find_link", lambda g, t, e: seen.append((g, t, e)) or link())
		identity.resolve_run_user(gw(), ev(sender="U9", team="T9"))
		assert seen == [("GW-1", "T9", "U9")]

	def test_miss_team_mismatch_is_unlinked(self):
		monkeypatch = self.monkeypatch
		monkeypatch.setattr(identity, "_find_link", lambda g, t, e: link() if t == "T1" else None)
		monkeypatch.setattr(identity, "get_gateway_credential", lambda g, k: "")
		with self.assertRaises(gw_hooks.GatewayHookDenied):
			identity.resolve_run_user(gw(), ev(team="T2"))

	def test_missing_team_denied_admin_only(self):
		e = ev()
		e.raw_payload = {}
		with self.assertRaises(gw_hooks.GatewayHookDenied) as exc:
			identity.resolve_run_user(gw(), e)
		assert not exc.exception.reason.startswith(HOOK_REASON_PREFIX)

	def test_team_from_event_attr_and_json_string(self):
		monkeypatch = self.monkeypatch
		monkeypatch.setattr(identity, "_find_link", lambda g, t, e: link())
		e = ev()
		e.raw_payload = "{}"
		e.team_id = "T1"
		assert identity.resolve_run_user(gw(), e) == "alice@x.com"

	def test_linked_guest_never_returned(self):
		monkeypatch = self.monkeypatch
		monkeypatch.setattr(identity, "_find_link", lambda g, t, e: link("Guest"))
		with self.assertRaises(gw_hooks.GatewayHookDenied):
			identity.resolve_run_user(gw(), ev())

	def test_linked_disabled_user_denied(self):
		monkeypatch = self.monkeypatch
		monkeypatch.setattr(identity, "_find_link", lambda g, t, e: link("disabled@x.com"))
		with self.assertRaises(gw_hooks.GatewayHookDenied) as exc:
			identity.resolve_run_user(gw(), ev())
		assert exc.exception.reason.startswith(HOOK_REASON_PREFIX)

	def test_administrator_only_if_admin_linked(self):
		monkeypatch = self.monkeypatch
		monkeypatch.setattr(identity, "_find_link", lambda g, t, e: link("Administrator", "Admin"))
		assert identity.resolve_run_user(gw(), ev()) == "Administrator"
		monkeypatch.setattr(identity, "_find_link", lambda g, t, e: link("Administrator", "Auto email"))
		with self.assertRaises(gw_hooks.GatewayHookDenied):
			identity.resolve_run_user(gw(), ev())

	def test_auto_map_success(self):
		monkeypatch = self.monkeypatch
		created = _auto_setup(monkeypatch)
		assert identity.resolve_run_user(gw(), ev()) == "bob@x.com"
		assert created and created[0][4] == "Auto email"

	def test_auto_map_flag_off(self):
		for flag in ["", "0"]:
			with self.subTest(flag=flag):
				self.reset_fixtures()
				monkeypatch = self.monkeypatch
				created = _auto_setup(monkeypatch, flag=flag)
				with self.assertRaises(gw_hooks.GatewayHookDenied):
					identity.resolve_run_user(gw(), ev())
				assert not created

	def test_auto_map_rejects_unsafe_users(self):
		for info in [{"is_bot": True}, {"deleted": True}, {"is_restricted": True}, {"is_ultra_restricted": True},
	 {"team_id": "T-OTHER"}, {"profile": {}}]:
			with self.subTest(info=info):
				self.reset_fixtures()
				monkeypatch = self.monkeypatch
				created = _auto_setup(monkeypatch, info=info)
				with self.assertRaises(gw_hooks.GatewayHookDenied):
					identity.resolve_run_user(gw(), ev())
				assert not created

	def test_auto_map_ambiguous_email(self):
		monkeypatch = self.monkeypatch
		created = _auto_setup(monkeypatch, users=("a@x.com", "b@x.com"))
		with self.assertRaises(gw_hooks.GatewayHookDenied):
			identity.resolve_run_user(gw(), ev())
		assert not created

	def test_auto_map_no_frappe_user(self):
		monkeypatch = self.monkeypatch
		_auto_setup(monkeypatch, users=())
		with self.assertRaises(gw_hooks.GatewayHookDenied):
			identity.resolve_run_user(gw(), ev())

	def test_auto_map_event_team_not_workspace(self):
		monkeypatch = self.monkeypatch
		created = _auto_setup(monkeypatch, workspace="T-GATEWAY")
		with self.assertRaises(gw_hooks.GatewayHookDenied):
			identity.resolve_run_user(gw(), ev())
		assert not created

	def test_auto_map_never_administrator(self):
		monkeypatch = self.monkeypatch
		created = _auto_setup(monkeypatch, users=("Administrator",))
		with self.assertRaises(gw_hooks.GatewayHookDenied):
			identity.resolve_run_user(gw(), ev())
		assert not created

	# ---- policy + deny message ----------------------------------------------------
	def test_ask_policy_message_is_user_visible_with_link(self):
		monkeypatch = self.monkeypatch
		monkeypatch.setattr(identity, "_find_link", lambda g, t, e: None)
		monkeypatch.setattr(identity, "get_gateway_credential", lambda g, k: "")
		with self.assertRaises(gw_hooks.GatewayHookDenied) as exc:
			identity.resolve_run_user(gw(), ev())
		r = exc.exception.reason
		assert r.startswith(HOOK_REASON_PREFIX) and "https://huf.test/huf/link-account?token=" in r
		assert "@" not in r.split("token=")[1]

	def test_service_user_policy_returns_none(self):
		monkeypatch = self.monkeypatch
		monkeypatch.setattr(identity, "_find_link", lambda g, t, e: None)
		monkeypatch.setattr(identity, "get_gateway_credential", lambda g, k: "")
		assert identity.resolve_run_user(gw("Use service user"), ev()) is None

	def test_token_roundtrip_and_confirm(self):
		monkeypatch = self.monkeypatch
		env = self.use(_fx_env)
		created = []
		monkeypatch.setattr(identity, "_create_link", lambda *a, **k: created.append(a))
		monkeypatch.setattr(identity, "_find_link", lambda g, t, e: None)
		monkeypatch.setattr(frappe, "get_doc", _get_doc, raising=False)
		tok = identity.create_self_link_token("GW-1", "T1", "U1")
		assert identity.preview_self_link(tok)["external_id"] == "U1"
		sent = []
		fake_confirm(monkeypatch, lambda *a: sent.append(a))
		monkeypatch.setattr(identity, "_create_link", lambda *a, **k: created.append((a, k)) or SimpleNamespace(name="L5"))
		assert identity.confirm_self_link(tok) == {"linked": False, "pending": True, "user": "alice@x.com"}
		args, kw = created[0]
		assert args[2:5] == ("U1", "alice@x.com", "Self link") and kw["state"] == "Pending"
		assert sent[0][1:] == ("L5", "T1", "U1", "alice@x.com")

	def test_token_replay_rejected(self):
		monkeypatch = self.monkeypatch
		fake_confirm(monkeypatch, lambda *a: None)
		monkeypatch.setattr(identity, "_create_link", lambda *a, **k: SimpleNamespace(name="L5"))
		monkeypatch.setattr(identity, "_find_link", lambda g, t, e: None)
		monkeypatch.setattr(frappe, "get_doc", _get_doc, raising=False)
		tok = identity.create_self_link_token("GW-1", "T1", "U1")
		identity.confirm_self_link(tok)
		with self.assertRaises(Perm):
			identity.confirm_self_link(tok)

	def test_token_tamper_rejected(self):
		tok = identity.create_self_link_token("GW-1", "T1", "U1")
		body, sig = tok.split(".")
		forged = identity._b64(json.dumps({"g": "GW-1", "t": "T1", "x": "U-EVIL", "e": 9999999999, "n": "nonce0"}).encode())
		for bad in (f"{forged}.{sig}", f"{body}.{'0' * 64}", "garbage", "", None):
			with self.assertRaises(Perm):
				identity.confirm_self_link(bad)

	def test_token_expired(self):
		monkeypatch = self.monkeypatch
		tok = identity.create_self_link_token("GW-1", "T1", "U1")
		real = time.time
		monkeypatch.setattr(identity.time, "time", lambda: real() + identity.TOKEN_TTL_SECONDS + 5)
		with self.assertRaises(Perm):
			identity.confirm_self_link(tok)

	def test_confirm_rejects_bad_callers(self):
		for user in ["Guest", "Administrator", "disabled@x.com"]:
			with self.subTest(user=user):
				self.reset_fixtures()
				monkeypatch = self.monkeypatch
				tok = identity.create_self_link_token("GW-1", "T1", "U1")
				monkeypatch.setattr(frappe, "session", SimpleNamespace(user=user))
				with self.assertRaises(Perm):
					identity.confirm_self_link(tok)

	def test_confirm_refuses_identity_linked_to_other_user(self):
		monkeypatch = self.monkeypatch
		tok = identity.create_self_link_token("GW-1", "T1", "U1")
		monkeypatch.setattr(identity, "_find_link", lambda g, t, e: link("bob@x.com"))
		monkeypatch.setattr(frappe, "get_doc", _get_doc, raising=False)
		with self.assertRaises(Perm):
			identity.confirm_self_link(tok)

	def test_token_has_no_email(self):
		tok = identity.create_self_link_token("GW-1", "T1", "U1")
		assert "@" not in tok and "alice" not in tok

	# ---- admin APIs ---------------------------------------------------------------
	def test_admin_apis_reject_guest_and_unprivileged(self):
		monkeypatch = self.monkeypatch
		monkeypatch.setattr(frappe, "has_permission", lambda *a, **k: False, raising=False)
		monkeypatch.setattr(frappe, "get_roles", lambda: ["Huf User"])
		monkeypatch.setattr(frappe.db, "get_value", lambda *a, **k: "GW-1")
		for fn, args in ((identity.list_identity_links, ("GW-1",)),
				(identity.link_identity, ("GW-1", "T1", "U1", "bob@x.com")),
				(identity.unlink_identity, ("L1",))):
			with self.assertRaises(Perm):
				fn(*args)
		monkeypatch.setattr(frappe, "session", SimpleNamespace(user="Guest"))
		monkeypatch.setattr(frappe, "get_roles", lambda: ["System Manager"])
		with self.assertRaises(Perm):
			identity.list_identity_links("GW-1")

	def test_gateway_write_permission_allows(self):
		monkeypatch = self.monkeypatch
		monkeypatch.setattr(frappe, "get_roles", lambda: ["Huf Manager"])
		monkeypatch.setattr(frappe, "has_permission", lambda dt, p, n=None, **k: dt == "Gateway" and p == "write", raising=False)
		monkeypatch.setattr(frappe, "get_all", lambda *a, **k: [{"name": "L1"}], raising=False)
		assert identity.list_identity_links("GW-1") == [{"name": "L1"}]

	def test_link_identity_rejects_guest_target(self):
		with self.assertRaises(Exception):
			identity.link_identity("GW-1", "T1", "U1", "Guest")

	def test_link_identity_creates_admin_link(self):
		monkeypatch = self.monkeypatch
		created = []
		monkeypatch.setattr(identity, "_find_link", lambda g, t, e: None)
		monkeypatch.setattr(identity, "_create_link", lambda *a, **k: created.append(a) or SimpleNamespace(name="L9"))
		monkeypatch.setattr(frappe, "get_doc", _get_doc, raising=False)
		assert identity.link_identity("GW-1", "T1", "U1", "bob@x.com") == {"name": "L9", "user": "bob@x.com"}
		assert created[0][4] == "Admin"

	def test_unlink_revokes(self):
		monkeypatch = self.monkeypatch
		monkeypatch.setattr(frappe.db, "get_value", lambda *a, **k: "GW-1")
		assert identity.unlink_identity("L1")["state"] == "Revoked"
		frappe.db.set_value.assert_called_with(identity.DOCTYPE, "L1", "state", "Revoked")

	# ---- conversation key ---------------------------------------------------------
	def test_key_per_user_when_unthreaded(self):
		a = identity.resolve_conversation_key(gw(), ev(sender="U1"))
		b = identity.resolve_conversation_key(gw(), ev(sender="U2"))
		assert a == "T1:C1:U1" and b == "T1:C1:U2" and a != b

	def test_key_per_thread_shared_between_users(self):
		p = {"event": {"channel": "C1", "thread_ts": "99.9"}}
		a = identity.resolve_conversation_key(gw(), ev(sender="U1", payload=p))
		b = identity.resolve_conversation_key(gw(), ev(sender="U2", payload=p))
		assert a == b == "T1:C1:99.9"

	def test_key_falls_back_to_gateway_name_and_none(self):
		e = ev()
		e.raw_payload = {}
		assert identity.resolve_conversation_key(gw(), e) == "GW-1:C1:U1"
		e.sender_id = ""
		assert identity.resolve_conversation_key(gw(), e) is None

	# ---- requester recording ------------------------------------------------------
	def test_requester_recorded_for_agent(self):
		monkeypatch = self.monkeypatch
		monkeypatch.setattr(identity, "_find_link", lambda g, t, e: link("bob@x.com"))
		identity.on_run_success(gw(), ev(agent_run="AR-1"), "agent", "ok")
		frappe.db.set_value.assert_called_with(
			"Agent Run", "AR-1",
			{"gateway": "GW-1", "gateway_event": "EV-1", "requester_external_id": "U1", "requester_user": "bob@x.com"},
			update_modified=False,
		)

	def test_requester_recorded_for_flow(self):
		monkeypatch = self.monkeypatch
		monkeypatch.setattr(identity, "_find_link", lambda g, t, e: None)
		identity.on_run_success(gw(), ev(), "flow", SimpleNamespace(name="FR-1"))
		frappe.db.set_value.assert_called_with(
			"Flow Run", "FR-1",
			{"gateway_event": "EV-1", "requester_external_id": "U1", "requester_user": "alice@x.com"},
			update_modified=False,
		)

	def test_recording_failure_never_raises(self):
		monkeypatch = self.monkeypatch
		monkeypatch.setattr(identity, "_find_link", lambda g, t, e: link())
		frappe.db.set_value.side_effect = RuntimeError("db down")
		monkeypatch.setattr(frappe, "log_error", MagicMock(), raising=False)
		monkeypatch.setattr(frappe, "get_traceback", lambda: "tb", raising=False)
		identity.on_run_success(gw(), ev(agent_run="AR-1"), "agent", "ok")

	def test_import_registers_expected_hooks(self):
		src = pathlib.Path(identity.__file__).read_text()
		for h in ("RESOLVE_RUN_USER", "RESOLVE_CONVERSATION_KEY", "ON_RUN_SUCCESS"):
			assert f"gw_hooks.register(gw_hooks.{h}" in src and 'provider="slack"' in src

	def test_json_valid_and_fields_ordered(self):
		for rel in JSONS:
			with self.subTest(rel=rel):
				self.reset_fixtures()
				doc = json.loads((ROOT / rel).read_text())
				names = [f["fieldname"] for f in doc["fields"]]
				assert len(names) == len(set(names))
				assert set(doc["field_order"]) == set(names) and len(doc["field_order"]) == len(names)

	def test_new_fields_present(self):
		def fields(rel):
			return {f["fieldname"]: f for f in json.loads((ROOT / rel).read_text())["fields"]}

		ar, fr, g = fields(JSONS[1]), fields(JSONS[2]), fields(JSONS[3])
		for n in ("gateway", "gateway_event", "requester_external_id", "requester_user"):
			assert ar[n]["read_only"] == 1
		for n in ("gateway_event", "requester_external_id", "requester_user"):
			assert fr[n]["read_only"] == 1
		assert g["unmapped_policy"]["default"] == "Ask to link account"
		assert g["unmapped_policy"]["options"] == "Ask to link account\nUse service user"
		idl = fields(JSONS[0])
		assert idl["state"]["options"] == "Pending\nLinked\nRevoked"
		assert idl["source"]["options"] == "Auto email\nAdmin\nSelf link"

	def test_self_link_url_format(self):
		assert identity.self_link_url("abc.def") == "https://huf.test/huf/link-account?token=abc.def"

	def test_prompt_throttle_reuses_token_within_window(self):
		monkeypatch = self.monkeypatch
		env = self.use(_fx_env)
		first = _ask(monkeypatch)
		second = _ask(monkeypatch)
		assert first == second
		assert len([k for k in env.cache.d if k.startswith(identity._NONCE_PREFIX)]) == 1

	def test_prompt_throttle_mints_new_after_ttl(self):
		monkeypatch = self.monkeypatch
		env = self.use(_fx_env)
		first = _ask(monkeypatch)
		for k in [k for k in env.cache.d if k.startswith(identity._PROMPT_PREFIX)]:
			env.cache.delete_value(k)  # TTL elapsed
		second = _ask(monkeypatch)
		assert first != second

	def test_prompt_throttle_is_per_sender(self):
		monkeypatch = self.monkeypatch
		assert _ask(monkeypatch, ev(sender="U1")) != _ask(monkeypatch, ev(sender="U2"))

	def test_prompt_mints_new_if_cached_token_was_used(self):
		monkeypatch = self.monkeypatch
		env = self.use(_fx_env)
		first = _ask(monkeypatch)
		for k in [k for k in env.cache.d if k.startswith(identity._NONCE_PREFIX)]:
			env.cache.delete_value(k)
		assert _ask(monkeypatch) != first

	def test_preview_includes_labels(self):
		monkeypatch = self.monkeypatch
		tok = identity.create_self_link_token("GW-1", "T1", "U1", "Sam Rivera")
		out = identity.preview_self_link(tok)
		assert out["slack_label"] == "Sam Rivera" and out["workspace_label"] == "GW-1"

	def test_preview_label_falls_back_to_id_and_event_label_used(self):
		monkeypatch = self.monkeypatch
		out = identity.preview_self_link(identity.create_self_link_token("GW-1", "T1", "U1"))
		assert out["slack_label"] == "U1"
		e = ev(payload={"event": {"channel": "C1", "user_profile": {"display_name": "sam"}}})
		reason = _ask(monkeypatch, e)
		tok = reason.split("token=")[1]
		assert identity.preview_self_link(tok)["slack_label"] == "sam"

	# ---- S8 hardening ---------------------------------------------------------------
	def test_auto_map_skips_revoked_identity(self):
		monkeypatch = self.monkeypatch
		created = _auto_setup(monkeypatch)
		monkeypatch.setattr(identity, "_has_revoked", lambda g, t, e: True)
		with self.assertRaises(gw_hooks.GatewayHookDenied):
			identity.resolve_run_user(gw(), ev())
		assert not created

	def test_pending_link_does_not_resolve(self):
		monkeypatch = self.monkeypatch
		# _find_link only matches state Linked
		seen = {}
		monkeypatch.setattr(frappe.db, "get_value", lambda dt, filters, *a, **k: seen.update(f=filters))
		assert identity._find_link("GW-1", "T1", "U1") is None
		assert seen["f"]["state"] == "Linked"

	def test_service_policy_none_only_after_handler_ran(self):
		monkeypatch = self.monkeypatch
		monkeypatch.setattr(identity, "_find_link", lambda g, t, e: None)
		monkeypatch.setattr(identity, "get_gateway_credential", lambda g, k: "")
		monkeypatch.setattr(identity, "_has_revoked", lambda g, t, e: False)
		assert identity.resolve_run_user(gw("Use service user"), ev()) is None

	def test_auto_map_error_propagates_not_swallowed(self):
		monkeypatch = self.monkeypatch
		_auto_setup(monkeypatch)
		monkeypatch.setattr(identity, "get_slack_api", lambda g: (_ for _ in ()).throw(RuntimeError("down")))
		with self.assertRaises(RuntimeError):
			identity.resolve_run_user(gw(), ev())

	def test_nonce_consumed_once_even_if_cache_gate_passes_twice(self):
		"""Atomic claim: a second confirm with the same token fails even if the nonce key is still there."""
		monkeypatch = self.monkeypatch
		fake_confirm(monkeypatch, lambda *a: None)
		monkeypatch.setattr(identity, "_create_link", lambda *a, **k: SimpleNamespace(name="L5"))
		monkeypatch.setattr(identity, "_find_link", lambda g, t, e: None)
		monkeypatch.setattr(frappe, "get_doc", _get_doc, raising=False)
		tok = identity.create_self_link_token("GW-1", "T1", "U1")
		real_delete = identity._cache().delete_value
		identity._cache().delete_value = lambda k: None  # simulate the lost-delete race
		try:
			identity.confirm_self_link(tok)
			with self.assertRaises(Perm):
				identity.confirm_self_link(tok)
		finally:
			identity._cache().delete_value = real_delete

	def test_concurrent_confirm_blocked_by_key_lock(self):
		monkeypatch = self.monkeypatch
		fake_confirm(monkeypatch, lambda *a: None)
		created = []
		monkeypatch.setattr(identity, "_create_link", lambda *a, **k: created.append(a) or SimpleNamespace(name="L5"))
		monkeypatch.setattr(identity, "_find_link", lambda g, t, e: None)
		monkeypatch.setattr(frappe, "get_doc", _get_doc, raising=False)
		tok = identity.create_self_link_token("GW-1", "T1", "U1")
		held = identity.key_lock("GW-1", "T1", "U1")
		assert held
		with self.assertRaises(Perm):
			identity.confirm_self_link(tok)
		assert not created
		identity.release_key_lock(held)

	def test_confirm_dm_failure_revokes_pending(self):
		monkeypatch = self.monkeypatch
		def boom(*a):
			raise RuntimeError("no im:write")

		fake_confirm(monkeypatch, boom)
		monkeypatch.setattr(identity, "_create_link", lambda *a, **k: SimpleNamespace(name="L5"))
		monkeypatch.setattr(identity, "_find_link", lambda g, t, e: None)
		monkeypatch.setattr(frappe, "get_doc", _get_doc, raising=False)
		monkeypatch.setattr(frappe, "log_error", lambda *a, **k: None, raising=False)
		monkeypatch.setattr(frappe, "get_traceback", lambda: "tb", raising=False)
		tok = identity.create_self_link_token("GW-1", "T1", "U1")
		with self.assertRaises(Exception):
			identity.confirm_self_link(tok)
		frappe.db.set_value.assert_called_with(identity.DOCTYPE, "L5", "state", "Revoked")

	def test_gateway_writer_cannot_link_privileged_user(self):
		for target, roles in [("Administrator", []), ("boss@x.com", ["System Manager"])]:
			with self.subTest(target=target, roles=roles):
				self.reset_fixtures()
				monkeypatch = self.monkeypatch
				monkeypatch.setattr(frappe, "get_roles", lambda user=None: roles if user else ["Huf Manager"])
				monkeypatch.setattr(frappe, "has_permission", lambda *a, **k: True, raising=False)
				monkeypatch.setattr(identity, "_find_link", lambda g, t, e: None)
				monkeypatch.setattr(identity, "_create_link", lambda *a, **k: self.fail("must not link"))
				monkeypatch.setattr(frappe, "get_doc", _get_doc, raising=False)
				with self.assertRaises(Perm):
					identity.link_identity("GW-1", "T1", "U1", target)

	def test_gateway_writer_cannot_take_over_privileged_existing_link(self):
		monkeypatch = self.monkeypatch
		monkeypatch.setattr(frappe, "get_roles", lambda user=None: ["System Manager"] if user else ["Huf Manager"])
		monkeypatch.setattr(frappe, "has_permission", lambda *a, **k: True, raising=False)
		monkeypatch.setattr(identity, "_find_link", lambda g, t, e: SimpleNamespace(name="L1", user="bob@x.com"))
		monkeypatch.setattr(frappe, "get_doc", _get_doc, raising=False)
		with self.assertRaises(Perm):
			identity.link_identity("GW-1", "T1", "U1", "carol@x.com")

	def test_gateway_writer_can_link_ordinary_user(self):
		monkeypatch = self.monkeypatch
		monkeypatch.setattr(frappe, "get_roles", lambda user=None: ["Huf User"] if user else ["Huf Manager"])
		monkeypatch.setattr(frappe, "has_permission", lambda *a, **k: True, raising=False)
		monkeypatch.setattr(identity, "_find_link", lambda g, t, e: None)
		monkeypatch.setattr(identity, "_create_link", lambda *a, **k: SimpleNamespace(name="L9"))
		monkeypatch.setattr(frappe, "get_doc", _get_doc, raising=False)
		assert identity.link_identity("GW-1", "T1", "U1", "bob@x.com")["user"] == "bob@x.com"

	def test_system_manager_can_link_administrator(self):
		monkeypatch = self.monkeypatch
		monkeypatch.setattr(identity, "_find_link", lambda g, t, e: None)
		monkeypatch.setattr(identity, "_create_link", lambda *a, **k: SimpleNamespace(name="L9"))
		monkeypatch.setattr(frappe, "get_doc", _get_doc, raising=False)
		assert identity.link_identity("GW-1", "T1", "U1", "Administrator")["user"] == "Administrator"

	def test_usable_rejects_administrator_for_non_admin_sources(self):
		for source in ["Self link", "Auto email", None]:
			with self.subTest(source=source):
				self.reset_fixtures()
				assert identity._usable("Administrator", source) is False
				assert identity._usable("Administrator", "Admin") is True
