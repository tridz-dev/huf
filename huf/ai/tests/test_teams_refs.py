import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, "huf/ai/tests")
import _stub_env  # noqa: E402

_stub_env.install()

import pytest  # noqa: E402

from huf.ai.gateways import hooks  # noqa: E402
from huf.ai.gateways import teams_contract as tc  # noqa: E402
from huf.ai.gateways import teams_refs as refs  # noqa: E402
from huf.ai.gateways.teams_refs import reference_name  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures" / "teams"
DOCTYPE_JSON = (
	Path(__file__).parents[2]
	/ "huf/doctype/teams_conversation_reference/teams_conversation_reference.json"
)
TENANT = "00000000-0000-0000-0000-00000000aaaa"
AAD = "00000000-0000-0000-0000-0000000000u1"
BOT = "28:00000000-0000-0000-0000-0000000000b1"


def load(name):
	return json.loads((FIXTURES / f"{name}.json").read_text())


class DupError(Exception):
	pass


class FakeDB:
	def __init__(self):
		self.rows = {}

	def _match(self, row, filters):
		return all(row.get(k) == v for k, v in filters.items())

	def get_value(self, doctype, filters, field):
		for name, row in self.rows.items():
			if self._match(row, filters):
				return name
		return None

	def set_value(self, doctype, name, values):
		self.rows[name].update(values)

	def get_all(self, doctype, filters=None, fields=None, order_by=None, limit=None):
		out = [dict(r) for r in self.rows.values() if self._match(r, filters or {})]
		out.sort(key=lambda r: r.get("last_seen_at") or 0, reverse=True)
		return out[:limit] if limit else out


@pytest.fixture
def db(monkeypatch):
	fake = FakeDB()
	counter = {"t": 0}

	def now():
		counter["t"] += 1
		return counter["t"]

	def get_doc(values):
		def insert(ignore_permissions=False):
			name = reference_name(values["gateway"], values["tenant_id"], values["conversation_id"])
			if name in fake.rows:
				raise DupError(name)
			fake.rows[name] = dict(values, name=name)
			doc.name = name

		doc = SimpleNamespace(insert=insert, name=None)
		return doc

	fr = SimpleNamespace(db=fake, get_all=fake.get_all, get_doc=get_doc, DuplicateEntryError=DupError)
	monkeypatch.setattr(refs, "frappe", fr)
	monkeypatch.setattr(refs, "now_datetime", now)
	refs.set_tenant_allowed_check(lambda gw, tenant: tenant == TENANT)
	yield fake
	refs.set_tenant_allowed_check(None)


GW = SimpleNamespace(name="gw1", provider="Microsoft Teams")


# --- parse_meta ---------------------------------------------------------------------------


@pytest.mark.parametrize("fixture", sorted(p.stem for p in FIXTURES.glob("*.json")))
def test_parse_meta_every_fixture(fixture):
	m = refs.parse_meta(load(fixture))
	assert isinstance(m, tc.TeamsMeta)
	assert m.tenant_id and m.service_url.startswith("https://")
	assert m.conversation_id and m.bot_id == BOT
	assert m.conversation_type in ("personal", "channel", "groupChat")


def test_parse_meta_channel_details():
	m = refs.parse_meta(load("channel_mention"))
	assert m.conversation_type == "channel"
	assert m.root_id == "1700000000100"
	assert m.team_id == "19:faketeam@thread.tacv2"
	assert m.channel_id == "19:fakechannel@thread.tacv2"
	assert m.user_aad_id == AAD and m.tenant_id == TENANT


def test_parse_meta_personal_has_no_root():
	m = refs.parse_meta(load("personal_message"))
	assert m.root_id == "" and m.team_id == "" and m.conversation_type == "personal"


def test_parse_meta_tenant_fallback_and_garbage():
	m = refs.parse_meta({"conversation": {"tenantId": "T"}})
	assert m.tenant_id == "T"
	assert refs.parse_meta(None) == tc.TeamsMeta()
	assert refs.parse_meta({"conversation": None, "channelData": None}).tenant_id == ""


# --- upsert / lifecycle -------------------------------------------------------------------


def test_upsert_creates_then_idempotent(db):
	m = refs.parse_meta(load("personal_message"))
	a = refs.upsert_reference("gw1", m)
	b = refs.upsert_reference("gw1", m)
	assert a == b and len(db.rows) == 1
	row = db.rows[a]
	assert row["installed"] == 1 and row["user_aad_id"] == AAD and row["bot_id"] == BOT


def test_upsert_bumps_last_seen(db):
	m = refs.parse_meta(load("personal_message"))
	name = refs.upsert_reference("gw1", m)
	first = db.rows[name]["last_seen_at"]
	refs.upsert_reference("gw1", m)
	assert db.rows[name]["last_seen_at"] > first


def test_service_url_updates_when_changed(db):
	act = load("personal_message")
	name = refs.upsert_reference("gw1", refs.parse_meta(act))
	act["serviceUrl"] = "https://smba.trafficmanager.net/emea/"
	refs.upsert_reference("gw1", refs.parse_meta(act))
	assert db.rows[name]["service_url"].endswith("/emea/")


def test_partial_activity_does_not_blank_fields(db):
	name = refs.upsert_reference("gw1", refs.parse_meta(load("personal_message")))
	refs.upsert_reference("gw1", tc.TeamsMeta(tenant_id=TENANT, conversation_id="a:1fakeconversation"))
	assert db.rows[name]["service_url"] and db.rows[name]["user_aad_id"] == AAD


def test_upsert_requires_key_parts(db):
	with pytest.raises(ValueError):
		refs.upsert_reference("gw1", tc.TeamsMeta(tenant_id=TENANT))


def test_channel_reference_is_per_channel_not_per_thread(db):
	act = load("channel_mention")
	n1 = refs.upsert_reference("gw1", refs.parse_meta(act))
	act["conversation"]["id"] = "19:fakechannel@thread.tacv2;messageid=999"
	n2 = refs.upsert_reference("gw1", refs.parse_meta(act))
	assert n1 == n2 and db.rows[n1]["conversation_id"] == "19:fakechannel@thread.tacv2"


def test_uninstall_flips_installed_and_reinstall_restores(db):
	m = refs.parse_meta(load("personal_message"))
	name = refs.upsert_reference("gw1", m)
	assert refs.mark_uninstalled("gw1", m) == name
	assert db.rows[name]["installed"] == 0
	refs.upsert_reference("gw1", m)
	assert db.rows[name]["installed"] == 1


def test_mark_uninstalled_unknown_creates_nothing(db):
	assert refs.mark_uninstalled("gw1", refs.parse_meta(load("personal_message"))) is None
	assert db.rows == {}


def test_unique_key_semantics(db):
	m = refs.parse_meta(load("personal_message"))
	n1 = refs.upsert_reference("gw1", m)
	n2 = refs.upsert_reference("gw2", m)  # other gateway: separate row
	assert n1 != n2 and len(db.rows) == 2
	assert reference_name("gw1", TENANT, "x") == reference_name("gw1", TENANT, "x")
	assert reference_name("gw1", TENANT, "x") != reference_name("gw1", "other", "x")


def test_duplicate_insert_race_falls_back_to_update(db, monkeypatch):
	m = refs.parse_meta(load("personal_message"))
	name = reference_name("gw1", TENANT, m.conversation_id)
	real_find = refs._find
	calls = {"n": 0}

	def find(*a):
		calls["n"] += 1
		return None if calls["n"] == 1 else real_find(*a)

	db.rows[name] = {"name": name, "gateway": "gw1", "tenant_id": TENANT, "conversation_id": m.conversation_id}
	monkeypatch.setattr(refs, "_find", find)
	assert refs.upsert_reference("gw1", m) == name
	assert db.rows[name]["installed"] == 1


# --- personal lookup ----------------------------------------------------------------------


def test_personal_lookup(db):
	refs.upsert_reference("gw1", refs.parse_meta(load("personal_message")))
	ref = refs.get_personal_reference("gw1", TENANT, AAD)
	assert ref and ref["conversation_type"] == "personal"


def test_personal_lookup_none_when_uninstalled(db):
	m = refs.parse_meta(load("personal_message"))
	refs.upsert_reference("gw1", m)
	refs.mark_uninstalled("gw1", m)
	assert refs.get_personal_reference("gw1", TENANT, AAD) is None


def test_personal_lookup_ignores_channels_and_other_tenants(db):
	refs.upsert_reference("gw1", refs.parse_meta(load("channel_mention")))
	assert refs.get_personal_reference("gw1", TENANT, AAD) is None
	refs.upsert_reference("gw1", refs.parse_meta(load("personal_message")))
	assert refs.get_personal_reference("gw1", "other-tenant", AAD) is None
	assert refs.get_personal_reference("gw1", TENANT, "") is None


def test_no_cross_tenant_leak_same_user_id(db):
	refs.upsert_reference("gw1", refs.parse_meta(load("foreign_tenant_message")))
	foreign = refs.parse_meta(load("foreign_tenant_message"))
	assert refs.get_personal_reference("gw1", TENANT, foreign.user_aad_id) is None
	assert refs.get_personal_reference("gw1", foreign.tenant_id, foreign.user_aad_id)


# --- hooks --------------------------------------------------------------------------------


def test_install_add_recorded_and_dropped(db):
	assert refs._pre_ingest_install(GW, {"raw_payload": load("installation_add")}) is False
	assert refs.get_personal_reference("gw1", TENANT, AAD)


def test_install_remove_recorded_and_dropped(db):
	refs._pre_ingest_install(GW, {"raw_payload": load("installation_add")})
	assert refs._pre_ingest_install(GW, {"raw_payload": load("installation_remove")}) is False
	assert refs.get_personal_reference("gw1", TENANT, AAD) is None
	assert len(db.rows) == 1


def test_conversation_update_bot_added_and_removed(db):
	act = load("conversation_update")
	assert refs._pre_ingest_install(GW, {"raw_payload": act}) is False
	assert len(db.rows) == 1 and next(iter(db.rows.values()))["installed"] == 1
	act["membersAdded"], act["membersRemoved"] = None, [{"id": BOT}]
	assert refs._pre_ingest_install(GW, {"raw_payload": act}) is False
	assert next(iter(db.rows.values()))["installed"] == 0


def test_conversation_update_other_member_dropped_without_row(db):
	act = load("conversation_update")
	act["membersAdded"] = [{"id": "29:someoneelse"}]
	assert refs._pre_ingest_install(GW, {"raw_payload": act}) is False
	assert db.rows == {}


def test_normal_message_passes_filter(db):
	assert refs._pre_ingest_install(GW, {"raw_payload": load("personal_message")}) is True
	assert refs._pre_ingest_install(GW, {}) is True
	assert db.rows == {}


def test_raw_payload_may_be_json_string(db):
	ctx = {"raw_payload": json.dumps(load("installation_add"))}
	assert refs._pre_ingest_install(GW, ctx) is False and len(db.rows) == 1


def test_foreign_tenant_install_creates_no_row(db):
	refs.set_tenant_allowed_check(lambda gw, tenant: tenant == TENANT)
	act = load("installation_add")
	act["channelData"]["tenant"]["id"] = "foreign"
	act["conversation"]["tenantId"] = "foreign"
	assert refs._pre_ingest_install(GW, {"raw_payload": act}) is False
	assert db.rows == {}


def test_event_received_upserts_message_only(db):
	ev = SimpleNamespace(raw_payload=load("personal_message"))
	refs._on_event_received(GW, ev)
	assert len(db.rows) == 1
	refs._on_event_received(GW, SimpleNamespace(raw_payload=load("installation_remove")))
	assert next(iter(db.rows.values()))["installed"] == 1  # install kinds do not touch via this hook


def test_event_received_foreign_tenant_no_row(db):
	refs.set_tenant_allowed_check(lambda gw, tenant: False)
	refs._on_event_received(GW, SimpleNamespace(raw_payload=load("foreign_tenant_message")))
	assert db.rows == {}


def test_hooks_registered_for_lowercased_provider_label():
	hooks.clear()
	importlib.reload(refs)
	assert refs.HOOK_PROVIDER == "microsoft teams" != tc.PROVIDER_ID
	flt = [h for h in hooks._HANDLERS[hooks.PRE_INGEST_FILTER] if h[3] is refs._pre_ingest_install]
	assert flt and flt[0][0] == tc.HOOK_PRIORITY_INSTALL and flt[0][2] == "microsoft teams"
	assert hooks._provider_of((GW,)) == refs.HOOK_PROVIDER
	rcv = [h for h in hooks._HANDLERS[hooks.ON_EVENT_RECEIVED] if h[3] is refs._on_event_received]
	assert rcv and rcv[0][2] == "microsoft teams"


# --- doctype JSON -------------------------------------------------------------------------


def test_doctype_json_sanity():
	d = json.loads(DOCTYPE_JSON.read_text())
	names = [f["fieldname"] for f in d["fields"]]
	assert [n for n in d["field_order"]] == names
	assert len(set(names)) == len(names)
	for required in ("gateway", "tenant_id", "conversation_id", "conversation_type", "service_url",
		"team_id", "channel_id", "user_aad_id", "bot_id", "installed", "last_seen_at"):
		assert required in names
	assert [p["role"] for p in d["permissions"]] == ["System Manager"]
	by = {f["fieldname"]: f for f in d["fields"]}
	assert by["gateway"]["fieldtype"] == "Link" and by["installed"]["fieldtype"] == "Check"
	assert by["conversation_type"]["options"].split("\n") == ["personal", "channel", "groupChat"]


# --- T16: production default is the real allowlist, fail closed --------------------------


def test_default_tenant_check_is_teams_tenant_and_fails_closed(db, monkeypatch):
	import importlib

	refs.set_tenant_allowed_check(None)  # production default
	assert refs._tenant_allowed is refs._default_tenant_allowed
	tt = importlib.import_module("huf.ai.gateways.teams_tenant")
	monkeypatch.setattr(tt, "is_tenant_allowed", lambda gw, t: t == TENANT)
	act = load("installation_add")
	assert refs._pre_ingest_install(GW, {"raw_payload": act}) is False
	assert len(db.rows) == 1
	foreign = load("installation_add")
	foreign["channelData"]["tenant"]["id"] = "foreign"
	foreign["conversation"]["tenantId"] = "foreign"
	foreign["conversation"]["id"] = "19:other@thread.tacv2"
	assert refs._pre_ingest_install(GW, {"raw_payload": foreign}) is False
	assert len(db.rows) == 1  # no row, no state change for a foreign tenant
	monkeypatch.setattr(tt, "is_tenant_allowed", lambda gw, t: 1 / 0)
	again = load("installation_add")
	again["conversation"]["id"] = "19:third@thread.tacv2"
	refs._pre_ingest_install(GW, {"raw_payload": again})
	assert len(db.rows) == 1  # exception => fail closed


def test_foreign_conversation_update_and_uninstall_change_nothing(db):
	for fixture in ("conversation_update", "installation_remove"):
		try:
			act = load(fixture)
		except FileNotFoundError:
			continue
		act["channelData"]["tenant"]["id"] = "foreign"
		act["conversation"]["tenantId"] = "foreign"
		before = dict(db.rows)
		assert refs._pre_ingest_install(GW, {"raw_payload": act}) is False
		assert db.rows == before
