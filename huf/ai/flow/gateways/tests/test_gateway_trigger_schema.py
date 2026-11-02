# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Schema, validator and publish-time checks for trigger.gateway / trigger.whatsapp / trigger.telegram (WP1 contract)."""

import copy
import unittest

from huf.ai.flow.gateways.registry import GATEWAY_NODE_TYPES, MAX_LIST_ITEMS, MAX_PARAMS, param_problems
from huf.ai.graph.tests.test_flow_field_contract import OUT, _errs, _graph
from huf.huf.doctype.flow_definition.activation_rules import collect_activation_problems


def _flow(node_type, config):
	trigger = {"id": "t", "type": node_type, "config": config, "next": "end"}
	return _graph([trigger, dict(OUT)], "t")


def _cfg(graph):
	return graph["nodes"][0]["config"]


class TestGatewayTriggerSchema(unittest.TestCase):
	def assertAccepted(self, graph):
		result, msg = _errs(graph)
		self.assertTrue(result.ok, msg)

	def assertRejected(self, graph):
		result, _msg = _errs(graph)
		self.assertFalse(result.ok, "expected rejection")

	def test_all_three_node_types_accept_gateway_and_params(self):
		config = {"gateway": "Support", "params": [{"key": "keywords", "value": ["order", "refund"]}, {"key": "ignore_bots", "value": True}]}
		for node_type in GATEWAY_NODE_TYPES:
			with self.subTest(node_type):
				self.assertAccepted(_flow(node_type, copy.deepcopy(config)))

	def test_blank_gateway_and_empty_config_are_fine_in_a_draft(self):
		for node_type in GATEWAY_NODE_TYPES:
			with self.subTest(node_type):
				self.assertAccepted(_flow(node_type, {}))
				self.assertAccepted(_flow(node_type, {"gateway": "", "params": []}))

	def test_config_is_closed(self):
		for node_type in GATEWAY_NODE_TYPES:
			with self.subTest(node_type):
				self.assertRejected(_flow(node_type, {"gateway": "S", "token": "x"}))
				self.assertRejected(_flow(node_type, {"gateway": "S", "params": [{"key": "keywords", "value": "a", "label": "x"}]}))
				self.assertRejected(_flow(node_type, {"gateway": "S", "params": [{"key": "keywords"}]}))

	def test_param_key_and_value_shapes(self):
		for bad in ({"key": "Keywords", "value": "a"}, {"key": "1a", "value": "a"}, {"key": "a-b", "value": "a"}):
			self.assertRejected(_flow("trigger.gateway", {"params": [bad]}))
		self.assertRejected(_flow("trigger.gateway", {"params": [{"key": "keywords", "value": {"a": 1}}]}))
		self.assertRejected(_flow("trigger.gateway", {"params": [{"key": "keywords", "value": [1, 2]}]}))
		self.assertRejected(_flow("trigger.gateway", {"params": [{"key": "keywords", "value": [["a"]]}]}))

	def test_schema_caps(self):
		self.assertRejected(_flow("trigger.gateway", {"params": [{"key": "keywords", "value": ["w"] * (MAX_LIST_ITEMS + 1)}]}))
		self.assertRejected(_flow("trigger.gateway", {"params": [{"key": "starts_with", "value": "x" * 501}]}))
		self.assertRejected(_flow("trigger.gateway", {"params": [{"key": "keywords", "value": ["x" * 201]}]}))
		self.assertRejected(_flow("trigger.gateway", {"params": [{"key": f"k{i}", "value": True} for i in range(MAX_PARAMS + 1)]}))
		self.assertRejected(_flow("trigger.gateway", {"gateway": "g" * 141}))

	def test_validator_knows_exactly_the_registry_node_types(self):
		from huf.ai.graph.validator import FLOW_ONLY_NODE_TYPES

		chat = {t for t in FLOW_ONLY_NODE_TYPES if t in ("trigger.gateway", "trigger.whatsapp", "trigger.telegram")}
		self.assertEqual(chat, set(GATEWAY_NODE_TYPES))

	def test_other_triggers_unaffected(self):
		webhook = _graph([{"id": "t", "type": "trigger.webhook", "config": {"method": "POST", "secret": "s" * 32}, "next": "end"}, dict(OUT)], "t")
		self.assertAccepted(webhook)


class TestGatewayTriggerPublishRules(unittest.TestCase):
	def problems(self, node_type, config):
		return collect_activation_problems(_flow(node_type, config))

	def test_blank_gateway_blocks_publish_with_a_reason(self):
		for node_type in GATEWAY_NODE_TYPES:
			with self.subTest(node_type):
				self.assertTrue(any("'gateway' is empty" in p for p in self.problems(node_type, {})))
				self.assertTrue(any("'gateway' is empty" in p for p in self.problems(node_type, {"gateway": "  "})))

	def test_valid_trigger_has_no_problems(self):
		config = {"gateway": "Support", "params": [{"key": "keywords", "value": ["order"]}, {"key": "max_runs_per_sender_per_hour", "value": 10}]}
		for node_type in GATEWAY_NODE_TYPES:
			with self.subTest(node_type):
				self.assertEqual(self.problems(node_type, config), [])

	def test_unknown_key_for_the_provider_is_rejected_at_publish(self):
		bad = {"gateway": "S", "params": [{"key": "commands", "value": ["start"]}]}
		self.assertTrue(self.problems("trigger.whatsapp", bad))  # commands is Telegram-only
		self.assertTrue(self.problems("trigger.gateway", bad))
		self.assertEqual(self.problems("trigger.telegram", bad), [])

	def test_value_types_checked_per_key(self):
		for key, value in (
			("keywords", "order"),  # list expected
			("ignore_bots", "yes"),  # boolean expected
			("max_runs_per_sender_per_hour", True),  # bool is not a number
			("max_runs_per_sender_per_hour", -1),
			("max_runs_per_sender_per_hour", "30"),
			("starts_with", ["a"]),
			("message_kinds", ["spaceship"]),  # not an option
			("chat_scope", "everywhere"),  # not an option
		):
			with self.subTest(key=key, value=value):
				self.assertTrue(self.problems("trigger.gateway", {"gateway": "S", "params": [{"key": key, "value": value}]}))

	def test_duplicate_keys_rejected_unless_multiple(self):
		dup = [{"key": "keywords", "value": ["a"]}, {"key": "keywords", "value": ["b"]}]
		self.assertTrue(param_problems("trigger.gateway", dup))

	def test_null_value_means_unset(self):
		self.assertEqual(param_problems("trigger.gateway", [{"key": "keywords", "value": None}]), [])
