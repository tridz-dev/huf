# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""W2 gate (H-W2-20): the guarantees G1-G5, one class each. All data here is synthetic.

See docs/flow/GUARANTEES.md for what each case proves and how Happiol CI runs the same cases.

Run with:
    bench --site <site> run-tests --app huf --module huf.ai.flow.tests.test_flow_guarantees
"""

import json
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.channels.outbound import guard, guard_steps
from huf.ai.flow import engine
from huf.ai.flow.nodes import retry, send
from huf.ai.flow.runs import park
from huf.ai.flow.support import pii, step_keys
from huf.ai.flow.support.pii_mask import mask_pii
from huf.ai.flow.testrun import gate
from huf.ai.flow.tests.test_flow_draft_validation import finished_flow
from huf.ai.graph.executor import GraphContext
from huf.ai.graph.validation.flow_validation import VALIDATOR_HOOK, validate_flow
from huf.huf.doctype.flow_definition.flow_definition import FlowDefinition

HERE = "huf.ai.flow.tests.test_flow_guarantees"
PHONE = "+91 98765 43210"
DIGITS = "919876543210"
EMAIL = "asha.rao@example.test"
NAME = "Asha Raoul"
CONFIG = {"gateway": "gw", "recipient": PHONE, "template": "promo", "category": "marketing"}
NODE = {"id": "s1", "type": "send.message", "next": "n2", "config": CONFIG}
# node id -> ledger kind: how the stand-in policy tells which registered steps are ledger steps
LEDGER_IDS: dict = {}
LEDGER_KINDS = ("grant_points", "issue_coupon", "adjust_points", "redeem_points")


def run_doc(run_mode="", waiting=None):
	return SimpleNamespace(
		name="RUN-G",
		flow_id="flow-g",
		flow_version="1",
		member_key="m1",
		run_mode=run_mode,
		status="Running",
		waiting=waiting,
	)


def allow(request):
	return {"allow": True}


@contextmanager
def send_harness(steps, live=True, hooks=None, ctx=None):
	"""Run ``send.message`` with ``steps`` as the built-in guard steps and a fake transport."""
	transport = MagicMock(return_value=None)
	persisted = []
	registry = hooks or {}
	context = ctx if ctx is not None else GraphContext()
	patchers = (
		patch.object(guard, "BUILTIN_STEPS", steps),
		patch.object(guard, "_hook_paths", return_value=list(registry)),
		patch.object(guard_steps, "window_resolvers", return_value=[]),
		patch.object(guard_steps, "resolve_caps", return_value=[]),
		patch.object(gate, "live_send_on", return_value=live),
		patch.object(gate, "pin_is_current", return_value=True),
		patch.object(send, "_enqueue", transport),
		patch.object(send, "channel_of", return_value="whatsapp"),
		patch.object(engine, "_context_of", return_value=context),
		patch.object(
			engine,
			"_persist_context",
			side_effect=lambda r, c, s: persisted.append(json.dumps(c.data, default=str)),
		),
		patch.object(engine, "_transition_run", return_value=True),
		patch("huf.ai.flow.runs.member.set_status"),
	)
	real_get_attr = frappe.get_attr
	with patch.object(
		frappe, "get_attr", side_effect=lambda p: registry[p] if p in registry else real_get_attr(p)
	):
		for p in patchers:
			p.start()
		try:
			yield SimpleNamespace(transport=transport, persisted=persisted, ctx=context)
		finally:
			for p in reversed(patchers):
				p.stop()


def send_once(node=None, run_mode=""):
	node = node or step_keys.with_key(NODE, "RUN-G:s1:1")
	return send.exec_send_message(run_doc(run_mode), node, dict(node.get("config") or CONFIG), {})


# --- G1: ledger nodes only through the guarded ledger path ---------------------------------------------


def happiol_like_ledger_policy(graph):
	"""Stands in for Happiol's node policy (P-W3-08): raw ledger_write is refused; ledger nodes need key and caps."""
	errors = []
	for n in graph["nodes"]:
		config = n.get("config") or {}
		if n["type"] == "ledger_write":
			errors.append(
				{
					"code": "LEDGER_RAW_WRITE",
					"node_id": n["id"],
					"field": "type",
					"message": "Raw ledger writes are not allowed.",
				}
			)
		elif n["type"] in LEDGER_KINDS or LEDGER_IDS.get(n["id"]) in LEDGER_KINDS:
			if not config.get("idempotency_key"):
				errors.append(
					{
						"code": "LEDGER_NO_KEY",
						"node_id": n["id"],
						"field": "config.idempotency_key",
						"message": "A ledger step needs an idempotency key.",
					}
				)
			if not config.get("node_cap") or not config.get("flow_cap"):
				errors.append(
					{
						"code": "LEDGER_NO_CAP",
						"node_id": n["id"],
						"field": "config.node_cap",
						"message": "A ledger step needs budget caps.",
					}
				)
	return errors


def crash(graph):
	raise RuntimeError(EMAIL)


@contextmanager
def validators(*names):
	real = frappe.get_hooks

	def get_hooks(hook=None, *args, **kwargs):
		if hook == VALIDATOR_HOOK:
			return [f"{HERE}.{n}" for n in names]
		return real(hook, *args, **kwargs)

	with patch.object(frappe, "get_hooks", get_hooks):
		yield


def with_node(node):
	g = finished_flow()
	g["nodes"].append(node)
	return g


class TestG1LedgerOnlyThroughGuardedPath(IntegrationTestCase):
	def codes(self, graph, mode):
		result = validate_flow(graph, mode)
		return result.ok, {e.code for e in result.errors}

	def test_raw_ledger_write_is_refused_in_every_mode(self):
		g = with_node({"id": "lw", "type": "ledger_write", "config": {"amount": 10}})
		with validators("happiol_like_ledger_policy"):
			for mode in ("draft", "publish"):
				ok, codes = self.codes(g, mode)
				self.assertFalse(ok, mode)
				# Core refuses the unregistered kind (SCHEMA) before any app policy; either refusal is G1.
				self.assertTrue(codes & {"SCHEMA", "LEDGER_RAW_WRITE"}, (mode, codes))
		self.assertEqual([e["code"] for e in happiol_like_ledger_policy(g)], ["LEDGER_RAW_WRITE"])

	def test_ledger_node_without_key_or_caps_is_refused(self):
		for kind in LEDGER_KINDS:
			# A registered kind stands in for the app's ledger node (Huf has no ledger kinds of its own).
			g = finished_flow()
			LEDGER_IDS["cond"] = kind
			self.addCleanup(LEDGER_IDS.clear)
			with self.subTest(kind=kind), validators("happiol_like_ledger_policy"):
				ok, codes = self.codes(g, "publish")
				self.assertFalse(ok)
				self.assertTrue({"LEDGER_NO_KEY", "LEDGER_NO_CAP"} <= codes, codes)

	def test_ledger_node_with_key_and_caps_raises_no_policy_error(self):
		node = {
			"id": "lg",
			"type": "grant_points",
			"config": {"idempotency_key": "run,node,member", "node_cap": 100, "flow_cap": 1000},
		}
		self.assertEqual(happiol_like_ledger_policy(with_node(node)), [])

	def test_broken_policy_fails_closed(self):
		g = finished_flow()
		with validators("crash"):
			result = validate_flow(g, "publish")
		self.assertFalse(result.ok)
		self.assertIn("APP_VALIDATOR_FAILED", {e.code for e in result.errors})
		self.assertNotIn(EMAIL, json.dumps(result.to_dict()))


# --- G2: a blocked send is final and is never retried ----------------------------------------------------


class TestG2BlockedIsFinal(IntegrationTestCase):
	def setUp(self):
		self.calls = 0

	def block(self, request):
		self.calls += 1
		return {"allow": False, "reason": "opted_out"}

	def test_blocked_not_retried_by_retry_wrapper(self):
		node = {
			**NODE,
			"config": {**CONFIG, "retry": {"attempts": 3, "backoff": "fixed", "delay_seconds": 60}},
		}
		with send_harness([("block", self.block)]) as h, patch.object(park, "park_run") as park_run:
			result = retry.run_with_retry(
				run_doc(), node, {}, lambda: send.exec_send_message(run_doc(), NODE, dict(CONFIG), {})
			)
		self.assertEqual(result["output"], {"status": "blocked", "reason": "opted_out"})
		self.assertEqual(h.transport.call_count, 0)
		self.assertEqual(park_run.call_count, 0)
		self.assertEqual(self.calls, 1)
		self.assertIsNone(retry.policy_of(node))

	def test_blocked_stays_blocked_after_resume(self):
		woken = json.dumps({"node_id": "s1", "reason": park.SEND_WINDOW_REASON, "woke": {"reason": "timer"}})
		with send_harness([("block", self.block)]) as h:
			result = send.exec_send_message(run_doc(waiting=woken), NODE, dict(CONFIG), {})
		self.assertEqual(result["output"]["status"], "blocked")
		self.assertEqual(h.transport.call_count, 0)

	def test_redelivery_after_republish_replays_the_block(self):
		"""Same run, same step key: once blocked, a later pass (re-delivered job, republished flow) never sends."""
		ctx = GraphContext()
		with send_harness([("block", self.block)], ctx=ctx) as h:
			first = send_once()
		self.assertEqual(first["output"]["status"], "blocked")
		with send_harness([("allow", allow)], ctx=ctx) as h:
			second = send_once()
		self.assertEqual(second["output"], first["output"])
		self.assertEqual(h.transport.call_count, 0)
		self.assertEqual(self.calls, 1)

	def test_republish_turns_live_send_off(self):
		before = SimpleNamespace(status="Active", definition_json='{"a":1}')
		doc = SimpleNamespace(status="Active", definition_json='{"a":2}', live_send=1)
		doc.is_new = lambda: False
		doc.get_doc_before_save = lambda: before
		FlowDefinition._reset_live_send_on_republish(doc)
		self.assertEqual(doc.live_send, 0)


# --- G3: live means live_send AND NOT dry_run --------------------------------------------------------------


class TestG3LiveMatrix(IntegrationTestCase):
	def test_truth_table_and_transport(self):
		for dry, live_send, expected in (
			(True, True, False),
			(True, False, False),
			(False, False, False),
			(False, True, True),
		):
			mode = gate.STORED_TEST if dry else ""
			with self.subTest(dry=dry, live_send=live_send):
				with (
					patch.object(gate, "live_send_on", return_value=live_send),
					patch.object(gate, "pin_is_current", return_value=True),
				):
					self.assertIs(gate.is_live(run_doc(mode)), expected)
				with send_harness([("allow", allow)], live=live_send) as h:
					result = send_once(run_mode=mode)
				self.assertEqual(result["output"]["status"], "queued" if expected else "previewed")
				self.assertEqual(h.transport.call_count, 1 if expected else 0)

	def test_step_test_scope_is_dry(self):
		with gate.step_test_scope(), patch.object(gate, "live_send_on", return_value=True):
			self.assertFalse(gate.is_live(run_doc()))

	def test_live_send_lookup_fails_closed(self):
		self.assertFalse(gate.live_send_on(None))
		with patch.object(frappe.db, "get_value", side_effect=RuntimeError("x")):
			self.assertFalse(gate.live_send_on("flow-g"))


# --- G4: no PII in traces or logs -----------------------------------------------------------------------


class TestG4NoPiiInTraceOrLog(IntegrationTestCase):
	RAW = (PHONE, DIGITS, "9876543210", EMAIL)

	def assertClean(self, text):
		for value in self.RAW:
			self.assertNotIn(value, text)

	def test_send_flow_writes_no_pii_to_context_trace_or_log(self):
		def block_with_pii(request):
			return {"allow": False, "reason": f"no consent for {request['recipient']} {EMAIL}"}

		for steps, status in (([("allow", allow)], "queued"), ([("pii", block_with_pii)], "blocked")):
			with self.subTest(status=status), patch.object(frappe, "logger") as logger:
				with send_harness(steps) as h:
					result = send_once()
				self.assertEqual(result["output"]["status"], status)
				self.assertClean(json.dumps(result, default=str))
				self.assertClean(" ".join(h.persisted))
				self.assertClean(repr(logger.mock_calls))

	def test_block_reason_is_a_code_not_free_text(self):
		with send_harness([("pii", lambda r: {"allow": False, "reason": f"bad {r['recipient']}"})]):
			result = send_once()
		self.assertEqual(result["output"]["reason"], "unknown")

	def test_trace_and_error_log_writers_mask(self):
		masked = mask_pii(
			{"customer_name": NAME, "mobile_no": PHONE, "email": EMAIL, "note": f"call {PHONE}"}
		)
		self.assertClean(json.dumps(masked))
		self.assertNotIn(NAME, json.dumps(masked))
		self.assertClean(pii.mask_text(f"failed for {DIGITS} ({EMAIL})"))
		with patch.object(frappe, "log_error") as log_error:
			pii.log_flow_error(f"Traceback: bad {DIGITS} {EMAIL}", "Flow node s1 raised")
		self.assertClean(repr(log_error.mock_calls))


# --- G5: every send goes through the fail-closed pre-send guard chain -------------------------------------


class TestG5FailClosedGuard(IntegrationTestCase):
	def assertBlockedSend(self, steps=None, hooks=None, reason=None):
		with send_harness(steps if steps is not None else [], hooks=hooks) as h:
			result = send_once()
		self.assertEqual(result["output"]["status"], "blocked")
		if reason:
			self.assertEqual(result["output"]["reason"], reason)
		self.assertEqual(h.transport.call_count, 0)
		return result

	def test_hook_error_blocks(self):
		def boom(request):
			raise ValueError(request["recipient"])

		self.assertBlockedSend(hooks={"app.boom": boom}, reason=guard.HOOK_ERROR)
		self.assertBlockedSend(hooks={"app.junk": lambda r: {"allow": "yes"}}, reason=guard.HOOK_ERROR)

	def test_hook_timeout_blocks(self):
		import threading

		release = threading.Event()

		def slow(request):
			release.wait(2)
			return {"allow": True}

		with patch.object(guard, "_timeout", return_value=0.05):
			self.assertBlockedSend(hooks={"app.slow": slow}, reason=guard.HOOK_TIMEOUT)
		release.set()

	def test_missing_consent_blocks(self):
		# WhatsApp consent with no gateway on the request: Huf's own consent step refuses.
		self.assertEqual(
			guard_steps.check_consent({"channel": "whatsapp", "recipient": PHONE}),
			{"allow": False, "reason": "blocked_by_hook"},
		)
		with patch("huf.ai.channels.channel_consent.has_consent", return_value=(False, "opted_out")):
			verdict = guard_steps.check_consent(
				{"channel": "sms", "recipient": PHONE, "category": "marketing"}
			)
		self.assertIs(verdict.get("allow"), False)
		consent_step = [("consent", lambda r: {"allow": False, "reason": "marketing_opted_out"})]
		self.assertBlockedSend(steps=consent_step, reason="marketing_opted_out")

	def test_broken_hook_lookup_blocks(self):
		with patch.object(guard, "_hook_paths", side_effect=RuntimeError):
			self.assertFalse(guard.evaluate({"recipient": PHONE}).allowed)

	def test_allowing_chain_sends_exactly_once(self):
		with send_harness([("allow", allow)], hooks={"app.ok": allow}) as h:
			self.assertEqual(send_once()["output"]["status"], "queued")
		self.assertEqual(h.transport.call_count, 1)
