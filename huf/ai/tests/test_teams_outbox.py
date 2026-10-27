import ast
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, "huf/testing")
import _stub_env  # noqa: E402

_stub_env.install()

import pytest  # noqa: E402

from huf.ai.gateways import teams_outbox as ob  # noqa: E402

NOW = datetime(2026, 10, 27, 12, 0, 0)
SNAP = {"conversation_ref": "ref1", "conversation_id": "19:abc", "service_url": "https://smba.trafficmanager.net/x/", "tenant_id": "t1"}


class Dup(Exception):
	pass


class FakeErr(Exception):
	def __init__(self, msg="", status=None, retry_after=None):
		super().__init__(msg)
		self.status = status
		self.retry_after = retry_after


@pytest.fixture
def store(monkeypatch):
	rows: dict[str, dict] = {}
	jobs: list = []
	state = {"n": 0, "race": False}

	def find(key):
		for n, r in rows.items():
			if r["idempotency_key"] == key:
				return n
		return None

	def insert(values):
		if state["race"]:
			state["race"] = False
			rows["race-winner"] = {"name": "race-winner", **values}
			raise Dup()
		if find(values["idempotency_key"]):
			raise Dup()
		state["n"] += 1
		n = f"row{state['n']}"
		rows[n] = {"name": n, **values}
		return n

	def claim(name, now):
		r = rows[name]
		if r["status"] == "Pending" and (r["next_attempt_at"] is None or r["next_attempt_at"] <= now):
			r["next_attempt_at"] = now + timedelta(seconds=ob.CLAIM_LEASE_SECONDS)
			return True
		return False

	def due(now, limit):
		d = [r for r in rows.values() if r["status"] == "Pending" and (r["next_attempt_at"] or now) <= now]
		d.sort(key=lambda r: r["next_attempt_at"] or now)
		return [r["name"] for r in d][:limit]

	monkeypatch.setattr(ob, "_find_by_key", find)
	monkeypatch.setattr(ob, "_insert", insert)
	monkeypatch.setattr(ob, "_load", lambda n: dict(rows[n]) if n in rows else None)
	monkeypatch.setattr(ob, "_update", lambda n, v: rows[n].update(v))
	monkeypatch.setattr(ob, "_claim", claim)
	monkeypatch.setattr(ob, "_due_names", due)
	monkeypatch.setattr(ob, "_dup_errors", lambda: (Dup,))
	monkeypatch.setattr(ob, "_enqueue_job", lambda method, **kw: jobs.append((method, kw)))
	monkeypatch.setattr(ob, "_now", lambda: NOW)
	return type("S", (), {"rows": rows, "jobs": jobs, "state": state})


def mk(store, key="k1", kind="reply", payload=None):
	return ob.enqueue("gw", SNAP, kind, payload or {"text": "hi"}, key)


def ok_sender(kind, snap, payload):
	return "msg-1"


def failing(exc):
	def s(kind, snap, payload):
		raise exc

	return s


# ---------------------------------------------------------------- enqueue


def test_enqueue_creates_pending_row(store):
	n = mk(store)
	r = store.rows[n]
	assert r["status"] == "Pending" and r["attempts"] == 0 and r["gateway"] == "gw"
	assert r["conversation_id"] == "19:abc" and r["tenant_id"] == "t1" and r["service_url"].startswith("https://")


def test_enqueue_idempotent_returns_existing(store):
	a, b = mk(store), mk(store)
	assert a == b and len(store.rows) == 1


def test_enqueue_race_duplicate_returns_winner(store, monkeypatch):
	monkeypatch.setattr(ob, "_find_by_key", lambda k: None if not store.rows else "race-winner")
	store.state["race"] = True
	assert mk(store, "kr") == "race-winner"


def test_enqueue_triggers_delivery_after_commit(store, monkeypatch):
	captured = {}

	def fake_enqueue(method, **kw):
		captured.update(kw, method=method)

	monkeypatch.setattr(ob, "_enqueue_job", fake_enqueue)
	n = mk(store)
	assert captured["method"] == "huf.ai.gateways.teams_outbox.deliver" and captured["name"] == n


def test_enqueue_job_uses_enqueue_after_commit(monkeypatch):
	calls = []
	monkeypatch.setattr(ob.frappe, "enqueue", lambda *a, **k: calls.append(k), raising=False)
	ob._enqueue_job("x.y", name="n")
	assert calls[0]["enqueue_after_commit"] is True


def test_enqueue_never_raises_when_scheduling_fails(store, monkeypatch):
	def boom(*a, **k):
		raise RuntimeError("redis down")

	monkeypatch.setattr(ob, "_enqueue_job", boom)
	assert mk(store)


def test_enqueue_rejects_bad_kind_and_empty_key(store):
	with pytest.raises(ValueError):
		ob.enqueue("gw", SNAP, "weird", {}, "k")
	with pytest.raises(ValueError):
		ob.enqueue("gw", SNAP, "reply", {}, "")


# -------------------------------------------------------------- redaction


def test_redact_payload_keys_and_nested():
	p = {"text": "hi", "access_token": "abc", "headers": {"Authorization": "Bearer xyz"}, "l": [{"client_secret": "s"}]}
	r = ob.redact_payload(p)
	assert r["text"] == "hi" and r["access_token"] == ob.REDACTED
	assert r["headers"]["Authorization"] == ob.REDACTED and r["l"][0]["client_secret"] == ob.REDACTED
	assert p["access_token"] == "abc"  # not mutated


def test_redact_payload_scrubs_bearer_in_text():
	assert "abc123" not in ob.redact_payload({"t": "x Bearer abc123.def end"})["t"]


def test_stored_payload_is_redacted(store):
	n = mk(store, payload={"text": "a", "token": "SECRET"})
	assert "SECRET" not in store.rows[n]["payload"]
	assert json.loads(store.rows[n]["payload"])["text"] == "a"


# ----------------------------------------------------------------- backoff


def test_backoff_schedule_exact():
	assert [ob.retry_delay(FakeErr(status=503), i) for i in range(1, 6)] == [30, 120, 600, 1800, 7200]


def test_retry_after_overrides_backoff():
	assert ob.retry_delay(FakeErr(status=429, retry_after=45), 1) == 45
	assert ob.retry_delay(FakeErr(status=429, retry_after="12"), 3) == 12


def test_retry_after_invalid_falls_back():
	assert ob.retry_delay(FakeErr(status=429, retry_after="soon"), 2) == 120


def test_retry_after_capped():
	assert ob.retry_delay(FakeErr(retry_after=10**7), 1) == ob.MAX_RETRY_AFTER


# ------------------------------------------------------------ classification


@pytest.mark.parametrize("status", [429, 500, 502, 503, 599])
def test_transient_statuses(status):
	assert ob.is_transient(FakeErr(status=status))


@pytest.mark.parametrize("status", [400, 401, 403, 404, 413])
def test_permanent_statuses(status):
	assert not ob.is_transient(FakeErr(status=status))


def test_timeouts_transient_validation_permanent():
	assert ob.is_transient(TimeoutError()) and ob.is_transient(ConnectionError())
	assert not ob.is_transient(ValueError("bad payload"))


# ------------------------------------------------------------------ deliver


def test_deliver_success_stores_provider_id(store):
	n = mk(store)
	assert ob.deliver(n, sender=ok_sender, now=NOW) == "Sent"
	r = store.rows[n]
	assert r["status"] == "Sent" and r["provider_message_id"] == "msg-1" and r["attempts"] == 1 and r["sent_at"] == NOW


def test_deliver_sender_receives_snapshot_and_payload(store):
	seen = {}

	def s(kind, snap, payload):
		seen.update(kind=kind, snap=snap, payload=payload)
		return "x"

	n = mk(store, kind="card", payload={"activity": {"a": 1}})
	ob.deliver(n, sender=s, now=NOW)
	assert seen["kind"] == "card" and seen["snap"]["conversation_id"] == "19:abc" and seen["payload"] == {"activity": {"a": 1}}


def test_transient_failure_schedules_retry(store):
	n = mk(store)
	assert ob.deliver(n, sender=failing(FakeErr("x", status=503)), now=NOW) == "Pending"
	r = store.rows[n]
	assert r["attempts"] == 1 and r["next_attempt_at"] == NOW + timedelta(seconds=30)


def test_429_retry_after_honoured(store):
	n = mk(store)
	ob.deliver(n, sender=failing(FakeErr("x", status=429, retry_after=77)), now=NOW)
	assert store.rows[n]["next_attempt_at"] == NOW + timedelta(seconds=77)


def test_permanent_failure_marks_failed(store):
	n = mk(store)
	assert ob.deliver(n, sender=failing(FakeErr("nope", status=403)), now=NOW) == "Failed"
	assert store.rows[n]["status"] == "Failed"


def test_dead_after_six_attempts(store):
	n = mk(store)
	t = NOW
	for i in range(1, 7):
		res = ob.deliver(n, sender=failing(FakeErr("x", status=500)), now=t)
		if i < 6:
			assert res == "Pending"
			t = store.rows[n]["next_attempt_at"]
	assert res == "Dead" and store.rows[n]["attempts"] == 6


def test_full_schedule_sequence(store):
	n = mk(store)
	t, gaps = NOW, []
	for _ in range(5):
		ob.deliver(n, sender=failing(FakeErr("x", status=500)), now=t)
		nxt = store.rows[n]["next_attempt_at"]
		gaps.append(int((nxt - t).total_seconds()))
		t = nxt
	assert gaps == [30, 120, 600, 1800, 7200]


def test_atomic_claim_one_winner(store):
	n = mk(store)
	calls = []

	def s(k, sn, p):
		calls.append(1)
		return "m"

	first = ob.deliver(n, sender=s, now=NOW)
	# a concurrent worker that loaded the row before it was updated loses the claim
	store.rows[n]["status"] = "Pending"
	store.rows[n]["next_attempt_at"] = NOW + timedelta(seconds=300)
	second = ob.deliver(n, sender=s, now=NOW)
	assert first == "Sent" and second == "Skipped" and len(calls) == 1


def test_two_deliverers_one_wins(store):
	n = mk(store)
	assert ob._claim(n, NOW) is True
	assert ob._claim(n, NOW) is False


def test_deliver_skips_non_pending(store):
	n = mk(store)
	store.rows[n]["status"] = "Sent"
	assert ob.deliver(n, sender=ok_sender, now=NOW) == "Skipped"
	assert ob.deliver("missing", sender=ok_sender, now=NOW) == "Skipped"


def test_default_sender_fails_closed_without_teams_api(store, monkeypatch):
	monkeypatch.setitem(sys.modules, "huf.ai.gateways.teams_api", None)
	import huf.ai.gateways as _pkg

	# `from pkg import mod` prefers a cached package attribute over sys.modules.
	monkeypatch.delattr(_pkg, "teams_api", raising=False)
	n = mk(store)
	assert ob.deliver(n, now=NOW) == "Pending" or store.rows[n]["status"] in ("Pending", "Failed")
	assert "teams_api" in store.rows[n]["last_error"]


def test_last_error_has_no_secrets(store):
	n = mk(store)
	ob.deliver(n, sender=failing(FakeErr("401 Bearer eyJabcdefghij.klmnop.qrs access_token=ZZZ", status=500)), now=NOW)
	err = store.rows[n]["last_error"]
	assert "eyJabc" not in err and "ZZZ" not in err and len(err) <= ob.MAX_ERROR_LEN


# ---------------------------------------------------------------- retry_due


def test_retry_due_selects_only_due_pending(store):
	a, b, c = mk(store, "a"), mk(store, "b"), mk(store, "c")
	store.rows[b]["next_attempt_at"] = NOW + timedelta(seconds=60)
	store.rows[c]["status"] = "Sent"
	store.jobs.clear()
	assert ob.retry_due(now=NOW) == [a]
	assert [j[1]["name"] for j in store.jobs] == [a]


def test_retry_due_respects_limit(store):
	for i in range(5):
		mk(store, f"k{i}")
	store.jobs.clear()
	assert len(ob.retry_due(limit=3, now=NOW)) == 3 and len(store.jobs) == 3


# ------------------------------------------------------- static / structure


def test_scheduler_line_in_hooks_static():
	src = Path("huf/hooks.py").read_text()
	tree = ast.parse(src)
	for node in tree.body:
		if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "scheduler_events":
			ev = ast.literal_eval(node.value)
			assert "huf.ai.gateways.teams_outbox.retry_due" in ev["cron"]["*/1 * * * *"]
			return
	pytest.fail("scheduler_events not found")


def test_hooks_py_compiles():
	import py_compile

	py_compile.compile("huf/hooks.py", doraise=True)


def test_doctype_json_field_order_sane():
	d = json.loads(Path("huf/huf/doctype/teams_outbound_message/teams_outbound_message.json").read_text())
	names = {f["fieldname"] for f in d["fields"]}
	assert [x for x in d["field_order"] if x not in names] == []
	assert {f["fieldname"] for f in d["fields"] if f["fieldtype"] not in ("Section Break",)} <= set(d["field_order"])
	f = {x["fieldname"]: x for x in d["fields"]}
	assert f["idempotency_key"]["unique"] == 1
	assert f["status"]["options"].split("\n") == ["Pending", "Sent", "Failed", "Dead"]
	assert f["kind"]["options"].split("\n") == ["reply", "card", "card_update", "proactive"]
	assert [p["role"] for p in d["permissions"]] == ["System Manager"]


# ---------------------------------------------------- T16: default sender really delivers


class _Resp:
	def __init__(self, status=200, body=None):
		self.status_code, self._b, self.headers = status, body, {}

	def json(self):
		return self._b


class _Http:
	"""Token endpoint + Bot Connector in one fake HTTP layer."""

	def __init__(self, post_status=200):
		self.calls = []
		self.post_status = post_status

	def __call__(self, method, url, *, headers, json=None, data=None, timeout=10):
		self.calls.append({"method": method, "url": url, "headers": headers, "json": json, "data": data})
		if "login.microsoftonline.com" in url:
			return _Resp(200, {"access_token": "TKN-1", "expires_in": 3600})
		return _Resp(self.post_status, {"id": "act-9"})


class _Cache:
	def __init__(self):
		self.d = {}

	def get_value(self, k):
		return self.d.get(k)

	def set_value(self, k, v, expires_in_sec=None):
		self.d[k] = v

	def delete_value(self, k):
		self.d.pop(k, None)


@pytest.fixture
def real_sender(store, monkeypatch):
	from huf.ai.gateways import teams_api, teams_tenant

	creds = {"app_id": "app-1", "app_password": "s3cret-pw", "tenant_id": "tenant-guid"}
	state = type("St", (), {"creds": creds, "http": _Http(), "gw_docs": []})
	monkeypatch.setattr(teams_api, "_cache", lambda: _Cache())
	monkeypatch.setattr(
		ob.frappe, "get_doc", lambda dt, name=None: state.gw_docs.append((dt, name)) or type("G", (), {"name": name})(),
		raising=False,
	)
	monkeypatch.setattr(teams_tenant, "get_gateway_credential", lambda gw, key: state.creds.get(key, ""))
	state.api = teams_api
	return state


def test_default_sender_delivers_with_token_provider_and_auth_header(store, real_sender):
	seen = {}
	orig = real_sender.api.post_activity

	def spy(*a, **kw):
		seen["token"] = kw.get("token")
		return orig(*a, **kw)

	real_sender.api.post_activity = spy
	try:
		n = mk(store, payload={"activity": {"type": "message", "text": "hi"}})
		assert ob.deliver(n, now=NOW, http=real_sender.http) == "Sent"
	finally:
		real_sender.api.post_activity = orig
	assert callable(seen["token"])
	assert store.rows[n]["provider_message_id"] == "act-9" and not store.rows[n].get("last_error")
	post = [c for c in real_sender.http.calls if "/v3/conversations/" in c["url"]][0]
	assert post["headers"]["Authorization"] == "Bearer TKN-1"
	assert post["json"] == {"type": "message", "text": "hi"}
	tok = [c for c in real_sender.http.calls if "login.microsoftonline.com" in c["url"]][0]
	assert "tenant-guid" in tok["url"] and tok["data"]["client_id"] == "app-1"
	assert real_sender.gw_docs == [("Gateway", "gw")]


def test_default_sender_card_update_passes_token(store, real_sender):
	n = mk(store, kind="card_update", payload={"activity_id": "A1", "activity": {"type": "message"}})
	assert ob.deliver(n, now=NOW, http=real_sender.http) == "Sent"
	put = [c for c in real_sender.http.calls if c["method"] == "PUT"][0]
	assert put["url"].endswith("/activities/A1") and put["headers"]["Authorization"] == "Bearer TKN-1"


@pytest.mark.parametrize("drop", ["app_id", "app_password", "tenant_id"])
def test_default_sender_fails_closed_without_credentials(store, real_sender, drop):
	real_sender.creds = {k: v for k, v in real_sender.creds.items() if k != drop}
	n = mk(store)
	assert ob.deliver(n, now=NOW, http=real_sender.http) == "Failed"
	err = store.rows[n]["last_error"]
	assert drop in err and "s3cret-pw" not in err
	assert real_sender.http.calls == []  # no token request, no post


def test_default_sender_no_gateway_is_permanent_failure(store, real_sender):
	n = mk(store)
	store.rows[n]["gateway"] = None
	assert ob.deliver(n, now=NOW, http=real_sender.http) == "Failed"
	assert real_sender.http.calls == []


def test_card_delivery_records_activity_id_on_session(store, real_sender, monkeypatch):
	from huf.ai.gateways import teams_actions

	got = []
	monkeypatch.setattr(teams_actions, "record_card_activity", lambda s, a: got.append((s, a)))
	n = mk(store, kind="card", payload={"activity": {"type": "message"}, "action_session": "tas-7"})
	assert ob.deliver(n, now=NOW, http=real_sender.http) == "Sent"
	assert got == [("tas-7", "act-9")]
	got.clear()
	n2 = mk(store, key="k2", kind="card", payload={"activity": {"type": "message"}})
	ob.deliver(n2, now=NOW, http=real_sender.http)
	n3 = mk(store, key="k3", kind="reply", payload={"activity": {"type": "message"}, "action_session": "x"})
	ob.deliver(n3, now=NOW, http=real_sender.http)
	assert got == []  # no session / not a card: nothing recorded


def test_record_card_activity_failure_does_not_fail_delivery(store, real_sender, monkeypatch):
	from huf.ai.gateways import teams_actions

	def boom(s, a):
		raise RuntimeError("db down")

	monkeypatch.setattr(teams_actions, "record_card_activity", boom)
	n = mk(store, kind="card", payload={"activity": {"type": "message"}, "action_session": "tas-7"})
	assert ob.deliver(n, now=NOW, http=real_sender.http) == "Sent"


def test_transport_failure_status_zero_is_transient():
	class _Err(Exception):
		def __init__(self, status):
			super().__init__("x")
			self.status = status

	assert ob.is_transient(_Err(0)) is True  # transport failure: retry
	assert ob.is_transient(_Err(408)) is True
	assert ob.is_transient(_Err(429)) is True
	assert ob.is_transient(_Err(503)) is True
	assert ob.is_transient(_Err(400)) is False
	assert ob.is_transient(_Err(401)) is False
