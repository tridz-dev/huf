# Copyright (c) 2025, Tridz Technologies Pvt Ltd and Contributors
# See license.txt

import json

from frappe.tests.utils import FrappeTestCase

from huf.ai.sdk_tools import _load_state as sdk_load_state
from huf.ai.conversation_data_tools import _load_state as cd_load_state


class TestConversationDataLoadState(FrappeTestCase):
    """Batch 1: malformed/legacy conversation_data must not abort the agent run."""

    def test_load_state_returns_default_for_none(self):
        for fn in (sdk_load_state, cd_load_state):
            result = fn(None)
            self.assertEqual(result, {"version": 1, "scope": {}, "items": []})

    def test_load_state_returns_default_for_empty_string(self):
        for fn in (sdk_load_state, cd_load_state):
            result = fn("")
            self.assertEqual(result, {"version": 1, "scope": {}, "items": []})

    def test_load_state_returns_default_for_invalid_json(self):
        for fn in (sdk_load_state, cd_load_state):
            result = fn("not valid json {{")
            self.assertEqual(result, {"version": 1, "scope": {}, "items": []})

    def test_load_state_returns_default_for_non_string_non_dict(self):
        for fn in (sdk_load_state, cd_load_state):
            result = fn(12345)
            self.assertEqual(result, {"version": 1, "scope": {}, "items": []})

    def test_load_state_handles_double_encoded_string(self):
        payload = {"items": [{"name": "x", "value": 1}], "version": 2}
        for fn in (sdk_load_state, cd_load_state):
            result = fn(json.dumps(json.dumps(payload)))
            self.assertEqual(result["version"], 2)
            self.assertEqual(result["items"], [{"name": "x", "value": 1}])

    def test_load_state_preserves_valid_dict(self):
        payload = {"items": [{"name": "y", "value": "ok"}]}
        for fn in (sdk_load_state, cd_load_state):
            result = fn(payload)
            self.assertEqual(result["items"], [{"name": "y", "value": "ok"}])
