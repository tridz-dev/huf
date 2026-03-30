# Copyright (c) 2025, Huf and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class AgentKnowledgeOverride(Document):
	"""Override vector store profile for specific agent-knowledge source pairs."""
	
	def validate(self):
		"""Ensure unique override per agent-knowledge source pair."""
		self._validate_unique_override()
	
	def _validate_unique_override(self):
		"""Check for existing override."""
		existing = frappe.db.exists(
			"Agent Knowledge Override",
			{
				"agent": self.agent,
				"knowledge_source": self.knowledge_source,
				"name": ("!=", self.name)
			}
		)
		if existing:
			frappe.throw(
				f"Override already exists for Agent {self.agent} and Knowledge Source {self.knowledge_source}"
			)
