# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

import re

import frappe
from frappe import _
from frappe.model.document import Document

_SLUG_MAX = 100


def slugify_skill_title(title: str | None) -> str:
	"""Lower-case snake_case slug of a title; falls back to ``skill``."""
	slug = re.sub(r"[^a-z0-9]+", "_", (title or "").lower()).strip("_")
	return slug[:_SLUG_MAX].strip("_") or "skill"


def make_unique_skill_name(title: str | None, exists) -> str:
	"""Derive a skill_name from ``title`` that ``exists(name)`` reports as free."""
	base = slugify_skill_title(title)
	candidate = base
	counter = 2
	while exists(candidate):
		suffix = f"_{counter}"
		candidate = f"{base[: _SLUG_MAX - len(suffix)]}{suffix}"
		counter += 1
	return candidate


class Skill(Document):
	def before_insert(self):
		# Runs before autoname (field:skill_name). Explicit names from import,
		# hooks or the API are respected; only a missing one is derived.
		if not (self.skill_name or "").strip():
			self.skill_name = make_unique_skill_name(self.title, lambda name: frappe.db.exists("Skill", name))

	def validate(self):
		if self.source_type == "App Provided" and not self.provider_app:
			frappe.throw(_("Provider App is required for App Provided skills."))

	def on_trash(self):
		attached_agents = frappe.get_all(
			"Agent Skill",
			filters={"skill": self.name},
			pluck="parent",
		)
		if attached_agents:
			frappe.throw(
				_("Cannot delete skill {0}: attached to {1} agent(s): {2}").format(
					frappe.bold(self.name),
					len(attached_agents),
					", ".join(attached_agents[:5]),
				)
			)

		# Skill Import Log is a historical audit trail, not a real dependency —
		# safe to unlink so it never blocks deleting the skill it logged.
		frappe.db.delete("Skill Import Log", {"skill": self.name})
