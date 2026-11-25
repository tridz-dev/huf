"""Integration regressions: new step types and settings pass validation, and the wake sweeper reads UTC."""

import json
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.flow import triggers
from huf.ai.flow.tests.test_flow_draft_validation import _end, _graph, _trigger
from huf.ai.graph.validator import validate_graph


def _ok(nodes, envelope=None, writes=0):
	graph = _graph(nodes)
	if envelope:
		graph["contract"]["permission_envelope"] = envelope
	graph["contract"]["limits"]["max_writes"] = writes
	return validate_graph(graph, "flow")


class TestNewStepsValidate(unittest.TestCase):
	def _step(self, node_type, config, **extra):
		return _ok([_trigger("s"), {"id": "s", "type": node_type, "next": "end", "config": config, **extra}, _end()])

	def test_new_node_types_are_valid(self):
		env = {"read": [{"doctype": "ToDo"}], "write": [{"doctype": "ToDo"}], "http": "none", "code": "none"}
		cases = {
			"stop": {"message": "no", "as": "error"},
			"doc.get": {"doctype": "ToDo", "name": "x", "fields": ["description"]},
			"doc.update": {"doctype": "ToDo", "name": "x", "values": {"description": "y"}},
			"flow.call": {"flow_id": "other", "mode": "wait"},
			"member.set": {"vars": {"tier": "gold"}},
		}
		for node_type, config in cases.items():
			node = {"id": "s", "type": node_type, "next": "end", "config": config}
			result = _ok([_trigger("s"), node, _end()], envelope=env, writes=3)
			self.assertTrue(result.ok, (node_type, [str(e) for e in result.errors]))

	def test_switch_rules_without_policy(self):
		node = {
			"id": "s",
			"type": "router.decision",
			"config": {"options": [{"label": "big", "node_id": "end", "expression": "input['n'] > 1"}], "default": "end"},
		}
		result = _ok([_trigger("s"), node, _end()])
		self.assertTrue(result.ok, [str(e) for e in result.errors])

	def test_wait_for_and_gateway_entry_policy(self):
		wait = {"id": "s", "type": "wait", "next": "end", "config": {"mode": "resume", "resume": {"wait_for": "member_reply"}}}
		start = {"id": "start", "type": "trigger.gateway", "next": "s", "config": {"gateway": "g", "entry_policy": "resume_if_waiting"}}
		result = _ok([start, wait, _end()])
		self.assertTrue(result.ok, [str(e) for e in result.errors])

	def test_retry_policy_on_tool_call_schema(self):
		retry = {"attempts": 3, "backoff": "exponential", "delay_seconds": 60, "max_delay_seconds": 600}
		result = self._step("tool.call", {"tool_id": "t", "input": {}, "retry": retry})
		self.assertFalse([e for e in result.errors if "retry" in str(e)], [str(e) for e in result.errors])
		bad = self._step("tool.call", {"tool_id": "t", "input": {}, "retry": {"attempts": 99}})
		self.assertTrue([e for e in bad.errors if "retry" in str(e)])


class TestSweeperReadsUtc(unittest.TestCase):
	def test_default_cutoff_is_utc(self):
		seen = {}
		real = frappe.get_all

		def spy(doctype, **kw):
			seen["filters"] = kw.get("filters")
			return []

		with patch("frappe.get_all", side_effect=spy):
			triggers.wake_due_waits()
		cutoff = seen["filters"]["resume_at"][1]
		utc_now = datetime.now(timezone.utc).replace(tzinfo=None)
		self.assertLess(abs((cutoff - utc_now).total_seconds()), 5)
		self.assertIs(real, frappe.get_all)
