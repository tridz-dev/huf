# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

import re

import frappe
from frappe import _
from frappe.model.document import Document

from huf.ai.telegram_templates import (
	TEMPLATE_NAME_HELP,
	TEMPLATE_NAME_RE,
	VAR_NAME_RE,
	button_problems,
	detect_variables,
	placeholder_problems,
)

LANG_RE = re.compile(r"^[a-z]{2,3}([-_][A-Za-z0-9]{2,8})*$")
TAG_RE = re.compile(r"<(/?)([a-zA-Z][a-zA-Z0-9-]*)\b[^>]*>")
HTML_TAGS = {
	"b", "strong", "i", "em", "u", "ins", "s", "strike", "del", "a", "code", "pre",
	"span", "tg-spoiler", "tg-emoji", "blockquote",
}  # fmt: skip


def html_problems(body: str) -> list[str]:
	"""Unsupported or unbalanced Telegram HTML tags in ``body`` (empty list when fine)."""
	problems: list[str] = []
	stack: list[str] = []
	for m in TAG_RE.finditer(body or ""):
		closing, tag = m.group(1), m.group(2).lower()
		if tag not in HTML_TAGS:
			problems.append(_("Tag <{0}> is not supported by Telegram.").format(tag))
		elif closing:
			if not stack or stack[-1] != tag:
				problems.append(_("Closing tag </{0}> does not match an open tag.").format(tag))
			else:
				stack.pop()
		else:
			stack.append(tag)
	for tag in stack:
		problems.append(_("Tag <{0}> is never closed.").format(tag))
	return problems


class TelegramMessageTemplate(Document):
	def validate(self):
		name = (self.template_name or "").strip()
		if not TEMPLATE_NAME_RE.match(name):
			frappe.throw(_(TEMPLATE_NAME_HELP))
		self.template_name = name

		media_type = self.media_type or "none"
		if media_type != "none" and not self.media:
			frappe.throw(
				_("Attach a file for the {0} media type, or set the media type to none.").format(media_type)
			)
		if media_type == "none" and not (self.body or "").strip():
			frappe.throw(_("Add message text or choose a media type and attach a file."))

		language = (self.language or "").strip()
		if language and not LANG_RE.match(language):
			frappe.throw(_("Language must be a code like en or pt-BR."))
		self.language = language

		declared = {(row.variable or "").strip() for row in self.get("variables") or []}
		for row in self.get("variables") or []:
			if not VAR_NAME_RE.fullmatch((row.variable or "").strip()):
				frappe.throw(
					_("Variable {0} must use letters, digits and underscores only.").format(row.variable)
				)
		missing = [v for v in detect_variables(self.body, self.buttons_json) if v not in declared]
		if missing:
			frappe.msgprint(
				_(
					"These variables are used in the text but not listed: {0}. They will be left empty."
				).format(", ".join(missing)),
				indicator="orange",
				alert=True,
			)

		if self.parse_mode == "HTML":
			problems = html_problems(self.body)
			if problems:
				frappe.throw("<br>".join(problems))

		bad = placeholder_problems(self.body, self.buttons_json)
		if bad:
			frappe.throw("<br>".join(bad))

		if (self.buttons_json or "").strip():
			errors = button_problems(self.buttons_json)
			if errors:
				frappe.throw(_("Buttons are not valid: {0}").format("; ".join(errors)))
