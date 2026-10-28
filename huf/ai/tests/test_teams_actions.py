import ast
import copy
import importlib
import json
import py_compile
import pathlib
import sys
import threading
from datetime import datetime, timedelta
from pathlib import Path
from types import ModuleType, SimpleNamespace

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "testing"))
import _stub_env  # noqa: E402

_stub_env.install()

import pytest  # noqa: E402

from huf.ai.gateways import hooks  # noqa: E402
from huf.ai.gateways.teams.messaging import cards  # noqa: E402
from huf.ai.gateways.teams import contract as tc  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures" / "teams"
TENANT = "00000000-0000-0000-0000-00000000aaaa"
AAD = "00000000-0000-0000-0000-0000000000u1"
AAD2 = "00000000-0000-0000-0000-0000000000u2"
CONV = "a:1fakeconversation"
GW = SimpleNamespace(name="gw1", provider="Microsoft Teams")
NOW = datetime(2026, 1, 1, 12, 0, 0)


class Perm(Exception):
	pass


PermissionError_ = type("PermissionError", (Exception,), {})


def fresh_module():
	sys.modules.pop("huf.ai.gateways.teams.actions", None)
	pkg = sys.modules.get("huf.ai.gateways")
	if pkg is not None and hasattr(pkg, "teams_actions"):
		delattr(pkg, "teams_actions")
	hooks.clear()
	return importlib.import_module("huf.ai.gateways.teams.actions")


class Sess:
	def __init__(self, world):
		self.w = world

	@property
	def user(self):
		return self.w.user


class FakeCache:
	def __init__(self):
		self.d = {}

	def get_value(self, k):
		return self.d.get(k)

	def set_value(self, k, v, expires_in_sec=None):
		self.d[k] = v


class FakeDb:
	"""In-memory Teams Action Session table honouring the conditional UPDATEs."""

	def __init__(self, world):
		self.w = world
		self.lock = threading.Lock()
		self._cursor = SimpleNamespace(rowcount=0)
		self.tls = threading.local()

	def sql(self, query, params=()):
		with self.lock:
			n = 0
			if "SET state='Decided'" in query:
				actor, name, now = params
				row = self.w.sessions.get(name)
				if row and row["state"] == "Open" and row["expires_at"] > now:
					row["state"], row["decided_by"] = "Decided", actor
					n = 1
			elif "SET state='Open'" in query:
				name, actor = params
				row = self.w.sessions.get(name)
				if row and row["state"] == "Decided" and row["decided_by"] == actor and not row.get("decision"):
					row["state"], row["decided_by"] = "Open", None
					n = 1
			elif "SET state='Expired'" in query:
				row = self.w.sessions.get(params[0])
				if row and row["state"] == "Open":
					row["state"] = "Expired"
					n = 1
			self._cursor_set(n)

	def _cursor_set(self, n):
		self.tls.rowcount = n
		self._cursor = SimpleNamespace(rowcount=n)

	def get_value(self, dt, name, fields, as_dict=False):
		if dt == "Teams Action Session":
			row = self.w.sessions.get(name)
			if row is None:
				return None
			if isinstance(fields, str):
				return row.get(fields)
			return {k: row.get(k) for k in fields} if as_dict else [row.get(k) for k in fields]
		if dt == "Agent Execution Approval":
			ap = self.w.approvals.get(name)
			return ap.status if ap else None
		if dt == "User":
			return self.w.names.get(name)
		return None

	def set_value(self, dt, name, field, value):
		self.w.sessions[name][field] = value


class FakeDoc:
	def __init__(self, values, world):
		self.values, self.w = values, world
		self.name = None

	def insert(self, ignore_permissions=False):
		self.name = f"S{len(self.w.sessions) + 1:04d}"
		row = dict(self.values)
		row["name"] = self.name
		row["payload"] = row.get("payload")
		self.w.sessions[self.name] = row
		return self


class World:
	def __init__(self):
		self.sessions = {}
		self.approvals = {}
		self.names = {"ada@x.com": "Ada Lovelace", "eve@x.com": "Eve"}
		self.links = {(TENANT, AAD): "ada@x.com", (TENANT, AAD2): "eve@x.com"}
		self.can_decide = {"ada@x.com": True, "eve@x.com": False}
		self.user = "Administrator"
		self.users_during = []
		self.calls = []
		self.errors = []
		self.outbox = []
		self.fail_with = None
		self.local = SimpleNamespace()
		self.cache = FakeCache()
		self.gateways = ["gw1"]
		self.refs = {}
		self.all_rows = {}
		self.enqueued = []


@pytest.fixture
def env(monkeypatch):
	ta = fresh_module()
	w = World()
	w.ta = ta
	w.db = FakeDb(w)

	def set_user(user):
		w.user = user

	def get_all(dt, filters=None, pluck=None, **k):
		return w.all_rows.get((dt, pluck), [])

	fake = SimpleNamespace(
		db=w.db,
		local=w.local,
		session=Sess(w),
		set_user=set_user,
		cache=lambda: w.cache,
		get_all=get_all,
		get_doc=lambda dt, n=None: FakeDoc(dt, w) if isinstance(dt, dict) else w.approvals[n],
		enqueue=lambda *a, **k: w.enqueued.append((a, k)),
		log_error=lambda *a, **k: w.errors.append(a or k),
		utils=SimpleNamespace(
			now=lambda: NOW,
			now_datetime=lambda: NOW,
			get_datetime=lambda v: v,
			add_to_date=lambda d, seconds=0: d + timedelta(seconds=seconds),
		),
	)
	monkeypatch.setattr(ta, "frappe", fake)
	monkeypatch.setattr(ta.teams_identity, "resolve_user", lambda gw, t, a: w.links.get((t, a)))
	w.allowed_tenants = {TENANT}
	monkeypatch.setattr(ta, "_tenant_ok", lambda gw, t: t in w.allowed_tenants)

	def approve(name, comment=None):
		w.users_during.append(w.user)
		w.calls.append(("approve", name, w.user, comment))
		if w.fail_with:
			raise w.fail_with
		w.approvals[name].status = "Approved"

	def reject(name, comment=None):
		w.users_during.append(w.user)
		w.calls.append(("reject", name, w.user, comment))
		if w.fail_with:
			raise w.fail_with
		w.approvals[name].status = "Rejected"

	mod = ModuleType("huf.huf.doctype.agent_execution_approval.agent_execution_approval")
	mod.approve_execution, mod.reject_execution = approve, reject
	mod._can_decide = lambda doc, user: w.can_decide.get(user, False)
	pkg = importlib.import_module("huf.huf.doctype.agent_execution_approval")
	monkeypatch.setitem(sys.modules, mod.__name__, mod)
	monkeypatch.setattr(pkg, "agent_execution_approval", mod, raising=False)
	w.approvals["AP-1"] = SimpleNamespace(
		name="AP-1", status="Pending", execution_kind="code_execution", requested_capability="run",
		code_ref="job-1", expires_on=NOW + timedelta(hours=2), requested_by="req@x.com",
		approver_users=[SimpleNamespace(user="ada@x.com")], approver_role=None,
	)
	w.sessions["tas-1"] = {
		"name": "tas-1", "gateway": "gw1", "kind": ta.KIND_EXECUTION, "state": "Open",
		"intended_user": "ada@x.com", "tenant_id": TENANT, "conversation_id": CONV,
		"payload": json.dumps({"kind": ta.KIND_EXECUTION, "name": "AP-1"}),
		"expires_at": NOW + timedelta(hours=1), "decided_by": None, "decision": None,
	}
	yield w
	hooks.clear()


def activity(session="tas-1", verb=cards.VERB_APPROVE, aad=AAD, tenant=TENANT, conv=CONV, tag=True):
	act = copy.deepcopy(json.loads((FIXTURES / "invoke_card_action.json").read_text()))
	act["from"]["aadObjectId"] = aad
	act["conversation"]["tenantId"] = tenant
	act["channelData"]["tenant"]["id"] = tenant
	act["conversation"]["id"] = conv
	act["value"]["action"]["verb"] = verb
	act["value"]["action"]["data"] = {"session": session}
	if tag:
		act["huf_kind"] = "card_action"
	return act


def click(env, act=None, **kw):
	env.local.gateway_response_override = None
	act = act or activity(**kw)
	result = env.ta.pre_ingest_card_action(GW, {"raw_payload": act})
	return result, env.local.gateway_response_override


def body(override):
	assert override["status"] == 200 and override["content_type"] == "application/json"
	return json.loads(override["body"])


def is_card(b):
	return b["type"] == cards.CARD_CONTENT_TYPE


# --- registration & routing ----------------------------------------------------------------


def test_registered_priority_30_for_teams():
	ta = fresh_module()
	entries = [e for e in hooks._HANDLERS[hooks.PRE_INGEST_FILTER] if e[3] is ta.pre_ingest_card_action]
	assert [(p, prov) for p, _s, prov, _f in entries] == [(30, "microsoft teams")]
	assert tc.HOOK_PRIORITY_CARD_ACTION == 30
	hooks.clear()


def test_not_called_for_other_provider(env):
	assert hooks.call_all(hooks.PRE_INGEST_FILTER, SimpleNamespace(provider="Slack"), {}) == []


def test_non_card_activity_passes_through(env):
	res, ov = click(env, act={"type": "message", "huf_kind": "message", "text": "hi"})
	assert res is True and ov is None


def test_untagged_invoke_passes_through(env):
	res, ov = click(env, activity(tag=False))
	assert res is True and ov is None and env.calls == []


def test_forged_tag_value_other_kind_passes(env):
	act = activity()
	act["huf_kind"] = "message"
	res, ov = click(env, act)
	assert res is True and ov is None


def test_dispatch_through_hooks_module(env):
	env.local.gateway_response_override = None
	res = hooks.call_all(hooks.PRE_INGEST_FILTER, GW, {"raw_payload": activity()})
	assert res == [False] and env.calls[0][0] == "approve"


# --- happy paths ----------------------------------------------------------------------------


def test_approve_calls_api_as_clicker(env):
	res, ov = click(env)
	assert res is False
	assert env.calls == [("approve", "AP-1", "ada@x.com", "Decided via Microsoft Teams")]
	b = body(ov)
	assert is_card(b) and b["statusCode"] == 200
	assert "Approved by Ada Lovelace" in json.dumps(b)
	assert "actions" not in b["value"]


def test_reject_calls_reject_api(env):
	click(env, verb=cards.VERB_REJECT)
	assert env.calls[0][:3] == ("reject", "AP-1", "ada@x.com")
	assert env.approvals["AP-1"].status == "Rejected"


def test_session_marked_decided_with_decision(env):
	click(env)
	s = env.sessions["tas-1"]
	assert (s["state"], s["decided_by"], s["decision"]) == ("Decided", "ada@x.com", "approve")


def test_user_restored_after_success(env):
	env.user = "Administrator"
	click(env)
	assert env.user == "Administrator" and env.users_during == ["ada@x.com"]


def test_user_restored_after_permission_error(env):
	env.fail_with = PermissionError_("no")
	click(env)
	assert env.user == "Administrator"


def test_user_restored_after_generic_exception(env):
	env.fail_with = RuntimeError("boom")
	click(env)
	assert env.user == "Administrator"


def test_decision_from_verb_not_card_data(env):
	act = activity(verb=cards.VERB_REJECT)
	act["value"]["action"]["data"]["decision"] = "approve"
	click(env, act)
	assert env.calls[0][0] == "reject"


def test_clicker_identity_not_taken_from_card_data(env):
	act = activity(aad=AAD2)
	act["value"]["action"]["data"]["user"] = "ada@x.com"
	act["value"]["action"]["data"]["actor"] = "ada@x.com"
	_r, ov = click(env, act)
	assert env.calls == [] and env.sessions["tas-1"]["state"] == "Open"
	assert not is_card(body(ov))


def test_other_approver_with_rights_may_decide(env):
	env.can_decide["eve@x.com"] = True
	click(env, aad=AAD2)
	assert env.calls[0][2] == "eve@x.com"
	assert env.sessions["tas-1"]["decided_by"] == "eve@x.com"


# --- refusals: no state change --------------------------------------------------------------


def assert_untouched(env):
	s = env.sessions["tas-1"]
	assert s["state"] == "Open" and s["decided_by"] is None and env.calls == []
	assert env.approvals["AP-1"].status == "Pending"


def test_wrong_user_refused(env):
	_r, ov = click(env, aad=AAD2)
	assert_untouched(env)
	assert body(ov)["type"] == cards.MESSAGE_CONTENT_TYPE
	assert body(ov)["value"] == env.ta.MSG_DENIED


def test_unlinked_user_refused(env):
	_r, ov = click(env, aad="00000000-0000-0000-0000-0000000000zz")
	assert_untouched(env)
	assert body(ov)["value"] == env.ta.MSG_UNLINKED


def test_wrong_tenant_refused(env):
	env.links[("other-tenant", AAD)] = "ada@x.com"
	_r, ov = click(env, tenant="other-tenant")
	assert_untouched(env)
	assert body(ov)["value"] == env.ta.MSG_UNAVAILABLE


def test_wrong_conversation_refused(env):
	_r, ov = click(env, conv="a:someoneelse")
	assert_untouched(env)
	assert body(ov)["value"] == env.ta.MSG_UNAVAILABLE


def test_conversation_thread_suffix_normalised(env):
	click(env, conv=CONV + ";messageid=123")
	assert env.calls and env.calls[0][0] == "approve"


def test_wrong_gateway_refused(env):
	env.sessions["tas-1"]["gateway"] = "gw2"
	click(env)
	assert_untouched(env)


def test_unknown_session_refused(env):
	_r, ov = click(env, session="nope")
	assert body(ov)["value"] == env.ta.MSG_UNAVAILABLE and env.calls == []


def test_wrong_kind_refused(env):
	env.sessions["tas-1"]["kind"] = "approval:flow"
	click(env)
	assert_untouched(env)


def test_unknown_verb_refused(env):
	click(env, verb="delete_everything")
	assert_untouched(env)


def test_missing_session_in_data_refused(env):
	act = activity()
	act["value"]["action"]["data"] = {}
	click(env, act)
	assert_untouched(env)


def test_malformed_value_refused(env):
	act = activity()
	act["value"] = "garbage"
	res, ov = click(env, act)
	assert res is False and body(ov)["type"] == cards.MESSAGE_CONTENT_TYPE


def test_oversized_session_name_refused(env):
	click(env, session="x" * 500)
	assert_untouched(env)


def test_expired_session_replaced_and_not_decided(env):
	env.sessions["tas-1"]["expires_at"] = NOW - timedelta(seconds=1)
	_r, ov = click(env)
	assert env.calls == [] and env.sessions["tas-1"]["state"] == "Expired"
	assert is_card(body(ov)) and env.ta.MSG_EXPIRED in json.dumps(body(ov))


def test_already_decided_session_refused(env):
	click(env)
	env.calls.clear()
	_r, ov = click(env)
	assert env.calls == [] and env.ta.MSG_DECIDED in json.dumps(body(ov))


def test_expired_state_session_refused(env):
	env.sessions["tas-1"]["state"] = "Expired"
	_r, ov = click(env)
	assert env.calls == [] and env.ta.MSG_EXPIRED in json.dumps(body(ov))


def test_permission_error_refusal_and_session_released(env):
	env.fail_with = PermissionError_("denied")
	_r, ov = click(env)
	assert body(ov)["value"] == env.ta.MSG_DENIED
	assert env.sessions["tas-1"]["state"] == "Open" and env.sessions["tas-1"]["decided_by"] is None


def test_generic_failure_releases_session_no_detail_leak(env):
	env.fail_with = RuntimeError("SECRET-DB-DETAIL")
	_r, ov = click(env)
	assert "SECRET" not in ov["body"] and body(ov)["value"] == env.ta.MSG_FAILED
	assert env.sessions["tas-1"]["state"] == "Open"


def test_failure_when_approval_no_longer_pending_closes_session(env):
	def boom(name, comment=None):
		env.approvals[name].status = "Expired"
		raise ValueError("x")

	sys.modules["huf.huf.doctype.agent_execution_approval.agent_execution_approval"].approve_execution = boom
	_r, ov = click(env)
	assert env.sessions["tas-1"]["state"] == "Decided" and env.sessions["tas-1"]["decision"] == "superseded"
	assert env.ta.MSG_NOT_PENDING in json.dumps(body(ov))


def test_handler_exception_yields_safe_refusal(env, monkeypatch):
	monkeypatch.setattr(env.ta, "_handle", lambda *a: (_ for _ in ()).throw(RuntimeError("leak-me")))
	res, ov = click(env)
	assert res is False and "leak-me" not in ov["body"] and env.errors


def test_refusal_has_no_restricted_content(env):
	_r, ov = click(env, aad=AAD2)
	text = ov["body"]
	for word in ("job-1", "AP-1", "run", "req@x.com", "ada@x.com"):
		assert word not in text.replace("not permitted", "")


def test_unauthorised_approver_cannot_probe_state(env):
	env.sessions["tas-1"]["state"] = "Decided"
	_r, ov = click(env, aad=AAD2)
	# a wrong user still learns only that the approval is decided, never who decided or what it was
	assert "ada@x.com" not in ov["body"] and "AP-1" not in ov["body"]


# --- atomicity -------------------------------------------------------------------------------


def test_double_click_reentrant_exactly_one_decision(env):
	env.can_decide["eve@x.com"] = True
	inner = {}

	def slow_approve(name, comment=None):
		env.calls.append(("approve", name, env.user))
		_r, inner["ov"] = click(env, aad=AAD2)  # second click arrives mid-decision
		env.approvals[name].status = "Approved"

	sys.modules["huf.huf.doctype.agent_execution_approval.agent_execution_approval"].approve_execution = slow_approve
	click(env)
	assert len([c for c in env.calls if c[0] == "approve"]) == 1
	assert env.ta.MSG_DECIDED in json.dumps(body(inner["ov"]))
	assert env.sessions["tas-1"]["decided_by"] == "ada@x.com"


def test_two_consumers_threads_one_winner(env):
	results = []
	barrier = threading.Barrier(8)

	def consumer(i):
		barrier.wait()
		results.append(env.ta.consume_session("tas-1", f"u{i}"))

	threads = [threading.Thread(target=consumer, args=(i,)) for i in range(8)]
	[t.start() for t in threads]
	[t.join() for t in threads]
	assert results.count("ok") == 1 and results.count("decided") == 7


def test_consume_expired_marks_expired(env):
	env.sessions["tas-1"]["expires_at"] = NOW
	assert env.ta.consume_session("tas-1", "u") == "expired"
	assert env.sessions["tas-1"]["state"] == "Expired"


def test_consume_unknown(env):
	assert env.ta.consume_session("zzz", "u") == "unknown"


def test_release_only_for_same_actor(env):
	env.ta.consume_session("tas-1", "ada@x.com")
	assert env.ta.release_session("tas-1", "eve@x.com") is False
	assert env.ta.release_session("tas-1", "ada@x.com") is True
	assert env.sessions["tas-1"]["state"] == "Open"


def test_release_refused_after_decision_recorded(env):
	env.ta.consume_session("tas-1", "ada@x.com")
	env.sessions["tas-1"]["decision"] = "approve"
	assert env.ta.release_session("tas-1", "ada@x.com") is False


# --- notify ----------------------------------------------------------------------------------


def setup_notify(env, monkeypatch, with_ref=True):
	ref = {"name": "REF", "conversation_id": CONV, "service_url": "https://smba.trafficmanager.net/amer/",
		"tenant_id": TENANT}
	monkeypatch.setattr(env.ta.teams_notify, "teams_user_reference",
		lambda gw, user: {"tenant_id": TENANT, "aad_id": AAD, "reference": ref if with_ref else None}
		if user == "ada@x.com" else None)
	env.enq = []
	monkeypatch.setattr(env.ta.teams_outbox, "enqueue",
		lambda gw, snap, kind, payload, key: env.enq.append((gw, snap, kind, payload, key)) or "O1")
	env.all_rows[("Gateway", "name")] = ["gw1"]


def test_create_approval_card_enqueues_card_to_personal_chat(env, monkeypatch):
	setup_notify(env, monkeypatch)
	assert env.ta.create_approval_card(env.approvals["AP-1"], "ada@x.com") == 1
	gw, snap, kind, payload, key = env.enq[0]
	assert (gw, kind) == ("gw1", "card") and snap["conversation_id"] == CONV and snap["tenant_id"] == TENANT
	card = payload["activity"]["attachments"][0]["content"]
	sid = card["actions"][0]["data"]["session"]
	assert env.sessions[sid]["intended_user"] == "ada@x.com" and env.sessions[sid]["tenant_id"] == TENANT
	assert json.loads(env.sessions[sid]["payload"]) == {"kind": env.ta.KIND_EXECUTION, "name": "AP-1"}
	assert payload["activity"]["text"]


def test_create_approval_card_by_name(env, monkeypatch):
	setup_notify(env, monkeypatch)
	assert env.ta.create_approval_card("AP-1", "ada@x.com") == 1


def test_no_reference_means_no_card(env, monkeypatch):
	setup_notify(env, monkeypatch, with_ref=False)
	assert env.ta.create_approval_card(env.approvals["AP-1"], "ada@x.com") == 0 and env.enq == []


def test_unlinked_approver_skipped(env, monkeypatch):
	setup_notify(env, monkeypatch)
	assert env.ta.create_approval_card(env.approvals["AP-1"], "zed@x.com") == 0


def test_skip_users(env, monkeypatch):
	setup_notify(env, monkeypatch)
	assert env.ta.create_approval_card(env.approvals["AP-1"], "Administrator") == 0


def test_notify_deduped_per_approval_and_user(env, monkeypatch):
	setup_notify(env, monkeypatch)
	env.ta.create_approval_card(env.approvals["AP-1"], "ada@x.com")
	assert env.ta.create_approval_card(env.approvals["AP-1"], "ada@x.com") == 0
	assert len(env.enq) == 1


def test_outbox_payload_has_no_secrets(env, monkeypatch):
	setup_notify(env, monkeypatch)
	env.ta.create_approval_card(env.approvals["AP-1"], "ada@x.com")
	text = json.dumps(env.enq[0][3]).lower()
	for word in ("password", "secret", "bearer", "token", "api_key", "ada@x.com", "req@x.com"):
		assert word not in text


def test_notify_approvers_enumerates_users_and_role_excluding_requester(env, monkeypatch):
	setup_notify(env, monkeypatch)
	doc = env.approvals["AP-1"]
	doc.approver_users = [SimpleNamespace(user="ada@x.com"), SimpleNamespace(user="req@x.com")]
	doc.approver_role = "Approver"
	env.all_rows[("Has Role", "parent")] = ["ada@x.com", "bob@x.com"]
	env.all_rows[("User", "name")] = ["ada@x.com", "bob@x.com"]
	assert env.ta._execution_approvers(doc) == ["ada@x.com", "bob@x.com"]
	assert env.ta.notify_approvers(doc) == 1


def test_notify_skips_non_pending(env, monkeypatch):
	setup_notify(env, monkeypatch)
	env.approvals["AP-1"].status = "Approved"
	assert env.ta.notify_approvers(env.approvals["AP-1"]) == 0


def test_on_approval_inserted_enqueues_after_commit(env):
	env.ta.on_approval_inserted(SimpleNamespace(name="AP-1"))
	args, kw = env.enqueued[0]
	assert args[0].endswith("teams.actions.notify_approvers_job")
	assert kw["approval_name"] == "AP-1" and kw["enqueue_after_commit"] is True


def test_on_approval_inserted_never_raises(env, monkeypatch):
	monkeypatch.setattr(env.ta.frappe, "enqueue", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
	env.ta.on_approval_inserted(SimpleNamespace(name="AP-1"))
	assert env.errors


def test_notify_job_never_raises(env):
	env.ta.notify_approvers_job("missing")  # KeyError inside the fake get_doc is swallowed
	assert env.errors


def test_record_card_activity(env):
	env.ta.record_card_activity("tas-1", "act-9")
	assert env.sessions["tas-1"]["card_activity_id"] == "act-9"


# --- doctype / hooks.py static ---------------------------------------------------------------


def test_doctype_json_shape():
	p = Path("huf/huf/doctype/teams_action_session/teams_action_session.json")
	d = json.loads(p.read_text())
	assert d["name"] == "Teams Action Session"
	assert [x["role"] for x in d["permissions"]] == ["System Manager"]
	fields = {f["fieldname"]: f for f in d["fields"]}
	for name in ("gateway", "kind", "intended_user", "tenant_id", "conversation_id", "card_activity_id",
		"payload", "state", "decided_by", "decision", "expires_at"):
		assert name in fields
	assert fields["state"]["options"].split("\n") == ["Open", "Decided", "Expired"]
	py_compile.compile("huf/huf/doctype/teams_action_session/teams_action_session.py", doraise=True)


def test_hooks_py_doc_events_is_list_with_both_handlers():
	src = Path("huf/hooks.py").read_text()
	py_compile.compile("huf/hooks.py", doraise=True)
	tree = ast.parse(src)
	value = None
	for node in ast.walk(tree):
		if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "doc_events" for t in node.targets):
			value = ast.literal_eval(node.value)
	entry = value["Agent Execution Approval"]["after_insert"]
	assert isinstance(entry, list)
	assert "huf.ai.gateways.approvals.on_approval_inserted" in entry
	assert "huf.ai.gateways.teams.actions.on_approval_inserted" in entry


def test_teams_actions_has_no_slack_imports():
	src = Path("huf/ai/gateways/teams/actions.py").read_text()
	assert "slack" not in src.lower().replace("slack's", "")


def test_modules_compile():
	for f in ("teams/actions.py", "teams/messaging/cards.py"):
		py_compile.compile(f"huf/ai/gateways/{f}", doraise=True)


# --- gateway_webhook response override (unit, with fakes) -----------------------------------


class FakeResponse:
	def __init__(self, body, status=200, mimetype="text/plain"):
		self.body, self.status, self.mimetype = body, status, mimetype


@pytest.fixture
def wh(monkeypatch):
	rl = ModuleType("frappe.rate_limiter")
	rl.rate_limit = lambda **kw: (lambda fn: fn)
	monkeypatch.setitem(sys.modules, "frappe.rate_limiter", rl)
	monkeypatch.delitem(sys.modules, "huf.ai.gateway_webhook", raising=False)
	gw = importlib.import_module("huf.ai.gateway_webhook")
	monkeypatch.delitem(sys.modules, "huf.ai.gateway_webhook", raising=False)
	local = SimpleNamespace(response=SimpleNamespace(http_status_code=200))
	fake_frappe = SimpleNamespace(
		request=SimpleNamespace(args={"gateway_name": "gw1"}),
		form_dict={},
		local=local,
		get_doc=lambda dt, n: SimpleNamespace(name=n, is_enabled=1, provider="Microsoft Teams"),
		DoesNotExistError=KeyError,
	)
	calls = []
	adapter = SimpleNamespace(
		verify_inbound=lambda r: True,
		normalize_inbound=lambda r: SimpleNamespace(
			provider_event_id="e1", raw_payload={}, sender_id="s", conversation_id="c", message_text="",
			thread_id=None, is_room=False, mentioned=True, display_name="", attachments=()),
	)
	service = ModuleType("huf.ai.gateway_service")
	state = SimpleNamespace(local=local, calls=calls, hook=None, verified=True)

	def ingest(*a, **k):
		calls.append(a)
		if state.hook:
			state.hook()
		return {"filtered": True}

	service.ingest_gateway_event = ingest
	wz = ModuleType("werkzeug")
	wzw = ModuleType("werkzeug.wrappers")
	wzw.Response = FakeResponse
	monkeypatch.setitem(sys.modules, "huf.ai.gateway_service", service)
	monkeypatch.setitem(sys.modules, "werkzeug", wz)
	monkeypatch.setitem(sys.modules, "werkzeug.wrappers", wzw)
	monkeypatch.setattr(gw, "frappe", fake_frappe)
	monkeypatch.setattr(gw, "get_gateway_adapter", lambda g: adapter)
	monkeypatch.setattr(gw, "_inbound_request", lambda: SimpleNamespace(method="POST"))
	adapter.verify_inbound = lambda r: state.verified
	state.gw = gw
	return state


def test_webhook_override_returned_as_response(wh):
	override = {"status": 200, "body": json.dumps({"statusCode": 200}), "content_type": "application/json"}
	wh.hook = lambda: setattr(wh.local, "gateway_response_override", override)
	out = wh.gw.handle_gateway_webhook()
	assert isinstance(out, FakeResponse) and out.status == 200 and out.mimetype == "application/json"
	assert json.loads(out.body) == {"statusCode": 200}
	assert wh.local.gateway_response_override is None


def test_webhook_override_dict_body_serialised(wh):
	wh.hook = lambda: setattr(wh.local, "gateway_response_override",
		{"status": 201, "body": {"a": 1}, "content_type": "application/json"})
	out = wh.gw.handle_gateway_webhook()
	assert out.status == 201 and json.loads(out.body) == {"a": 1}


def test_webhook_without_override_unchanged(wh):
	assert wh.gw.handle_gateway_webhook() == {"success": True, "filtered": True}


def test_webhook_stale_override_cleared_before_ingest(wh):
	wh.local.gateway_response_override = {"status": 200, "body": "stale", "content_type": "text/plain"}
	assert wh.gw.handle_gateway_webhook() == {"success": True, "filtered": True}


def test_webhook_malformed_override_ignored(wh):
	wh.hook = lambda: setattr(wh.local, "gateway_response_override", {"status": 200, "body": 42})
	assert wh.gw.handle_gateway_webhook() == {"success": True, "filtered": True}


def test_webhook_non_dict_override_ignored(wh):
	wh.hook = lambda: setattr(wh.local, "gateway_response_override", "x")
	assert wh.gw.handle_gateway_webhook() == {"success": True, "filtered": True}


def test_webhook_override_not_honoured_when_verification_fails(wh):
	wh.verified = False
	wh.local.gateway_response_override = {"status": 200, "body": "x", "content_type": "text/plain"}
	out = wh.gw.handle_gateway_webhook()
	assert out == {"success": False, "error": "Provider verification failed"}
	assert wh.local.response.http_status_code == 401 and wh.calls == []


def test_end_to_end_handler_sets_override_through_webhook(wh, env):
	def run_handler():
		env.local = wh.local
		env.ta.frappe.local = wh.local
		env.ta.pre_ingest_card_action(GW, {"raw_payload": activity()})

	wh.hook = run_handler
	out = wh.gw.handle_gateway_webhook()
	b = json.loads(out.body)
	assert b["statusCode"] == 200 and b["type"] == cards.CARD_CONTENT_TYPE


# --- T16: defence in depth, tenant verified by the handler itself ----------------------------


def test_card_action_foreign_tenant_changes_nothing(env):
	foreign = "00000000-0000-0000-0000-00000000ffff"
	env.links[(foreign, AAD)] = "ada@x.com"  # even a (hypothetical) link must not help
	res, ov = click(env, activity(tenant=foreign))
	assert res is False
	assert env.calls == [] and env.sessions["tas-1"]["state"] == "Open"
	assert env.approvals["AP-1"].status == "Pending"


def test_real_tenant_ok_fails_closed(env, monkeypatch):
	ta = env.ta
	monkeypatch.undo()  # drop the harness stub for _tenant_ok
	teams_tenant = importlib.import_module("huf.ai.gateways.teams.tenant")
	monkeypatch.setattr(teams_tenant, "is_tenant_allowed", lambda gw, t: t == TENANT)
	assert ta._tenant_ok(GW, TENANT) is True
	assert ta._tenant_ok(GW, "other") is False
	assert ta._tenant_ok(GW, "") is False

	def boom(gw, t):
		raise RuntimeError("settings down")

	monkeypatch.setattr(teams_tenant, "is_tenant_allowed", boom)
	assert ta._tenant_ok(GW, TENANT) is False


# --- T16: duplicate / redelivered card click gets a proper invoke body -------------------------


def _dup_setup(env, wh, monkeypatch, raw, result=None):
	wh.gw.frappe.local = env.local
	env.local.response = SimpleNamespace(http_status_code=200)
	adapter = wh.gw.get_gateway_adapter(None)
	ev = adapter.normalize_inbound(None)
	ev.raw_payload = raw
	adapter.normalize_inbound = lambda r: ev
	monkeypatch.setattr(sys.modules["huf.ai.gateway_service"], "ingest_gateway_event", lambda *a, **k: result or {
		"duplicate": True, "event_name": "EVT-0"})
	monkeypatch.setattr(env.ta.teams_identity, "resolve_user", lambda *a: "ada@x.com")


def test_duplicate_click_decided_session_returns_decided_card(env, wh, monkeypatch):
	env.sessions["tas-1"]["state"] = "Decided"
	_dup_setup(env, wh, monkeypatch, activity())
	out = wh.gw.handle_gateway_webhook()
	assert isinstance(out, FakeResponse) and out.status == 200
	b = json.loads(out.body)
	assert b["statusCode"] == 200
	assert MSG_in(b, env.ta.MSG_DECIDED)
	assert env.calls == []  # nothing decided by a duplicate


def test_duplicate_click_open_session_is_not_decided_and_gets_message(env, wh, monkeypatch):
	_dup_setup(env, wh, monkeypatch, activity())
	out = wh.gw.handle_gateway_webhook()
	assert json.loads(out.body)["statusCode"] == 200
	assert env.calls == [] and env.sessions["tas-1"]["state"] == "Open"
	assert MSG_in(json.loads(out.body), env.ta.MSG_DUPLICATE)


def test_duplicate_click_foreign_tenant_refused(env, wh, monkeypatch):
	foreign = "00000000-0000-0000-0000-00000000ffff"
	env.sessions["tas-1"]["state"] = "Decided"
	_dup_setup(env, wh, monkeypatch, activity(tenant=foreign))
	out = wh.gw.handle_gateway_webhook()
	assert MSG_in(json.loads(out.body), env.ta.MSG_UNAVAILABLE)


def test_duplicate_non_card_event_keeps_generic_json(env, wh, monkeypatch):
	_dup_setup(env, wh, monkeypatch, {"type": "message", "huf_kind": "message"})
	assert wh.gw.handle_gateway_webhook() == {"success": True, "duplicate": True, "event_name": "EVT-0"}


def MSG_in(body, text):  # noqa: N802
	return text in json.dumps(body)


def test_webhook_adapter_built_with_gateway_name(monkeypatch):
	rl = ModuleType("frappe.rate_limiter")
	rl.rate_limit = lambda **kw: (lambda fn: fn)
	monkeypatch.setitem(sys.modules, "frappe.rate_limiter", rl)
	monkeypatch.delitem(sys.modules, "huf.ai.gateway_webhook", raising=False)
	gw = importlib.import_module("huf.ai.gateway_webhook")
	monkeypatch.delitem(sys.modules, "huf.ai.gateway_webhook", raising=False)
	built = []

	class WithName:
		def __init__(self, credentials, *, gateway_name=None):
			built.append(("with", credentials, gateway_name))

	class Plain:
		def __init__(self, credentials):
			built.append(("plain", credentials))

	monkeypatch.setattr(gw, "_gateway_credentials", lambda g: {"k": "v"})
	g = SimpleNamespace(name="gw-7", provider="X")
	monkeypatch.setattr(gw, "_adapter_class_for_provider", lambda p: WithName)
	gw.get_gateway_adapter(g)
	monkeypatch.setattr(gw, "_adapter_class_for_provider", lambda p: Plain)
	gw.get_gateway_adapter(g)
	assert built == [("with", {"k": "v"}, "gw-7"), ("plain", {"k": "v"})]
