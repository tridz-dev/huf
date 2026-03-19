# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

import re
import frappe
from frappe import _
from frappe.model.document import Document


class Skill(Document):
	def validate(self):
		self._validate_skill_name()

	def _validate_skill_name(self):
		"""Ensure skill_name follows slug format: lowercase, alphanumeric, hyphens."""
		pattern = r"^[a-z0-9]+(-[a-z0-9]+)*$"
		if not re.match(pattern, self.skill_name or ""):
			frappe.throw(
				_(
					"Skill Name must contain only lowercase letters, numbers, and hyphens "
					"(e.g. 'frappe-reporting', 'customer-onboarding'). Got: {0}"
				).format(self.skill_name),
				title=_("Invalid Skill Name"),
			)


@frappe.whitelist()
def get_skills(search=None, scope=None):
	"""Return active skills for selection UI."""
	filters = {"is_active": 1}
	if scope:
		filters["scope"] = scope

	fields = ["name", "skill_name", "display_name", "description", "scope", "version", "author"]

	if search:
		return frappe.get_all(
			"Skill",
			filters=filters,
			or_filters=[
				["display_name", "like", f"%{search}%"],
				["description", "like", f"%{search}%"],
				["skill_name", "like", f"%{search}%"],
			],
			fields=fields,
			order_by="display_name asc",
			limit=50,
		)

	return frappe.get_all(
		"Skill",
		filters=filters,
		fields=fields,
		order_by="display_name asc",
		limit=100,
	)


@frappe.whitelist()
def get_skill_content(skill_name):
	"""Return full content of a skill (used by load_skill tool)."""
	skill = frappe.get_doc("Skill", skill_name)
	if not skill.is_active:
		return {"error": f"Skill '{skill_name}' is not active."}

	return {
		"skill_name": skill.skill_name,
		"display_name": skill.display_name,
		"description": skill.description,
		"content": skill.content or "",
		"version": skill.version,
		"author": skill.author,
	}
