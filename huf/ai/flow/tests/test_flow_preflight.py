# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""H-W2-09: preflight findings, the ``huf_flow_preflight`` hook, and publish blocking on error findings.

Run with:
    bench --site <site> run-tests --app huf --module huf.ai.flow.tests.test_flow_preflight
"""

import json
from unittest import mock

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.flow import api as flow_api
from huf.ai.flow import preflight, publish_guard
from huf.ai.flow.tests.test_flow_draft_validation import _end, _graph, _trigger, finished_flow

MODULE = __name__
FLOW_ID = "test-flow-preflight"
PHONE = "+919999999999"


def hook_raises(defn, flow_id):
	raise RuntimeError(f"could not reach {PHONE}")


def hook_returns_none(defn, flow_id):
	return None


def hook_bad_item(defn, flow_id):
	return [{"code": "has spaces " + PHONE, "severity": "info"}]


def hook_error(defn, flow_id):
	return [{"code": "APP_BLOCK", "severity": "error", "node_id": "cond", "message": PHONE}]


def hook_warning(defn, flow_id):
	return [{"code": "APP_NOTE", "severity": "warning", "node_id": PHONE}]


def _hooks(*names):
	return mock.patch.object(preflight, "_hook_paths", return_value=[f"{MODULE}.{n}" for n in names])


def _send(config):
	return _graph([_trigger("s"), {"id": "s", "type": "send.message", "config": config, "next": "end"}, _end()])


def _codes(findings, severity="error"):
	return {(f.code, f.node_id) for f in findings if f.severity == severity}


class TestFlowPreflight(IntegrationTestCase):
	def test_finished_flow_has_no_findings(self):
		with _hooks():
			self.assertEqual(preflight.run_preflight(finished_flow()), [])

	def test_unreachable_node_is_an_error(self):
		g = finished_flow()
		g["nodes"].append(_end("loose"))
		with _hooks():
			self.assertIn(("UNREACHABLE_NODE", "loose"), _codes(preflight.run_preflight(g)))
			self.assertRaises(frappe.ValidationError, publish_guard.check_preflight, g)

	def test_missing_template_is_an_error(self):
		with _hooks():
			for config in ({}, {"template": "no-such-template-xyz"}):
				findings = preflight.run_preflight(_send(config))
				self.assertIn(("TEMPLATE_MISSING", "s"), _codes(findings), config)
				self.assertIn(("AUDIENCE_ESTIMATE_UNAVAILABLE", None), _codes(findings, "info"))

	def test_existing_template_passes(self):
		with _hooks(), mock.patch.object(preflight, "template_exists", return_value=True):
			codes = _codes(preflight.run_preflight(_send({"template": "welcome"})))
		self.assertNotIn(("TEMPLATE_MISSING", "s"), codes)

	def test_broken_hooks_are_error_findings(self):
		cases = {
			"hook_raises": "PREFLIGHT_HOOK_ERROR",
			"no_such_function": "PREFLIGHT_HOOK_ERROR",
			"hook_returns_none": "PREFLIGHT_HOOK_BAD_RESULT",
			"hook_bad_item": "PREFLIGHT_HOOK_BAD_RESULT",
		}
		for name, code in cases.items():
			with _hooks(name), mock.patch.object(frappe, "log_error") as log:
				findings = preflight.run_preflight(finished_flow())
				self.assertEqual(_codes(findings), {(code, None)}, name)
				self.assertRaises(frappe.ValidationError, publish_guard.check_preflight, finished_flow())
				self.assertNotIn(PHONE, str(log.call_args_list))

	def test_check_that_breaks_is_an_error(self):
		with _hooks(), mock.patch.object(preflight, "template_exists", side_effect=RuntimeError):
			findings = preflight.run_preflight(_send({"template": "x"}))
		self.assertIn(("PREFLIGHT_CHECK_ERROR", None), _codes(findings))

	def test_findings_carry_only_code_node_and_severity(self):
		with _hooks("hook_error", "hook_warning"):
			findings = [f.to_dict() for f in preflight.run_preflight(finished_flow())]
		self.assertEqual(
			findings,
			[
				{"code": "APP_BLOCK", "node_id": "cond", "severity": "error"},
				{"code": "APP_NOTE", "node_id": None, "severity": "warning"},
			],
		)
		self.assertNotIn(PHONE, json.dumps(findings))


class TestPublishBlocking(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		if frappe.db.exists("Flow Definition", FLOW_ID):
			frappe.delete_doc("Flow Definition", FLOW_ID, force=True)
		self.addCleanup(
			lambda: frappe.db.exists("Flow Definition", FLOW_ID)
			and frappe.delete_doc("Flow Definition", FLOW_ID, force=True)
		)
		flow_api.save_flow_definition(FLOW_ID, finished_flow())

	def _status(self):
		return frappe.db.get_value("Flow Definition", FLOW_ID, "status")

	def test_error_finding_blocks_publish(self):
		with _hooks("hook_error"):
			with self.assertRaises(frappe.ValidationError) as ctx:
				flow_api.publish_flow(FLOW_ID)
		self.assertIn("APP_BLOCK", str(ctx.exception))
		self.assertEqual(self._status(), "Draft")

	def test_warning_does_not_block_publish(self):
		with _hooks("hook_warning"):
			flow_api.publish_flow(FLOW_ID)
		self.assertEqual(self._status(), "Active")
