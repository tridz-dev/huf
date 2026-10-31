# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""The gateway trigger registry shape is a frozen contract.

``registry_snapshot.json`` holds the whole registry. Any change to a spec (a new key, label, option, field) fails this
test on purpose: the frontend, the payload builder and the docs all read the same shape, so a change needs coordinator
approval. To accept an approved change run ``UPDATE_GATEWAY_REGISTRY_SNAPSHOT=1`` once and commit the new snapshot.
"""

import json
import os
import re
import unittest
from pathlib import Path

from huf.ai.flow.gateways.registry import GATEWAY_NODE_TYPES, get_gateway_trigger_spec, get_registry
from huf.ai.flow.gateways.spec_kit import PARAM_TYPES, PAYLOAD_TYPES

SNAPSHOT = Path(__file__).with_name("registry_snapshot.json")
PARAM_KEYS = {"key", "label", "help", "type", "options", "required", "default", "multiple", "show_when", "section"}
FIELD_KEYS = {"path", "label", "type", "sample", "customer_provided", "sensitive", "advanced"}
SPEC_KEYS = {"provider", "label", "node_type", "event_kinds", "params", "payload_fields", "sample_payload"}


def _dump(value) -> str:
	return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


class TestRegistrySnapshot(unittest.TestCase):
	def test_registry_matches_the_frozen_snapshot(self):
		current = _dump(get_registry())
		if os.environ.get("UPDATE_GATEWAY_REGISTRY_SNAPSHOT"):
			SNAPSHOT.write_text(current, encoding="utf-8")
		self.assertEqual(
			current,
			SNAPSHOT.read_text(encoding="utf-8"),
			"The gateway trigger registry changed. This is a frozen contract; get coordinator approval, then update the snapshot.",
		)


class TestRegistryShape(unittest.TestCase):
	def specs(self):
		return [get_gateway_trigger_spec(None, node_type) for node_type in GATEWAY_NODE_TYPES]

	def test_spec_keys_are_exact_and_applies_to_is_gone(self):
		for spec in self.specs():
			self.assertEqual(set(spec), SPEC_KEYS)
			for p in spec["params"]:
				self.assertEqual(set(p), PARAM_KEYS)
			for f in spec["payload_fields"]:
				self.assertEqual(set(f), FIELD_KEYS)
		self.assertNotIn("applies_to", _dump(get_registry()))

	def test_param_keys_unique_valid_and_typed(self):
		for spec in self.specs():
			keys = [p["key"] for p in spec["params"]]
			self.assertEqual(len(keys), len(set(keys)), spec["node_type"])
			for p in spec["params"]:
				self.assertRegex(p["key"], r"^[a-z][a-z0-9_]*$")
				self.assertIn(p["type"], PARAM_TYPES)
				if p["type"] in ("select", "multiselect"):
					self.assertTrue(p["options"], p["key"])
				if p["show_when"]:
					self.assertIn(p["show_when"]["key"], keys)

	def test_payload_paths_live_under_input_and_match_the_sample(self):
		for spec in self.specs():
			paths = [f["path"] for f in spec["payload_fields"]]
			self.assertEqual(len(paths), len(set(paths)))
			for f in spec["payload_fields"]:
				self.assertRegex(f["path"], r"^input\.[a-z][a-z0-9_]*$")
				self.assertIn(f["type"], PAYLOAD_TYPES)
				self.assertNotIn("trigger.", f["path"])
			self.assertEqual(set(spec["sample_payload"]), {p.removeprefix("input.") for p in paths})

	def test_dedicated_specs_extend_the_generic_one(self):
		generic = get_gateway_trigger_spec("Slack")
		self.assertEqual(generic["node_type"], "trigger.gateway")
		self.assertEqual(generic["provider"], "Slack")
		generic_keys = {p["key"] for p in generic["params"]}
		whatsapp = get_gateway_trigger_spec(None, "trigger.whatsapp")
		telegram = get_gateway_trigger_spec(None, "trigger.telegram")
		self.assertEqual((whatsapp["provider"], telegram["provider"]), ("WhatsApp", "Telegram"))
		self.assertIn("button_reply_ids", {p["key"] for p in whatsapp["params"]})
		self.assertIn("commands", {p["key"] for p in telegram["params"]})
		self.assertNotIn("language", {p["key"] for p in whatsapp["params"]})  # Meta sends none
		self.assertNotIn("commands", generic_keys)

	def test_no_secret_looking_names_anywhere(self):
		text = _dump(get_registry()).lower()
		for word in ("password", "secret", "api_key", "access_token", "authorization"):
			self.assertNotIn(word, text)

	def test_the_registry_never_teaches_a_trigger_root(self):
		self.assertIsNone(re.search(r"\{trigger\.", _dump(get_registry())))
