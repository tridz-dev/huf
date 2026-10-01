"""Schema-level checks for the PR1 decision runtime activation data model."""
from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).parents[3] / "huf" / "doctype"


class TestDecisionSchema(unittest.TestCase):
    def load(self, slug):
        return json.loads((ROOT / slug / f"{slug}.json").read_text())

    def test_canonical_and_serving_identity_are_separate(self):
        model = self.load("decision_model")
        deployment = self.load("decision_deployment")
        model_fields = {field["fieldname"] for field in model["fields"]}
        deployment_fields = {field["fieldname"] for field in deployment["fields"]}
        self.assertIn("canonical_version", model_fields)
        self.assertIn("decision_model", deployment_fields)
        self.assertIn("ai_model", deployment_fields)
        self.assertIn("provider", deployment_fields)
        self.assertIn("provider_model_id", deployment_fields)
        self.assertNotIn("provider_model_id", model_fields)

    def test_model_family_has_adapter_id(self):
        family = self.load("decision_model_family")
        fields = {field["fieldname"]: field for field in family["fields"]}
        self.assertIn("adapter_id", fields)
        self.assertEqual(fields["adapter_id"]["fieldtype"], "Data")

    def test_deployment_capabilities_and_wire_protocol(self):
        deployment = self.load("decision_deployment")
        fields = {field["fieldname"] for field in deployment["fields"]}
        self.assertTrue({"supports_select", "supports_judge", "supports_score"} <= fields)
        self.assertIn("input_modalities", fields)
        self.assertIn("ai_model", fields)
        self.assertIn("wire_protocol", fields)
        self.assertIn("endpoint_path", fields)

    def test_call_has_resolved_provider_and_origin_metadata(self):
        call = self.load("decision_call")
        call_fields = {field["fieldname"] for field in call["fields"]}
        # resolved_provider replaces decision_provider
        self.assertIn("resolved_provider", call_fields)
        self.assertNotIn("decision_provider", call_fields)
        # origin metadata fields
        self.assertIn("origin_type", call_fields)
        self.assertIn("automation", call_fields)
        self.assertIn("shadow_of", call_fields)
        self.assertIn("decision_model", call_fields)
        self.assertIn("resolved_model_version", call_fields)
        self.assertIn("deployment_fallback_chain", call_fields)
        self.assertIn("fallback_action", call_fields)
        self.assertIn("state_hash", call_fields)

    def test_policy_has_api_access_control(self):
        policy = self.load("decision_policy")
        policy_fields = {field["fieldname"] for field in policy["fields"]}
        self.assertIn("allow_api_access", policy_fields)
        self.assertIn("definition_json", policy_fields)
        self.assertIn("fingerprint", policy_fields)
        self.assertIn("current_version", policy_fields)

    def test_agent_has_decision_bindings(self):
        agent = self.load("agent")
        fields = {field["fieldname"] for field in agent["fields"]}
        self.assertIn("decision_bindings", fields)


if __name__ == "__main__":
    unittest.main()
