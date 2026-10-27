"""Unit tests for Slack approvals (notify path + click handler). Stub env; no network, no bench."""

from __future__ import annotations

import ast
import json
import os
import sys
import types
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _stub_env  # noqa: E402

_stub_env.install()
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, ROOT)

import frappe as _frappe_stub  # noqa: E402

TARGETS = ("huf.ai.gateways.slack_interactivity", "huf.ai.gateways.approvals")


def _load_isolated():
	touched, stubs = {}, {}
	if "frappe.rate_limiter" not in sys.modules:
		rl = types.ModuleType("frappe.rate_limiter")
		rl.rate_limit = lambda *a, **k: (lambda fn: fn)
		stubs["frappe.rate_limiter"] = rl
	for name in TARGETS:
		touched[name] = sys.modules.pop(name, None)
	sys.modules.update(stubs)
	orig = _frappe_stub.whitelist
	_frappe_stub.whitelist = lambda *a, **k: (lambda fn: fn)
	try:
		from huf.ai.gateways import approvals as ap
		from huf.ai.gateways import slack_interactivity as si
	finally:
		_frappe_stub.whitelist = orig
		for name in stubs:
			sys.modules.pop(name, None)
		for name, old in touched.items():
			sys.modules.pop(name, None)
			if old is not None:
				sys.modules[name] = old
	return ap, si


ap, si = _load_isolated()
from huf.ai.gateways import blocks as bk  # noqa: E402


class PermissionError_(Exception):
	pass


PermissionError_.__name__ = "PermissionError"


class Cache:
	def __init__(self):
		self.d = {}

	def get_value(self, k):
		return self.d.get(k)

	def set_value(self, k, v, expires_in_sec=None):
		self.d[k] = v


class World:
	def __init__(self):
		self.gateways = ["gw1"]
		self.links = {("gw1", "alice@x.com"): "UALICE", ("gw1", "bob@x.com"): "UBOB",
			("gw2", "alice@x.com"): "UALICE2"}
		self.role_users = {"Approver": ["bob@x.com", "off@x.com"]}
		self.enabled = {"bob@x.com"}
		self.posts = []
		self.sessions = []
		self.user = "Administrator"
		self.set_users = []
		self.cache = Cache()
		self.logged = []
		self.enqueued = []
		self.post_error = None

	def get_all(self, doctype, filters=None, pluck=None, **kw):
		if doctype == "Gateway":
			assert filters == {"provider": "Slack", "is_enabled": 1}
			return list(self.gateways)
		if doctype == "Has Role":
			return list(self.role_users.get(filters["role"], []))
		if doctype == "User":
			return [u for u in filters["name"][1] if u in self.enabled]
		return []


def _row(**kw):
	return SimpleNamespace(**kw)


def _doc(name="AEA-1", users=("alice@x.com",), role=None, requested_by="req@x.com", status="Pending", **kw):
	return SimpleNamespace(name=name, status=status, execution_kind="code_execution",
		requested_capability="execution.approve", code_ref="run_script", requested_by=requested_by,
		approver_role=role, approver_users=[_row(user=u) for u in users], expires_on=None, **kw)


class Base(unittest.TestCase):
	def setUp(self):
		self.w = World()
		w = self.w

		class Api:
			def conversations_open(_s, users):
				return "D" + users[0]

			def post_message(_s, channel, text=None, blocks=None, **kw):
				if w.post_error:
					raise w.post_error
				w.posts.append({"channel": channel, "text": text, "blocks": blocks})

		def fake_session(gateway, kind, payload=None, intended_user=None, intended_slack_user=None,
			ttl_seconds=0, **kw):
			name = f"S{len(w.sessions) + 1}"
			w.sessions.append({"name": name, "gateway": gateway, "kind": kind, "payload": payload,
				"intended_user": intended_user, "intended_slack_user": intended_slack_user, "ttl": ttl_seconds})
			return name

		def set_user(u):
			w.set_users.append(u)
			w.user = u

		self.fake = SimpleNamespace(
			get_all=w.get_all, cache=lambda: w.cache, session=SimpleNamespace(),
			set_user=set_user, log_error=lambda title=None, **k: w.logged.append(title),
			enqueue=lambda *a, **k: w.enqueued.append((a, k)),
			utils=SimpleNamespace(now=lambda: "2026-01-02 03:04:05",
				get_datetime=lambda v: v, now_datetime=lambda: 0),
		)
		self.fake.session = type("S", (), {"user": property(lambda _s: w.user)})()
		self.patches = [
			patch.object(ap, "frappe", self.fake),
			patch.object(si, "create_action_session", fake_session),
			patch("huf.ai.gateways.recipients.slack_id_for_user",
				lambda gw, user: w.links.get((gw, user))),
			patch("huf.ai.gateways.slack_context.get_slack_api", lambda gw: Api()),
		]
		for p in self.patches:
			p.start()
			self.addCleanup(p.stop)


class TestNotify(Base):
	def test_linked_approver_gets_card(self):
		self.assertEqual(ap.notify_approvers(_doc()), 1)
		post = self.w.posts[0]
		self.assertEqual(post["channel"], "DUALICE")
		self.assertEqual(post["blocks"][1]["type"], "actions")

	def test_session_bound_to_approver_and_minimal_payload(self):
		ap.notify_approvers(_doc())
		s = self.w.sessions[0]
		self.assertEqual(s["intended_user"], "alice@x.com")
		self.assertEqual(s["intended_slack_user"], "UALICE")
		self.assertEqual(s["kind"], "approval:execution")
		self.assertEqual(s["payload"], {"kind": "approval:execution", "name": "AEA-1"})

	def test_buttons_carry_session_name(self):
		ap.notify_approvers(_doc())
		els = self.w.posts[0]["blocks"][1]["elements"]
		self.assertEqual({e["value"] for e in els}, {"S1"})

	def test_unlinked_skipped_silently(self):
		self.assertEqual(ap.notify_approvers(_doc(users=("nobody@x.com",))), 0)
		self.assertEqual(self.w.posts, [])
		self.assertEqual(self.w.logged, [])

	def test_multiple_approvers(self):
		self.assertEqual(ap.notify_approvers(_doc(users=("alice@x.com", "bob@x.com"))), 2)
		self.assertEqual({p["channel"] for p in self.w.posts}, {"DUALICE", "DUBOB"})
		self.assertEqual(len({s["name"] for s in self.w.sessions}), 2)

	def test_role_approvers_enabled_only(self):
		self.assertEqual(ap.notify_approvers(_doc(users=(), role="Approver")), 1)
		self.assertEqual(self.w.posts[0]["channel"], "DUBOB")

	def test_duplicate_users_notified_once(self):
		self.assertEqual(ap.notify_approvers(_doc(users=("alice@x.com", "alice@x.com"))), 1)

	def test_multiple_gateways(self):
		self.w.gateways = ["gw1", "gw2"]
		self.assertEqual(ap.notify_approvers(_doc()), 2)
		self.assertEqual({s["gateway"] for s in self.w.sessions}, {"gw1", "gw2"})

	def test_no_slack_gateways(self):
		self.w.gateways = []
		self.assertEqual(ap.notify_approvers(_doc()), 0)

	def test_idempotent(self):
		d = _doc()
		self.assertEqual(ap.notify_approvers(d), 1)
		self.assertEqual(ap.notify_approvers(d), 0)
		self.assertEqual(len(self.w.posts), 1)

	def test_failed_post_not_marked_notified_and_no_raise(self):
		self.w.post_error = RuntimeError("boom")
		self.assertEqual(ap.notify_approvers(_doc()), 0)
		self.w.post_error = None
		self.assertEqual(ap.notify_approvers(_doc()), 1)

	def test_requester_not_notified(self):
		self.assertEqual(ap.notify_approvers(_doc(users=("alice@x.com",), requested_by="alice@x.com")), 0)

	def test_non_pending_skipped(self):
		self.assertEqual(ap.notify_approvers(_doc(status="Approved")), 0)

	def test_no_exception_escapes(self):
		self.fake.get_all = MagicMock(side_effect=RuntimeError("db down"))
		self.assertEqual(ap.notify_approvers(_doc()), 0)
		self.assertEqual(ap.notify_approvers(object()), 0)

	def test_text_escaped(self):
		d = _doc(users=("alice@x.com",))
		d.code_ref = "<!channel> & <script>"
		ap.notify_approvers(d)
		text = self.w.posts[0]["blocks"][0]["text"]["text"]
		self.assertNotIn("<!channel>", text)
		self.assertIn("&lt;!channel&gt; &amp;", text)

	def test_details_limited_to_doc_fields(self):
		ap.notify_approvers(_doc())
		text = self.w.posts[0]["blocks"][0]["text"]["text"]
		self.assertIn("execution.approve", text)
		self.assertIn("req@x.com", text)

	def test_flow_run_notify(self):
		fr = SimpleNamespace(name="FR-1", waiting=json.dumps(
			{"approval_type": "users", "approver_users": ["alice@x.com"]}))
		self.assertEqual(ap.notify_flow_run_approvers(fr), 1)
		self.assertEqual(self.w.sessions[0]["kind"], "approval:flow")
		self.assertEqual(self.w.sessions[0]["payload"]["name"], "FR-1")

	def test_flow_run_bad_waiting_no_raise(self):
		self.assertEqual(ap.notify_flow_run_approvers(SimpleNamespace(name="FR", waiting="{bad")), 0)

	def test_hook_wrapper_enqueues_and_never_raises(self):
		ap.on_approval_inserted(_doc())
		self.assertEqual(len(self.w.enqueued), 1)
		self.assertTrue(self.w.enqueued[0][1]["enqueue_after_commit"])
		self.fake.enqueue = MagicMock(side_effect=RuntimeError("redis down"))
		ap.on_approval_inserted(_doc())  # must not raise

	def test_job_swallows_errors(self):
		self.fake.get_doc = MagicMock(side_effect=RuntimeError("gone"))
		ap.notify_approvers_job("AEA-X")


class TestClick(Base):
	def setUp(self):
		super().setUp()
		self.calls = []
		w = self.w

		def make(name, err=None):
			def fn(docname, comment=None):
				self.calls.append((name, docname, w.user, comment))
				if err:
					raise err
				return {"status": "ok"}

			return fn

		self.make = make
		self.fns = {("approval:execution", "approve"): make("exec_approve"),
			("approval:execution", "reject"): make("exec_reject"),
			("approval:flow", "approve"): make("flow_approve"),
			("approval:flow", "reject"): make("flow_reject")}
		p = patch.object(ap, "_decision_fn", lambda kind, choice: self.fns[(kind, choice)])
		p.start()
		self.addCleanup(p.stop)

	def sess(self, kind="approval:execution", choice="approve", name="AEA-1"):
		return {"kind": kind, "choice": choice, "payload": {"kind": kind, "name": name}}

	def test_registry_prefix(self):
		self.assertIs(si._HANDLERS["approval:"], ap.handle_click)
		self.assertIs(si.get_action_handler.__globals__["_HANDLERS"]["approval:"], ap.handle_click)

	def test_exec_approve_runs_as_actor(self):
		out = ap.handle_click("gw1", self.sess(), "alice@x.com", {})
		self.assertEqual(self.calls, [("exec_approve", "AEA-1", "alice@x.com", "Decided via Slack")])
		self.assertIn("Approved by alice@x.com", out["text"])

	def test_exec_reject(self):
		out = ap.handle_click("gw1", self.sess(choice="reject"), "alice@x.com", {})
		self.assertEqual(self.calls[0][0], "exec_reject")
		self.assertIn("Rejected by alice@x.com", out["text"])

	def test_flow_approve_and_reject(self):
		ap.handle_click("gw1", self.sess("approval:flow", "approve", "FR-1"), "bob@x.com", {})
		ap.handle_click("gw1", self.sess("approval:flow", "reject", "FR-2"), "bob@x.com", {})
		self.assertEqual([c[0] for c in self.calls], ["flow_approve", "flow_reject"])
		self.assertEqual([c[2] for c in self.calls], ["bob@x.com", "bob@x.com"])

	def test_user_restored_even_on_error(self):
		self.fns[("approval:execution", "approve")] = self.make("x", RuntimeError("bad"))
		ap.handle_click("gw1", self.sess(), "alice@x.com", {})
		self.assertEqual(self.w.set_users, ["alice@x.com", "Administrator"])
		self.assertEqual(self.w.user, "Administrator")

	def test_permission_error_polite(self):
		self.fns[("approval:execution", "approve")] = self.make("x", PermissionError_("secret detail"))
		out = ap.handle_click("gw1", self.sess(), "alice@x.com", {})
		self.assertEqual(out["text"], ap.MSG_DENIED)
		self.assertNotIn("blocks", out)

	def test_validation_error_surfaced_escaped_by_renderer(self):
		self.fns[("approval:execution", "approve")] = self.make("x", ValueError("Only Pending approvals <b>"))
		out = ap.handle_click("gw1", self.sess(), "alice@x.com", {})
		self.assertIn("Only Pending approvals", out["text"])
		self.assertIn("&lt;b&gt;", bk.status_line(out["text"]).blocks[0]["elements"][0]["text"])

	def test_success_blocks_have_no_buttons_and_include_who_when(self):
		out = ap.handle_click("gw1", self.sess(), "alice@x.com", {})
		self.assertEqual(out["blocks"][0]["type"], "context")
		self.assertIn("alice@x.com", out["blocks"][0]["elements"][0]["text"])
		self.assertIn("2026-01-02 03:04:05", out["blocks"][0]["elements"][0]["text"])

	def test_bad_choice_or_kind_decides_nothing(self):
		for s in (self.sess(choice="maybe"), self.sess(kind="approval:other"), self.sess(name="")):
			self.assertEqual(ap.handle_click("gw1", s, "alice@x.com", {})["text"], ap.MSG_FAILED)
		self.assertEqual(self.calls, [])

	def test_no_actor_decides_nothing(self):
		self.assertEqual(ap.handle_click("gw1", self.sess(), "", {})["text"], ap.MSG_FAILED)
		self.assertEqual(self.calls, [])

	def test_payload_as_json_string(self):
		s = self.sess()
		s["payload"] = json.dumps(s["payload"])
		ap.handle_click("gw1", s, "alice@x.com", {})
		self.assertEqual(len(self.calls), 1)

	def test_decision_fn_targets_real_apis(self):
		ex = types.ModuleType("m1")
		ex.approve_execution = lambda *a: "ea"
		ex.reject_execution = lambda *a: "er"
		fl = types.ModuleType("m2")
		fl.approve_flow_run = lambda *a: "fa"
		fl.reject_flow_run = lambda *a: "fr"
		# call the real function (setUp patched the module attribute only)
		real = self._real_decision_fn
		with patch.dict(sys.modules, {
			"huf.huf.doctype.agent_execution_approval.agent_execution_approval": ex,
			"huf.ai.flow_api": fl}):
			self.assertEqual(real("approval:execution", "approve")(), "ea")
			self.assertEqual(real("approval:execution", "reject")(), "er")
			self.assertEqual(real("approval:flow", "approve")(), "fa")
			self.assertEqual(real("approval:flow", "reject")(), "fr")

	_real_decision_fn = staticmethod(ap._decision_fn)


class TestEndToEndWithB1(Base):
	"""B1's dispatcher enforces wrong-actor / double-click before our handler runs."""

	def test_wrong_actor_rejected_and_double_click_single_decision(self):
		decisions = []
		sessions = {"S1": {"state": "Pending", "intended_user": "alice@x.com"}}

		def click(actor):
			s = sessions["S1"]
			if s["intended_user"] != actor:
				return si.MSG_NOT_FOR_YOU
			if s["state"] != "Pending":
				return si.MSG_USED
			s["state"] = "Consumed"
			decisions.append(actor)
			return ap.handle_click("gw1", {"kind": "approval:execution", "choice": "approve",
				"payload": {"name": "AEA-1"}}, actor, {})["text"]

		with patch.object(ap, "_decision_fn", lambda k, c: (lambda n, cm=None: None)):
			self.assertEqual(click("bob@x.com"), si.MSG_NOT_FOR_YOU)
			self.assertIn("Approved", click("alice@x.com"))
			self.assertEqual(click("alice@x.com"), si.MSG_USED)
		self.assertEqual(decisions, ["alice@x.com"])


class TestStatic(unittest.TestCase):
	def test_hooks_entry_present(self):
		src = open(os.path.join(ROOT, "huf", "hooks.py")).read()
		tree = ast.parse(src)
		events = None
		for node in tree.body:
			if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "doc_events":
				events = ast.literal_eval(node.value)
		entry = events["Agent Execution Approval"]
		self.assertEqual(entry, {"after_insert": "huf.ai.gateways.approvals.on_approval_inserted"})
		self.assertTrue(callable(ap.on_approval_inserted))

	def test_hooks_py_compiles(self):
		import py_compile

		py_compile.compile(os.path.join(ROOT, "huf", "hooks.py"), doraise=True)

	def test_flow_run_hook_untouched(self):
		self.assertIn("huf.ai.gateways.flow_reply.on_flow_run_update",
			open(os.path.join(ROOT, "huf", "hooks.py")).read())


if __name__ == "__main__":
	unittest.main()
