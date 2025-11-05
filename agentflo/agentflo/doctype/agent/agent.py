# Copyright (c) 2025, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from agentflo.ai.agent_hooks import clear_doc_event_agents_cache
from frappe.utils.safe_exec import get_safe_globals, safe_eval


def get_context(doc):
	return {"doc": frappe._dict(doc), **get_safe_globals()}

class Agent(Document):
	def validate(self):
		if not self.instructions:
			frappe.throw(_("Please provide an instruction for this AI Agent."))
		if self.is_scheduled and self.is_doc_event:
			frappe.throw(_("An Agent cannot be both Scheduled and Doc Event based. Please choose only one."))
		self.validate_condition()
		if self.allow_chat == 1 and self.persist_conversation == 0:
			frappe.throw(_("An agent cannot be allowed in Agent Chat when persistent conversation is off."))



	def get_indicator(doc):
		if doc.disabled:
			return _("Disabled"), "red", "disabled,=,Yes"
		else:
			return _("Enabled"), "green", "disabled,=,No"

	def on_update(self):
		clear_doc_event_agents_cache()  

	def on_trash(self):
		clear_doc_event_agents_cache()
	
	def validate_condition(self):
		if not self.condition:
			return

		temp_doc = frappe.new_doc(self.reference_doctype)
		try:
			frappe.safe_eval(self.condition, None, get_context(temp_doc.as_dict()))
		except Exception:
			frappe.throw(_("The Condition '{0}' is invalid").format(self.condition))
	
	def before_export(self, doc_dict):
		"""
		Hook called before export - clean up sensitive/unnecessary data.
		"""
		# Remove conversation history, run logs, execution data
		doc_dict.pop("last_run", None)
		doc_dict.pop("total_run", None)
		doc_dict.pop("last_execution", None)
		doc_dict.pop("next_execution", None)
		
		# Ensure is_standard is set appropriately
		# This will be handled by the export utility
	
	@frappe.whitelist()
	def export_agent(self):
		"""
		Export this agent.
		
		Returns:
			Dictionary containing agent data and dependencies
		"""
		from agentflo.export import export_agent
		
		# Check permissions
		if not frappe.has_permission("Agent", "read", self.name):
			frappe.throw(_("Permission denied"), frappe.PermissionError)
		
		return export_agent(self.name, include_dependencies=True)
	
	@staticmethod
	@frappe.whitelist()
	def import_agent(agent_data, import_mode="merge"):
		"""
		Import an agent from structured dictionary.
		
		Args:
			agent_data: Dictionary containing agent data and dependencies
			import_mode: How to handle conflicts (merge/skip/overwrite)
			
		Returns:
			Name of the imported agent
		"""
		from agentflo.export import import_agent
		
		# Check permissions
		if not frappe.has_permission("Agent", "create"):
			frappe.throw(_("Permission denied"), frappe.PermissionError)
		
		return import_agent(agent_data, import_mode)
	
	@staticmethod
	@frappe.whitelist()
	def import_agent_from_file(file_path, import_mode="merge"):
		"""
		Import an agent from JSON file.
		
		Args:
			file_path: Path to the JSON file
			import_mode: How to handle conflicts (merge/skip/overwrite)
			
		Returns:
			Name of the imported agent
		"""
		from agentflo.export import import_agent_from_file
		
		# Check permissions
		if not frappe.has_permission("Agent", "create"):
			frappe.throw(_("Permission denied"), frappe.PermissionError)
		
		return import_agent_from_file(file_path, import_mode)
		