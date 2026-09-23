"""
Tests for Decision Policy portability: export/import via app_seeding.
Run with:
    bench --site dr-activation.local run-tests --app huf --module huf.ai.app_seeding.tests.test_decision_policy_seed
"""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import frappe

from huf.ai.app_seeding.exporter import export_decision_policy_to_seed
from huf.ai.app_seeding.loaders import upsert_decision_policy, upsert_agent
from huf.ai.app_seeding.seeder import LOAD_ORDER, seed_app


class TestDecisionPolicySeed(unittest.TestCase):
    """Acceptance tests for T10.05: export/import Decision Policies with agents."""

    def setUp(self):
        self.test_app = "test_decision_policy_seed_app"
        self.huf_dir = Path(tempfile.mkdtemp()) / "huf"
        self.huf_dir.mkdir()

        self.suffix = frappe.generate_hash(length=8)
        self._created_policies = []
        self._created_agents = []

        # Minimal AI Provider/Model so Agent payloads can reference them like
        # every other agent seed test does.
        self.provider_name = f"DP-Provider-{self.suffix}"
        self.model_name = f"DP-Model-{self.suffix}"
        self.provider_doc = frappe.get_doc({
            "doctype": "AI Provider",
            "provider_name": self.provider_name,
            "api_key": "test-key",
        }).insert(ignore_permissions=True)
        self.model_doc = frappe.get_doc({
            "doctype": "AI Model",
            "model_name": self.model_name,
            "provider": self.provider_name,
        }).insert(ignore_permissions=True)

    def tearDown(self):
        shutil.rmtree(self.huf_dir.parent, ignore_errors=True)

        for agent_name in self._created_agents:
            try:
                frappe.db.sql("DELETE FROM `tabAgent Decision Binding` WHERE parent = %s", agent_name)
                frappe.db.sql("DELETE FROM `tabAgent` WHERE agent_name = %s", agent_name)
            except Exception:
                pass

        for policy_name in self._created_policies:
            try:
                frappe.db.sql("DELETE FROM `tabDecision Policy Version` WHERE policy = %s", policy_name)
                frappe.db.sql("DELETE FROM `tabDecision Policy` WHERE policy_name = %s", policy_name)
            except Exception:
                pass

        try:
            frappe.db.sql("DELETE FROM `tabAI Model` WHERE name = %s", self.model_doc.name)
            frappe.db.sql("DELETE FROM `tabAI Provider` WHERE name = %s", self.provider_doc.name)
        except Exception:
            pass

        frappe.db.commit()

    # -- helpers ----------------------------------------------------------

    def _definition(self, policy_id):
        return json.dumps({
            "policy_id": policy_id,
            "questions": [
                {
                    "id": "q1",
                    "kind": "judge",
                    "instructions": "Decide something for the test.",
                    "positive_criteria": "Looks right.",
                }
            ],
        })

    def _policy_payload(self, policy_name, purpose="Generic"):
        return {
            "policy_name": policy_name,
            "purpose": purpose,
            "description": "Seed test policy",
            "enabled": 1,
            "definition_json": self._definition(policy_name),
            "schema_version": "1.0",
        }

    def _make_local_policy(self, policy_name, mode="Advise"):
        """Create + publish a policy directly on this site (simulates a pre-existing
        target-site policy, not an imported one)."""
        doc = frappe.get_doc({
            "doctype": "Decision Policy",
            "policy_name": policy_name,
            "purpose": "Generic",
            "definition_json": self._definition(policy_name),
        }).insert(ignore_permissions=True)
        doc.publish_version()
        self._created_policies.append(policy_name)
        return doc

    def _write_seed(self, folder, filename, payload):
        target_dir = self.huf_dir / folder
        target_dir.mkdir(exist_ok=True)
        target_path = target_dir / filename
        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(payload, f)
        return target_path

    def _agent_payload(self, agent_name, decision_bindings=None):
        payload = {
            "agent_name": agent_name,
            "provider": self.provider_name,
            "model": self.model_name,
            "instructions": "Test instructions",
        }
        if decision_bindings is not None:
            payload["decision_bindings"] = decision_bindings
        return payload

    # -- LOAD_ORDER ---------------------------------------------------------

    def test_decision_policies_load_before_agents(self):
        keys = [key for key, _fn in LOAD_ORDER]
        self.assertIn("decision_policies", keys)
        self.assertIn("agents", keys)
        self.assertLess(
            keys.index("decision_policies"), keys.index("agents"),
            "decision_policies must load before agents so Agent.decision_bindings"
            " Link refs to Decision Policy resolve on import",
        )

    # -- export ---------------------------------------------------------

    def test_export_excludes_version_fingerprint_and_deployment_state(self):
        policy_name = f"DP-Export-{self.suffix}"
        doc = self._make_local_policy(policy_name)
        self.assertTrue(doc.current_version)
        self.assertTrue(doc.fingerprint)

        exported = export_decision_policy_to_seed(policy_name)

        self.assertEqual(exported["policy_name"], policy_name)
        self.assertIn("definition_json", exported)
        self.assertNotIn("current_version", exported)
        self.assertNotIn("fingerprint", exported)
        # Site/provenance bookkeeping fields never travel either.
        for field in ("name", "creation", "modified", "modified_by", "owner", "source_app", "source_file"):
            self.assertNotIn(field, exported)
        # Decision Policy has no deployment/key fields to begin with; assert the
        # exported payload never grows one.
        self.assertFalse(any("deployment" in k or "api_key" in k for k in exported))

    # -- import / upsert --------------------------------------------------

    def test_upsert_decision_policy_republishes_locally(self):
        policy_name = f"DP-Import-{self.suffix}"
        self._created_policies.append(policy_name)
        data = self._policy_payload(policy_name)

        ok, error = upsert_decision_policy(data, self.test_app, "huf/decision_policies/test.json")

        self.assertTrue(ok, error)
        self.assertTrue(frappe.db.exists("Decision Policy", policy_name))

        doc = frappe.get_doc("Decision Policy", policy_name)
        self.assertTrue(doc.current_version, "Import must publish a version, not just save the draft")
        self.assertTrue(doc.fingerprint)

        version = frappe.get_doc("Decision Policy Version", doc.current_version)
        self.assertEqual(version.status, "Published")

    def test_upsert_decision_policy_ignores_source_version_fingerprint(self):
        """Even if a hand-authored seed file carries current_version/fingerprint from
        the source site, the import never trusts them -- it republishes locally."""
        policy_name = f"DP-IgnoreFP-{self.suffix}"
        self._created_policies.append(policy_name)
        data = self._policy_payload(policy_name)
        data["current_version"] = "some-other-site_v99"
        data["fingerprint"] = "not-a-real-fingerprint"

        ok, error = upsert_decision_policy(data, self.test_app, "huf/decision_policies/test.json")

        self.assertTrue(ok, error)
        doc = frappe.get_doc("Decision Policy", policy_name)
        self.assertNotEqual(doc.current_version, "some-other-site_v99")
        self.assertNotEqual(doc.fingerprint, "not-a-real-fingerprint")

    def test_seed_app_seeds_policy_before_agent_and_link_resolves(self):
        policy_name = f"DP-SeedFlow-{self.suffix}"
        agent_name = f"DP-SeedFlow-Agent-{self.suffix}"
        self._created_policies.append(policy_name)
        self._created_agents.append(agent_name)

        self._write_seed("decision_policies", "policy.json", self._policy_payload(policy_name))
        self._write_seed(
            "agents",
            "agent.json",
            self._agent_payload(
                agent_name,
                decision_bindings=[{"surface": "Tool Selection", "policy": policy_name, "mode": "Enforce"}],
            ),
        )

        result = seed_app(self.test_app, self.huf_dir)

        self.assertTrue(frappe.db.exists("Decision Policy", policy_name))
        self.assertTrue(frappe.db.exists("Agent", agent_name))
        self.assertEqual(result.errors, [])

        agent = frappe.get_doc("Agent", agent_name)
        self.assertEqual(len(agent.decision_bindings), 1)
        self.assertEqual(agent.decision_bindings[0].policy, policy_name)

    # -- decision_bindings forced Off ------------------------------------

    def test_imported_binding_forced_off_when_not_already_enabled(self):
        policy_name = f"DP-ForceOff-{self.suffix}"
        agent_name = f"DP-ForceOff-Agent-{self.suffix}"
        self._make_local_policy(policy_name)
        self._created_agents.append(agent_name)

        data = self._agent_payload(
            agent_name,
            decision_bindings=[{"surface": "Model Routing", "policy": policy_name, "mode": "Enforce"}],
        )
        ok, error = upsert_agent(data, self.test_app, "huf/agents/test.json")

        self.assertTrue(ok, error)
        agent = frappe.get_doc("Agent", agent_name)
        self.assertEqual(len(agent.decision_bindings), 1)
        self.assertEqual(
            agent.decision_bindings[0].mode, "Off",
            "A binding with no pre-existing enabled match on the target must import as Off",
        )

    def test_imported_binding_kept_when_already_enabled_on_target(self):
        policy_name = f"DP-KeepEnabled-{self.suffix}"
        agent_name = f"DP-KeepEnabled-Agent-{self.suffix}"
        self._make_local_policy(policy_name)
        self._created_agents.append(agent_name)

        # Simulate a pre-existing target-site agent with this binding already enabled.
        existing = frappe.get_doc({
            "doctype": "Agent",
            "agent_name": agent_name,
            "provider": self.provider_name,
            "model": self.model_name,
            "instructions": "Test instructions",
            "decision_bindings": [
                {"surface": "Model Routing", "policy": policy_name, "mode": "Shadow", "enabled": 1}
            ],
        }).insert(ignore_permissions=True)
        self.assertEqual(existing.decision_bindings[0].mode, "Shadow")

        # Re-import (e.g. app update) with the same surface/policy pair but a
        # different mode from the source app.
        data = self._agent_payload(
            agent_name,
            decision_bindings=[{"surface": "Model Routing", "policy": policy_name, "mode": "Enforce"}],
        )
        ok, error = upsert_agent(data, self.test_app, "huf/agents/test.json")

        self.assertTrue(ok, error)
        agent = frappe.get_doc("Agent", agent_name)
        self.assertEqual(len(agent.decision_bindings), 1)
        self.assertEqual(
            agent.decision_bindings[0].mode, "Enforce",
            "A surface/policy pair already enabled on the target site is not forced to Off on re-import",
        )

    def test_imported_binding_forced_off_when_existing_disabled(self):
        """A same-surface/policy binding that exists but is mode=Off on the target
        does not count as 'already enabled' -- the import still forces Off."""
        policy_name = f"DP-DisabledExisting-{self.suffix}"
        agent_name = f"DP-DisabledExisting-Agent-{self.suffix}"
        self._make_local_policy(policy_name)
        self._created_agents.append(agent_name)

        frappe.get_doc({
            "doctype": "Agent",
            "agent_name": agent_name,
            "provider": self.provider_name,
            "model": self.model_name,
            "instructions": "Test instructions",
            "decision_bindings": [
                {"surface": "Model Routing", "policy": policy_name, "mode": "Off", "enabled": 1}
            ],
        }).insert(ignore_permissions=True)

        data = self._agent_payload(
            agent_name,
            decision_bindings=[{"surface": "Model Routing", "policy": policy_name, "mode": "Enforce"}],
        )
        ok, error = upsert_agent(data, self.test_app, "huf/agents/test.json")

        self.assertTrue(ok, error)
        agent = frappe.get_doc("Agent", agent_name)
        self.assertEqual(agent.decision_bindings[0].mode, "Off")


if __name__ == "__main__":
    unittest.main()
