# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# See license.txt

import frappe

from huf.tests.utils import HufTestSuite


class TestAgentTrigger(HufTestSuite):
	def _make_trigger(self, **kwargs):
		doc = {
			"doctype": "Agent Trigger",
			"trigger_name": "_Test Trigger",
			"agent": self.bootstrap.agent.name,
		}
		doc.update(kwargs)
		return frappe.get_doc(doc).insert(ignore_permissions=True)

	def test_create_doc_event_trigger(self):
		trigger = self._make_trigger(
			trigger_name="_Test Doc Event Trigger",
			trigger_type="Doc Event",
			reference_doctype="ToDo",
			doc_event="after_insert",
		)

		# autoname is field:trigger_name
		self.assertEqual(trigger.name, "_Test Doc Event Trigger")
		self.assertEqual(trigger.agent, self.bootstrap.agent.name)
		self.assertEqual(trigger.trigger_type, "Doc Event")

	def test_agent_required(self):
		with self.assertRaises(frappe.MandatoryError):
			frappe.get_doc({
				"doctype": "Agent Trigger",
				"trigger_name": "_Test Trigger No Agent",
			}).insert(ignore_permissions=True)

	def test_doc_event_requires_reference_doctype_and_event(self):
		with self.assertRaises(frappe.ValidationError):
			self._make_trigger(
				trigger_name="_Test Invalid Doc Event",
				trigger_type="Doc Event",
			)

	def test_schedule_requires_interval(self):
		with self.assertRaises(frappe.ValidationError):
			self._make_trigger(
				trigger_name="_Test Invalid Schedule",
				trigger_type="Schedule",
			)

	def test_valid_condition_accepted(self):
		trigger = self._make_trigger(
			trigger_name="_Test Condition Trigger",
			trigger_type="Doc Event",
			reference_doctype="ToDo",
			doc_event="after_insert",
			condition="doc.status == 'Open'",
		)

		self.assertEqual(trigger.condition, "doc.status == 'Open'")

	def test_invalid_condition_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			self._make_trigger(
				trigger_name="_Test Bad Condition",
				trigger_type="Doc Event",
				reference_doctype="ToDo",
				doc_event="after_insert",
				condition="doc.status ==",
			)
