"""Schema-level checks for the PR2 canonical identity data model."""
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
        self.assertIn("provider", deployment_fields)
        self.assertIn("provider_model_id", deployment_fields)
        self.assertNotIn("provider_model_id", model_fields)

    def test_provider_credentials_and_adapter_boundary(self):
        provider = self.load("decision_provider")
        fields = {field["fieldname"]: field for field in provider["fields"]}
        self.assertEqual(fields["api_key"]["fieldtype"], "Password")
        self.assertIn("adapter_id", fields)
        self.assertNotIn("import_path", fields)

    def test_deployment_capabilities_are_explicit(self):
        deployment = self.load("decision_deployment")
        fields = {field["fieldname"] for field in deployment["fields"]}
        self.assertTrue({"supports_select", "supports_judge", "supports_score"} <= fields)
        self.assertIn("input_modalities", fields)


if __name__ == "__main__":
    unittest.main()
