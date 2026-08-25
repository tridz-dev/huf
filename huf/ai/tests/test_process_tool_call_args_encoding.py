"""Regression test for the tool_args double-JSON-encoding bug in agent_integration.py.

Per the OpenAI/litellm tool-call convention (see providers/litellm.py, where a raw tool
call's ``args`` originates from ``tool_call.function.arguments``), ``args`` normally
arrives at ``process_tool_call`` already JSON-encoded as a string (e.g. '{"city": "X"}').
Before the fix, both insert and update call sites in ``process_tool_call`` did an
unconditional ``json.dumps(args)`` on this already-encoded string, producing a
double-encoded value in the ``Agent Tool Call.tool_args`` field -- a value that needs
``json.loads()`` TWICE to reach the real dict, instead of once.

This test runs against a real Frappe bench/site (FrappeTestCase) and drives the actual
``process_tool_call`` insert path end-to-end: it creates the minimal Agent / Agent
Conversation / Agent Run fixtures, calls ``process_tool_call`` with ``args`` as an
already-JSON-encoded string exactly as litellm would hand it over, then reloads the
persisted ``Agent Tool Call`` doc from the database and asserts that a SINGLE
``json.loads()`` on ``tool_args`` yields the real dict -- not a string that itself still
needs decoding.

Run with:
    bench --site <site> run-tests --app huf --module huf.ai.tests.test_process_tool_call_args_encoding
"""

import json

import frappe
from frappe.tests.utils import FrappeTestCase

from huf.ai.agent_integration import _normalize_tool_args_json, process_tool_call


class TestProcessToolCallArgsEncoding(FrappeTestCase):
    def setUp(self):
        self.agent = frappe.get_doc({
            "doctype": "Agent",
            "agent_name": frappe.generate_hash(length=10),
            "agent_modality": "Text",
        }).insert(ignore_permissions=True)

        self.conversation = frappe.get_doc({
            "doctype": "Agent Conversation",
            "session_id": frappe.generate_hash(length=10),
            "agent": self.agent.name,
        }).insert(ignore_permissions=True)

        self.agent_run = frappe.get_doc({
            "doctype": "Agent Run",
            "agent": self.agent.name,
            "conversation": self.conversation.name,
        }).insert(ignore_permissions=True)

    def tearDown(self):
        frappe.delete_doc("Agent Run", self.agent_run.name, force=True, ignore_permissions=True)
        frappe.delete_doc("Agent Conversation", self.conversation.name, force=True, ignore_permissions=True)
        frappe.delete_doc("Agent", self.agent.name, force=True, ignore_permissions=True)

    def test_tool_args_round_trips_through_single_json_loads_on_insert(self):
        """The bug: args arrives already JSON-encoded (litellm convention); the insert
        call site used to json.dumps() it again, double-encoding it."""
        real_args = {"city": "San Francisco", "unit": "celsius"}
        already_encoded_args = json.dumps(real_args)

        doc_name = process_tool_call(
            agent_run=self.agent_run.name,
            conversation=self.conversation.name,
            name="get_weather",
            args=already_encoded_args,
            tool_call_id=frappe.generate_hash(length=8),
        )
        self.assertTrue(doc_name)

        stored_tool_args = frappe.db.get_value("Agent Tool Call", doc_name, "tool_args")

        # A single json.loads() must yield the real dict directly -- not a string that
        # itself still needs a second json.loads() call to reach the dict.
        decoded_once = json.loads(stored_tool_args)
        self.assertIsInstance(
            decoded_once,
            dict,
            f"tool_args was double-encoded: one json.loads() produced {type(decoded_once)!r} "
            f"({decoded_once!r}) instead of a dict",
        )
        self.assertEqual(decoded_once, real_args)

    def test_tool_args_round_trips_through_single_json_loads_on_update(self):
        """Same bug, but on the update-existing-queued-call path (the second
        json.dumps(args) call site, guarded by `existing_name`)."""
        real_args = {"query": "double encoding regression"}
        already_encoded_args = json.dumps(real_args)
        call_id = frappe.generate_hash(length=8)

        # First call inserts the row with no args (simulating the client-side tool call
        # creating the row before args are known), second call updates it with args --
        # this exercises the `existing_name` / update_data["tool_args"] call site.
        first_doc_name = process_tool_call(
            agent_run=self.agent_run.name,
            conversation=self.conversation.name,
            name="search",
            args=None,
            tool_call_id=call_id,
        )
        self.assertTrue(first_doc_name)

        second_doc_name = process_tool_call(
            agent_run=self.agent_run.name,
            conversation=self.conversation.name,
            name="search",
            args=already_encoded_args,
            tool_call_id=call_id,
        )
        self.assertEqual(first_doc_name, second_doc_name)

        stored_tool_args = frappe.db.get_value("Agent Tool Call", second_doc_name, "tool_args")
        decoded_once = json.loads(stored_tool_args)
        self.assertIsInstance(decoded_once, dict)
        self.assertEqual(decoded_once, real_args)

    def test_normalize_helper_passes_through_already_valid_json_string(self):
        real_args = {"a": 1, "b": [1, 2, 3]}
        already_encoded = json.dumps(real_args)
        self.assertEqual(_normalize_tool_args_json(already_encoded), already_encoded)

    def test_normalize_helper_still_encodes_dict_input(self):
        real_args = {"a": 1}
        normalized = _normalize_tool_args_json(real_args)
        self.assertEqual(json.loads(normalized), real_args)

    def test_normalize_helper_encodes_plain_non_json_string(self):
        # A string that is not itself valid JSON (e.g. a bare tool name) must still be
        # encoded so it round-trips through json.loads() as a string.
        plain = "not-json-at-all"
        normalized = _normalize_tool_args_json(plain)
        self.assertEqual(json.loads(normalized), plain)
