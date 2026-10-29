"""D1: direct_policy 'Open' is allowed only for identity-gated providers (Slack, Microsoft Teams)."""

from __future__ import annotations

import importlib
import importlib.util
import os
import sys
import types
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, os.pardir, "testing"))
import _stub_env  # noqa: E402

_stub_env.install()

import frappe  # noqa: E402
from huf.ai.tests.unit_support import SupportCase  # noqa: E402

from huf.ai.gateways import identity_policy  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def _mod(name, **attrs):
	m = types.ModuleType(name)
	m.__dict__.update(attrs)
	return m


def _fx_heavy(self):
	"""Load the Gateway controller and gateway_service with the adapter layer stubbed."""
	monkeypatch = self.monkeypatch

	def _throw(msg, *a, **k):
		raise ValueError(str(msg))

	monkeypatch.setattr(frappe, "throw", _throw, raising=False)
	monkeypatch.setattr(frappe, "_", lambda s, *a: s, raising=False)
	pkg = _mod("huf.ai.gateway_adapters")
	pkg.__path__ = []
	model = _mod("frappe.model")
	document = _mod("frappe.model.document", Document=object)
	stubs = {
		"frappe.model": model,
		"frappe.model.document": document,
		"frappe.rate_limiter": _mod("frappe.rate_limiter", rate_limit=lambda **k: (lambda f: f)),
		"huf.ai.gateway_adapters": pkg,
		"huf.ai.gateway_adapters.provider_hooks": _mod("h", get=lambda *a, **k: None),
		"huf.ai.gateway_adapters.provider_ids": _mod("p", provider_to_service_id=lambda x: x),
		"huf.ai.gateway_adapters.registered": _mod("r", get_adapter_class=lambda *a, **k: None),
		"huf.ai.gateway_adapters.types": _mod("t", GatewayReply=object),
	}
	for k, v in stubs.items():
		monkeypatch.setitem(sys.modules, k, v)
	for k in ("huf.ai.gateway_webhook", "huf.ai.gateway_service"):
		monkeypatch.delitem(sys.modules, k, raising=False)
	spec = importlib.util.spec_from_file_location(
		"_gateway_doctype_under_test", ROOT / "huf/doctype/gateway/gateway.py"
	)
	mod = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(mod)
	gs = importlib.import_module("huf.ai.gateway_service")
	try:
		yield SimpleNamespace(Gateway=mod.Gateway, gs=gs)
	finally:
		sys.modules.pop("huf.ai.gateway_service", None)


def _doc(provider, policy="Open"):
	d = SimpleNamespace(
		provider=provider, direct_policy=policy, is_enabled=0, execution_user="",
		default_target_type="", default_agent="", default_flow="", integration_settings="",
	)
	d.get = lambda key, default=None: getattr(d, key, default)
	return d


class TestModule(SupportCase):
	def test_open_allowed_for_identity_providers(self):
		for provider in ["Slack", "slack", "Microsoft Teams", "microsoft teams", " MICROSOFT TEAMS "]:
			with self.subTest(provider=provider):
				self.reset_fixtures()
				heavy = self.use(_fx_heavy)
				heavy.Gateway.validate(_doc(provider))

	def test_open_blocked_for_other_providers(self):
		for provider in ["Telegram", "WhatsApp", "Discord", "", None]:
			with self.subTest(provider=provider):
				self.reset_fixtures()
				heavy = self.use(_fx_heavy)
				with self.assertRaisesRegex(ValueError, "Public direct-message gateways are not available"):
					heavy.Gateway.validate(_doc(provider))

	def test_other_policies_unaffected(self):
		heavy = self.use(_fx_heavy)
		heavy.Gateway.validate(_doc("Telegram", "Allow list"))
		heavy.Gateway.validate(_doc("Slack", "Allow list"))

	def test_shared_constant_is_the_service_constant(self):
		heavy = self.use(_fx_heavy)
		gs = heavy.gs
		assert gs.IDENTITY_REQUIRED_PROVIDERS is identity_policy.IDENTITY_REQUIRED_PROVIDERS
		assert identity_policy.is_identity_required("Slack")
		assert not identity_policy.is_identity_required("Telegram")
		assert not identity_policy.is_identity_required(None)

	def test_admission_still_admits_open(self):
		heavy = self.use(_fx_heavy)
		gs = heavy.gs
		gw = SimpleNamespace(direct_policy="Open", provider="Slack")
		assert gs._admission(gw, {"sender_id": "U1", "conversation_id": "D1", "is_room": False}) == (True, "")

	def test_slack_direct_policy_check(self):
		slack_setup = importlib.import_module("huf.ai.gateways.slack.setup")
		ok = slack_setup._direct_policy_check(SimpleNamespace(direct_policy="Open"))
		assert ok["id"] == "direct_policy" and ok["status"] == "pass" and ok["ok"] and ok["informational"]
		warn = slack_setup._direct_policy_check(SimpleNamespace(direct_policy="Allow list"))
		assert warn["status"] == "warn" and not warn["ok"]
		assert warn["how_to_fix"].startswith("Set the access policy to Open")

		class Boom:
			@property
			def direct_policy(self):
				raise RuntimeError("x")

		assert slack_setup._direct_policy_check(Boom())["status"] == "warn"

	def test_teams_direct_policy_check(self):
		monkeypatch = self.monkeypatch
		monkeypatch.setattr(frappe, "_", lambda s, *a: s, raising=False)
		td = importlib.import_module("huf.ai.gateways.teams.diagnostics")
		ok = td._check_direct_policy({"direct_policy": "Open"})[0]
		assert ok["id"] == "direct_policy" and ok["status"] == td.PASS
		warn = td._check_direct_policy({})[0]
		assert warn["status"] == td.WARN and "Open" in warn["how_to_fix"]
		assert any(cid == "direct_policy" for cid, _fn in td._CHECKS)

	def test_health_explanation(self):
		health = importlib.import_module("huf.ai.gateways.health")
		gs = SimpleNamespace(_has_access_entry=lambda *a: False)
		ctx = {"sender_id": "U1", "conversation_id": "D1", "is_room": False}
		slack = SimpleNamespace(direct_policy="Allow list", provider="Slack")
		assert "Open" in health._admission_check(gs, slack, ctx)["how_to_fix"]
		tele = SimpleNamespace(direct_policy="Allow list", provider="Telegram")
		assert "Open" not in health._admission_check(gs, tele, ctx)["how_to_fix"]
		opened = SimpleNamespace(direct_policy="Open", provider="Slack")
		assert health._admission_check(gs, opened, ctx)["ok"] is True
