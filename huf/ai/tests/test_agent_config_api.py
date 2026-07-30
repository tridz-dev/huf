import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.agent_config_api import get_agent_section, update_agent_section


class TestAgentConfigAPI(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		model = frappe.get_all("AI Model", fields=["name", "provider"], limit=1)
		if not model:
			self.skipTest("no AI Model records on this site")
		self.agent = frappe.get_doc(
			{
				"doctype": "Agent",
				"agent_name": f"section-api-{frappe.generate_hash(length=8)}",
				"provider": model[0].provider,
				"model": model[0].name,
				"instructions": "Keep this instruction",
				"allow_chat": 0,
				"persist_conversation": 1,
			}
		).insert(ignore_permissions=True)

	def tearDown(self):
		if getattr(self, "agent", None) and frappe.db.exists("Agent", self.agent.name):
			frappe.delete_doc("Agent", self.agent.name, ignore_permissions=True, force=True)

	def test_section_read_is_narrow(self):
		result = get_agent_section(self.agent.name, "general")

		self.assertEqual(result["name"], self.agent.name)
		self.assertIn("instructions", result["values"])
		self.assertNotIn("agent_tool", result["values"])
		self.assertNotIn("agent_knowledge", result["values"])

	def test_section_update_preserves_other_sections(self):
		before = get_agent_section(self.agent.name, "behavior")
		result = update_agent_section(
			self.agent.name,
			"behavior",
			{"allow_chat": 1, "persist_conversation": 1},
			before["modified"],
		)

		self.assertEqual(result["values"]["allow_chat"], 1)
		self.assertEqual(
			frappe.db.get_value("Agent", self.agent.name, "instructions"),
			"Keep this instruction",
		)

	def test_stale_revision_is_rejected(self):
		before = get_agent_section(self.agent.name, "behavior")
		frappe.db.set_value("Agent", self.agent.name, "description", "changed elsewhere")

		with self.assertRaises(frappe.TimestampMismatchError):
			update_agent_section(
				self.agent.name,
				"behavior",
				{"persist_conversation": 1},
				before["modified"],
			)

	def test_cross_section_field_is_rejected(self):
		before = get_agent_section(self.agent.name, "behavior")

		with self.assertRaises(frappe.ValidationError):
			update_agent_section(
				self.agent.name,
				"behavior",
				{"instructions": "not a behavior field"},
				before["modified"],
			)

	def test_general_section_can_rename_agent(self):
		before = get_agent_section(self.agent.name, "general")
		new_name = f"{self.agent.name}-renamed"

		result = update_agent_section(
			self.agent.name,
			"general",
			{"agent_name": new_name},
			before["modified"],
		)

		self.agent = frappe.get_doc("Agent", new_name)
		self.assertEqual(result["name"], new_name)
		self.assertEqual(self.agent.agent_name, new_name)
