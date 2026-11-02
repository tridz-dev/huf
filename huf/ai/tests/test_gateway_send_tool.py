import json
from types import SimpleNamespace

from huf.ai.tests.unit_support import SupportCase  # noqa: E402

from huf.ai.gateways.slack import recipients as rcp
from huf.ai.tools.gateways import send as tool
from huf.ai.gateways.slack.api import SlackApiError


class FakeCache:
	def __init__(self):
		self.d = {}

	def get_value(self, k):
		return self.d.get(k)

	def set_value(self, k, v, expires_in_sec=None):
		self.d[k] = v

	def delete_value(self, k):
		self.d.pop(k, None)


class FakeApi:
	def __init__(self, world):
		self.w = world

	def conversations_open(self, users):
		return "D" + users[0]

	def post_message(self, channel, text=None, **kw):
		if channel in self.w.fail_channels:
			raise SlackApiError("chat.postMessage", "channel_not_found")
		self.w.posts.append((channel, text))
		return {"ok": True}


class World:
	def __init__(self):
		self.links = {"alice@x.com": "UALICE", "bob@x.com": "UBOB"}  # linked
		self.users = {"alice@x.com": 1, "bob@x.com": 1, "carol@x.com": 1, "off@x.com": 0}
		self.roles = {"Sales": ["alice@x.com", "carol@x.com", "off@x.com"]}
		self.bindings = {"CBIND"}
		self.entries = {"CROOM"}
		self.docs = {("Task", "T1"): {"owner": "bob@x.com", "empty": None}}
		self.readable = {("Task", "T1")}
		self.recipients = {"sales alerts": "CALERT", "dana": "UDANA"}
		self.enabled = 1
		self.provider = "Slack"
		self.posts = []
		self.fail_channels = set()
		self.cache = FakeCache()
		self.logged = []
		self.sleeps = []
		self.token = "xoxb-SECRET-TOKEN"

	def get_all(self, doctype, filters=None, pluck=None, **kw):
		if doctype == "Gateway Identity Link":
			if "user" in filters:
				sid = self.links.get(filters["user"])
				return [sid] if sid else []
			if "external_id" in filters:
				for u, s in self.links.items():
					if s == filters["external_id"]:
						return [u]
			return []
		if doctype == "Has Role":
			return list(self.roles.get(filters["role"], []))
		return []

	def exists(self, doctype, name):
		if doctype == "Gateway":
			return name == "GW"
		if doctype == "Gateway Binding":
			return name["match_value"] in self.bindings
		if doctype == "Gateway Access Entry":
			return name["external_id"] in self.entries
		return False

	def get_value(self, doctype, name, field=None):
		if doctype == "User":
			return self.users.get(name)
		return self.docs.get((doctype, name), {}).get(field)


def _fx_w(self):
	monkeypatch = self.monkeypatch
	w = World()
	fake = SimpleNamespace(
		db=SimpleNamespace(exists=w.exists, get_value=w.get_value),
		get_all=w.get_all,
		get_doc=lambda dt, n: SimpleNamespace(name="GW", is_enabled=w.enabled, provider=w.provider),
		has_permission=lambda dt, perm, name, user=None: (dt, name) in w.readable,
		cache=lambda: w.cache,
		session=SimpleNamespace(user="caller@x.com"),
		log_error=lambda *a, **k: w.logged.append(a),
		get_traceback=lambda: "Traceback",
	)
	for m in (tool, rcp):
		monkeypatch.setattr(m, "frappe", fake)
	monkeypatch.setattr(tool, "get_slack_api", lambda gw: FakeApi(w))
	monkeypatch.setattr(tool, "_sleep", lambda s: w.sleeps.append(s))
	monkeypatch.setattr(
		rcp, "_lookup_named",
		lambda n: w.recipients.get(n.lower()),
	)
	return w


def run(**kw):
	kw.setdefault("gateway", "GW")
	kw.setdefault("text", "hello")
	return json.loads(tool.handle_gateway_send(**kw))


class TestModule(SupportCase):
	def test_user_dm(self):
		w = self.use(_fx_w)
		r = run(recipient={"user": "alice@x.com"})
		assert r["sent"] == ["alice@x.com"] and w.posts == [("DUALICE", "hello")]

	def test_user_unlinked_skipped(self):
		w = self.use(_fx_w)
		r = run(recipient={"user": "carol@x.com"})
		assert r["sent"] == [] and r["skipped"][0]["reason"] == "no linked Slack identity"
		assert not w.posts

	def test_user_disabled_skipped(self):
		w = self.use(_fx_w)
		r = run(recipient={"user": "off@x.com"})
		assert r["skipped"][0]["reason"] == "user not found or disabled"

	def test_guest_and_admin_never(self):
		w = self.use(_fx_w)
		r = run(recipient=[{"user": "Guest"}, {"user": "Administrator"}])
		assert len(r["skipped"]) == 2 and not w.posts

	def test_role_expansion_reports_unlinked(self):
		w = self.use(_fx_w)
		r = run(recipient={"role": "Sales"})
		assert r["sent"] == ["alice@x.com"]
		reasons = {s["recipient"]: s["reason"] for s in r["skipped"]}
		assert "carol@x.com" in reasons and "off@x.com" in reasons

	def test_role_empty(self):
		w = self.use(_fx_w)
		r = run(recipient={"role": "Nobody"})
		assert r["success"] is False and r["skipped"][0]["reason"] == "no users with this role"

	def test_doc_field_with_permission(self):
		w = self.use(_fx_w)
		r = run(recipient={"doc_field": {"doctype": "Task", "name": "T1", "field": "owner"}})
		assert r["sent"] == ["bob@x.com"]

	def test_doc_field_without_permission(self):
		w = self.use(_fx_w)
		w.readable.clear()
		r = run(recipient={"doc_field": {"doctype": "Task", "name": "T1", "field": "owner"}})
		assert r["sent"] == [] and "permission" in r["skipped"][0]["reason"]
		assert not w.posts

	def test_doc_field_empty_and_incomplete(self):
		w = self.use(_fx_w)
		r = run(recipient=[{"doc_field": {"doctype": "Task", "name": "T1", "field": "empty"}}, {"doc_field": {"doctype": "Task"}}])
		assert len(r["skipped"]) == 2

	def test_recipient_name_channel_and_user(self):
		w = self.use(_fx_w)
		r = run(recipient=[{"recipient_name": "Sales Alerts"}, {"recipient_name": "Dana"}])
		assert ("CALERT", "hello") in w.posts and ("DUDANA", "hello") in w.posts and len(r["sent"]) == 2

	def test_recipient_name_unknown(self):
		w = self.use(_fx_w)
		r = run(recipient={"recipient_name": "nope"})
		assert r["skipped"][0]["reason"] == "unknown recipient name"

	def test_channel_approved_via_binding_and_entry(self):
		w = self.use(_fx_w)
		r = run(recipient=[{"channel": "CBIND"}, {"channel": "CROOM"}])
		assert r["sent"] == ["CBIND", "CROOM"]

	def test_channel_raw_refused(self):
		w = self.use(_fx_w)
		r = run(recipient={"channel": "CRANDOM"})
		assert r["sent"] == [] and "not approved" in r["skipped"][0]["reason"] and not w.posts

	def test_channel_malformed_refused(self):
		w = self.use(_fx_w)
		r = run(recipient={"channel": "#general"})
		assert not w.posts and r["skipped"]

	def test_slack_user_only_if_linked(self):
		w = self.use(_fx_w)
		r = run(recipient=[{"slack_user": "UALICE"}, {"slack_user": "UEVIL"}])
		assert r["sent"] == ["UALICE"] and r["skipped"][0]["recipient"] == "UEVIL"

	def test_json_string_recipient(self):
		w = self.use(_fx_w)
		r = run(recipient='{"user": "alice@x.com"}')
		assert r["sent"] == ["alice@x.com"]

	def test_bad_recipient_inputs(self):
		w = self.use(_fx_w)
		for bad in ("", "not json", "[]", 5, [1]):
			assert run(recipient=bad)["success"] is False

	def test_unknown_unrecognised_kind(self):
		w = self.use(_fx_w)
		r = run(recipient={"bogus": 1})
		assert r["skipped"][0]["reason"] == "unknown recipient kind"

	def test_cap(self):
		w = self.use(_fx_w)
		monkeypatch = self.monkeypatch
		w.users.update({f"u{i}@x.com": 1 for i in range(60)})
		w.links.update({f"u{i}@x.com": f"UID{i:03d}" for i in range(60)})
		r = run(recipient=[{"user": f"u{i}@x.com"} for i in range(60)])
		assert len(r["sent"]) == 50 and len(r["skipped"]) == 10
		assert all("cap" in s["reason"] for s in r["skipped"])

	def test_destination_deduped_within_call(self):
		w = self.use(_fx_w)
		r = run(recipient=[{"user": "alice@x.com"}, {"slack_user": "UALICE"}])
		assert len(w.posts) == 1 and len(r["sent"]) == 1

	def test_dedupe_key(self):
		w = self.use(_fx_w)
		a = run(recipient={"user": "alice@x.com"}, dedupe_key="k1")
		b = run(recipient={"user": "alice@x.com"}, dedupe_key="k1")
		c = run(recipient={"user": "alice@x.com"}, dedupe_key="k2")
		assert a["sent"] and b["sent"] == [] and b["deduped"] == ["alice@x.com"] and c["sent"]
		assert len(w.posts) == 2

	def test_dedupe_per_recipient(self):
		w = self.use(_fx_w)
		run(recipient={"user": "alice@x.com"}, dedupe_key="k")
		r = run(recipient={"user": "bob@x.com"}, dedupe_key="k")
		assert r["sent"] == ["bob@x.com"]

	def test_dedupe_released_on_failure(self):
		w = self.use(_fx_w)
		w.fail_channels.add("DUALICE")
		r = run(recipient={"user": "alice@x.com"}, dedupe_key="k")
		assert r["sent"] == [] and "send failed" in r["skipped"][0]["reason"]
		w.fail_channels.clear()
		assert run(recipient={"user": "alice@x.com"}, dedupe_key="k")["sent"] == ["alice@x.com"]

	def test_dedupe_uses_atomic_nx_when_available(self):
		w = self.use(_fx_w)
		calls = []

		class NxCache(FakeCache):
			def make_key(self, k):
				return "p:" + k

			def set(self, key, val, nx=False, ex=None):
				calls.append((key, nx, ex))
				return key not in self.d and not self.d.update({key: val})

		w.cache = NxCache()
		assert tool._claim("k", 60) is True and tool._claim("k", 60) is False
		assert calls[0] == ("p:k", True, 60)

	def test_dedupe_hours_configures_ttl(self):
		w = self.use(_fx_w)
		monkeypatch = self.monkeypatch
		seen = []
		monkeypatch.setattr(tool, "_claim", lambda k, ttl: seen.append(ttl) or True)
		run(recipient={"user": "alice@x.com"}, dedupe_key="k", dedupe_hours=2)
		run(recipient={"user": "alice@x.com"}, dedupe_key="k")
		assert seen == [7200, 86400]

	def test_partial_failure_reporting(self):
		w = self.use(_fx_w)
		w.fail_channels.add("DUBOB")
		r = run(recipient=[{"user": "alice@x.com"}, {"user": "bob@x.com"}])
		assert r["success"] is True and r["sent"] == ["alice@x.com"]
		assert r["skipped"][0] == {"recipient": "bob@x.com", "reason": "send failed: channel_not_found"}

	def test_all_fail_is_not_success(self):
		w = self.use(_fx_w)
		w.fail_channels.add("DUALICE")
		assert run(recipient={"user": "alice@x.com"})["success"] is False

	def test_escaping_blocks_pings(self):
		w = self.use(_fx_w)
		run(recipient={"user": "alice@x.com"}, text="<!channel> hi <@U1> a&b")
		assert w.posts[0][1] == "&lt;!channel&gt; hi &lt;@U1&gt; a&amp;b"

	def test_allow_mentions_flag_is_explicit_only(self):
		w = self.use(_fx_w)
		run(recipient={"user": "alice@x.com"}, text="<@U1>", allow_mentions=True)
		assert w.posts[0][1] == "<@U1>"
		assert "allow_mentions" not in [p["fieldname"] for p in tool.GATEWAY_SEND_TOOLS[0]["parameters"]]

	def test_text_cap_and_empty(self):
		w = self.use(_fx_w)
		run(recipient={"user": "alice@x.com"}, text="x" * 5000)
		assert len(w.posts[0][1]) == 3000 and w.posts[0][1].endswith("...")
		assert run(recipient={"user": "alice@x.com"}, text="  ")["success"] is False

	def test_gateway_disabled_unknown_and_wrong_provider(self):
		w = self.use(_fx_w)
		w.enabled = 0
		assert run(recipient={"user": "alice@x.com"})["error"] == "Gateway is disabled."
		w.enabled = 1
		assert run(recipient={"user": "alice@x.com"}, gateway="other")["error"] == "Unknown gateway."
		w.provider = "Telegram"
		assert run(recipient={"user": "alice@x.com"})["success"] is False
		assert not w.posts

	def test_no_token_leak(self):
		w = self.use(_fx_w)
		monkeypatch = self.monkeypatch
		def boom(gw):
			raise RuntimeError(w.token)

		monkeypatch.setattr(tool, "get_slack_api", boom)
		out = tool.handle_gateway_send(gateway="GW", recipient={"user": "alice@x.com"}, text="hi")
		assert w.token not in out

	def test_missing_token_message(self):
		w = self.use(_fx_w)
		monkeypatch = self.monkeypatch
		def nope(gw):
			raise ValueError("Slack gateway has no bot token configured")

		monkeypatch.setattr(tool, "get_slack_api", nope)
		assert run(recipient={"user": "alice@x.com"})["error"] == "Gateway has no bot token configured."

	def test_rate_spacing_between_sends(self):
		w = self.use(_fx_w)
		run(recipient=[{"user": "alice@x.com"}, {"user": "bob@x.com"}])
		assert w.sleeps == [tool.SEND_INTERVAL_SECONDS]

	def test_tool_registered_in_hooks(self):
		import pathlib
		src = (pathlib.Path(__file__).parents[2] / "hooks.py").read_text()
		assert "huf.ai.tools.gateways.send.GATEWAY_SEND_TOOLS" in src
		assert tool.GATEWAY_SEND_TOOLS[0]["function_path"] == "huf.ai.tools.gateways.send.handle_gateway_send"
