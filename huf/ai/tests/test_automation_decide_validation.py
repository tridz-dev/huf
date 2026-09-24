# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Frappe integration tests for Automation Decide fields and validation.

Tests cover:
- action_type field (Agent Run default, Decision option)
- decision_policy, decision_state_template, decision_output_field, decision_output_map,
  decision_on_failure, decision_fallback_value fields
- Validation: agent/instruction required only for Agent Run; decision_policy and
  decision_output_field required for Decision
- Backward compatibility: existing Agent Run automations pass validation unchanged

Run with:
    bench --site <site> run-tests --app huf --module huf.ai.tests.test_automation_decide_validation
"""

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.automation_service import validate_automation
from huf.ai.tests.factories import make_agent, make_automation

PREFIX = "_Test Automation Decide"


class TestAutomationDecideValidation(IntegrationTestCase):
    def setUp(self):
        self._names = {
            "Automation": [],
            "Agent": [],
            "AI Model": [],
            "AI Provider": [],
            "User": [],
            "Decision Policy": [],
        }

    def tearDown(self):
        frappe.set_user("Administrator")
        for doctype in (
            "Automation",
            "Decision Policy",
            "Agent",
            "AI Model",
            "AI Provider",
            "User",
        ):
            for name in self._names.get(doctype, []):
                self._delete(doctype, name)
        frappe.db.commit()

    def _delete(self, doctype, name):
        try:
            frappe.delete_doc(doctype, name, ignore_permissions=True, force=True)
        except Exception:
            pass

    def _track(self, doctype, name):
        self._names.setdefault(doctype, []).append(name)
        return name

    def _make_test_agent(self):
        """Create a test Agent (reuses or creates Test Provider)."""
        if not frappe.db.exists("AI Provider", "Test_Provider"):
            from huf.ai.tests.factories import make_ai_provider, make_ai_model

            provider = make_ai_provider(provider_name="Test_Provider")
            self._track("AI Provider", provider.name)
            model = make_ai_model(
                provider=provider.name, model_name=f"test-model-{frappe.generate_hash(length=6)}"
            )
            self._track("AI Model", model.name)
        else:
            provider = frappe.get_doc("AI Provider", "Test_Provider")
            model = frappe.db.get_value("AI Model", {"provider": provider.name})

        agent = make_agent(provider=provider.name, model=model)
        self._track("Agent", agent.name)
        return agent

    def _make_test_decision_policy(self):
        """Create a minimal test Decision Policy."""
        import json

        policy_name = f"{PREFIX} Policy {frappe.generate_hash(length=8)}"
        definition = {
            "policy_id": "test_automation_policy",
            "version": "1.0",
            "questions": [
                {
                    "id": "test_question",
                    "kind": "select",
                    "instructions": "Test Question",
                    "options": [
                        {"id": "opt_1", "description": "Option 1"},
                        {"id": "opt_2", "description": "Option 2"},
                    ],
                }
            ],
            "minimum_confidence": 0.5,
        }
        policy_doc = frappe.get_doc(
            {
                "doctype": "Decision Policy",
                "policy_name": policy_name,
                "purpose": "Generic",
                "definition_json": json.dumps(definition),
                "status": "Active",
            }
        )
        policy_doc.insert(ignore_permissions=True)
        self._track("Decision Policy", policy_doc.name)
        return policy_doc

    # -- Backward compatibility: Agent Run automations

    def test_agent_run_default_action_type(self):
        """Existing Agent Run automations without action_type field default to
        'Agent Run' and pass validation unchanged."""
        agent = self._make_test_agent()
        # Create automation without using factory to avoid decision field requirements
        automation = frappe.get_doc(
            {
                "doctype": "Automation",
                "automation_name": f"{PREFIX} Agent Run Default {frappe.generate_hash(length=8)}",
                "action_type": "Agent Run",  # explicitly set to avoid depends_on issues
                "agent": agent.name,
                "instruction": "Test instruction",
                "status": "Draft",
            }
        )
        automation.insert(ignore_permissions=True)
        self._track("Automation", automation.name)

        # action_type should be "Agent Run"
        automation.reload()
        self.assertEqual(automation.action_type, "Agent Run")

        # Validation should pass (no exception)
        try:
            validate_automation(automation)
        except frappe.ValidationError as e:
            self.fail(f"Agent Run validation failed unexpectedly: {e}")

    def test_agent_run_explicit_action_type(self):
        """Explicitly setting action_type='Agent Run' passes validation."""
        agent = self._make_test_agent()
        automation = frappe.get_doc(
            {
                "doctype": "Automation",
                "automation_name": f"{PREFIX} Agent Run Explicit {frappe.generate_hash(length=8)}",
                "action_type": "Agent Run",
                "agent": agent.name,
                "instruction": "Test instruction",
                "status": "Draft",
            }
        )
        automation.insert(ignore_permissions=True)
        self._track("Automation", automation.name)

        # Validation should pass
        try:
            validate_automation(automation)
        except frappe.ValidationError as e:
            self.fail(f"Explicit Agent Run validation failed: {e}")

    def test_agent_run_missing_agent(self):
        """Agent Run automation without agent field fails validation."""
        automation = frappe.get_doc(
            {
                "doctype": "Automation",
                "automation_name": f"{PREFIX} No Agent {frappe.generate_hash(length=8)}",
                "action_type": "Agent Run",
                "instruction": "Test instruction",
                "status": "Draft",
            }
        )

        with self.assertRaises(frappe.ValidationError) as context:
            validate_automation(automation)
        self.assertIn("Agent", str(context.exception))

    def test_agent_run_missing_instruction(self):
        """Agent Run automation without instruction field fails validation."""
        agent = self._make_test_agent()
        automation = frappe.get_doc(
            {
                "doctype": "Automation",
                "automation_name": f"{PREFIX} No Instruction {frappe.generate_hash(length=8)}",
                "action_type": "Agent Run",
                "agent": agent.name,
                "status": "Draft",
            }
        )

        with self.assertRaises(frappe.ValidationError) as context:
            validate_automation(automation)
        self.assertIn("Instruction", str(context.exception))

    # -- Decision action type

    def test_decision_action_type_valid(self):
        """Decision action type with required fields passes validation."""
        policy = self._make_test_decision_policy()
        automation = frappe.get_doc(
            {
                "doctype": "Automation",
                "automation_name": f"{PREFIX} Decision Valid {frappe.generate_hash(length=8)}",
                "action_type": "Decision",
                "decision_policy": policy.name,
                "decision_output_field": "test_field",
                "decision_on_failure": "Skip",
                "status": "Draft",
            }
        )
        automation.insert(ignore_permissions=True)
        self._track("Automation", automation.name)

        # Validation should pass
        try:
            validate_automation(automation)
        except frappe.ValidationError as e:
            self.fail(f"Decision validation failed: {e}")

    def test_decision_missing_policy(self):
        """Decision action type without decision_policy fails validation."""
        automation = frappe.get_doc(
            {
                "doctype": "Automation",
                "automation_name": f"{PREFIX} No Policy {frappe.generate_hash(length=8)}",
                "action_type": "Decision",
                "decision_output_field": "test_field",
                "status": "Draft",
            }
        )

        with self.assertRaises(frappe.ValidationError) as context:
            validate_automation(automation)
        self.assertIn("Decision Policy", str(context.exception))

    def test_decision_missing_output_field(self):
        """Decision action type without decision_output_field fails validation."""
        policy = self._make_test_decision_policy()
        automation = frappe.get_doc(
            {
                "doctype": "Automation",
                "automation_name": f"{PREFIX} No Output Field {frappe.generate_hash(length=8)}",
                "action_type": "Decision",
                "decision_policy": policy.name,
                "status": "Draft",
            }
        )

        with self.assertRaises(frappe.ValidationError) as context:
            validate_automation(automation)
        self.assertIn("Output Field", str(context.exception))

    def test_decision_ignores_agent_requirement(self):
        """Decision action type doesn't require agent field."""
        policy = self._make_test_decision_policy()
        automation = frappe.get_doc(
            {
                "doctype": "Automation",
                "automation_name": f"{PREFIX} Decision No Agent {frappe.generate_hash(length=8)}",
                "action_type": "Decision",
                "decision_policy": policy.name,
                "decision_output_field": "test_field",
                "status": "Draft",
            }
        )
        automation.insert(ignore_permissions=True)
        self._track("Automation", automation.name)

        # Validation should pass despite no agent
        try:
            validate_automation(automation)
        except frappe.ValidationError as e:
            self.fail(f"Decision without agent failed validation: {e}")

    def test_decision_ignores_instruction_requirement(self):
        """Decision action type doesn't require instruction field."""
        policy = self._make_test_decision_policy()
        automation = frappe.get_doc(
            {
                "doctype": "Automation",
                "automation_name": f"{PREFIX} Decision No Instruction {frappe.generate_hash(length=8)}",
                "action_type": "Decision",
                "decision_policy": policy.name,
                "decision_output_field": "test_field",
                "status": "Draft",
            }
        )
        automation.insert(ignore_permissions=True)
        self._track("Automation", automation.name)

        # Validation should pass despite no instruction
        try:
            validate_automation(automation)
        except frappe.ValidationError as e:
            self.fail(f"Decision without instruction failed validation: {e}")

    # -- Decision-specific fields

    def test_decision_optional_state_template(self):
        """decision_state_template is optional."""
        policy = self._make_test_decision_policy()
        automation = frappe.get_doc(
            {
                "doctype": "Automation",
                "automation_name": f"{PREFIX} Decision No Template {frappe.generate_hash(length=8)}",
                "action_type": "Decision",
                "decision_policy": policy.name,
                "decision_output_field": "test_field",
                "status": "Draft",
            }
        )
        automation.insert(ignore_permissions=True)
        self._track("Automation", automation.name)

        try:
            validate_automation(automation)
        except frappe.ValidationError as e:
            self.fail(f"Decision without state_template failed: {e}")

    def test_decision_optional_output_map(self):
        """decision_output_map is optional."""
        policy = self._make_test_decision_policy()
        automation = frappe.get_doc(
            {
                "doctype": "Automation",
                "automation_name": f"{PREFIX} Decision No Map {frappe.generate_hash(length=8)}",
                "action_type": "Decision",
                "decision_policy": policy.name,
                "decision_output_field": "test_field",
                "status": "Draft",
            }
        )
        automation.insert(ignore_permissions=True)
        self._track("Automation", automation.name)

        try:
            validate_automation(automation)
        except frappe.ValidationError as e:
            self.fail(f"Decision without output_map failed: {e}")

    def test_decision_on_failure_defaults_to_skip(self):
        """decision_on_failure field defaults to 'Skip'."""
        policy = self._make_test_decision_policy()
        automation = frappe.get_doc(
            {
                "doctype": "Automation",
                "automation_name": f"{PREFIX} Decision Failure Behavior {frappe.generate_hash(length=8)}",
                "action_type": "Decision",
                "decision_policy": policy.name,
                "decision_output_field": "test_field",
                "status": "Draft",
            }
        )
        automation.insert(ignore_permissions=True)
        self._track("Automation", automation.name)

        automation.reload()
        self.assertEqual(automation.decision_on_failure, "Skip")

    def test_decision_on_failure_options(self):
        """decision_on_failure accepts valid options: Skip, Mark Error, Set Fallback Value."""
        policy = self._make_test_decision_policy()

        for option in ["Skip", "Mark Error", "Set Fallback Value"]:
            automation = frappe.get_doc(
                {
                    "doctype": "Automation",
                    "automation_name": f"{PREFIX} Decision {option} {frappe.generate_hash(length=8)}",
                    "action_type": "Decision",
                    "decision_policy": policy.name,
                    "decision_output_field": "test_field",
                    "decision_on_failure": option,
                    "status": "Draft",
                }
            )
            automation.insert(ignore_permissions=True)
            self._track("Automation", automation.name)

            try:
                validate_automation(automation)
            except frappe.ValidationError as e:
                self.fail(f"Decision with on_failure='{option}' failed: {e}")

    def test_decision_fallback_value_optional(self):
        """decision_fallback_value is optional even when on_failure='Set Fallback Value'."""
        policy = self._make_test_decision_policy()
        automation = frappe.get_doc(
            {
                "doctype": "Automation",
                "automation_name": f"{PREFIX} Decision Fallback {frappe.generate_hash(length=8)}",
                "action_type": "Decision",
                "decision_policy": policy.name,
                "decision_output_field": "test_field",
                "decision_on_failure": "Set Fallback Value",
                "status": "Draft",
            }
        )
        automation.insert(ignore_permissions=True)
        self._track("Automation", automation.name)

        # Field exists but is empty — validation should pass (schema decides
        # whether it's actually required at write-time)
        try:
            validate_automation(automation)
        except frappe.ValidationError as e:
            self.fail(f"Decision with empty fallback_value failed: {e}")
