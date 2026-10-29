"""Frappe LMS tools for the WhatsApp agent, plus the daily lesson-reminder job.

Every tool acts for the member matched to the current conversation's number (``channels/adapters/lms.py``); a number
with no matching user gets a refusal, never a new User. When LMS is not installed each tool answers
"LMS is not installed". Certificates go out through the WhatsApp file send gates (STOP, allow-list, 24h window).
Reminders are templates sent through the bridge, so the outbound policy applies to them too.
"""

from __future__ import annotations

import json
from typing import Any

import frappe
from frappe.utils import add_days, get_datetime

from huf.ai.channels import reminder_policy, run_as
from huf.ai.channels.adapters import lms
from huf.ai.gateway_adapters import whatsapp_bridge as bridge
from huf.ai.tools.whatsapp import _free_form_refusal
from huf.ai.whatsapp import send_file

COURSE = lms.COURSE
ENROLLMENT = lms.ENROLLMENT
CERTIFICATE = lms.CERTIFICATE
PROGRESS = lms.PROGRESS
REMINDER_DAYS = 3
REMINDER_KIND = "lms_lesson_reminder"
_MAX_ENROLLMENTS_PER_RUN = 500
_NOT_INSTALLED = "LMS is not installed"


def _err(code: str, message: str = "") -> str:
	return json.dumps({"success": False, "error": code, "message": message}, default=str)


def _schema_ready() -> bool:
	"""LMS is installed and its DocTypes this module reads exist."""
	return lms.lms_installed() and all(lms._has_doctype(d) for d in (COURSE, ENROLLMENT, CERTIFICATE))


def _conversation():
	"""Channel Conversation of the current run (the chat the agent is answering), or None."""
	name = run_as.current_conversation()
	if not name:
		from huf.ai.tools.handoff import _chat_conversation, _run_chat

		gateway, space_key = _run_chat()
		name = _chat_conversation(gateway, space_key) if gateway else None
	if not name:
		return None
	try:
		return frappe.get_doc("Channel Conversation", name)
	except Exception:
		return None


def _member_for_conversation(conversation) -> str | None:
	return lms.find_member(conversation.get("contact_handle"))


def _published_course(course: str | None) -> str | None:
	key = (course or "").strip()
	if not key:
		return None
	rows = frappe.get_all(
		COURSE,
		filters={"published": 1},
		or_filters={"name": key, "title": key},
		fields=["name"],
		limit_page_length=1,
	)
	return rows[0]["name"] if rows else None


def _certificate_file(member: str, course: str) -> dict | None:
	"""Latest PDF File attached to the member's LMS Certificate for ``course``."""
	certs = frappe.get_all(
		CERTIFICATE,
		filters={"member": member, "course": course},
		fields=["name"],
		order_by="creation desc",
		limit_page_length=1,
	)
	if not certs:
		return None
	files = frappe.get_all(
		"File",
		filters={"attached_to_doctype": CERTIFICATE, "attached_to_name": certs[0]["name"], "is_folder": 0},
		fields=["name", "file_url", "file_name", "file_size", "is_private", "owner"],
		order_by="creation desc",
		limit_page_length=1,
	)
	return files[0] if files else None


def _certificate_resolved(row: dict) -> dict[str, Any]:
	"""The shape ``send_file.prepare_upload`` takes, built from a File the member's certificate owns."""
	name = row.get("file_name") or str(row.get("file_url") or "").rsplit("/", 1)[-1] or "certificate.pdf"
	return {"row": row, "filename": name, "mime": "application/pdf", "size": int(row.get("file_size") or 0)}


def _account_for_gateway(gateway: str) -> str | None:
	account = frappe.db.get_value("Gateway", gateway, "whatsapp_account")
	resolved = bridge.resolve_account(account) if account else None
	return resolved["name"] if resolved and not resolved.get("error") else None


# ---------------------------------------------------------------- agent tools
def lms_list_courses(**_ignored) -> str:
	if not _schema_ready():
		return _err("lms_not_installed", _NOT_INSTALLED)
	courses = frappe.get_all(COURSE, filters={"published": 1}, fields=["name", "title"], order_by="title asc")
	return json.dumps({"success": True, "courses": courses}, default=str)


def lms_enroll(course: str = "", **_ignored) -> str:
	if not _schema_ready():
		return _err("lms_not_installed", _NOT_INSTALLED)
	conversation = _conversation()
	if not conversation:
		return _err("conversation_required", "lms_enroll only works inside a WhatsApp conversation")
	member = _member_for_conversation(conversation)
	if not member:
		return _err("member_not_found", "No account matches this WhatsApp number, so there is no LMS member to enroll.")
	course_name = _published_course(course)
	if not course_name:
		return _err("course_not_found", "No published course matches that name.")
	existing = frappe.get_all(ENROLLMENT, filters={"course": course_name, "member": member}, fields=["name"], limit_page_length=1)
	if existing:
		return json.dumps({"success": True, "enrollment": existing[0]["name"], "created": False}, default=str)
	doc = frappe.get_doc({"doctype": ENROLLMENT, "course": course_name, "member": member})
	doc.insert(ignore_permissions=True)
	return json.dumps({"success": True, "enrollment": doc.name, "created": True}, default=str)


def lms_my_progress(**_ignored) -> str:
	if not _schema_ready():
		return _err("lms_not_installed", _NOT_INSTALLED)
	conversation = _conversation()
	if not conversation:
		return _err("conversation_required", "lms_my_progress only works inside a WhatsApp conversation")
	member = _member_for_conversation(conversation)
	if not member:
		return _err("member_not_found", "No account matches this WhatsApp number.")
	rows = frappe.get_all(ENROLLMENT, filters={"member": member}, fields=["course", "progress"], order_by="modified desc")
	return json.dumps({"success": True, "courses": rows}, default=str)


def lms_send_certificate(course: str = "", **_ignored) -> str:
	if not _schema_ready():
		return _err("lms_not_installed", _NOT_INSTALLED)
	conversation = _conversation()
	if not conversation:
		return _err("conversation_required", "lms_send_certificate only works inside a WhatsApp conversation")
	member = _member_for_conversation(conversation)
	if not member:
		return _err("member_not_found", "No account matches this WhatsApp number.")
	course_name = _published_course(course)
	if not course_name:
		return _err("course_not_found", "No published course matches that name.")
	row = _certificate_file(member, course_name)
	if not row:
		return _err("certificate_not_found", "No certificate has been issued for this course yet.")
	gateway = conversation.get("gateway") or ""
	recipient = lms.normalize_phone(conversation.get("contact_handle"))
	try:
		prepared = send_file.prepare_upload(_certificate_resolved(row), "document", False)
	except send_file.FileSendError as e:
		return _err(e.code, e.message)
	refusal = _free_form_refusal({"gateway_name": gateway}, recipient, "a certificate")
	if refusal:
		return refusal
	account = _account_for_gateway(gateway) if gateway else None
	if not account:
		return _err("no_account", "This gateway has no WhatsApp account to send from.")
	try:
		media = bridge.upload_media(account, prepared["content"], prepared["mime"], prepared["filename"], kind="document")
		result = bridge.send_media(account, recipient, "document", media_id=str(media["media_id"]), filename=prepared["filename"])
	except bridge.BridgeError as e:
		payload = e.payload or {}
		return _err(str(payload.get("error") or "send_failed"), str(payload.get("message") or "Could not send the certificate."))
	return json.dumps(result if isinstance(result, dict) else {"success": True}, default=str)


# ---------------------------------------------------------------- daily lesson reminders
def _last_progress(member: str, course: str):
	if not lms._has_doctype(PROGRESS):
		return None
	rows = frappe.get_all(
		PROGRESS, filters={"member": member, "course": course}, fields=["modified"], order_by="modified desc", limit_page_length=1
	)
	return rows[0]["modified"] if rows else None


def _stale_enrollments(now) -> list[dict[str, Any]]:
	"""Enrollments whose last progress (or enrollment, when none) is at least REMINDER_DAYS old."""
	cutoff = add_days(now, -REMINDER_DAYS)
	rows = frappe.get_all(ENROLLMENT, fields=["name", "member", "course", "creation"], limit_page_length=_MAX_ENROLLMENTS_PER_RUN)
	out = []
	for row in rows:
		last = _last_progress(row["member"], row["course"])
		if get_datetime(last or row["creation"]) <= get_datetime(cutoff):
			out.append({**row, "last": last})
	return out


def _reminder_target(member: str) -> tuple[str, str] | None:
	"""(gateway, digits) to remind ``member`` through: their number's open conversation on a gateway with a reminder template."""
	if not lms._usable(member):
		return None
	digits = lms.normalize_phone(frappe.db.get_value("User", member, "mobile_no"))
	if not digits:
		return None
	rows = frappe.get_all(
		"Channel Conversation",
		filters={"contact_handle": digits, "status": ["!=", "closed"]},
		fields=["gateway"],
		order_by="modified desc",
		limit_page_length=5,
	)
	for row in rows:
		if row.get("gateway") and _gateway_template(row["gateway"]):
			return row["gateway"], digits
	return None


def _gateway_template(gateway: str) -> str:
	return str(frappe.db.get_value("Gateway", gateway, "lms_reminder_template") or "").strip()


def _send_template(gateway: str, phone: str, template: str, params: list[str]) -> dict[str, Any]:
	account = _account_for_gateway(gateway)
	if not account:
		return {"success": False, "error": "no_account"}
	try:
		res = bridge.send_template(account, phone, template, params, gateway_name=gateway)
	except bridge.BridgeError as e:
		return {"success": False, "error": (e.payload or {}).get("error") or "send_failed"}
	res = res if isinstance(res, dict) else {}
	return {**res, "success": not res.get("error")}


def send_lesson_reminders() -> int:
	"""Daily job: remind enrolled members with no progress for REMINDER_DAYS, at most once per REMINDER_DAYS.

	The lesson_reminder template (Gateway.lms_reminder_template) gets the course title as its one body variable.
	Returns the number of reminders sent.
	"""
	if not _schema_ready():
		return 0
	now = frappe.utils.now_datetime()
	sent = 0
	for enrollment in _stale_enrollments(now):
		target = _reminder_target(enrollment["member"])
		if not target:
			continue
		gateway, phone = target
		template = _gateway_template(gateway)
		if not template:
			continue
		if reminder_policy.recently_sent(REMINDER_KIND, ENROLLMENT, enrollment["name"], REMINDER_DAYS):
			continue
		if not reminder_policy.may_send_proactive(gateway, phone):
			continue
		res = _send_template(gateway, phone, template, [enrollment["course"]])
		if res.get("success"):
			reminder_policy.record(gateway, phone, REMINDER_KIND, ENROLLMENT, enrollment["name"])
			sent += 1
		else:
			frappe.logger("huf").info(f"LMS reminder for {enrollment['name']} not sent: {res.get('error')}")
	return sent
