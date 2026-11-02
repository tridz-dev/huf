"""Frappe LMS adapter: maps a WhatsApp number to an existing Huf/Frappe user (the LMS member).

Built against LMS's documented schema (LMS Course: name/title/published; LMS Enrollment: course, member (User);
LMS Certificate: course, member). Nothing here imports LMS; every LMS DocType is guarded with
``frappe.db.exists("DocType", ...)``. The adapter never creates Users: a number with no matching user has no member.
"""

from __future__ import annotations

import re
from typing import Any

import frappe

from huf.ai.channels.adapters import ChannelAdapter

COURSE = "LMS Course"
ENROLLMENT = "LMS Enrollment"
CERTIFICATE = "LMS Certificate"
PROGRESS = "LMS Course Progress"
_NEVER_MEMBERS = ("Guest", "Administrator")
_TAIL = 10


def lms_installed() -> bool:
	return "lms" in frappe.get_installed_apps()


def _has_doctype(doctype: str) -> bool:
	try:
		return bool(frappe.db.exists("DocType", doctype))
	except Exception:
		return False


def normalize_phone(raw: str | None) -> str:
	return re.sub(r"\D", "", raw or "")


def _usable(user: str | None) -> bool:
	if not user or user in _NEVER_MEMBERS:
		return False
	try:
		return bool(frappe.db.get_value("User", user, "enabled"))
	except Exception:
		return False


def _contact_user(digits: str) -> str | None:
	"""User linked from a Contact whose mobile number matches ``digits``."""
	rows = frappe.get_all(
		"Contact",
		filters={"mobile_no": ["like", f"%{digits[-_TAIL:]}"], "user": ["is", "set"]},
		fields=["user", "mobile_no"],
		limit_page_length=20,
	)
	for row in rows:
		if normalize_phone(row.get("mobile_no")) == digits:
			return row.get("user")
	return None


def find_member(phone: str | None) -> str | None:
	"""Enabled User (LMS member) whose Contact or User mobile number matches ``phone``; None when there is none."""
	digits = normalize_phone(phone)
	if not digits:
		return None
	linked = _contact_user(digits)
	if linked and _usable(linked):
		return linked
	rows = frappe.get_all(
		"User",
		filters={"mobile_no": ["like", f"%{digits[-_TAIL:]}"], "enabled": 1},
		fields=["name", "mobile_no"],
		limit_page_length=20,
	)
	for row in rows:
		if normalize_phone(row.get("mobile_no")) == digits and _usable(row.get("name")):
			return row.get("name")
	return None


class Adapter(ChannelAdapter):
	name = "lms"

	def lookup_customer(self, phone: str) -> dict[str, Any] | None:
		"""``{doctype: "User", name}`` of the LMS member for ``phone``, or None (no account, no member)."""
		user = find_member(phone)
		return {"doctype": "User", "name": user} if user else None
