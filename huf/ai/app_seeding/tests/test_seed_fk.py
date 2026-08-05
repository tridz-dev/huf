"""
Tests for seed Link-field reference validation.
Run with:
    bench --site hufai.localhost run-tests --app huf --module huf.ai.app_seeding.tests.test_seed_fk
"""
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

import frappe

from huf.ai.app_seeding.loaders import _upsert_doc, _validate_link_refs
from huf.ai.app_seeding.seeder import seed_app, seed_all_apps


@unittest.skip("quarantined pending RegressionCI triage - see Tracks/RegressionCI/CONTEXT.md Quarantine backlog")
class TestSeedFKValidation(unittest.TestCase):
    """Acceptance tests for seed foreign-reference validation."""

    def setUp(self):
        self.test_app = "test_seed_fk_app"
        self.huf_dir = Path(tempfile.mkdtemp()) / "huf"
        self.huf_dir.mkdir()

        # Unique suffix to avoid collisions across test runs
        self.suffix = frappe.generate_hash(length=8)
        self.valid_provider = f"FK-Valid-Provider-{self.suffix}"
        self.valid_model = f"FK-Valid-Model-{self.suffix}"
        self.invalid_provider = f"FK-Invalid-Provider-{self.suffix}"
        self.invalid_model = f"FK-Invalid-Model-{self.suffix}"

        # Create a real AI Provider and AI Model for valid seeds
        self.provider_doc = frappe.get_doc({
            "doctype": "AI Provider",
            "provider_name": self.valid_provider,
            "api_key": "test-key",
        }).insert(ignore_permissions=True)

        self.model_doc = frappe.get_doc({
            "doctype": "AI Model",
            "model_name": self.valid_model,
            "provider": self.valid_provider,
        }).insert(ignore_permissions=True)

        self._created_agents = []

    def tearDown(self):
        # Remove temp seed directory
        shutil.rmtree(self.huf_dir.parent, ignore_errors=True)

        # Delete agents created by tests
        for agent_name in self._created_agents:
            try:
                frappe.db.sql("DELETE FROM `tabAgent` WHERE agent_name = %s", agent_name)
                frappe.db.sql("DELETE FROM `tabAgent Tool` WHERE parent = %s", agent_name)
                frappe.db.sql("DELETE FROM `tabAgent Knowledge` WHERE parent = %s", agent_name)
                frappe.db.sql("DELETE FROM `tabAgent User` WHERE parent = %s", agent_name)
                frappe.db.sql("DELETE FROM `tabAgent Role` WHERE parent = %s", agent_name)
            except Exception:
                pass

        # Delete model and provider
        try:
            frappe.db.sql("DELETE FROM `tabAI Model` WHERE name = %s", self.model_doc.name)
            frappe.db.sql("DELETE FROM `tabAI Provider` WHERE name = %s", self.provider_doc.name)
        except Exception:
            pass

        frappe.db.commit()

    def _write_seed(self, folder, filename, payload):
        target_dir = self.huf_dir / folder
        target_dir.mkdir(exist_ok=True)
        target_path = target_dir / filename
        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(payload, f)
        return target_path

    def _agent_payload(self, agent_name, provider, model, tools=None, knowledge=None,
                        allowed_users=None, allowed_roles=None):
        payload = {
            "agent_name": agent_name,
            "provider": provider,
            "model": model,
            "instructions": "Test instructions",
        }
        if tools is not None:
            payload["tools"] = tools
        if knowledge is not None:
            payload["knowledge"] = knowledge
        if allowed_users is not None:
            payload["allowed_users"] = allowed_users
        if allowed_roles is not None:
            payload["allowed_roles"] = allowed_roles
        return payload

    def test_invalid_agent_missing_provider_model_is_skipped(self):
        """AC1: a seed referencing a nonexistent AI Provider/AI Model is NOT inserted,
        and the log/summary names the app, file, and missing references."""
        agent_name = f"FK-Invalid-Agent-{self.suffix}"
        self._write_seed(
            "agents",
            "invalid_agent.json",
            self._agent_payload(agent_name, self.invalid_provider, self.invalid_model),
        )

        result = seed_app(self.test_app, self.huf_dir)

        self.assertFalse(
            frappe.db.exists("Agent", agent_name),
            "Invalid agent seed should not be inserted",
        )
        self.assertEqual(result.seeded, 0)
        self.assertEqual(result.skipped, 1)
        self.assertEqual(len(result.skipped_records), 1)

        skipped = result.skipped_records[0]
        self.assertEqual(skipped["app"], self.test_app)
        self.assertEqual(skipped["file"], "huf/agents/invalid_agent.json")
        self.assertEqual(skipped["record"], agent_name)
        self.assertIn("Missing reference(s):", skipped["error"])

        missing = skipped["missing_refs"]
        self.assertIn(f"AI Provider:{self.invalid_provider}", missing)
        self.assertIn(f"AI Model:{self.invalid_model}", missing)

    def test_valid_agent_seed_loads(self):
        """AC2: valid seeds in the same batch still load."""
        agent_name = f"FK-Valid-Agent-{self.suffix}"
        self._write_seed(
            "agents",
            "valid_agent.json",
            self._agent_payload(agent_name, self.valid_provider, self.valid_model),
        )
        self._created_agents.append(agent_name)

        result = seed_app(self.test_app, self.huf_dir)

        self.assertTrue(
            frappe.db.exists("Agent", agent_name),
            "Valid agent seed should be inserted",
        )
        self.assertEqual(result.seeded, 1)
        self.assertEqual(result.skipped, 0)
        self.assertEqual(len(result.skipped_records), 0)

    def test_seed_app_completes_with_mixed_valid_invalid(self):
        """AC3: migrate (seed_all) completes successfully despite invalid seeds,
        and valid seeds still load while invalid ones are skipped."""
        valid_agent = f"FK-Mixed-Valid-Agent-{self.suffix}"
        invalid_agent = f"FK-Mixed-Invalid-Agent-{self.suffix}"
        self._created_agents.append(valid_agent)

        self._write_seed(
            "agents",
            "valid_agent.json",
            self._agent_payload(valid_agent, self.valid_provider, self.valid_model),
        )
        self._write_seed(
            "agents",
            "invalid_agent.json",
            self._agent_payload(invalid_agent, self.invalid_provider, self.invalid_model),
        )

        # seed_app must not raise
        result = seed_app(self.test_app, self.huf_dir)

        self.assertTrue(
            frappe.db.exists("Agent", valid_agent),
            "Valid agent should be inserted even when mixed with invalid seeds",
        )
        self.assertFalse(
            frappe.db.exists("Agent", invalid_agent),
            "Invalid agent should be skipped",
        )
        self.assertEqual(result.seeded, 1)
        self.assertEqual(result.skipped, 1)
        self.assertEqual(len(result.skipped_records), 1)

    def test_invalid_child_table_reference_is_skipped(self):
        """Child-table Link references are also validated (agent tools)."""
        agent_name = f"FK-Child-Table-Agent-{self.suffix}"
        self._write_seed(
            "agents",
            "child_table_agent.json",
            self._agent_payload(
                agent_name,
                self.valid_provider,
                self.valid_model,
                tools=[f"FK-Missing-Tool-{self.suffix}"],
            ),
        )

        result = seed_app(self.test_app, self.huf_dir)

        self.assertFalse(frappe.db.exists("Agent", agent_name))
        self.assertEqual(result.skipped, 1)
        skipped = result.skipped_records[0]
        self.assertTrue(
            any("Agent Tool Function" in ref and f"FK-Missing-Tool-{self.suffix}" in ref for ref in skipped["missing_refs"]),
            "Missing child-table tool reference should be reported",
        )

    def test_loader_returns_structured_missing_refs_payload(self):
        """AC5: loaders return missing refs as a structured payload;
        seeder does not parse error strings."""
        agent_name = f"FK-Structured-Agent-{self.suffix}"
        data = {
            "agent_name": agent_name,
            "provider": self.invalid_provider,
            "model": self.invalid_model,
            "instructions": "test",
        }

        ok, error = _upsert_doc("Agent", "agent_name", data, self.test_app, "huf/agents/test.json")

        self.assertFalse(ok)
        self.assertIsInstance(error, dict)
        self.assertEqual(error.get("reason"), "missing_refs")
        self.assertIn(f"AI Provider:{self.invalid_provider}", error["missing_refs"])
        self.assertIn(f"AI Model:{self.invalid_model}", error["missing_refs"])

    def test_table_multiselect_references_are_validated(self):
        """AC6: Table MultiSelect fields (Agent.allowed_users, Agent.allowed_roles)
        are validated and missing values are reported."""
        agent_name = f"FK-MultiSelect-Agent-{self.suffix}"
        self._write_seed(
            "agents",
            "multiselect_agent.json",
            self._agent_payload(
                agent_name,
                self.valid_provider,
                self.valid_model,
                allowed_users=[f"FK-Missing-User-{self.suffix}"],
                allowed_roles=[f"FK-Missing-Role-{self.suffix}"],
            ),
        )

        result = seed_app(self.test_app, self.huf_dir)

        self.assertFalse(frappe.db.exists("Agent", agent_name))
        self.assertEqual(result.skipped, 1)
        skipped = result.skipped_records[0]
        missing = skipped["missing_refs"]
        self.assertTrue(
            any("User" in ref and f"FK-Missing-User-{self.suffix}" in ref for ref in missing),
            "Missing allowed_users reference should be reported",
        )
        self.assertTrue(
            any("Role" in ref and f"FK-Missing-Role-{self.suffix}" in ref for ref in missing),
            "Missing allowed_roles reference should be reported",
        )

    def test_dynamic_link_references_are_validated(self):
        """AC6: Dynamic Link fields are validated and missing values are reported.
        Uses Agent Context Artifact schema because no seeded DocType currently
        carries a Dynamic Link field."""
        missing = _validate_link_refs("Agent Context Artifact", {
            "artifact_type": "JSON",
            "reference_doctype": "Agent",
            "reference_name": f"FK-Missing-Agent-{self.suffix}",
        })

        self.assertTrue(
            any("Agent" in ref and f"FK-Missing-Agent-{self.suffix}" in ref for ref in missing),
            "Missing Dynamic Link reference should be reported",
        )

    def test_migrate_emits_warning_logs_for_skipped_records(self):
        """AC7: every skipped record produces a WARNING-level structured log during
        migrate naming app, file, record, and missing refs."""
        from huf.install import _log_seed_results

        agent_name = f"FK-Logged-Agent-{self.suffix}"
        self._write_seed(
            "agents",
            "logged_agent.json",
            self._agent_payload(agent_name, self.invalid_provider, self.invalid_model),
        )
        result = seed_app(self.test_app, self.huf_dir)

        logger = MagicMock()
        _log_seed_results([result], logger)

        warning_calls = [c for c in logger.warning.call_args_list]
        self.assertTrue(warning_calls, "At least one warning log should be emitted")

        per_record_logged = False
        for call in warning_calls:
            payload = json.loads(call.args[0])
            if payload.get("record") == agent_name:
                per_record_logged = True
                self.assertEqual(payload["app"], self.test_app)
                self.assertEqual(payload["file"], "huf/agents/logged_agent.json")
                self.assertIn(f"AI Provider:{self.invalid_provider}", payload["missing_refs"])
                self.assertIn(f"AI Model:{self.invalid_model}", payload["missing_refs"])

        self.assertTrue(per_record_logged, "Per-record warning log should name app, file, record, and missing refs")

    def test_sync_app_seeds_endpoint_returns_skipped_record_summaries(self):
        """AC8: the Sync App Seeds backend endpoint returns per-record missing-ref
        summaries so the Desk dialog can display them."""
        agent_name = f"FK-UI-Agent-{self.suffix}"
        self._write_seed(
            "agents",
            "ui_agent.json",
            self._agent_payload(agent_name, self.invalid_provider, self.invalid_model),
        )

        # Patch scanner to discover our temp test app directory
        from huf.ai.app_seeding import seeder as seeder_module
        original_find_seed_dirs = seeder_module.find_seed_dirs
        seeder_module.find_seed_dirs = lambda: {self.test_app: self.huf_dir}
        try:
            frappe.set_user("Administrator")
            response = seed_all_apps()
        finally:
            seeder_module.find_seed_dirs = original_find_seed_dirs

        self.assertEqual(response["status"], "success")
        results = response.get("results", [])
        self.assertTrue(results, "Response should include per-app results")

        matching = [
            rec for res in results
            for rec in res.get("skipped_records", [])
            if rec.get("record") == agent_name
        ]
        self.assertTrue(matching, "Skipped record summary should be returned")
        rec = matching[0]
        self.assertIn(f"AI Provider:{self.invalid_provider}", rec["missing_refs"])
        self.assertIn(f"AI Model:{self.invalid_model}", rec["missing_refs"])


if __name__ == "__main__":
    unittest.main()
